"""生命周期钩子：不改核心代码即可接入审核、审计与可观测逻辑。

设计原则（与阶段 3 总原则一致）：
1. 默认零钩子：未配置 `AGENT__HOOKS_MODULES` 时注册表为空，钩子点只做一次字典查找；
2. 失败不阻断：钩子异常默认只告警并继续，只有显式 `blocking=True` 才中断主流程；
3. 不碰密钥：`HookContext` 不含请求头、Token 与 API Key，`text` 只承载调用方明确提供的内容。

注册方式：

    @register_hook(HookPoint.AFTER_MODEL, blocking=True)
    async def audit_output(context: HookContext) -> None:
        if "违规" in (context.text or ""):
            raise HookBlockedError("输出命中审核规则")

模块通过 `AGENT__HOOKS_MODULES`（逗号分隔的点分路径）声明，启动期导入并完成注册。
"""

import importlib
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

MAX_HOOK_REASON_LENGTH = 200


class HookPoint(StrEnum):
    """钩子点；枚举值同时用作日志字段，保持稳定。"""

    BEFORE_REQUEST = "before_request"
    BEFORE_MODEL = "before_model"
    AFTER_MODEL = "after_model"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    ON_STREAM_END = "on_stream_end"


@dataclass(frozen=True, slots=True)
class HookContext:
    """钩子可见的上下文。

    只放调用方明确提供的字段：请求头、Token、API Key 一律不进这里，
    避免接入方把钩子日志变成凭证泄漏点。
    """

    point: HookPoint
    thread_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    tool_name: str | None = None
    # 模型输出或工具结果；调用方按需提供
    text: str | None = None
    error_type: str | None = None


HookFunc = Callable[[HookContext], Awaitable[None]]


class HookBlockedError(RuntimeError):
    """阻断信号；`reason` 会写入日志，不要放敏感内容。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class HookModuleImportError(RuntimeError):
    """钩子模块导入失败；错误信息必须带模块名，便于排障。"""


@dataclass(frozen=True, slots=True)
class HookDefinition:
    point: HookPoint
    name: str
    func: HookFunc
    priority: int
    blocking: bool


_HOOKS: dict[HookPoint, list[HookDefinition]] = {point: [] for point in HookPoint}
_is_discovery_complete = False


def _safe_reason(reason: str) -> str:
    """压成单行并截断，避免钩子把长文本或换行带进日志。"""
    return " ".join(reason.split())[:MAX_HOOK_REASON_LENGTH]


def register_hook(
    point: HookPoint,
    *,
    priority: int = 0,
    blocking: bool = False,
    name: str | None = None,
) -> Callable[[HookFunc], HookFunc]:
    """注册钩子：`priority` 越小越先执行，同优先级按注册顺序。"""

    def decorator(func: HookFunc) -> HookFunc:
        _HOOKS[point].append(
            HookDefinition(
                point=point,
                name=name or f"{func.__module__}.{func.__name__}",
                func=func,
                priority=priority,
                blocking=blocking,
            )
        )
        return func

    return decorator


def has_blocking_hook(point: HookPoint) -> bool:
    """该钩子点是否存在阻断型钩子。

    流式层据此决定是否缓冲模型输出：阻断钩子要在 `after_model` 通过后
    才允许把文本推给客户端，否则被拦截的内容已经流出。
    """
    return any(definition.blocking for definition in _HOOKS[point])


def should_buffer_model_output() -> bool:
    """模型输出是否需要等 `after_model` 钩子放行后再下发。

    把「阻断钩子 ⇒ 必须缓冲」这条策略留在钩子模块：流式层只问结论，
    不需要知道具体的钩子点或钩子类型。
    """
    return has_blocking_hook(HookPoint.AFTER_MODEL)


async def run_hooks(context: HookContext) -> None:
    """按优先级执行某个钩子点的全部钩子。

    非阻断钩子失败：告警后继续；阻断钩子失败或主动抛 `HookBlockedError`：
    告警并向上抛出，由调用方转成对用户安全的错误。
    """
    for definition in sorted(_HOOKS[context.point], key=lambda item: item.priority):
        try:
            await definition.func(context)
        except HookBlockedError as exc:
            if definition.blocking:
                logger.warning(
                    "hook.blocked",
                    hook=definition.name,
                    point=context.point.value,
                    reason=_safe_reason(exc.reason),
                )
                raise
            logger.warning(
                "hook.blocked_ignored",
                hook=definition.name,
                point=context.point.value,
            )
        except Exception as exc:
            if definition.blocking:
                # 阻断钩子的异常按失败处理：主流程必须停下，且只暴露安全文案
                logger.error(
                    "hook.failed_blocking",
                    hook=definition.name,
                    point=context.point.value,
                    error_type=type(exc).__name__,
                )
                raise HookBlockedError(f"钩子 {definition.name} 执行失败") from exc
            logger.warning(
                "hook.failed",
                hook=definition.name,
                point=context.point.value,
                error_type=type(exc).__name__,
            )


def discover_hooks(extra_modules: Iterable[str] | None = None) -> None:
    """导入配置声明的钩子模块；导入失败直接抛出，交给启动期 fail-fast。"""
    module_names = (
        list(get_settings().agent.hooks_modules)
        if extra_modules is None
        else list(extra_modules)
    )
    for module_name in dict.fromkeys(module_names):
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            raise HookModuleImportError(
                f"钩子模块 {module_name} 导入失败（{type(exc).__name__}）：{exc}"
            ) from exc


def ensure_hooks_loaded() -> None:
    """启动期调用一次；Python 导入缓存保证重复调用不会重复注册。"""
    global _is_discovery_complete
    if _is_discovery_complete:
        return
    discover_hooks()
    _is_discovery_complete = True


def reset_hooks() -> None:
    """清空注册表；仅供测试隔离使用，生产环境不调用。"""
    global _is_discovery_complete
    for definitions in _HOOKS.values():
        definitions.clear()
    _is_discovery_complete = False
