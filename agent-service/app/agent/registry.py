"""工具注册、发现与治理。

模板中的工具不能直接交给模型执行，否则会出现三类问题：
1. 工具卡死：没有超时，一次外部调用能把整轮对话拖死；
2. 瞬时故障：网络抖动直接让对话失败，没有重试；
3. 越权调用：模型不知道用户角色，工具必须由服务端校验权限。

治理后的工具仍然暴露同样的名称、描述与参数 schema，模型无感知。
错误消息只返回安全文案，堆栈留在服务端日志。

扩展方式（新增工具不用改 `app/` 核心）：
1. 在 `app/agent/tools_ext/` 新增模块，启动时自动导入；
2. 通过 `AGENT__TOOL_MODULES` 声明额外的点分模块路径（逗号分隔）。

注册表是进程级单例：模块导入期完成注册，同名工具直接抛错，
让服务在启动阶段失败，而不是静默覆盖掉已有工具。
"""

import asyncio
import copy
import importlib
import importlib.util
import inspect
import json
import pkgutil
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import structlog
from langchain_core.tools import BaseTool, StructuredTool

from app.agent.context import count_tokens, truncate_to_token_budget
from app.agent.hooks import HookBlockedError, HookContext, HookPoint, run_hooks
from app.agent.tool_context import get_current_tool_turn
from app.core.config import get_settings
from app.core.metrics import (
    TOOL_CALLS_TOTAL,
    TOOL_OUTPUT_TOKENS,
    TOOL_RETRIES_TOTAL,
    TOOL_STATUS_ERROR,
    TOOL_STATUS_FORBIDDEN,
    TOOL_STATUS_LIMITED,
    TOOL_STATUS_SUCCESS,
    TOOL_STATUS_TIMEOUT,
)

logger = structlog.get_logger(__name__)

BUILTIN_TOOL_MODULE = "app.agent.pc.tools"
TOOLS_EXT_PACKAGE = "app.agent.tools_ext"
# OpenAI 兼容端点对函数名的约束；提前校验，避免调用模型时才报错
TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# 工具返回给模型前的脱敏规则；只作用于模型可见内容，原始结果不落库、不打日志
_PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
_EMAIL_PATTERN = re.compile(
    r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)
_ID_CARD_PATTERN = re.compile(r"(?<!\d)(\d{6})\d{8}([\dXx]{4})(?!\d)")
_SECRET_TOKEN_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{8,}")
# 保留 Bearer 前缀，便于模型理解这是凭据而非普通文本
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}")
TRUNCATION_NOTICE = "\n[结果已截断，原长度 {chars} 字符]"
# 结构化结果被裁剪时追加的标记字段，调用方可据此判断数据不完整
STRUCTURED_TRUNCATION_KEY = "_truncated"
# 字符数到 token 的保守换算，仅用于估算裁剪比例，避免对大 payload 反复分词
_CHARS_PER_TOKEN_ESTIMATE = 3


class ToolExecutionError(RuntimeError):
    """工具执行失败；消息可安全返回给模型与用户。"""


class ToolRegistrationError(ValueError):
    """工具注册失败：名称非法、描述缺失或同名重复。"""


class ToolModuleImportError(RuntimeError):
    """工具模块导入失败；错误信息必须带模块名，便于排障。"""


@dataclass(frozen=True)
class ToolSpec:
    """一个工具的治理参数；未填写的项使用全局默认值。"""

    tool: BaseTool
    timeout_seconds: float | None = None
    max_retries: int | None = None
    # 允许调用该工具的角色；为空表示所有登录用户可用
    required_roles: tuple[str, ...] = ()
    # 以下三项由注册元数据固化，治理执行时按「工具覆盖 > 全局默认」读取
    max_output_tokens: int | None = None
    max_calls_per_turn: int | None = None
    is_read_only: bool = True
    # builtin / ext / mcp：重名冲突与排障时用于定位来源，不改变治理行为
    source: str = "builtin"


# 注册顺序决定绑定给模型的工具顺序，dict 保持插入顺序
_TOOL_SPECS: dict[str, ToolSpec] = {}
# 治理包装按名称缓存，避免确定性节点每次调用都重新创建 StructuredTool
_GOVERNED_TOOLS: dict[str, BaseTool] = {}
_is_discovery_complete = False


def _resolve_limits(spec: ToolSpec) -> tuple[float, int]:
    settings = get_settings().agent
    timeout = (
        spec.timeout_seconds
        if spec.timeout_seconds is not None
        else settings.tool_timeout_seconds
    )
    retries = (
        spec.max_retries if spec.max_retries is not None else settings.tool_max_retries
    )
    if timeout <= 0:
        raise ValueError("工具超时必须大于 0")
    if retries < 0:
        raise ValueError("工具重试次数不能为负")
    return timeout, retries


def _check_permission(spec: ToolSpec) -> None:
    """权限在每次调用时校验：同一张图会被不同角色的用户复用。"""
    if not spec.required_roles:
        return
    turn = get_current_tool_turn()
    current_roles = set(turn.roles) if turn is not None else set()
    missing_roles = set(spec.required_roles) - current_roles
    if missing_roles:
        logger.warning(
            "tool.forbidden",
            tool=spec.tool.name,
            required_roles=sorted(spec.required_roles),
        )
        raise ToolExecutionError("当前用户无权调用该工具")


def redact_sensitive_text(text: str) -> str:
    """脱敏模型可见的工具输出：手机号、邮箱、身份证、API Key 与 Bearer 凭据。

    只做形态匹配，不做语义判断：宁可多打码，也不把真实个人信息送进第三方模型。
    """
    text = _BEARER_TOKEN_PATTERN.sub(r"\1****", text)
    text = _SECRET_TOKEN_PATTERN.sub("sk-****", text)
    text = _EMAIL_PATTERN.sub(r"\1***@\2", text)
    text = _ID_CARD_PATTERN.sub(r"\1********\2", text)
    return _PHONE_PATTERN.sub(r"\1****\2", text)


def _resolve_max_calls(spec: ToolSpec) -> int:
    """工具单轮调用上限：工具注册值优先，否则取全局默认。"""
    limit = (
        spec.max_calls_per_turn
        if spec.max_calls_per_turn is not None
        else get_settings().agent.tool_max_calls_per_turn
    )
    if limit < 1:
        raise ValueError("工具单轮调用上限必须大于 0")
    return limit


def _serialize_structured(payload: Any) -> str:
    """结构化结果统一序列化口径，保证裁剪前后格式一致。"""
    return json.dumps(payload, ensure_ascii=False, default=str)


def _shrink_structured_payload(node: Any, ratio: float) -> bool:
    """按比例裁剪结构中的列表项与超长字符串；返回是否发生变化。

    只做「减少元素」不做「截断字节」，保证裁剪后仍是合法 JSON。
    """
    changed = False
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, list) and value:
                keep = max(1, int(len(value) * ratio))
                if keep < len(value):
                    value = value[:keep]
                    node[key] = value
                    changed = True
                for item in value:
                    changed = _shrink_structured_payload(item, ratio) or changed
            elif isinstance(value, dict):
                changed = _shrink_structured_payload(value, ratio) or changed
            elif isinstance(value, str) and len(value) > 256:
                cut = max(64, int(len(value) * ratio))
                if cut < len(value):
                    node[key] = value[:cut]
                    changed = True
    elif isinstance(node, list):
        for item in node:
            changed = _shrink_structured_payload(item, ratio) or changed
    return changed


def _govern_structured_output(payload: Any, budget: int, original_chars: int) -> str:
    """把结构化结果裁剪到 token 预算内，始终返回合法 JSON。

    面向模型的纯文本可以按前缀截断，但结构化结果被截断后会变成非法 JSON，
    让代码消费方误判为上游故障；这里改为裁剪列表项，保留顶层计数字段。
    """
    shrunk = copy.deepcopy(payload)
    if isinstance(shrunk, dict):
        shrunk[STRUCTURED_TRUNCATION_KEY] = True
    # 先用字符数粗估比例，避免对超大 payload 反复分词
    ratio = min(1.0, max(0.01, budget * _CHARS_PER_TOKEN_ESTIMATE / max(1, original_chars)))
    text = _serialize_structured(shrunk)
    for _ in range(6):
        if count_tokens(text) <= budget:
            return text
        if not _shrink_structured_payload(shrunk, ratio):
            break
        text = _serialize_structured(shrunk)
        # 首轮之后改为对半收缩，逐步逼近预算
        ratio = 0.5
    # 结构已无可裁剪项时宁可略微超预算，也不返回非法 JSON
    return text


def _govern_output(spec: ToolSpec, result: Any) -> str:
    """治理工具输出：统一转文本 → 脱敏 → 按 token 预算裁剪 → 记录大小指标。

    返回给模型的内容必须是字符串；非字符串结果用 JSON 序列化，保证截断逻辑统一。
    结构化结果采用「裁剪列表项」而非「截断字节」，避免半截 JSON。
    """
    settings = get_settings().agent
    is_structured = isinstance(result, (dict, list))
    raw_text = (
        result
        if isinstance(result, str)
        else _serialize_structured(result)
    )
    original_chars = len(raw_text)

    budget = (
        spec.max_output_tokens
        if spec.max_output_tokens is not None
        else settings.tool_max_output_tokens
    )
    if count_tokens(raw_text) <= budget:
        final_text = raw_text
        is_truncated = False
    elif is_structured:
        final_text = _govern_structured_output(result, budget, original_chars)
        is_truncated = True
    else:
        notice = TRUNCATION_NOTICE.format(chars=original_chars)
        # 预算要扣掉提示文本，否则截断后的内容仍会略微超出上限
        content_budget = max(1, budget - count_tokens(notice))
        prefix, _ = truncate_to_token_budget(raw_text, content_budget)
        final_text = f"{prefix}{notice}"
        is_truncated = True

    # 脱敏放在裁剪之后，保证裁剪出来的片段同样不会把敏感信息带给模型
    if settings.tool_redact_output:
        final_text = redact_sensitive_text(final_text)

    estimated_tokens = count_tokens(final_text)
    TOOL_OUTPUT_TOKENS.labels(tool=spec.tool.name).observe(estimated_tokens)
    logger.info(
        "tool.output",
        tool=spec.tool.name,
        chars=len(final_text),
        estimated_tokens=estimated_tokens,
        truncated=is_truncated,
        structured=is_structured,
    )
    return final_text


async def _invoke_with_governance(spec: ToolSpec, arguments: dict[str, Any]) -> Any:
    timeout, retries = _resolve_limits(spec)
    tool_name = spec.tool.name
    try:
        _check_permission(spec)
    except ToolExecutionError:
        TOOL_CALLS_TOTAL.labels(tool=tool_name, status=TOOL_STATUS_FORBIDDEN).inc()
        raise

    max_calls = _resolve_max_calls(spec)
    # 无回合上下文（脚本直接调工具）时不限次；有回合时按本轮配额占用
    turn = get_current_tool_turn()
    if turn is not None and not turn.acquire(tool_name, max_calls):
        # 超限不抛错：让模型看到明确原因并基于已有信息收敛回答
        TOOL_CALLS_TOTAL.labels(tool=tool_name, status=TOOL_STATUS_LIMITED).inc()
        logger.warning("tool.call_limit", tool=tool_name, limit=max_calls)
        return (
            f"工具 {tool_name} 本轮调用次数已达上限（{max_calls} 次），"
            "请基于已有信息直接回答，不要重复调用。"
        )

    # 钩子放在重试循环外：阻断属于策略决定，不应因为重试而重复执行
    try:
        await run_hooks(HookContext(point=HookPoint.BEFORE_TOOL, tool_name=tool_name))
    except HookBlockedError:
        TOOL_CALLS_TOTAL.labels(tool=tool_name, status=TOOL_STATUS_FORBIDDEN).inc()
        logger.warning("tool.before_hook_blocked", tool=tool_name)
        raise ToolExecutionError("工具调用被安全策略拦截") from None

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        # 首次执行不计重试，只有真正重跑才累加
        if attempt > 0:
            TOOL_RETRIES_TOTAL.labels(tool=tool_name).inc()
        try:
            async with asyncio.timeout(timeout):
                result = await spec.tool.ainvoke(arguments)
        except TimeoutError as exc:
            last_error = exc
            logger.warning(
                "tool.timeout",
                tool=tool_name,
                attempt=attempt + 1,
                timeout_seconds=timeout,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "tool.failed",
                tool=tool_name,
                attempt=attempt + 1,
                error_type=type(exc).__name__,
                # 工具异常文本面向模型生成，不含令牌与内网地址；保留它才能区分身份缺失与上游失败
                error_message=str(exc)[:200],
            )
        else:
            TOOL_CALLS_TOTAL.labels(tool=tool_name, status=TOOL_STATUS_SUCCESS).inc()
            output = _govern_output(spec, result)
            try:
                await run_hooks(
                    HookContext(point=HookPoint.AFTER_TOOL, tool_name=tool_name, text=output)
                )
            except HookBlockedError:
                logger.warning("tool.after_hook_blocked", tool=tool_name)
                raise ToolExecutionError("工具结果被安全策略拦截") from None
            return output

    # 一次调用只记录最终结果，重试过程由 retries 指标单独体现
    final_status = (
        TOOL_STATUS_TIMEOUT if isinstance(last_error, TimeoutError) else TOOL_STATUS_ERROR
    )
    TOOL_CALLS_TOTAL.labels(tool=tool_name, status=final_status).inc()
    raise ToolExecutionError(f"工具 {tool_name} 执行失败，请稍后重试") from last_error


def govern_tool(spec: ToolSpec) -> BaseTool:
    """把治理逻辑包装成新的工具，保持名称、描述与参数 schema 不变。"""
    source = spec.tool

    async def invoke(**arguments: Any) -> Any:
        return await _invoke_with_governance(spec, arguments)

    return StructuredTool.from_function(
        coroutine=invoke,
        name=source.name,
        description=source.description or source.name,
        args_schema=source.args_schema,
    )


def build_tools(specs: list[ToolSpec]) -> list[BaseTool]:
    """批量构建治理后的工具列表。"""
    return [govern_tool(spec) for spec in specs]


def _validate_metadata(name: str, description: str) -> None:
    """名称与描述是模型可见契约，非法值在注册期就应失败。"""
    if not TOOL_NAME_PATTERN.fullmatch(name):
        raise ToolRegistrationError(
            f"非法的工具名：{name}（只允许小写字母开头、小写字母/数字/下划线）"
        )
    if not description.strip():
        raise ToolRegistrationError(f"工具 {name} 缺少描述（模型据此决定是否调用）")


def _validate_limits(
    name: str,
    timeout_seconds: float | None,
    max_retries: int | None,
    max_output_tokens: int | None,
    max_calls_per_turn: int | None,
) -> None:
    """治理参数必须为正：注册期校验，避免错误配置拖到第一次调用才暴露。"""
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ToolRegistrationError(f"工具 {name} 的超时必须大于 0")
    if max_retries is not None and max_retries < 0:
        raise ToolRegistrationError(f"工具 {name} 的重试次数不能为负")
    if max_output_tokens is not None and max_output_tokens <= 0:
        raise ToolRegistrationError(f"工具 {name} 的输出上限必须大于 0")
    if max_calls_per_turn is not None and max_calls_per_turn <= 0:
        raise ToolRegistrationError(f"工具 {name} 的单轮调用上限必须大于 0")


def _validate_spec(spec: ToolSpec) -> None:
    _validate_metadata(spec.tool.name, spec.tool.description or "")
    _validate_limits(
        spec.tool.name,
        spec.timeout_seconds,
        spec.max_retries,
        spec.max_output_tokens,
        spec.max_calls_per_turn,
    )


def register_spec(spec: ToolSpec) -> None:
    """登记一个已构建好的工具；同名冲突直接失败，禁止静默覆盖。"""
    _validate_spec(spec)
    name = spec.tool.name
    existing = _TOOL_SPECS.get(name)
    if existing is not None:
        raise ToolRegistrationError(
            f"工具名重复注册：{name}（已存在 source={existing.source}，"
            f"新来源 source={spec.source}）"
        )
    _TOOL_SPECS[name] = spec


def register_tool(
    *,
    name: str,
    description: str,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
    required_roles: tuple[str, ...] = (),
    max_output_tokens: int | None = None,
    max_calls_per_turn: int | None = None,
    is_read_only: bool = True,
    source: str = "builtin",
) -> Callable[[Callable[..., Any]], BaseTool]:
    """装饰器：把一个函数变成注册表里的工具。

    用法：

        @register_tool(name="get_current_time", description="...", timeout_seconds=5)
        def get_current_time(timezone: str = "Asia/Shanghai") -> str: ...

    描述不用 docstring 自动提取：模型可见的描述需要写清楚「什么时候用」，
    而 docstring 往往写给维护者看，两者混用容易漂移。
    """
    normalized_description = description.strip()
    # 静态校验放在装饰器调用期，模块导入时即可暴露错误
    _validate_metadata(name, normalized_description)
    _validate_limits(name, timeout_seconds, max_retries, max_output_tokens, max_calls_per_turn)

    def decorator(func: Callable[..., Any]) -> BaseTool:
        if inspect.iscoroutinefunction(func):
            tool_object = StructuredTool.from_function(
                coroutine=func, name=name, description=normalized_description
            )
        else:
            tool_object = StructuredTool.from_function(
                func=func, name=name, description=normalized_description
            )
        register_spec(
            ToolSpec(
                tool=tool_object,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                required_roles=required_roles,
                max_output_tokens=max_output_tokens,
                max_calls_per_turn=max_calls_per_turn,
                is_read_only=is_read_only,
                source=source,
            )
        )
        return tool_object

    return decorator


def list_tool_specs() -> tuple[ToolSpec, ...]:
    """按注册顺序返回全部工具（未治理的原始对象）。"""
    return tuple(_TOOL_SPECS.values())


def get_tool_spec(name: str) -> ToolSpec | None:
    """按名称查询；未注册返回 None，由调用方决定是报错还是跳过。"""
    return _TOOL_SPECS.get(name)


def get_default_tools() -> list[BaseTool]:
    """返回注册表里全部工具（已治理），供图装配使用。"""
    ensure_tools_loaded()
    return build_tools(list(_TOOL_SPECS.values()))


def get_governed_tool(name: str) -> BaseTool | None:
    """按名称返回治理后的工具；PC 节点直接调用它，确保超时/重试/权限生效。"""
    ensure_tools_loaded()
    spec = _TOOL_SPECS.get(name)
    if spec is None:
        return None
    tool = _GOVERNED_TOOLS.get(name)
    if tool is None:
        tool = govern_tool(spec)
        _GOVERNED_TOOLS[name] = tool
    return tool


def _tools_in_package(package_name: str) -> list[str]:
    """列出扩展包内的所有子模块；包不存在时返回空列表。"""
    package_spec = importlib.util.find_spec(package_name)
    if package_spec is None or package_spec.submodule_search_locations is None:
        return []
    package = importlib.import_module(package_name)
    module_paths = list(getattr(package, "__path__", []))
    return [
        f"{package_name}.{module.name}"
        for module in pkgutil.iter_modules(module_paths)
        if not module.name.startswith("_")
    ]


def _import_tool_module(module_name: str) -> None:
    """导入单个工具模块；失败信息必须包含模块名。"""
    try:
        importlib.import_module(module_name)
    except (ToolRegistrationError, ToolModuleImportError):
        raise
    except Exception as exc:
        raise ToolModuleImportError(
            f"工具模块 {module_name} 导入失败（{type(exc).__name__}）：{exc}"
        ) from exc


def discover_tools(extra_modules: Iterable[str] | None = None) -> None:
    """导入内置、扩展包与配置追加的工具模块。

    Python 的导入缓存保证同一模块的装饰器只执行一次，因此重复调用不会重复注册。
    `extra_modules=None` 时读取 `AGENT__TOOL_MODULES`。
    """
    configured = (
        list(get_settings().agent.tool_modules)
        if extra_modules is None
        else list(extra_modules)
    )
    module_names = dict.fromkeys(
        [BUILTIN_TOOL_MODULE, *_tools_in_package(TOOLS_EXT_PACKAGE), *configured]
    )
    for module_name in module_names:
        _import_tool_module(module_name)


def ensure_tools_loaded() -> None:
    """启动期调用一次；导入失败或重名会直接抛错，阻止服务带病运行。"""
    global _is_discovery_complete
    if _is_discovery_complete:
        return
    discover_tools()
    _is_discovery_complete = True
