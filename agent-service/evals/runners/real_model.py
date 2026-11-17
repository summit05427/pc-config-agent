"""真实模型模式：真正跑一次对话，按用例断言工具调用与回答内容。

默认不启用（必须显式 `--real`）：每次运行都会产生真实 token 费用，
因此不进 CI（决策 D7）。
"""

from collections.abc import Sequence
from time import perf_counter
from typing import Any, cast
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, Interrupt
from pydantic import SecretStr

from app.agent.profiles import AgentProfile, resolve_profile
from app.agent.registry import redact_sensitive_text
from app.agent.tool_context import ToolTurn
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.services.model_runtime import PreparedAgent, prepare_agent
from app.services.turn import build_agent_config
from evals.report import (
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_SKIPPED,
    CaseResult,
    CheckResult,
)
from evals.schema import EvalCase, StructuredValue
from evals.usage import UsageCollector

# 失败原因里回显回答片段便于定位，但必须限长并脱敏
ANSWER_PREVIEW_CHARS = 200
ERROR_PREVIEW_CHARS = 300
EMPTY_ANSWER_NOTICE = "（空回答）"
CHECK_TOOL_SEQUENCE = "tool_sequence"
CHECK_INTERRUPT = "interrupt_type"
CHECK_RESUME = "resume"

# 评测用户角色只用于工具治理与知识检索权限过滤；真实身份由 EVALS__USER_TOKEN 决定
EVAL_USER_ROLES = ("USER",)
# 模型未解析必须以显式前缀出现在报告里，便于一眼区分「配置缺失」与「业务失败」
MODEL_UNRESOLVED_PREFIX = "模型未解析"

# 点路径取值失败的哨兵；用 None 会把「字段存在但值为 null」误判为缺失
_MISSING = object()


class ModelResolutionError(RuntimeError):
    """评测无法拿到运行时模型：必须直接判失败，不能继续构图走正则兜底。"""


def _eval_user_token() -> SecretStr | None:
    """评测身份只从配置读取；禁止在代码或仓库里硬编码令牌。"""
    return get_settings().evals.user_token


def _eval_user_id() -> str:
    """评测用户标识与模型解析使用同一个来源，避免两处身份漂移。"""
    return get_settings().evals.user_id


async def _prepare_graph(profile: AgentProfile, thread_id: str) -> PreparedAgent:
    """复用生产 `prepare_agent` 完成解析、凭证兑换与构图。

    这里不另写一套模型选择逻辑：评测与 `/chat/stream` 必须看到同一个
    `resolve_runtime` 结果，否则模型缺失时正则兜底会把问题伪装成成功。
    检查点改用内存实现，避免评测会话写入业务库。
    """
    token = _eval_user_token()
    try:
        prepared = await prepare_agent(
            profile,
            user_id=_eval_user_id(),
            thread_id=thread_id,
            access_token=token,
            requested_model=None,
            checkpointer=MemorySaver(),
        )
    except AppError as exc:
        raise ModelResolutionError(
            f"{MODEL_UNRESOLVED_PREFIX}：{exc.code}（{exc.message}）"
        ) from exc
    except Exception as exc:
        # 控制面不可达、凭证兑换失败等同样属于「模型不可用」，必须显式失败
        raise ModelResolutionError(
            f"{MODEL_UNRESOLVED_PREFIX}：{_describe_error(exc)}"
        ) from exc

    if get_settings().model_runtime.enabled and prepared.runtime is None:
        raise ModelResolutionError(
            f"{MODEL_UNRESOLVED_PREFIX}：运行时已启用但未返回模型"
        )
    return prepared


def _user_token_value(token: SecretStr | None) -> str | None:
    return token.get_secret_value() if token is not None else None


def _message_text(message: BaseMessage) -> str:
    """取消息文本；多模态内容只拼接文本片段，忽略图片等非文本部分。"""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _tool_call_names(result: dict[str, object]) -> list[str]:
    """PC 节点把实际工具调用写入 tool_events（phase=start）。"""
    names: list[str] = []
    events = result.get("tool_events")
    if not isinstance(events, list):
        return names
    for event in events:
        if isinstance(event, dict) and event.get("phase") == "start":
            name = event.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def _answer_text(messages: list[BaseMessage]) -> str:
    """最终回答 = 最后一条 AIMessage（PC 图只产出一条正文）。"""
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return _message_text(message)
    return ""


def _token_totals(messages: list[BaseMessage]) -> tuple[int | None, int | None]:
    """汇总 token；Provider 未返回 usage 时保持 None，不能用 0 冒充。"""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    for message in messages:
        usage = getattr(message, "usage_metadata", None)
        if not isinstance(usage, dict):
            continue
        prompt = usage.get("input_tokens")
        completion = usage.get("output_tokens")
        if isinstance(prompt, int):
            prompt_tokens = (prompt_tokens or 0) + prompt
        if isinstance(completion, int):
            completion_tokens = (completion_tokens or 0) + completion
    return prompt_tokens, completion_tokens


def _workflow_status(state: dict[str, Any]) -> str | None:
    value = state.get("workflow_status")
    return value if isinstance(value, str) and value else None


def _repair_count(state: dict[str, Any]) -> int | None:
    value = state.get("architect_repair_count")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _quality_passed(state: dict[str, Any]) -> bool | None:
    """质量评审通过 = 未触发重选且没有 issues；未进入评审返回 None。"""
    review = state.get("quality_review")
    if not isinstance(review, dict) or not review:
        return None
    retry = review.get("retry")
    if not isinstance(retry, bool):
        return None
    issues = review.get("issues")
    return not retry and not (isinstance(issues, list) and issues)


def _hard_constraint_status(state: dict[str, Any]) -> str | None:
    """从 compose 的兼容性报告归纳硬约束结论；UNKNOWN 一律不算通过。"""
    report = state.get("compatibility_report")
    if not isinstance(report, dict) or not report:
        return None
    checks = [item for item in report.get("checks") or [] if isinstance(item, dict)]
    statuses = {str(item.get("status") or "").upper() for item in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if statuses == {"PASS"}:
        return "PASS"
    return "UNKNOWN"


def _estimate_cost(
    prompt_tokens: int | None, completion_tokens: int | None, llm_calls: int
) -> float | None:
    """按模型目录单价折算单次成本；未配置单价时返回 None，报告记为未校验。

    一次模型调用都没发生的用例（如额度耗尽）成本确定是 0，不能用 None 拖累整轮汇总。
    """
    evals = get_settings().evals
    input_price = evals.price_input_per_million
    output_price = evals.price_output_per_million
    if llm_calls == 0:
        return 0.0
    if input_price is None or output_price is None:
        return None
    if prompt_tokens is None and completion_tokens is None:
        return None
    return (
        (prompt_tokens or 0) * input_price + (completion_tokens or 0) * output_price
    ) / 1_000_000


def _preview(text: str) -> str:
    if not text:
        return EMPTY_ANSWER_NOTICE
    cleaned = redact_sensitive_text(text).replace("\n", " ")
    if len(cleaned) <= ANSWER_PREVIEW_CHARS:
        return cleaned
    return f"{cleaned[:ANSWER_PREVIEW_CHARS]}…"


def _describe_error(exc: Exception) -> str:
    """异常文本可能含上游地址或对话片段：只保留类型与脱敏摘要。"""
    message = redact_sensitive_text(str(exc)).replace("\n", " ")
    if len(message) > ERROR_PREVIEW_CHARS:
        message = f"{message[:ERROR_PREVIEW_CHARS]}…"
    return f"{type(exc).__name__}: {message}"


def _state_value(state: dict[str, Any], path: str) -> object:
    """按点路径读取最终状态；任一层缺失都返回哨兵。"""
    current: object = state
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _value_matches(expected: StructuredValue, actual: object) -> bool:
    """bool、数字与字符串严格比较，避免 "8000" 与 8000 互相掩盖类型缺陷。"""
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(expected, (int, float)):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and float(actual) == float(expected)
        )
    return isinstance(actual, str) and actual == expected


def _ordered_subsequence(expected: list[str], actual: list[str]) -> bool:
    """期望顺序只需是实际调用的子序列，允许中间出现检索等辅助工具。"""
    index = 0
    for name in actual:
        if index < len(expected) and name == expected[index]:
            index += 1
    return index == len(expected)


def _collect_missing_slots(state: dict[str, Any]) -> set[str]:
    slots: set[str] = set()
    for key in ("requirements", "validation_result"):
        block = state.get(key)
        if isinstance(block, dict):
            values = block.get("missing_fields")
            if isinstance(values, list):
                slots.update(str(item) for item in values)
    return slots


def _check_tool_called(expected: str, tool_names: list[str]) -> CheckResult:
    if expected in tool_names:
        return CheckResult("tool_called", STATUS_PASSED, expected)
    actual = ", ".join(tool_names) or "无"
    return CheckResult(
        "tool_called", STATUS_FAILED, f"期望调用 {expected}，实际调用：{actual}"
    )


def _check_workflow_status(
    expected: str | Sequence[str], state: dict[str, Any]
) -> CheckResult:
    expected_values = [expected] if isinstance(expected, str) else list(expected)
    actual = state.get("workflow_status")
    if actual in expected_values:
        return CheckResult("workflow_status", STATUS_PASSED, str(actual))
    detail = f"期望 {' / '.join(expected_values)}，实际 {actual or '缺失'}"
    # 失败原因决定修复方向，必须回显；限长并脱敏，避免把模型原文或密钥带进报告
    failure = state.get("build_failure")
    if failure:
        detail = f"{detail}；原因 {redact_sensitive_text(str(failure))[:ERROR_PREVIEW_CHARS]}"
    return CheckResult("workflow_status", STATUS_FAILED, detail)


def _check_missing_slots(expected: list[str], state: dict[str, Any]) -> CheckResult:
    actual = _collect_missing_slots(state)
    missing = [slot for slot in expected if slot not in actual]
    if missing:
        return CheckResult(
            "missing_slots",
            STATUS_FAILED,
            f"未标记为缺失：{'、'.join(missing)}；实际：{'、'.join(sorted(actual)) or '无'}",
        )
    return CheckResult("missing_slots", STATUS_PASSED, "、".join(expected))


def _check_structured_fields(
    expected: dict[str, StructuredValue], state: dict[str, Any]
) -> CheckResult:
    mismatches = []
    for path, want in expected.items():
        actual = _state_value(state, path)
        if actual is _MISSING:
            mismatches.append(f"{path} 缺失")
        elif not _value_matches(want, actual):
            mismatches.append(f"{path} 期望 {want}，实际 {actual}")
    if mismatches:
        return CheckResult("structured_fields", STATUS_FAILED, "；".join(mismatches))
    return CheckResult("structured_fields", STATUS_PASSED, f"{len(expected)} 个字段一致")


def _check_price_consistency(state: dict[str, Any]) -> CheckResult:
    """分项合计必须等于总价；有预算上限时总价不得越界。"""
    build = state.get("build_result")
    if not isinstance(build, dict):
        return CheckResult(
            "price_consistency", STATUS_FAILED, "本次未产出配置，无法校验价格一致性"
        )

    components = build.get("components")
    total = build.get("totalPriceFen")
    if (
        not isinstance(components, list)
        or not components
        or not isinstance(total, int)
        or isinstance(total, bool)
    ):
        return CheckResult(
            "price_consistency", STATUS_FAILED, "配置缺少分项或总价，无法校验"
        )

    prices: list[int] = []
    for item in components:
        price = item.get("priceFen") if isinstance(item, dict) else None
        if not isinstance(price, int) or isinstance(price, bool):
            return CheckResult(
                "price_consistency", STATUS_FAILED, "存在缺失或非法的分项价格"
            )
        prices.append(price)

    component_total = sum(prices)
    if component_total != total:
        return CheckResult(
            "price_consistency",
            STATUS_FAILED,
            f"分项合计 {component_total} 分 ≠ 总价 {total} 分",
        )

    budget_max = build.get("budgetMaxFen")
    if (
        isinstance(budget_max, int)
        and not isinstance(budget_max, bool)
        and budget_max > 0
        and total > budget_max
    ):
        return CheckResult(
            "price_consistency",
            STATUS_FAILED,
            f"总价 {total} 分超过预算上限 {budget_max} 分",
        )
    return CheckResult(
        "price_consistency", STATUS_PASSED, f"分项合计 {total} 分，未超预算"
    )


def _text_checks(case: EvalCase, answer: str, tool_names: list[str]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    expect = case.expect

    if expect.tool_called is not None:
        checks.append(_check_tool_called(expect.tool_called, tool_names))

    if expect.tool_sequence:
        if _ordered_subsequence(list(expect.tool_sequence), tool_names):
            checks.append(
                CheckResult(
                    CHECK_TOOL_SEQUENCE,
                    STATUS_PASSED,
                    " → ".join(expect.tool_sequence),
                )
            )
        else:
            actual = ", ".join(tool_names) or "无"
            checks.append(
                CheckResult(
                    CHECK_TOOL_SEQUENCE,
                    STATUS_FAILED,
                    f"期望顺序 {' → '.join(expect.tool_sequence)}，实际调用：{actual}",
                )
            )

    if expect.must_contain:
        missing = [text for text in expect.must_contain if text not in answer]
        if missing:
            checks.append(
                CheckResult(
                    "must_contain",
                    STATUS_FAILED,
                    f"缺少片段：{'、'.join(missing)}；回答：{_preview(answer)}",
                )
            )
        else:
            checks.append(CheckResult("must_contain", STATUS_PASSED))

    if expect.must_not_contain:
        forbidden = [text for text in expect.must_not_contain if text in answer]
        if forbidden:
            checks.append(
                CheckResult(
                    "must_not_contain",
                    STATUS_FAILED,
                    f"出现禁用片段：{'、'.join(forbidden)}；回答：{_preview(answer)}",
                )
            )
        else:
            checks.append(CheckResult("must_not_contain", STATUS_PASSED))

    return checks


def _state_checks(case: EvalCase, state: dict[str, Any]) -> list[CheckResult]:
    expect = case.expect
    checks: list[CheckResult] = []
    if expect.workflow_status is not None:
        checks.append(_check_workflow_status(expect.workflow_status, state))
    if expect.missing_slots:
        checks.append(_check_missing_slots(expect.missing_slots, state))
    if expect.structured_fields:
        checks.append(_check_structured_fields(expect.structured_fields, state))
    if expect.price_consistency:
        checks.append(_check_price_consistency(state))
    return checks


def _check_interrupt(expected: str, interrupt: Interrupt | None) -> CheckResult:
    """中断是否发生在期望的交互类型上；用公开载荷而不是内部图状态。"""
    if interrupt is None:
        return CheckResult(
            CHECK_INTERRUPT, STATUS_FAILED, f"期望暂停于 {expected}，实际未暂停"
        )
    value = interrupt.value if isinstance(interrupt.value, dict) else {}
    actual = value.get("interaction_type")
    if actual == expected:
        return CheckResult(CHECK_INTERRUPT, STATUS_PASSED, expected)
    return CheckResult(
        CHECK_INTERRUPT, STATUS_FAILED, f"期望 {expected}，实际 {actual or '缺失'}"
    )


def _hitl_checks(
    case: EvalCase, interrupt: Interrupt | None, is_resolved: bool
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    if case.expect.interrupt_type is not None:
        checks.append(_check_interrupt(case.expect.interrupt_type, interrupt))

    if case.resume is not None:
        if interrupt is None:
            checks.append(
                CheckResult(CHECK_RESUME, STATUS_FAILED, "配置了 resume 但本轮未暂停")
            )
        elif not is_resolved:
            checks.append(
                CheckResult(CHECK_RESUME, STATUS_FAILED, "提交恢复后仍存在待处理中断")
            )
        else:
            checks.append(
                CheckResult(CHECK_RESUME, STATUS_PASSED, "中断已恢复并完成本轮")
            )
    return checks


def _budget_checks(
    case: EvalCase,
    latency_ms: int,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    max_latency = case.expect.max_latency_ms
    if max_latency is not None:
        status = STATUS_PASSED if latency_ms <= max_latency else STATUS_FAILED
        checks.append(
            CheckResult("max_latency_ms", status, f"{latency_ms}ms / 上限 {max_latency}ms")
        )

    max_tokens = case.expect.max_tokens
    if max_tokens is not None:
        if prompt_tokens is None and completion_tokens is None:
            checks.append(
                CheckResult("max_tokens", STATUS_SKIPPED, "Provider 未返回 usage")
            )
        else:
            total = (prompt_tokens or 0) + (completion_tokens or 0)
            status = STATUS_PASSED if total <= max_tokens else STATUS_FAILED
            checks.append(
                CheckResult("max_tokens", status, f"{total} tokens / 上限 {max_tokens}")
            )
    return checks


async def _resume_if_interrupted(
    graph: CompiledStateGraph,
    config: RunnableConfig,
    case: EvalCase,
    result: dict[str, Any],
) -> tuple[dict[str, Any], Interrupt | None, bool]:
    """首轮结束后若有待恢复中断，按用例配置提交一次恢复。

    返回 (最终状态, 首个中断, 是否已全部恢复)。未配置 `resume` 时不执行恢复，
    由断言如实报告「意外暂停」。仅恢复一次：若恢复后再次暂停，视为未收敛。
    """
    snapshot = await graph.aget_state(config)
    pending = list(snapshot.interrupts)
    if not pending:
        return result, None, False

    first = pending[0]
    if case.resume is None:
        return result, first, False

    resumed = await graph.ainvoke(
        Command(
            resume={
                "message": case.resume.message,
                "answer": dict(case.resume.answer),
            }
        ),
        config=config,
    )
    snapshot = await graph.aget_state(config)
    return resumed, first, not snapshot.interrupts


async def run_case(case: EvalCase) -> CaseResult:
    started_at = perf_counter()
    agent_id = case.agent_id or get_settings().agent.default_profile
    thread_id = f"eval-{case.id}-{uuid4().hex[:8]}"

    try:
        profile = resolve_profile(agent_id)
        prepared = await _prepare_graph(profile, thread_id)
        graph = prepared.graph
        # 与生产相同：运行时进 configurable 供用量上报，不写进图状态
        config: RunnableConfig = cast(
            "RunnableConfig",
            build_agent_config(
                thread_id=thread_id,
                runtime=prepared.runtime,
            ),
        )
        user_token = _user_token_value(prepared.user_token)
        # 回调是唯一能同时覆盖结构化、文本兜底与流式三条路径的用量观测点
        collector = UsageCollector()
        config["callbacks"] = [*cast("list[Any]", config.get("callbacks") or []), collector]
        # 每轮独立 ToolTurn：与 /chat/stream 一样按请求创建，
        # 否则多轮用例会共享工具配额，第二轮被「本轮调用次数已达上限」卡死
        result: dict[str, Any] = {}
        turn_calls: list[int] = []
        for text in (case.input, *case.turns):
            calls_before = collector.totals.calls
            with ToolTurn(EVAL_USER_ROLES, user_token, user_id=_eval_user_id()):
                result = await graph.ainvoke(
                    {"messages": [HumanMessage(content=text)]}, config=config
                )
            turn_calls.append(collector.totals.calls - calls_before)
        calls_before = collector.totals.calls
        with ToolTurn(EVAL_USER_ROLES, user_token, user_id=_eval_user_id()):
            result, interrupt, is_resume_resolved = await _resume_if_interrupted(
                graph, config, case, result
            )
        turn_calls.append(collector.totals.calls - calls_before)
    except ModelResolutionError as exc:
        # 模型不可用时直接失败：绝不继续执行图去触发正则/确定性兜底
        return CaseResult(
            case_id=case.id,
            agent_id=agent_id,
            error=str(exc),
            latency_ms=int((perf_counter() - started_at) * 1000),
        )
    except Exception as exc:
        return CaseResult(
            case_id=case.id,
            agent_id=agent_id,
            error=_describe_error(exc),
            latency_ms=int((perf_counter() - started_at) * 1000),
        )

    latency_ms = int((perf_counter() - started_at) * 1000)
    messages: list[BaseMessage] = result.get("messages", [])
    tool_names = _tool_call_names(result)
    answer = _answer_text(messages)
    prompt_tokens, completion_tokens = _token_totals(messages)
    if prompt_tokens is None and completion_tokens is None:
        # 图状态里的消息通常不带 usage_metadata，回落到回调累计值
        prompt_tokens = collector.totals.prompt_tokens
        completion_tokens = collector.totals.completion_tokens

    checks = _text_checks(case, answer, tool_names)
    checks.extend(_state_checks(case, result))
    checks.extend(_hitl_checks(case, interrupt, is_resume_resolved))
    checks.extend(_budget_checks(case, latency_ms, prompt_tokens, completion_tokens))

    return CaseResult(
        case_id=case.id,
        agent_id=agent_id,
        checks=checks,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        llm_calls=collector.totals.calls,
        cost=_estimate_cost(
            prompt_tokens, completion_tokens, collector.totals.calls
        ),
        workflow_status=_workflow_status(result),
        repair_count=_repair_count(result),
        expects_success=case.expect.workflow_status == "success",
        max_turn_llm_calls=max(turn_calls) if turn_calls else None,
        quality_passed=_quality_passed(result),
        hard_constraint=_hard_constraint_status(result),
    )


async def run_cases(cases: list[EvalCase]) -> list[CaseResult]:
    """顺序执行：并发会把真实费用与限流风险成倍放大。"""
    return [await run_case(case) for case in cases]
