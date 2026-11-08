"""回合模块测试：事件翻译、落库顺序与上下文归位，不经过 HTTP 层。"""

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)

from app.agent.hooks import (
    HookBlockedError,
    HookContext,
    HookPoint,
    register_hook,
    reset_hooks,
)
from app.agent.preferences import ChatPreferences
from app.agent.tool_context import get_current_tool_turn
from app.services import turn as turn_module
from app.services.turn import TurnOutcome, TurnRequest, run_turn


class _ToolGraph:
    """依次产出工具调用、工具结果与正文，并暴露最终状态。"""

    def __init__(self) -> None:
        self.config: dict[str, Any] | None = None

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        self.config = config
        tool_calls = [{"name": "get_current_time", "args": {"tz": "UTC"}, "id": "c1"}]
        yield "updates", {"model": {"messages": [AIMessage(content="", tool_calls=tool_calls)]}}
        yield (
            "updates",
            {
                "tools": {
                    "messages": [
                        ToolMessage(content="2026-10-24 12:00", tool_call_id="c1", name="clock")
                    ]
                }
            },
        )
        yield "messages", (AIMessageChunk(content="现在是 12 点"), {})

    async def aget_state(self, config: Any) -> Any:
        return SimpleNamespace(
            values={"messages": [HumanMessage(content="现在几点？"), AIMessage(content="回复")]}
        )


class _RecordingGraph:
    """记录传给图的状态，用于验证偏好透传。"""

    def __init__(self) -> None:
        self.inputs: dict[str, Any] | None = None

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        self.inputs = inputs
        yield "messages", (AIMessageChunk(content="收到"), {})

    async def aget_state(self, config: Any) -> Any:
        return SimpleNamespace(values={})


class _RegenerateGraph(_RecordingGraph):
    """带历史回答的图，用于验证重新生成会移除最后一条 AI 消息。"""

    async def aget_state(self, config: Any) -> Any:
        return SimpleNamespace(
            values={
                "messages": [
                    HumanMessage(content="现在几点？", id="human-1"),
                    AIMessage(content="上一次回答", id="ai-1"),
                ]
            }
        )


class _EmptyHistoryGraph(_RecordingGraph):
    """没有可替换回答时降级为普通回合。"""


class _BrokenGraph:
    """生成过程中抛错。"""

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        raise RuntimeError("模型网关超时")
        yield  # pragma: no cover


class _BufferedGraph:
    """先流出 token 再返回节点更新，用于验证阻断钩子放行后的缓冲释放。"""

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        yield "messages", (AIMessageChunk(content="你好"), {})
        yield "updates", {"model": {"messages": [AIMessage(content="你好")]}}

    async def aget_state(self, config: Any) -> Any:
        return SimpleNamespace(values={})


class _ReasoningGraph(_RecordingGraph):
    """先流思考内容再流正文，用于验证 reasoning 与 token 分离及缓冲顺序。"""

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        yield "messages", (
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "先分析"}),
            {},
        )
        yield "messages", (AIMessageChunk(content="答案"), {})
        yield "updates", {"model": {"messages": [AIMessage(content="答案")]}}


class _FakeStore:
    """记录落库调用，不依赖真实数据库。"""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self._error = error

    async def record_turn(
        self,
        user_id: str,
        thread_id: str,
        messages: Any,
        title: str | None,
        replace_existing: bool = False,
    ) -> None:
        if self._error is not None:
            raise self._error
        self.calls.append((user_id, thread_id, title))
        self.replace_existing = replace_existing


def _request(graph: Any, **overrides: Any) -> TurnRequest:
    values: dict[str, Any] = {
        "user_id": "u1",
        "user_roles": ("USER",),
        "client_thread_id": "t1",
        "checkpoint_thread_id": "u1:t1",
        "message": "现在几点？",
        "agent_id": None,
        "preferences": None,
        "graph": graph,
    }
    values.update(overrides)
    return TurnRequest(**values)


@pytest.fixture(autouse=True)
def _bind_fake_store(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    """回合落库统一走假 store，避免测试写进进程级内存适配器。"""
    store = _FakeStore()
    monkeypatch.setattr(turn_module, "get_session_store", lambda: store)
    return store


async def test_run_turn_translates_events_and_persists_before_done(
    _bind_fake_store: _FakeStore,
) -> None:
    """工具事件与正文按发生顺序产出，且 done 之前已完成落库。"""
    graph = _ToolGraph()
    outcome = TurnOutcome()
    event_types: list[str] = []

    async for event in run_turn(_request(graph), outcome):
        if event.type == "done":
            # 前端收到 done 后会立即查询历史，落库必须已经完成
            assert _bind_fake_store.calls
        event_types.append(event.type)

    assert event_types == ["tool_call", "tool_result", "token", "done"]
    assert _bind_fake_store.calls == [("u1", "t1", "现在几点？")]
    assert outcome.completed is True
    # 运行时与递归上限随 configurable 传给图，thread_id 用服务端命名空间
    assert graph.config is not None
    assert graph.config["configurable"]["thread_id"] == "u1:t1"


async def test_run_turn_passes_preferences_into_agent_state() -> None:
    """偏好渲染成提示词片段，use_history 随本轮状态显式传入。"""
    graph = _RecordingGraph()
    preferences = ChatPreferences(instructions="回答尽量简短", use_history=False)

    events = [
        event
        async for event in run_turn(
            _request(graph, preferences=preferences),
            TurnOutcome(),
        )
    ]

    assert [event.type for event in events] == ["token", "done"]
    assert graph.inputs is not None
    assert graph.inputs["use_history"] is False
    assert "回答尽量简短" in graph.inputs["preference_prompt"]


async def test_run_turn_regenerate_removes_last_answer(
    _bind_fake_store: _FakeStore,
) -> None:
    """重新生成只移除最后一条 AI 回答，并让落库走覆盖写入。"""
    graph = _RegenerateGraph()

    events = [event async for event in run_turn(_request(graph, regenerate=True), TurnOutcome())]

    assert [event.type for event in events] == ["token", "done"]
    assert graph.inputs is not None
    (regenerate_input,) = graph.inputs["messages"]
    assert isinstance(regenerate_input, RemoveMessage)
    assert regenerate_input.id == "ai-1"
    assert _bind_fake_store.replace_existing is True


async def test_run_turn_regenerate_falls_back_without_history() -> None:
    """没有可替换回答时退回普通回合，不阻断对话。"""
    graph = _EmptyHistoryGraph()

    events = [event async for event in run_turn(_request(graph, regenerate=True), TurnOutcome())]

    assert [event.type for event in events] == ["token", "done"]
    assert graph.inputs is not None
    (message,) = graph.inputs["messages"]
    assert isinstance(message, HumanMessage)
    assert message.content == "现在几点？"


async def test_run_turn_marks_failure_and_resets_tool_context() -> None:
    """异常透传给传输层，但本轮不得标记完成，工具上下文必须复位。"""
    outcome = TurnOutcome()

    with pytest.raises(RuntimeError):
        async for _ in run_turn(_request(_BrokenGraph()), outcome):
            pass

    assert outcome.completed is False
    assert get_current_tool_turn() is None


async def test_run_turn_keeps_streaming_when_persist_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """落库是旁路：失败只降级为无历史，不影响本轮 done。"""
    failing_store = _FakeStore(error=RuntimeError("数据库不可用"))
    monkeypatch.setattr(turn_module, "get_session_store", lambda: failing_store)
    outcome = TurnOutcome()

    events = [event async for event in run_turn(_request(_RecordingGraph()), outcome)]

    assert [event.type for event in events] == ["token", "done"]
    assert outcome.completed is True


async def test_run_turn_releases_buffered_tokens_after_model_update() -> None:
    """阻断型 after_model 钩子通过后，缓冲文本才在节点返回时放行。"""

    async def pass_guard(_: HookContext) -> None:
        return None

    reset_hooks()
    register_hook(HookPoint.AFTER_MODEL, blocking=True, name="test.pass")(pass_guard)
    try:
        events = [
            event
            async for event in run_turn(_request(_BufferedGraph()), TurnOutcome())
        ]
    finally:
        reset_hooks()

    assert [event.type for event in events] == ["token", "done"]
    assert events[0].data == {"text": "你好"}


async def test_run_turn_emits_reasoning_before_token() -> None:
    """思考内容以独立 reasoning 事件下发，不能混进正文。"""
    events = [event async for event in run_turn(_request(_ReasoningGraph()), TurnOutcome())]

    assert [event.type for event in events] == ["reasoning", "token", "done"]
    assert events[0].data == {"text": "先分析"}
    assert events[1].data == {"text": "答案"}


async def test_reasoning_is_buffered_with_tokens() -> None:
    """阻断型钩子未通过前，思考内容同样不能提前放行，且顺序保持不变。"""

    async def pass_guard(_: HookContext) -> None:
        return None

    reset_hooks()
    register_hook(HookPoint.AFTER_MODEL, blocking=True, name="test.pass")(pass_guard)
    try:
        events = [
            event async for event in run_turn(_request(_ReasoningGraph()), TurnOutcome())
        ]
    finally:
        reset_hooks()

    assert [event.type for event in events] == ["reasoning", "token", "done"]


async def test_run_turn_ignores_blocked_stream_end_hook() -> None:
    """流结束钩子只做观测：阻断信号不得影响 done 与工具上下文复位。"""

    async def block(_: HookContext) -> None:
        raise HookBlockedError("结束钩子拒绝")

    reset_hooks()
    register_hook(HookPoint.ON_STREAM_END, blocking=True, name="test.block_end")(block)
    try:
        events = [event async for event in run_turn(_request(_RecordingGraph()), TurnOutcome())]
    finally:
        reset_hooks()

    assert [event.type for event in events] == ["token", "done"]
    assert get_current_tool_turn() is None
