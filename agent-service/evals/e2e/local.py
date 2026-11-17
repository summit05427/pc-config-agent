"""local 模式：进程内 ASGI + 确定性假图，零费用验证 HTTP/SSE 契约。

不经过 Java 登录与 Nginx，因此只覆盖「Agent 传输层 + 回合编排 + 会话落库」；
鉴权、限流与额度由 service 模式覆盖。这样 CI 可以在没有任何外部依赖的情况下
先挡住事件契约与落库回归。

环境变量必须在导入 `app` 之前覆盖：`Settings` 读取根 `.env`，本地开发可能
已把存储切到 postgres、打开 RAG/多 Agent，会让「确定性」名不副实。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from time import perf_counter
from types import SimpleNamespace
from typing import Any, cast

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from evals.e2e.client import E2EClientError
from evals.e2e.contract import check_stream, interrupt_id
from evals.e2e.runner import (
    build_case_result,
    chat_payload,
    cleanup_session,
    elapsed_ms,
    ends_with_done,
    error_code,
    resume_expectation,
    resume_payload,
    session_checks,
    thread_id_for,
)
from evals.e2e.schema import E2ECase, E2EExpectation, E2ELocalScript
from evals.e2e.sse import SseEvent, parse_frames
from evals.report import STATUS_FAILED, CaseResult, CheckResult

HTTP_OK = 200
HTTP_NO_CONTENT = 204
HTTP_NOT_FOUND = 404
SESSIONS_PATH = "/api/v1/sessions"
CHAT_PATH = "/api/v1/chat/stream"
MAX_SESSION_PAGE_SIZE = 100
LOCAL_REASON_SUMMARY = "本地契约模式：确定性假图产出，不代表真实选型结果"
LOCAL_TOOL_PREVIEW = "本地占位工具结果"
# 假图固定中断 id；恢复时必须原样带回，用于验证 `_validate_resume` 的比对逻辑
LOCAL_INTERRUPT_ID = "int-local-1"

# 强制确定性环境；键必须与 app/core/config.py 的嵌套字段一致
LOCAL_ENV_OVERRIDES = {
    "APP_ENV": "dev",
    "DEBUG": "true",
    "STORAGE__BACKEND": "memory",
    "MODEL_RUNTIME__ENABLED": "false",
    "HITL__ENABLED": "false",
    "RAG__ENABLED": "false",
    "MCP__ENABLED": "false",
    "OPENUI__ENABLED": "false",
    "AGENT__MULTI_AGENT_ENABLED": "false",
    "RATE_LIMIT__CHAT_PER_MINUTE": "600",
}


def run_local_cases(cases: list[E2ECase]) -> list[CaseResult]:
    """在进程内跑完所有用例；鉴权用依赖覆盖，模型用确定性假图。"""
    _apply_local_env()

    from app.core.config import get_settings
    from app.core.security import CurrentUser, get_current_user
    from app.main import app
    from app.services import model_runtime

    settings = get_settings()
    # HITL 在 Settings 校验里只允许 postgres；local 模式为验证恢复协议临时放开。
    # 必须在 lifespan 启动之后再改：checkpointer 已按启动时配置初始化，若提前改成
    # postgres，启动阶段会去连真实库（Windows 下还会撞 ProactorEventLoop）。
    needs_hitl = any(case.resume is not None for case in cases)
    original_hitl = (settings.hitl.enabled, settings.storage.backend)

    holder: dict[str, _ScriptedGraph | None] = {"graph": None}
    original_factory = model_runtime._default_graph
    model_runtime._default_graph = _graph_factory(holder)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=_local_user_id(), roles=("USER",)
    )
    try:
        with TestClient(app) as client:
            if needs_hitl:
                settings.hitl.enabled = True
                settings.storage.backend = "postgres"
            return [_run_local_case(client, case, holder) for case in cases]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        model_runtime._default_graph = original_factory
        settings.hitl.enabled, settings.storage.backend = original_hitl


def _apply_local_env() -> None:
    for key, value in LOCAL_ENV_OVERRIDES.items():
        os.environ[key] = value


def _local_user_id() -> str:
    # 延迟导入：get_settings 必须在环境变量覆盖之后才构建
    from app.core.config import get_settings

    return get_settings().evals.user_id


def _graph_factory(
    holder: dict[str, _ScriptedGraph | None],
) -> Any:
    """返回替换 `_default_graph` 的工厂；图实例由每个用例在执行前写入 holder。"""

    def factory(profile: Any, checkpointer: Any = None) -> CompiledStateGraph:
        del profile, checkpointer
        return cast("CompiledStateGraph", holder["graph"])

    return factory


class _ScriptedGraph:
    """确定性假图：产出工具事件、最终正文与可选 build_result。

    必须实现 `astream` 与 `aget_state`：回合编排先用前者的 updates 生成事件，
    再用后者读取最终状态完成落库与 `done` 组装。
    """

    def __init__(
        self,
        script: E2ELocalScript,
        message: str,
        *,
        emit_build: bool,
    ) -> None:
        self._script = script
        self._message = message
        self._build = _fake_build() if emit_build else None
        # 只在首轮、且用例声明了 interrupt 时暂停；收到 Command 即视为恢复
        self._pending_interrupt = script.interrupt is not None

    async def astream(
        self, inputs: Any, config: Any, stream_mode: Any = None
    ) -> AsyncIterator[tuple[str, Any]]:
        del config, stream_mode
        if isinstance(inputs, Command):
            self._pending_interrupt = False
        elif self._pending_interrupt:
            yield "updates", {
                "__interrupt__": [
                    SimpleNamespace(id=LOCAL_INTERRUPT_ID, value=self._script.interrupt)
                ]
            }
            return
        if self._script.tool_names:
            yield "updates", {"candidate_retriever": {"tool_events": self._tool_events()}}
        yield "updates", {
            "response_generator": {
                "messages": [AIMessage(content=self._script.answer, id="local-answer")]
            }
        }

    async def aget_state(self, config: Any) -> Any:
        del config
        if self._pending_interrupt:
            # 恢复校验要求 interrupts 与 created_at；假图用 None 表示未超时
            return SimpleNamespace(
                values={"messages": [HumanMessage(content=self._message, id="local-question")]},
                interrupts=[
                    SimpleNamespace(id=LOCAL_INTERRUPT_ID, value=self._script.interrupt)
                ],
                created_at=None,
            )
        return SimpleNamespace(values=self._values(), interrupts=[], created_at=None)

    def _tool_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for name in self._script.tool_names:
            events.append({"phase": "start", "name": name, "args": {}})
            events.append(
                {"phase": "end", "name": name, "preview": LOCAL_TOOL_PREVIEW}
            )
        return events

    def _values(self) -> dict[str, Any]:
        return {
            "messages": [
                HumanMessage(content=self._message, id="local-question"),
                AIMessage(content=self._script.answer, id="local-answer"),
            ],
            "workflow_status": "success" if self._build is not None else "clarification",
            "build_result": self._build,
            "reason_summary": LOCAL_REASON_SUMMARY,
        }


def _fake_build() -> dict[str, Any]:
    """构造 Java 形状的合法配置：八类齐全、分项合计等于总价、兼容性 PASS。"""
    from app.agent.pc.schemas import REQUIRED_CATEGORIES

    components: list[dict[str, Any]] = []
    for category in REQUIRED_CATEGORIES:
        name = category.value
        components.append(
            {
                "category": name,
                "hardwareId": f"local-{name.lower()}",
                "modelName": f"演示{name}",
                "brand": "本地演示",
                "title": f"本地演示 {name}",
                "platform": "JD",
                "seller": "本地演示店",
                "priceSource": "MOCK_DEMO",
                "specSummary": "本地契约模式占位规格",
                "priceFen": 80000,
                "purchaseUrl": "https://example.com/local-demo",
                "benchmarkType": "DEMO",
                "benchmarkScore": 100,
            }
        )
    total = sum(item["priceFen"] for item in components)
    return {
        "buildId": "local-build",
        "components": components,
        "totalPriceFen": total,
        "budgetMaxFen": total,
        "budgetStatus": "WITHIN_BUDGET",
        "compatibilityReport": {
            "overallStatus": "PASS",
            "checks": [
                {
                    "ruleId": "local-demo",
                    "ruleName": "本地演示规则",
                    "status": "PASS",
                    "message": "本地契约模式固定返回 PASS",
                    "riskLevel": "INFO",
                }
            ],
        },
        "requirements": {"workloadProfile": "GAMING", "scoringVersion": "local"},
    }


def _run_local_case(
    client: TestClient,
    case: E2ECase,
    holder: dict[str, _ScriptedGraph | None],
) -> CaseResult:
    started_at = perf_counter()
    thread_id = thread_id_for(case)
    emit_build = (
        case.local.build_result
        if case.local.build_result is not None
        else case.expect.expect_build_result
    )
    holder["graph"] = _ScriptedGraph(case.local, case.message, emit_build=emit_build)

    checks: list[CheckResult] = []
    error: str | None = None
    latency_ms = 0
    try:
        response = client.post(CHAT_PATH, json=chat_payload(case, thread_id))
        latency_ms = elapsed_ms(started_at)
        if response.status_code != HTTP_OK:
            checks.append(
                CheckResult(
                    "http_status",
                    STATUS_FAILED,
                    f"HTTP {response.status_code} {error_code(response.text)}".strip(),
                )
            )
        else:
            first_checks, events = _stream_checks(case, response.text, latency_ms)
            checks.extend(first_checks)
            if case.resume is not None:
                resume_checks, resumed_done = _run_local_resume(
                    client, case, thread_id, events
                )
                checks.extend(resume_checks)
                if resumed_done:
                    checks.extend(_local_session_checks(client, thread_id))
            elif ends_with_done(events):
                checks.extend(_local_session_checks(client, thread_id))
    except Exception as exc:  # 进程内异常不应中断整轮评测
        error = f"{type(exc).__name__}: {exc}"
        latency_ms = elapsed_ms(started_at)
    finally:
        cleanup_session(lambda tid: _delete_session(client, tid), thread_id, checks)

    return build_case_result(case, checks, latency_ms, error=error)


def _run_local_resume(
    client: TestClient,
    case: E2ECase,
    thread_id: str,
    events: list[SseEvent],
) -> tuple[list[CheckResult], bool]:
    """首轮中断后提交恢复；与 service 模式共用断言，差别只在传输层。"""
    pending = interrupt_id(events)
    if pending is None:
        return [
            CheckResult("resume", STATUS_FAILED, "首轮未给出 interrupt_id，无法恢复")
        ], False

    started_at = perf_counter()
    response = client.post(CHAT_PATH, json=resume_payload(case, thread_id, pending))
    latency_ms = elapsed_ms(started_at)
    if response.status_code != HTTP_OK:
        return [
            CheckResult(
                "http_status_resume",
                STATUS_FAILED,
                f"HTTP {response.status_code} {error_code(response.text)}".strip(),
            )
        ], False
    resume_checks, resume_events = _stream_checks(
        case, response.text, latency_ms, expectation=resume_expectation(case)
    )
    return resume_checks, ends_with_done(resume_events)


def _local_session_checks(client: TestClient, thread_id: str) -> list[CheckResult]:
    return session_checks(
        lambda: _get_json(client, f"{SESSIONS_PATH}/{thread_id}/messages"),
        lambda: _get_json(client, SESSIONS_PATH, params={"size": MAX_SESSION_PAGE_SIZE}),
        thread_id,
    )


def _stream_checks(
    case: E2ECase,
    text: str,
    latency_ms: int,
    *,
    expectation: E2EExpectation | None = None,
) -> tuple[list[CheckResult], list[SseEvent]]:
    frames = list(parse_frames(text.splitlines()))
    return check_stream(case, frames, latency_ms, expectation=expectation)


def _get_json(
    client: TestClient, path: str, **kwargs: Any
) -> dict[str, Any]:
    response = client.get(path, **kwargs)
    if response.status_code != HTTP_OK:
        raise E2EClientError(f"{path} 返回 HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise E2EClientError(f"{path} 响应不是 JSON 对象")
    return payload


def _delete_session(client: TestClient, thread_id: str) -> bool:
    response = client.delete(f"{SESSIONS_PATH}/{thread_id}")
    return response.status_code in (HTTP_NO_CONTENT, HTTP_NOT_FOUND)
