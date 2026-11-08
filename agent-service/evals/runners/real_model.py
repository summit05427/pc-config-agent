"""真实模型模式：真正跑一次对话，按用例断言工具调用与回答内容。

默认不启用（必须显式 `--real`）：每次运行都会产生真实 token 费用，
因此不进 CI（决策 D7）。
"""

from time import perf_counter
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from app.agent.graph import build_agent
from app.agent.profiles import AgentProfile, resolve_profile
from app.agent.registry import redact_sensitive_text
from app.core.config import get_settings
from evals.report import STATUS_FAILED, STATUS_PASSED, CaseResult, CheckResult
from evals.schema import EvalCase

# 失败原因里回显回答片段便于定位，但必须限长并脱敏
ANSWER_PREVIEW_CHARS = 200
ERROR_PREVIEW_CHARS = 300
EMPTY_ANSWER_NOTICE = "（空回答）"

_GRAPHS: dict[str, CompiledStateGraph] = {}


def _graph_for(profile: AgentProfile) -> CompiledStateGraph:
    """同一 Profile 在一次运行内只构图一次；checkpointer 用内存实现，不写业务库。"""
    cached = _GRAPHS.get(profile.id)
    if cached is not None:
        return cached

    graph: CompiledStateGraph = build_agent(profile=profile, checkpointer=MemorySaver())
    _GRAPHS[profile.id] = graph
    return graph


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


def _tool_call_names(messages: list[BaseMessage]) -> list[str]:
    """按出现顺序收集实际调用过的工具名。"""
    names: list[str] = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            name = call.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def _answer_text(messages: list[BaseMessage]) -> str:
    """最终回答 = 最后一条不含 tool_calls 的 AIMessage。"""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
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


def _content_checks(
    case: EvalCase,
    tool_names: list[str],
    answer: str,
) -> list[CheckResult]:
    checks: list[CheckResult] = []

    expected_tool = case.expect.tool_called
    if expected_tool is not None:
        if expected_tool in tool_names:
            checks.append(CheckResult("tool_called", STATUS_PASSED, expected_tool))
        else:
            actual = ", ".join(tool_names) or "无"
            checks.append(
                CheckResult(
                    "tool_called",
                    STATUS_FAILED,
                    f"期望调用 {expected_tool}，实际调用：{actual}",
                )
            )

    if case.expect.must_contain:
        missing = [text for text in case.expect.must_contain if text not in answer]
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

    if case.expect.must_not_contain:
        forbidden = [text for text in case.expect.must_not_contain if text in answer]
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


async def run_case(case: EvalCase) -> CaseResult:
    started_at = perf_counter()
    agent_id = case.agent_id or get_settings().agent.default_profile

    try:
        profile = resolve_profile(agent_id)
        graph = _graph_for(profile)
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=case.input)]},
            config={
                # 每条用例独立 thread_id，避免上一条的对话历史污染本轮断言
                "configurable": {"thread_id": f"eval-{case.id}-{uuid4().hex[:8]}"},
                "recursion_limit": get_settings().agent.recursion_limit,
            },
        )
    except Exception as exc:
        return CaseResult(
            case_id=case.id,
            agent_id=agent_id,
            error=_describe_error(exc),
            latency_ms=int((perf_counter() - started_at) * 1000),
        )

    messages: list[BaseMessage] = result.get("messages", [])
    tool_names = _tool_call_names(messages)
    answer = _answer_text(messages)
    prompt_tokens, completion_tokens = _token_totals(messages)

    return CaseResult(
        case_id=case.id,
        agent_id=agent_id,
        checks=_content_checks(case, tool_names, answer),
        latency_ms=int((perf_counter() - started_at) * 1000),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


async def run_cases(cases: list[EvalCase]) -> list[CaseResult]:
    """顺序执行：并发会把真实费用与限流风险成倍放大。"""
    _GRAPHS.clear()
    return [await run_case(case) for case in cases]
