"""SSE 契约与事实断言。

分三层，任一不满足即判失败：
1. 契约层：事件类型、自增 id、`schema_version`、必填字段、终态唯一且最后；
2. 事实层：`done.build_result` 八类齐全、分项合计等于总价、不超预算；
3. 语义层：`UNKNOWN` 兼容性不得被正文说成「通过」，工具与内容片段符合用例期望。

只做断言，不发请求：网络与登录由 `client.py` 负责，便于单测直接喂构造好的帧。
"""

from __future__ import annotations

from typing import Any, TypeGuard

from app.agent.pc.schemas import REQUIRED_CATEGORIES
from app.api.v1.sse import SSE_SCHEMA_VERSION
from evals.e2e.schema import E2ECase, E2EExpectation
from evals.e2e.sse import SseEvent, SseFrame, parse_events
from evals.report import STATUS_FAILED, STATUS_PASSED, STATUS_SKIPPED, CheckResult

# 服务端当前只允许这 9 类事件；出现别的说明契约漂移
ALLOWED_EVENTS = frozenset(
    {
        "token",
        "reasoning",
        "stage",
        "tool_call",
        "tool_result",
        "citations",
        "interrupt",
        "done",
        "error",
    }
)
TERMINAL_EVENTS = frozenset({"done", "interrupt", "error"})
# 终态在契约里必须是最后一个事件
TERMINAL_POSITION = -1

# 各事件的必填字段与类型；`citations` 的嵌套结构单独校验
REQUIRED_FIELDS: dict[str, tuple[tuple[str, type], ...]] = {
    "token": (("text", str),),
    "reasoning": (("text", str),),
    "tool_call": (("name", str), ("args", dict)),
    "tool_result": (("name", str), ("preview", str)),
    "done": (("thread_id", str),),
    "error": (("code", str), ("message", str)),
}
CITATION_FIELDS: tuple[tuple[str, type], ...] = (
    ("source_id", str),
    ("title", str),
    ("snippet", str),
)
MAX_TOOL_PREVIEW_CHARS = 200
COMPATIBILITY_STATUSES = frozenset({"PASS", "WARNING", "FAIL", "UNKNOWN"})
# 非 PASS 时正文不得出现的「已确认兼容」类表述
FORBIDDEN_PASS_CLAIMS = ("兼容性通过", "兼容性全部通过", "完全兼容", "全部兼容")


def check_stream(
    case: E2ECase,
    frames: list[SseFrame],
    latency_ms: int,
    expectation: E2EExpectation | None = None,
) -> tuple[list[CheckResult], list[SseEvent]]:
    """校验一次请求的完整事件流；返回 (断言结果, 已解析事件)。

    `expectation` 用于 HITL 恢复回合：同一用例的首轮期望是 interrupt，
    恢复回合期望 done，不能共用一份配置。
    """
    events, parse_errors = parse_events(frames)
    if parse_errors:
        return [
            CheckResult("sse_parse", STATUS_FAILED, "；".join(parse_errors[:3]))
        ], events

    expect = expectation or case.expect
    checks: list[CheckResult] = []
    checks.extend(_check_event_ids(events))
    checks.extend(_check_schema_version(events))
    checks.extend(_check_event_types(events))
    checks.extend(_check_required_fields(events))
    checks.extend(_check_terminal(expect, events))
    checks.extend(_check_event_order(expect, events))
    checks.extend(_check_citations(expect, events))
    checks.extend(_check_tools(expect, events))
    checks.extend(_check_content(expect, events))
    checks.extend(_check_build_result(expect, events))
    checks.extend(_check_latency(expect, latency_ms))
    return checks, events


def interrupt_id(events: list[SseEvent]) -> str | None:
    """取首个 interrupt 事件的 id；缺失时返回 None，由调用方判失败。"""
    for event in events:
        if event.event != "interrupt":
            continue
        value = event.data.get("interrupt_id")
        if isinstance(value, str) and value:
            return value
    return None


def _check_event_ids(events: list[SseEvent]) -> list[CheckResult]:
    """id 必须从 1 开始逐条递增；心跳不带 id，已在解析阶段排除。"""
    expected = 1
    for event in events:
        if event.event_id is None:
            return [
                CheckResult(
                    "sse_event_ids",
                    STATUS_FAILED,
                    f"事件 {event.event} 缺少 id",
                )
            ]
        try:
            actual = int(event.event_id)
        except ValueError:
            return [
                CheckResult(
                    "sse_event_ids",
                    STATUS_FAILED,
                    f"事件 id 不是整数：{event.event_id}",
                )
            ]
        if actual != expected:
            return [
                CheckResult(
                    "sse_event_ids",
                    STATUS_FAILED,
                    f"第 {expected} 个事件 id 期望 {expected}，实际 {actual}",
                )
            ]
        expected += 1
    return [CheckResult("sse_event_ids", STATUS_PASSED, f"{len(events)} 个事件连续递增")]


def _check_schema_version(events: list[SseEvent]) -> list[CheckResult]:
    mismatched = [
        f"{event.event}={event.data.get('schema_version')}"
        for event in events
        if event.data.get("schema_version") != SSE_SCHEMA_VERSION
    ]
    if mismatched:
        return [
            CheckResult(
                "sse_schema_version",
                STATUS_FAILED,
                f"期望 {SSE_SCHEMA_VERSION}，异常事件：{'、'.join(mismatched[:5])}",
            )
        ]
    return [CheckResult("sse_schema_version", STATUS_PASSED, SSE_SCHEMA_VERSION)]


def _check_event_types(events: list[SseEvent]) -> list[CheckResult]:
    unknown = sorted({event.event for event in events if event.event not in ALLOWED_EVENTS})
    if unknown:
        return [
            CheckResult(
                "sse_event_types",
                STATUS_FAILED,
                f"出现未定义事件：{'、'.join(unknown)}",
            )
        ]
    return [CheckResult("sse_event_types", STATUS_PASSED, "事件类型均已在契约内")]


def _check_required_fields(events: list[SseEvent]) -> list[CheckResult]:
    problems: list[str] = []
    for event in events:
        if event.event == "citations":
            problems.extend(_citation_problems(event.data))
            continue
        if event.event == "interrupt":
            problems.extend(_interrupt_problems(event.data))
            continue
        for field_name, field_type in REQUIRED_FIELDS.get(event.event, ()):
            value = event.data.get(field_name)
            if not isinstance(value, field_type):
                problems.append(f"{event.event}.{field_name} 缺失或类型错误")
        if event.event == "tool_result":
            problems.extend(_tool_preview_problems(event.data))
    if problems:
        return [
            CheckResult("sse_required_fields", STATUS_FAILED, "；".join(problems[:6]))
        ]
    return [CheckResult("sse_required_fields", STATUS_PASSED, "必填字段齐全")]


def _citation_problems(data: dict[str, Any]) -> list[str]:
    citations = data.get("citations")
    if not isinstance(citations, list) or not citations:
        return ["citations.citations 必须是非空列表"]
    problems: list[str] = []
    for index, item in enumerate(citations):
        if not isinstance(item, dict):
            problems.append(f"citations[{index}] 不是对象")
            continue
        for field_name, field_type in CITATION_FIELDS:
            if not isinstance(item.get(field_name), field_type):
                problems.append(f"citations[{index}].{field_name} 缺失或类型错误")
        score = item.get("score")
        if score is not None and (
            not isinstance(score, (int, float)) or isinstance(score, bool)
        ):
            problems.append(f"citations[{index}].score 必须是数字")
    return problems


def _interrupt_problems(data: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for field_name in ("interrupt_id", "interaction_type", "question"):
        if not isinstance(data.get(field_name), str) or not data.get(field_name):
            problems.append(f"interrupt.{field_name} 缺失")
    schema = data.get("input_schema")
    if not isinstance(schema, dict) or not isinstance(schema.get("fields"), list):
        problems.append("interrupt.input_schema.fields 缺失")
    return problems


def _tool_preview_problems(data: dict[str, Any]) -> list[str]:
    preview = data.get("preview")
    if isinstance(preview, str) and len(preview) > MAX_TOOL_PREVIEW_CHARS:
        return [f"tool_result.preview 超过 {MAX_TOOL_PREVIEW_CHARS} 字符"]
    return []


def _check_terminal(expect: E2EExpectation, events: list[SseEvent]) -> list[CheckResult]:
    """终态事件必须唯一且位于末尾，并与用例期望一致。"""
    terminals = [event for event in events if event.event in TERMINAL_EVENTS]
    if not terminals:
        return [
            CheckResult("sse_terminal", STATUS_FAILED, "缺少 done / interrupt / error 终态事件")
        ]
    if len(terminals) > 1:
        names = "、".join(event.event for event in terminals)
        return [
            CheckResult("sse_terminal", STATUS_FAILED, f"出现多个终态事件：{names}")
        ]
    last = events[TERMINAL_POSITION]
    if last.event not in TERMINAL_EVENTS:
        return [
            CheckResult(
                "sse_terminal",
                STATUS_FAILED,
                f"终态事件 {last.event} 不在流末尾",
            )
        ]
    expected = expect.terminal
    if last.event != expected:
        return [
            CheckResult(
                "sse_terminal",
                STATUS_FAILED,
                f"期望以 {expected} 结束，实际 {last.event}",
            )
        ]
    return [CheckResult("sse_terminal", STATUS_PASSED, expected)]


def _check_event_order(
    expect: E2EExpectation, events: list[SseEvent]
) -> list[CheckResult]:
    """引用与思考必须早于首个正文 token；否则前端无法按约定折叠展示。"""
    names = [event.event for event in events]
    if "token" not in names:
        if expect.terminal in ("interrupt", "error"):
            # 中断与错误回合本就不产出正文，顺序约束不适用
            return [
                CheckResult(
                    "sse_event_order",
                    STATUS_PASSED,
                    f"{expect.terminal} 回合无正文，跳过顺序约束",
                )
            ]
        return [CheckResult("sse_event_order", STATUS_SKIPPED, "本轮无 token 事件")]
    first_token = names.index("token")
    for earlier in ("citations", "reasoning"):
        if earlier in names and names.index(earlier) > first_token:
            return [
                CheckResult(
                    "sse_event_order",
                    STATUS_FAILED,
                    f"{earlier} 出现在首个 token 之后",
                )
            ]
    return [CheckResult("sse_event_order", STATUS_PASSED, "引用/思考早于正文")]


def _check_citations(
    expect: E2EExpectation, events: list[SseEvent]
) -> list[CheckResult]:
    expected = expect.expect_citations
    if expected is None:
        return []
    present = any(event.event == "citations" for event in events)
    if present == expected:
        return [CheckResult("sse_citations", STATUS_PASSED, str(expected))]
    detail = "期望出现 citations 事件" if expected else "不应出现 citations 事件"
    return [CheckResult("sse_citations", STATUS_FAILED, detail)]


def _check_tools(expect: E2EExpectation, events: list[SseEvent]) -> list[CheckResult]:
    expected = expect.tool_names
    if not expected:
        return []
    called = {
        str(event.data.get("name")) for event in events if event.event == "tool_call"
    }
    missing = [name for name in expected if name not in called]
    if missing:
        actual = "、".join(sorted(called)) or "无"
        return [
            CheckResult(
                "sse_tool_names",
                STATUS_FAILED,
                f"未调用：{'、'.join(missing)}；实际：{actual}",
            )
        ]
    return [CheckResult("sse_tool_names", STATUS_PASSED, "、".join(expected))]


def _answer_text(events: list[SseEvent]) -> str:
    return "".join(
        str(event.data.get("text"))
        for event in events
        if event.event == "token" and isinstance(event.data.get("text"), str)
    )


def _check_content(expect: E2EExpectation, events: list[SseEvent]) -> list[CheckResult]:
    answer = _answer_text(events)
    checks: list[CheckResult] = []
    if expect.must_contain:
        missing = [text for text in expect.must_contain if text not in answer]
        checks.append(
            CheckResult(
                "must_contain",
                STATUS_FAILED if missing else STATUS_PASSED,
                f"缺少片段：{'、'.join(missing)}" if missing else "",
            )
        )
    if expect.must_not_contain:
        forbidden = [text for text in expect.must_not_contain if text in answer]
        checks.append(
            CheckResult(
                "must_not_contain",
                STATUS_FAILED if forbidden else STATUS_PASSED,
                f"出现禁用片段：{'、'.join(forbidden)}" if forbidden else "",
            )
        )
    return checks


def _check_build_result(
    expect: E2EExpectation, events: list[SseEvent]
) -> list[CheckResult]:
    done = next((event for event in events if event.event == "done"), None)
    build = done.data.get("build_result") if done is not None else None
    if not isinstance(build, dict):
        if expect.expect_build_result and done is not None:
            return [CheckResult("build_result", STATUS_FAILED, "done 事件缺少 build_result")]
        return []

    checks = [_check_categories(build)]
    checks.append(_check_price(build))
    checks.append(_check_compatibility(build, _answer_text(events)))
    return checks


def _check_categories(build: dict[str, Any]) -> CheckResult:
    components = build.get("components")
    if not isinstance(components, list):
        return CheckResult("build_categories", STATUS_FAILED, "components 缺失")
    categories = [
        str(item.get("category"))
        for item in components
        if isinstance(item, dict) and item.get("category")
    ]
    expected = {category.value for category in REQUIRED_CATEGORIES}
    if len(components) != len(expected) or set(categories) != expected:
        missing = sorted(expected - set(categories))
        missing_text = "、".join(missing) or "无"
        return CheckResult(
            "build_categories",
            STATUS_FAILED,
            f"期望 {len(expected)} 类，实际 {len(components)} 条；缺少：{missing_text}",
        )
    return CheckResult("build_categories", STATUS_PASSED, f"{len(expected)} 类齐全")


def _check_price(build: dict[str, Any]) -> CheckResult:
    """分项合计必须等于总价；有预算上限时总价不得越界。"""
    components = build.get("components")
    if not isinstance(components, list) or not components:
        return CheckResult("price_consistency", STATUS_FAILED, "缺少分项")
    total_value = build.get("total_price_fen")
    if not _is_int(total_value):
        return CheckResult("price_consistency", STATUS_FAILED, "total_price_fen 缺失或非整数")
    total = int(total_value)

    prices: list[int] = []
    for item in components:
        price_value = item.get("price_fen") if isinstance(item, dict) else None
        if not _is_int(price_value):
            return CheckResult("price_consistency", STATUS_FAILED, "存在缺失或非法的 price_fen")
        prices.append(int(price_value))

    component_total = sum(prices)
    if component_total != total:
        return CheckResult(
            "price_consistency",
            STATUS_FAILED,
            f"分项合计 {component_total} 分 ≠ 总价 {total} 分",
        )
    budget_value = build.get("budget_max_fen")
    if _is_int(budget_value):
        budget = int(budget_value)
        if budget > 0 and total > budget:
            return CheckResult(
                "price_consistency",
                STATUS_FAILED,
                f"总价 {total} 分超过预算上限 {budget} 分",
            )
    return CheckResult("price_consistency", STATUS_PASSED, f"分项合计 {total} 分")


def _check_compatibility(build: dict[str, Any], answer: str) -> CheckResult:
    """兼容性结论必须在合法枚举内；非 PASS 时正文不得宣称已通过。"""
    status = build.get("overall_status")
    if status not in COMPATIBILITY_STATUSES:
        return CheckResult(
            "compatibility_claims",
            STATUS_FAILED,
            f"overall_status 非法或缺失：{status}",
        )
    if status == "PASS":
        return CheckResult("compatibility_claims", STATUS_PASSED, "PASS")
    claimed = [phrase for phrase in FORBIDDEN_PASS_CLAIMS if phrase in answer]
    if claimed:
        return CheckResult(
            "compatibility_claims",
            STATUS_FAILED,
            f"结论为 {status}，正文却宣称：{'、'.join(claimed)}",
        )
    return CheckResult("compatibility_claims", STATUS_PASSED, str(status))


def _check_latency(expect: E2EExpectation, latency_ms: int) -> list[CheckResult]:
    limit = expect.max_latency_ms
    if limit is None:
        return []
    status = STATUS_PASSED if latency_ms <= limit else STATUS_FAILED
    return [CheckResult("max_latency_ms", status, f"{latency_ms}ms / 上限 {limit}ms")]


def _is_int(value: object) -> TypeGuard[int]:
    """排除 bool：Python 里 True 也是 int，价格与数量不能把布尔值当数字。"""
    return isinstance(value, int) and not isinstance(value, bool)
