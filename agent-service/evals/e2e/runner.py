"""E2E 运行器：把一条用例跑成「请求 → 事件流 → 落库 → 清理」的完整闭环。

断言编排与传输分离：本模块只负责组装请求、调用客户端、收集会话层证据，
事件契约与事实断言全部来自 `contract.py`。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from evals.e2e.client import E2EClientError, E2EUsageError, ServiceClient
from evals.e2e.contract import check_stream, interrupt_id
from evals.e2e.schema import E2ECase, E2EExpectation, E2EResume
from evals.e2e.sse import SseEvent
from evals.report import STATUS_FAILED, STATUS_PASSED, CaseResult, CheckResult

# 客户端 thread_id 上限 64；前缀与随机后缀固定，剩余留给用例 id
MAX_CASE_ID_IN_THREAD = 32
THREAD_SUFFIX_CHARS = 8
HTTP_OK = 200

HistoryFetcher = Callable[[], dict[str, Any]]
SessionFetcher = Callable[[], dict[str, Any]]


def thread_id_for(case: E2ECase) -> str:
    """每次运行使用唯一 thread_id：避免与历史会话串上下文，也便于并行重跑。"""
    return f"e2e-{case.id[:MAX_CASE_ID_IN_THREAD]}-{uuid4().hex[:THREAD_SUFFIX_CHARS]}"


def agent_id_for(case: E2ECase) -> str:
    return case.agent_id or get_settings().agent.default_profile


def chat_payload(case: E2ECase, thread_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": case.message, "thread_id": thread_id}
    if case.agent_id is not None:
        payload["agent_id"] = case.agent_id
    return payload


def resume_payload(case: E2ECase, thread_id: str, pending_id: str) -> dict[str, Any]:
    """恢复请求与首轮共用 thread_id；answer 按 interrupt 事件声明的字段填写。"""
    resume = case.resume or E2EResume()
    return {
        "message": resume.message,
        "thread_id": thread_id,
        "resume": {"interrupt_id": pending_id, "answer": dict(resume.answer)},
    }


def resume_expectation(case: E2ECase) -> E2EExpectation:
    """恢复回合默认要求正常 done；用例可单独覆盖内容与延迟断言。"""
    return case.resume_expect or E2EExpectation(terminal="done")


def build_case_result(
    case: E2ECase,
    checks: list[CheckResult],
    latency_ms: int,
    *,
    error: str | None = None,
) -> CaseResult:
    return CaseResult(
        case_id=case.id,
        agent_id=agent_id_for(case),
        checks=checks,
        latency_ms=latency_ms,
        expects_success=case.expect.terminal == "done",
        error=error,
    )


def session_checks(
    fetch_history: HistoryFetcher,
    fetch_sessions: SessionFetcher,
    thread_id: str,
) -> list[CheckResult]:
    """验证落库闭环：历史能读到本轮助手消息，会话列表能找到该会话。"""
    checks: list[CheckResult] = []
    try:
        history = fetch_history()
    except E2EClientError as exc:
        return [CheckResult("session_history", STATUS_FAILED, str(exc))]

    items = history.get("list")
    if not isinstance(items, list) or not items:
        checks.append(CheckResult("session_history", STATUS_FAILED, "历史消息为空"))
    else:
        checks.append(_check_assistant_message(items))

    try:
        sessions = fetch_sessions()
    except E2EClientError as exc:
        checks.append(CheckResult("session_list", STATUS_FAILED, str(exc)))
        return checks
    checks.append(_check_session_present(sessions, thread_id))
    return checks


def _check_assistant_message(items: list[Any]) -> CheckResult:
    assistants = [
        item
        for item in items
        if isinstance(item, dict) and item.get("role") == "assistant"
    ]
    if not assistants:
        return CheckResult("session_history", STATUS_FAILED, "历史中没有 assistant 消息")
    latest = assistants[-1]
    content = latest.get("content")
    if not isinstance(content, str) or not content.strip():
        return CheckResult("session_history", STATUS_FAILED, "assistant 消息内容为空")
    message_id = latest.get("message_id")
    if not isinstance(message_id, str) or not message_id:
        # message_id 缺失时前端会隐藏反馈入口，属于契约缺口
        return CheckResult("session_history", STATUS_FAILED, "assistant 消息缺少 message_id")
    return CheckResult(
        "session_history",
        STATUS_PASSED,
        f"{len(items)} 条消息，最新 message_id={message_id}",
    )


def _check_session_present(sessions: dict[str, Any], thread_id: str) -> CheckResult:
    items = sessions.get("list")
    if not isinstance(items, list):
        return CheckResult("session_list", STATUS_FAILED, "会话列表缺少 list 字段")
    matched = [
        item for item in items if isinstance(item, dict) and item.get("thread_id") == thread_id
    ]
    if not matched:
        return CheckResult("session_list", STATUS_FAILED, f"列表中找不到 {thread_id}")
    return CheckResult("session_list", STATUS_PASSED, thread_id)


def run_service_cases(cases: list[E2ECase]) -> list[CaseResult]:
    """真实服务模式：顺序执行，首次登录失败直接抛出（属于环境配置问题）。"""
    e2e = get_settings().evals.e2e
    if e2e.password is None:
        raise E2EUsageError(
            "service 模式需要登录口令：请设置 EVALS__E2E__PASSWORD 与 EVALS__E2E__USERNAME"
        )
    client = ServiceClient(
        agent_base_url=e2e.agent_base_url,
        java_base_url=e2e.java_base_url,
        username=e2e.username,
        password=e2e.password,
        timeout_seconds=e2e.timeout_seconds,
    )
    try:
        client.login()
        return [run_service_case(client, case) for case in cases]
    finally:
        client.close()


def run_service_case(client: ServiceClient, case: E2ECase) -> CaseResult:
    started_at = perf_counter()
    thread_id = thread_id_for(case)
    checks: list[CheckResult] = []
    error: str | None = None
    latency_ms = 0
    try:
        stream = client.stream_chat(
            chat_payload(case, thread_id), idempotency_key=str(uuid4())
        )
        latency_ms = elapsed_ms(started_at)
        if stream.status_code != HTTP_OK:
            # 流建立前的错误是裸 JSON：保留状态码与业务码，便于区分额度/鉴权/配置
            checks.append(
                CheckResult(
                    "http_status",
                    STATUS_FAILED,
                    f"HTTP {stream.status_code} {error_code(stream.body)}".strip(),
                )
            )
        else:
            stream_checks, events = check_stream(case, list(stream.frames), latency_ms)
            checks.extend(stream_checks)
            if case.resume is not None:
                resume_checks, resumed_done = _run_service_resume(
                    client, case, thread_id, events
                )
                checks.extend(resume_checks)
                if resumed_done:
                    checks.extend(_service_session_checks(client, thread_id))
            elif ends_with_done(events):
                checks.extend(_service_session_checks(client, thread_id))
    except E2EClientError as exc:
        error = str(exc)
        latency_ms = elapsed_ms(started_at)
    finally:
        cleanup_session(client.delete_session, thread_id, checks)

    return build_case_result(case, checks, latency_ms, error=error)


def _service_session_checks(client: ServiceClient, thread_id: str) -> list[CheckResult]:
    return session_checks(
        lambda: client.list_messages(thread_id),
        client.list_sessions,
        thread_id,
    )


def _run_service_resume(
    client: ServiceClient,
    case: E2ECase,
    thread_id: str,
    events: list[SseEvent],
) -> tuple[list[CheckResult], bool]:
    """首轮中断后用同一 thread_id 提交恢复，返回 (断言, 是否正常完成)。"""
    pending = interrupt_id(events)
    if pending is None:
        return [
            CheckResult("resume", STATUS_FAILED, "首轮未给出 interrupt_id，无法恢复")
        ], False

    started_at = perf_counter()
    stream = client.stream_chat(
        resume_payload(case, thread_id, pending), idempotency_key=str(uuid4())
    )
    latency_ms = elapsed_ms(started_at)
    if stream.status_code != HTTP_OK:
        return [
            CheckResult(
                "http_status_resume",
                STATUS_FAILED,
                f"HTTP {stream.status_code} {error_code(stream.body)}".strip(),
            )
        ], False
    resume_checks, resume_events = check_stream(
        case,
        list(stream.frames),
        latency_ms,
        expectation=resume_expectation(case),
    )
    return resume_checks, ends_with_done(resume_events)


def ends_with_done(events: list[SseEvent]) -> bool:
    """只有正常完成的回合才必然落库；interrupt/error 不写完整消息。"""
    return bool(events) and events[-1].event == "done"


def cleanup_session(
    delete: Callable[[str], bool], thread_id: str, checks: list[CheckResult]
) -> None:
    """清理失败不能掩盖断言结果，但要留痕，避免测试数据在环境里堆积。"""
    try:
        deleted = delete(thread_id)
    except E2EClientError as exc:
        checks.append(CheckResult("cleanup", STATUS_FAILED, str(exc)))
        return
    if not deleted:
        checks.append(CheckResult("cleanup", STATUS_FAILED, f"删除会话失败：{thread_id}"))


def error_code(body: str) -> str:
    """从裸 JSON 错误体提取业务码；解析失败时只回显片段，不猜测。"""
    if not body:
        return ""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body[:120]
    if isinstance(payload, dict) and isinstance(payload.get("code"), str):
        return str(payload["code"])
    return ""


def elapsed_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)
