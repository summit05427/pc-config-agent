"""SSE 对话接口测试：验证事件协议与流式拼装，不依赖真实模型。"""

import asyncio
import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import SecretStr
from redis.exceptions import ConnectionError as RedisConnectionError

from app.agent.pc.schemas import (
    REQUIRED_CATEGORIES,
    BuildProposal,
    BuildStrategy,
    SelectedComponent,
)
from app.api.v1 import chat as chat_module
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import CurrentUser, get_access_token, get_current_user
from app.main import app
from app.rag import Citation
from app.services import model_runtime as model_runtime_module
from app.services import turn as turn_module
from app.services.idempotency import STATUS_DONE, STATUS_PROCESSING, IdempotencyRecord
from app.services.model_resolver import ResolvedCredential, ResolvedRuntime


@pytest.fixture(autouse=True)
def _bypass_auth() -> Iterator[None]:
    """本模块只测流式协议，统一用假用户跳过鉴权（鉴权另有 test_auth.py 覆盖）。"""
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id="test-user")
    yield
    app.dependency_overrides.pop(get_current_user, None)


class FakeGraph:
    """产出 PC 流水线的工具事件与最终正文，用于验证 SSE 编码。"""

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        yield "updates", {
            "candidate_retriever": {
                "tool_events": [
                    {"phase": "start", "name": "get_current_time", "args": {"timezone": "UTC"}},
                    {
                        "phase": "end",
                        "name": "get_current_time",
                        "preview": "2026-10-24 12:00:00",
                    },
                ]
            }
        }
        yield "updates", {
            "response_generator": {"messages": [AIMessage(content="现在是 12 点")]}
        }


class AnswerGraph:
    """只产出最终正文的最小图替身。"""

    def __init__(self, answer: str) -> None:
        self.answer = answer

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        yield "updates", {
            "response_generator": {"messages": [AIMessage(content=self.answer)]}
        }


class HookBlockedGraph:
    """模拟输出审核阻断：节点返回前抛出 HookBlockedError。"""

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        from app.agent.hooks import HookContext, HookPoint, run_hooks

        await run_hooks(
            HookContext(
                point=HookPoint.AFTER_MODEL,
                thread_id=None,
                agent_id="pc-config",
                text="敏感内容",
            )
        )
        yield "updates", {
            "response_generator": {"messages": [AIMessage(content="敏感内容")]}
        }


class BrokenGraph:
    """模拟生成过程中抛异常。"""

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        raise RuntimeError("模型网关超时")
        yield  # pragma: no cover


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    """把 SSE 文本解析成 (event, data) 列表。"""
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        if not block:
            continue
        lines = block.splitlines()
        event = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        raw_data = next(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
        events.append((event, json.loads(raw_data)))
    return events


def test_stream_emits_tokens_and_done(client: TestClient, monkeypatch: Any) -> None:
    """最终正文应聚合成完整回复，并以 done 事件收尾。"""
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: AnswerGraph("你好，我是 Agent"))

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-stream"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    assert events[-1][0] == "done"
    assert "".join(data["text"] for event, data in events if event == "token") == "你好，我是 Agent"


def test_unknown_agent_id_returns_404_before_stream(client: TestClient) -> None:
    """未知 Profile 必须在建立流之前返回 404，不能下发 SSE error 事件。"""
    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-agent", "agent_id": "missing_agent"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "agent_not_found"


def test_stream_emits_tool_events(client: TestClient, monkeypatch: Any) -> None:
    """工具调用与结果应作为独立事件下发，便于前端展示执行过程。"""
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: FakeGraph())

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "现在几点？", "thread_id": "t-tool"},
    )

    events = _parse_sse(response.text)
    names = [event for event, _ in events]
    # 阶段事件用于推进指示器，工具顺序断言只看其余业务事件
    assert [name for name in names if name != "stage"] == [
        "tool_call",
        "tool_result",
        "token",
        "done",
    ]
    tool_call_payload = next(data for name, data in events if name == "tool_call")
    tool_result_payload = next(data for name, data in events if name == "tool_result")
    assert tool_call_payload["name"] == "get_current_time"
    assert tool_result_payload["preview"].startswith("2026-10-24")


class StubRetriever:
    """返回固定引用并记录检索请求，用于验证 RAG 接线。"""

    def __init__(self, citations: list[Citation]) -> None:
        self.citations = citations
        self.requests: list[Any] = []

    async def retrieve(self, request: Any) -> list[Citation]:
        self.requests.append(request)
        return self.citations


def test_stream_emits_citations_before_tokens(client: TestClient, monkeypatch: Any) -> None:
    """开启 RAG 时先下发引用再输出正文，引用不改变 done 收尾语义。"""
    retriever = StubRetriever(
        [Citation(source_id="kb-1", title="示例文档", snippet="示例片段", score=0.9)]
    )
    monkeypatch.setattr(turn_module, "get_retriever", lambda: retriever)
    monkeypatch.setattr(get_settings().rag, "enabled", True)
    monkeypatch.setattr(
        model_runtime_module,
        "get_agent",
        lambda: AnswerGraph("答案"),
    )

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "问题", "thread_id": "t-rag"},
    )

    events = _parse_sse(response.text)
    assert [event for event, _ in events][0] == "citations"
    assert events[0][1]["citations"][0]["source_id"] == "kb-1"
    assert events[-1][0] == "done"
    assert retriever.requests[0].user_id == "test-user"


def test_blocking_after_model_hook_hides_streamed_text(
    client: TestClient, monkeypatch: Any
) -> None:
    """阻断型输出审核生效时，模型文本必须在钩子通过后才下发。

    否则审核拒绝前内容已经流出，输出审核形同虚设。
    """
    from app.agent import hooks as hooks_module
    from app.agent.hooks import HookBlockedError, HookContext, HookPoint, register_hook

    async def guard(_: HookContext) -> None:
        raise HookBlockedError("输出命中审核规则")

    hooks_module.reset_hooks()
    register_hook(HookPoint.AFTER_MODEL, blocking=True, name="test.block")(guard)
    monkeypatch.setattr(
        model_runtime_module,
        "get_agent",
        lambda: HookBlockedGraph(),
    )

    try:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "问题", "thread_id": "t-hook-buffer"},
        )
        events = _parse_sse(response.text)

        assert [event for event, _ in events] == ["error"]
        assert events[0][1]["code"] == "agent_error"
    finally:
        hooks_module.reset_hooks()


def test_stream_reports_agent_error(client: TestClient, monkeypatch: Any) -> None:
    """生成失败时下发 error 事件，而不是让前端一直等待。"""
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: BrokenGraph())

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-error"},
    )

    events = _parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "agent_error"


def test_stream_requires_thread_id(client: TestClient) -> None:
    """缺少 thread_id 时走统一校验错误结构。"""
    response = client.post("/api/v1/chat/stream", json={"message": "你好"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_stream_events_carry_incremental_ids(client: TestClient, monkeypatch: Any) -> None:
    """事件 id 单调递增，便于前端排查乱序与丢帧。"""
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: FakeGraph())

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "现在几点？", "thread_id": "t-id"},
    )

    ids = [
        line.removeprefix("id: ")
        for line in response.text.splitlines()
        if line.startswith("id: ")
    ]
    assert ids == [str(index) for index in range(1, len(ids) + 1)]


class SlowGraph:
    """首次输出前故意停顿，用来触发心跳。"""

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        await asyncio.sleep(0.05)
        yield "messages", (AIMessageChunk(content="慢回复"), {})


def test_stream_emits_heartbeat_while_waiting(client: TestClient, monkeypatch: Any) -> None:
    """模型长时间无输出时应下发注释心跳，避免代理断开连接。"""
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: SlowGraph())
    monkeypatch.setattr(get_settings().agent, "sse_heartbeat_seconds", 0.01)

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-heartbeat"},
    )

    assert ": ping" in response.text


class FakeLockHandle:
    def __init__(self) -> None:
        self.is_released = False

    async def release(self) -> None:
        self.is_released = True


async def _fake_acquire_thread_lock(thread_id: str) -> FakeLockHandle:
    """隔离真实 Redis：锁行为本身由 test_locks.py 覆盖。"""
    return FakeLockHandle()


def _enable_redis(monkeypatch: Any) -> None:
    """打开 Redis 开关，同时隔离锁与幂等键，避免测试触碰真实连接。"""
    monkeypatch.setattr(chat_module, "is_redis_enabled", lambda: True)
    monkeypatch.setattr(chat_module, "acquire_thread_lock", _fake_acquire_thread_lock)


def test_stream_acquires_and_releases_thread_lock(client: TestClient, monkeypatch: Any) -> None:
    """同一会话必须先拿到锁，并在流结束后释放。"""
    handle = FakeLockHandle()
    captured: dict[str, str] = {}

    async def fake_acquire(thread_id: str) -> FakeLockHandle:
        captured["thread_id"] = thread_id
        return handle

    monkeypatch.setattr(chat_module, "acquire_thread_lock", fake_acquire)
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: FakeGraph())

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-lock"},
    )

    assert response.status_code == 200
    assert captured["thread_id"] == "test-user:t-lock"
    assert handle.is_released is True


def test_stream_rejects_duplicate_completed_request(client: TestClient, monkeypatch: Any) -> None:
    """已完成过的同一幂等键再次提交时应 409，避免重复调用模型。"""
    _enable_redis(monkeypatch)

    async def fake_begin(key: str) -> bool:
        return False

    async def fake_read(key: str) -> IdempotencyRecord:
        return IdempotencyRecord(status=STATUS_DONE, result={"thread_id": "t-dup"})

    async def fail(*_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError("重复请求不应进入流式执行")

    monkeypatch.setattr(chat_module, "idempotency_begin", fake_begin)
    monkeypatch.setattr(chat_module, "idempotency_read", fake_read)
    monkeypatch.setattr(model_runtime_module, "get_agent", fail)

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-dup"},
        headers={"Idempotency-Key": "request-0001"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "duplicate_request"


def test_stream_rejects_request_in_progress(client: TestClient, monkeypatch: Any) -> None:
    """同一幂等键正在处理时应 409，提示调用方稍后重试。"""
    _enable_redis(monkeypatch)

    async def fake_begin(key: str) -> bool:
        return False

    async def fake_read(key: str) -> IdempotencyRecord:
        return IdempotencyRecord(status=STATUS_PROCESSING)

    monkeypatch.setattr(chat_module, "idempotency_begin", fake_begin)
    monkeypatch.setattr(chat_module, "idempotency_read", fake_read)

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-busy"},
        headers={"Idempotency-Key": "request-0002"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "request_in_progress"


def test_stream_degrades_idempotency_when_redis_down(
    client: TestClient, monkeypatch: Any
) -> None:
    """幂等记录写不进去时应放行本次对话，而不是整条请求失败。"""
    _enable_redis(monkeypatch)

    async def failing_begin(key: str) -> bool:
        raise RedisConnectionError("redis down")

    monkeypatch.setattr(chat_module, "idempotency_begin", failing_begin)
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: FakeGraph())

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-redis-down"},
        headers={"Idempotency-Key": "request-0004"},
    )

    assert response.status_code == 200
    assert _parse_sse(response.text)[-1][0] == "done"


def test_stream_finishes_idempotency_after_success(client: TestClient, monkeypatch: Any) -> None:
    """流正常结束时把幂等记录标记为 done，结果可供重放。"""
    _enable_redis(monkeypatch)
    captured: dict[str, Any] = {}

    async def fake_begin(key: str) -> bool:
        return True

    async def fake_finish(key: str, result: Any) -> None:
        captured["key"] = key
        captured["result"] = result

    monkeypatch.setattr(chat_module, "idempotency_begin", fake_begin)
    monkeypatch.setattr(chat_module, "idempotency_finish", fake_finish)
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: FakeGraph())

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-done"},
        headers={"Idempotency-Key": "request-0003"},
    )

    assert response.status_code == 200
    assert captured["key"].endswith("chat:test-user:request-0003")
    assert captured["result"] == {"thread_id": "t-done"}


def test_persists_messages_with_client_thread_id(
    client: TestClient, monkeypatch: Any
) -> None:
    """历史接口按客户端原始 thread_id 查询，落库必须写同一个值。

    checkpointer 用命名空间 ID（用户ID:会话ID），业务表只存客户端原始值；
    两者混用会让历史接口恒返回 404。
    """
    captured: dict[str, Any] = {}
    messages = [HumanMessage(content="你好"), AIMessage(content="回复")]

    class PersistFakeGraph:
        async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
            yield "messages", (AIMessageChunk(content="回复"), {})

        async def aget_state(self, config: Any) -> Any:
            captured["checkpoint_thread_id"] = config["configurable"]["thread_id"]
            return SimpleNamespace(values={"messages": messages})

    class PersistFakeStore:
        async def record_turn(
            self,
            user_id: str,
            thread_id: str,
            stored: Any,
            title: str | None,
            replace_existing: bool = False,
            build_result: Any = None,
            citations: Any = None,
            had_reasoning: bool = False,
        ) -> None:
            captured["storage"] = (user_id, thread_id, stored)
            captured["meta"] = (user_id, thread_id, title)

    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: PersistFakeGraph())
    monkeypatch.setattr(turn_module, "get_session_store", lambda: PersistFakeStore())

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-persist"},
    )

    assert response.status_code == 200
    assert captured["checkpoint_thread_id"] == "test-user:t-persist"
    assert captured["storage"][:2] == ("test-user", "t-persist")
    # 标题取自首条用户消息，且与消息表使用同一个客户端原始 thread_id
    assert captured["meta"] == ("test-user", "t-persist", "你好")


def test_stream_aborts_idempotency_after_failure(client: TestClient, monkeypatch: Any) -> None:
    """生成失败时清理幂等记录，允许调用方立即重试。"""
    _enable_redis(monkeypatch)
    captured: dict[str, bool] = {"aborted": False}

    async def fake_begin(key: str) -> bool:
        return True

    async def fake_abort(key: str) -> None:
        captured["aborted"] = True

    monkeypatch.setattr(chat_module, "idempotency_begin", fake_begin)
    monkeypatch.setattr(chat_module, "idempotency_abort", fake_abort)
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: BrokenGraph())

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-abort"},
        headers={"Idempotency-Key": "request-0004"},
    )

    assert response.status_code == 200
    assert _parse_sse(response.text)[-1][0] == "error"
    assert captured["aborted"] is True


class RecordingGraph:
    """记录传给图的状态，用于验证偏好是否正确透传。"""

    def __init__(self) -> None:
        self.inputs: dict[str, Any] | None = None

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        self.inputs = inputs
        yield "messages", (AIMessageChunk(content="收到"), {})


def test_stream_passes_preferences_into_agent_state(
    client: TestClient, monkeypatch: Any
) -> None:
    """偏好应转成提示词片段与 use_history 标志，随本轮状态传入 Agent。"""
    graph = RecordingGraph()
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: graph)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "message": "你好",
            "thread_id": "t-preference",
            "preferences": {
                "instructions": "回答尽量简短",
                "reply_language": "zh-CN",
                "response_style": "concise",
                "use_history": False,
            },
        },
    )

    assert response.status_code == 200
    assert graph.inputs is not None
    assert graph.inputs["use_history"] is False
    prompt = graph.inputs["preference_prompt"]
    assert "回答尽量简短" in prompt
    assert "简体中文" in prompt
    assert isinstance(graph.inputs["messages"][0], HumanMessage)


def test_stream_resets_preferences_when_absent(client: TestClient, monkeypatch: Any) -> None:
    """未携带偏好时显式回到默认值，避免同一 thread 沿用上一轮的关闭历史。"""
    graph = RecordingGraph()
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: graph)

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-preference-default"},
    )

    assert response.status_code == 200
    assert graph.inputs is not None
    assert graph.inputs["use_history"] is True
    assert graph.inputs["preference_prompt"] is None


def test_stream_rejects_unknown_preference_values(client: TestClient) -> None:
    """偏好的枚举值非法时返回 422，并指出具体字段。"""
    response = client.post(
        "/api/v1/chat/stream",
        json={
            "message": "你好",
            "thread_id": "t-preference-invalid",
            "preferences": {"reply_language": "fr-FR"},
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert any("reply_language" in item["field"] for item in body["details"])


def _enable_model_runtime(monkeypatch: Any) -> None:
    """打开模型运行时并注入访问令牌，避免依赖真实 JWT。"""
    monkeypatch.setattr(get_settings().model_runtime, "enabled", True)
    monkeypatch.setitem(
        app.dependency_overrides, get_access_token, lambda: SecretStr("user-token")
    )


def test_stream_rejects_invalid_model_reference(client: TestClient) -> None:
    """模型引用必须是 `provider:model` 形式，非法字符在请求校验阶段就拒绝。"""
    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-model", "model": "OpenAI:GPT-4o"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_reasoning_flag_is_forwarded_to_agent_preparation(
    client: TestClient, monkeypatch: Any
) -> None:
    """请求体的 reasoning 必须原样交给准备阶段，由目录能力位统一门控。"""
    _enable_model_runtime(monkeypatch)
    calls: list[dict[str, Any]] = []

    async def fake_prepare(*_args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return SimpleNamespace(graph=FakeGraph(), runtime=None, user_token=None)

    monkeypatch.setattr(chat_module, "prepare_agent", fake_prepare)

    first = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-reasoning-on", "reasoning": True},
    )
    second = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-reasoning-default"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert [call["reasoning"] for call in calls] == [True, None]


def test_quota_exceeded_returns_bare_json_before_stream(
    client: TestClient, monkeypatch: Any
) -> None:
    """额度超限必须在流建立前返回裸 JSON，附带 quota 详情。"""
    _enable_model_runtime(monkeypatch)
    quota = {
        "quota_type": "daily_requests",
        "limit": 100,
        "used": 100,
        "reset_at": "2026-10-31T00:00:00Z",
    }

    async def raise_quota(**_kwargs: Any) -> ResolvedRuntime | None:
        raise AppError(
            "今日请求额度已用尽，请明日再试",
            code="quota_exceeded",
            status_code=429,
            extra={"quota": quota},
        )

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", raise_quota)

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-quota"},
    )

    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "quota_exceeded"
    assert body["quota"] == quota
    assert "request_id" in body
    assert response.headers["content-type"].startswith("application/json")


def test_control_plane_unavailable_degrades_and_stream_still_done(
    client: TestClient, monkeypatch: Any
) -> None:
    """控制面不可达时显式降级到默认模型，对话照常完成并下发 done。"""
    _enable_model_runtime(monkeypatch)

    async def degrade(**_kwargs: Any) -> ResolvedRuntime | None:
        return None

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", degrade)
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: FakeGraph())

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-degrade"},
    )

    assert response.status_code == 200
    assert _parse_sse(response.text)[-1][0] == "done"


def test_stream_requires_access_token_when_runtime_enabled(
    client: TestClient, monkeypatch: Any
) -> None:
    """开启模型运行时后缺少访问令牌，必须在流建立前返回 401。"""
    monkeypatch.setattr(get_settings().model_runtime, "enabled", True)
    monkeypatch.setitem(app.dependency_overrides, get_access_token, lambda: None)

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-no-token"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


class RuntimeCapturingGraph:
    """记录传给图的配置，用于断言运行时是否正确透传。"""

    def __init__(self) -> None:
        self.config: dict[str, Any] | None = None

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        self.config = config
        yield "messages", (AIMessageChunk(content="收到"), {})


def test_stream_passes_runtime_into_graph_config(
    client: TestClient, monkeypatch: Any
) -> None:
    """解析出的运行时随 configurable 传给图，而不是写进 AgentState。"""
    _enable_model_runtime(monkeypatch)
    runtime = ResolvedRuntime(
        task_id="task-1",
        provider="openai",
        model_key="openai:gpt-4o-mini",
        credential_source="MANAGED",
    )
    captured: dict[str, Any] = {}
    graph = RuntimeCapturingGraph()

    async def fake_resolve(**_kwargs: Any) -> ResolvedRuntime | None:
        return runtime

    def fake_get_agent_for_runtime(
        value: ResolvedRuntime | None, **_kwargs: Any
    ) -> RuntimeCapturingGraph:
        captured["runtime"] = value
        return graph

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fake_resolve)
    monkeypatch.setattr(model_runtime_module, "get_agent_for_runtime", fake_get_agent_for_runtime)

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-runtime"},
    )

    assert response.status_code == 200
    assert captured["runtime"] is runtime
    assert graph.config is not None
    assert graph.config["configurable"]["model_runtime"] is runtime
    assert _parse_sse(response.text)[-1][0] == "done"


class _PcStructured:
    """策略调用返回固定策略；选型调用返回完整八类提案。"""

    def __init__(self, schema: Any) -> None:
        self._schema = schema

    async def ainvoke(self, messages: Any, config: Any = None) -> Any:
        del messages, config
        if self._schema is BuildStrategy:
            parsed: Any = BuildStrategy(
                strategy_id="BALANCED", rationale_summary="按均衡策略组装。"
            )
        else:
            parsed = BuildProposal(
                selected_components=[
                    SelectedComponent(
                        category=category,
                        hardware_id=f"{category.value}-id",
                        reason_summary="覆盖需求",
                    )
                    for category in REQUIRED_CATEGORIES
                ]
            )
        return {"raw": AIMessage(content="{}"), "parsed": parsed, "parsing_error": None}


class _PcModel:
    """PC 流水线假模型：解析返回需求 JSON，策略/选型走结构化，正文走流式。"""

    def __init__(self) -> None:
        self._requirement = json.dumps(
            {
                "budget_max_fen": 800_000,
                "scenario": "GAMING",
                "scenario_explicit": True,
            }
        )

    async def ainvoke(self, messages: Any, config: Any = None) -> AIMessage:
        return AIMessage(content=self._requirement)

    def with_structured_output(self, schema: Any, *, include_raw: bool = False) -> Any:
        del include_raw
        return _PcStructured(schema)

    async def astream(self, messages: Any, config: Any = None, **_kwargs: Any) -> Any:
        """说明节点走流式调用；测试只关心最终正文与用量记录。"""
        yield AIMessageChunk(content="这套配置更偏向游戏性能。")


class _PcTool:
    def __init__(self, name: str, handler: Any) -> None:
        self.name = name
        self._handler = handler

    async def ainvoke(self, args: dict[str, Any]) -> str:
        return json.dumps(self._handler(args), ensure_ascii=False)


def _pc_components() -> list[dict[str, Any]]:
    categories = [
        "CPU",
        "MOTHERBOARD",
        "MEMORY",
        "GPU",
        "PSU",
        "CASE",
        "COOLER",
        "STORAGE",
    ]
    return [
        {
            "category": category,
            "hardwareId": f"{category}-id",
            "modelName": f"{category} 型号",
            "specSummary": "规格",
            "priceFen": 100_000,
            "priceSource": "VERIFIED",
            "purchaseUrl": "https://example.com/item",
            "verifiedAt": "2026-01-01T00:00:00Z",
        }
        for category in categories
    ]


def _pc_agent() -> Any:
    from app.agent.pc import nodes as nodes_module
    from app.agent.pc.graph import build_pc_graph
    from app.agent.profiles import resolve_profile

    build = {
        "buildId": "build-usage",
        "requirements": {"budgetMaxFen": 800_000, "scenario": "GAMING"},
        "components": _pc_components(),
        "totalPriceFen": 800_000,
        "budgetStatus": "WITHIN_BUDGET",
        "compatibilityReport": {"overallStatus": "PASS", "checks": []},
        "verifiedOfferCount": 8,
        "demoOfferCount": 0,
    }

    handlers = {
        "search_hardware_candidates": lambda args: {
            "catalogVersion": "catalog-1",
            "total": 1,
            "list": [{"hardwareId": f"{args['category']}-id"}],
        },
        "get_benchmark_data": lambda args: {
            "total": 1,
            "list": [{"benchmarkType": "PASSMARK", "score": 20000}],
        },
        "get_verified_offers": lambda args: {
            "dataStatus": "VERIFIED",
            "verifiedOfferCount": 8,
            "mockOfferCount": 0,
            "list": [],
        },
        "compose_pc_build": lambda args: {"composed": True, "build": build},
        "check_partial_compatibility": lambda args: {
            "overallStatus": "PASS",
            "checks": [],
        },
    }
    tools = {name: _PcTool(name, handler) for name, handler in handlers.items()}
    original = nodes_module.get_governed_tool
    _PC_TOOL_ORIGINAL.clear()
    _PC_TOOL_ORIGINAL.append(original)
    nodes_module.get_governed_tool = tools.get  # type: ignore[assignment]
    return build_pc_graph(
        model=_PcModel(),
        profile=resolve_profile("pc-config"),
        checkpointer=MemorySaver(),
    )


_PC_TOOL_ORIGINAL: list[Any] = []


def test_usage_record_is_captured_without_blocking_stream(
    client: TestClient, monkeypatch: Any
) -> None:
    """用量入队属于旁路统计，SSE 必须以 done 收尾。

    这里只捕获记录，不写真实 outbox：测试数据一旦落到共享 Postgres，
    会被后台投递成 dead 并污染本地指标与对账结果。
    """
    from app.agent.pc import nodes as nodes_module

    _enable_model_runtime(monkeypatch)
    runtime = ResolvedRuntime(
        task_id="task-usage",
        provider="openai",
        model_key="openai:gpt-4o-mini",
        credential_source="MANAGED",
    )
    agent = _pc_agent()
    records: list[Any] = []

    async def capture_usage(record: Any) -> None:
        records.append(record)

    async def fake_resolve(**_kwargs: Any) -> ResolvedRuntime | None:
        return runtime

    async def no_persist(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fake_resolve)
    monkeypatch.setattr(
        model_runtime_module, "get_agent_for_runtime", lambda _runtime, **_kwargs: agent
    )
    monkeypatch.setattr(turn_module, "_persist_turn", no_persist)
    monkeypatch.setattr("app.agent.pc.llm.record_usage", capture_usage)

    try:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "8000 元，打游戏", "thread_id": "t-usage"},
        )
    finally:
        if _PC_TOOL_ORIGINAL:
            nodes_module.get_governed_tool = _PC_TOOL_ORIGINAL[0]  # type: ignore[assignment]
            _PC_TOOL_ORIGINAL.clear()

    assert response.status_code == 200
    assert _parse_sse(response.text)[-1][0] == "done"
    # 解析、策略、选型与说明各调用一次模型，用量上报确实被触发
    assert len(records) == 4
    assert records[0]["task_id"] == "task-usage"


def _byok_runtime() -> ResolvedRuntime:
    return ResolvedRuntime(
        task_id="task-byok",
        provider="openai",
        model_key="openai:gpt-4o-mini",
        credential_source="BYOK",
        credential_id="cred-1",
        base_url="https://byok.example.com/v1",
    )


def test_byok_lease_failure_returns_unauthorized_before_stream(
    client: TestClient, monkeypatch: Any
) -> None:
    """凭证撤销后必须对流前返回 401，并清掉本地缓存的图与模型实例。"""
    _enable_model_runtime(monkeypatch)
    invalidated: list[str] = []

    async def fake_resolve(**_kwargs: Any) -> ResolvedRuntime | None:
        return _byok_runtime()

    async def raise_revoked(*_args: Any, **_kwargs: Any) -> ResolvedCredential | None:
        raise AppError("BYOK 凭证已撤销", code="credential_revoked", status_code=401)

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fake_resolve)
    monkeypatch.setattr(model_runtime_module, "resolve_credential", raise_revoked)
    monkeypatch.setattr(model_runtime_module, "invalidate_credential", invalidated.append)

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-byok-revoked"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "credential_revoked"
    assert invalidated == ["cred-1"]


def test_byok_credential_is_passed_to_graph_builder(
    client: TestClient, monkeypatch: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """兑换到的密钥与接入地址必须交给构图函数，而不是写进图配置或日志。"""
    caplog.set_level("INFO")
    _enable_model_runtime(monkeypatch)
    captured: dict[str, Any] = {}
    graph = RuntimeCapturingGraph()

    async def fake_resolve(**_kwargs: Any) -> ResolvedRuntime | None:
        return _byok_runtime()

    async def fake_lease(runtime: ResolvedRuntime, **_kwargs: Any) -> ResolvedCredential:
        return ResolvedCredential(api_key="sk-byok-secret", base_url=runtime.base_url)

    def fake_get_agent_for_runtime(
        runtime: ResolvedRuntime,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        **_profile_kwargs: Any,
    ) -> RuntimeCapturingGraph:
        captured.update({"runtime": runtime, "api_key": api_key, "base_url": base_url})
        return graph

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fake_resolve)
    monkeypatch.setattr(model_runtime_module, "resolve_credential", fake_lease)
    monkeypatch.setattr(model_runtime_module, "get_agent_for_runtime", fake_get_agent_for_runtime)

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "t-byok-ok"},
    )

    assert response.status_code == 200
    assert captured["api_key"] == "sk-byok-secret"
    assert captured["base_url"] == "https://byok.example.com/v1"
    assert _parse_sse(response.text)[-1][0] == "done"
    # 密钥只用于装配模型，不得进入图配置或日志
    assert graph.config is not None
    assert "sk-byok-secret" not in str(graph.config)
    assert "sk-byok-secret" not in caplog.text
