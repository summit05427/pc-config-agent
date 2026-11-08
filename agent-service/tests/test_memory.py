"""记忆策略接口：摘要生成、失败回退与长期记忆空实现。"""

from collections.abc import Sequence
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.constants import TAG_NOSTREAM

from app.agent import graph as graph_module
from app.agent.context import estimate_messages_tokens
from app.agent.memory import (
    SUMMARY_MARKER,
    LlmSummarizer,
    NoopMemory,
    NoopSummarizer,
    summarize_history,
)


class _FakeSummarizer:
    """按需返回固定摘要或抛错，用于验证回退路径。"""

    def __init__(
        self,
        summary: str | None = "早期对话的要点",
        error: Exception | None = None,
    ) -> None:
        self.summary = summary
        self.error = error
        self.calls: list[Sequence[object]] = []

    async def summarize(
        self,
        messages: Sequence[object],
        *,
        max_tokens: int,
    ) -> str | None:
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.summary


class _FakeModel:
    """最小可用的聊天模型替身：记录调用并按配置返回内容。"""

    def __init__(self, content: str | None = "摘要", error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls: list[Sequence[object]] = []
        self.configs: list[dict[str, object] | None] = []

    async def ainvoke(
        self,
        messages: Sequence[object],
        config: dict[str, object] | None = None,
    ) -> AIMessage:
        self.calls.append(messages)
        self.configs.append(config)
        if self.error is not None:
            raise self.error
        return AIMessage(content=self.content or "")


async def test_noop_summarizer_returns_none() -> None:
    summarizer = NoopSummarizer()

    assert await summarizer.summarize([HumanMessage("你好")], max_tokens=10) is None


async def test_noop_memory_is_inert() -> None:
    memory = NoopMemory()

    assert await memory.recall(user_id="u1", query="偏好") == []
    assert await memory.remember(user_id="u1", text="忽略") is None


async def test_summarize_history_replaces_older_messages_with_marked_system_message() -> None:
    messages = [
        HumanMessage("第一轮问题"),
        AIMessage("第一轮回答"),
        HumanMessage("第二轮问题"),
    ]
    summarizer = _FakeSummarizer("用户先问了个问题，助手已回复")

    result = await summarize_history(
        messages,
        keep_tokens=max(1, estimate_messages_tokens([messages[-1]])),
        summarizer=summarizer,
        max_summary_tokens=100,
    )

    assert len(summarizer.calls) == 1
    assert isinstance(result[0], SystemMessage)
    assert result[0].content.startswith(SUMMARY_MARKER)
    assert result[1:] == [messages[-1]]


async def test_summarize_history_returns_original_when_summary_is_empty() -> None:
    messages = [HumanMessage("旧问题"), HumanMessage("新问题")]
    summarizer = _FakeSummarizer(summary=None)

    result = await summarize_history(
        messages,
        keep_tokens=1,
        summarizer=summarizer,
        max_summary_tokens=100,
    )

    assert result == messages


async def test_summarize_history_returns_original_when_nothing_to_summarize() -> None:
    messages = [HumanMessage("只有一轮")]
    summarizer = _FakeSummarizer()

    result = await summarize_history(
        messages,
        keep_tokens=10_000,
        summarizer=summarizer,
        max_summary_tokens=100,
    )

    assert result == messages
    assert summarizer.calls == []


async def test_summarize_history_rejects_invalid_keep_budget() -> None:
    with pytest.raises(ValueError, match="保留预算"):
        await summarize_history(
            [HumanMessage("你好")],
            keep_tokens=0,
            summarizer=_FakeSummarizer(),
            max_summary_tokens=100,
        )


async def test_summarize_history_keeps_tool_pairs_out_of_recent_window() -> None:
    """最近窗口只能从完整消息单元开始，不能出现调用已丢失的孤儿 ToolMessage。"""
    ai_with_tool = AIMessage(
        content="",
        tool_calls=[{"name": "get_current_time", "args": {}, "id": "call-1"}],
    )
    messages = [
        HumanMessage("旧问题"),
        ai_with_tool,
        ToolMessage(content="工具结果", tool_call_id="call-1"),
        HumanMessage("新问题"),
    ]

    result = await summarize_history(
        messages,
        keep_tokens=max(1, estimate_messages_tokens([messages[-1]])),
        summarizer=_FakeSummarizer(),
        max_summary_tokens=100,
    )

    assert isinstance(result[0], SystemMessage)
    assert [type(message) for message in result[1:]] == [HumanMessage]


async def test_llm_summarizer_uses_model_and_returns_text() -> None:
    model = _FakeModel("用户目标：排查登录失败")
    summarizer = LlmSummarizer(model)  # type: ignore[arg-type]

    summary = await summarizer.summarize([HumanMessage("登录报错了")], max_tokens=100)

    assert summary == "用户目标：排查登录失败"
    assert len(model.calls) == 1


async def test_llm_summarizer_marks_call_as_nostream() -> None:
    """摘要调用必须带 nostream 标签，否则摘要 token 会混进 SSE 正文。"""
    model = _FakeModel("摘要文本")
    summarizer = LlmSummarizer(model)  # type: ignore[arg-type]

    await summarizer.summarize([HumanMessage("问题")], max_tokens=100)

    assert model.configs[0] is not None
    assert TAG_NOSTREAM in model.configs[0]["tags"]  # type: ignore[operator]


async def test_llm_summarizer_truncates_long_summary() -> None:
    model = _FakeModel("很长" * 200)
    summarizer = LlmSummarizer(model)  # type: ignore[arg-type]

    summary = await summarizer.summarize([HumanMessage("问题")], max_tokens=5)

    assert summary is not None
    assert estimate_messages_tokens([SystemMessage(content=summary)]) <= 20


async def test_llm_summarizer_returns_none_on_model_error() -> None:
    model = _FakeModel(error=RuntimeError("上游失败"))
    summarizer = LlmSummarizer(model)  # type: ignore[arg-type]

    assert await summarizer.summarize([HumanMessage("问题")], max_tokens=100) is None


async def test_llm_summarizer_returns_none_on_empty_reply() -> None:
    model = _FakeModel(content="")
    summarizer = LlmSummarizer(model)  # type: ignore[arg-type]

    assert await summarizer.summarize([HumanMessage("问题")], max_tokens=100) is None


async def test_llm_summarizer_returns_none_for_empty_messages() -> None:
    model = _FakeModel()
    summarizer = LlmSummarizer(model)  # type: ignore[arg-type]

    assert await summarizer.summarize([], max_tokens=100) is None
    assert model.calls == []


async def test_prepare_model_input_summarizes_above_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        graph_module,
        "get_settings",
        lambda: SimpleNamespace(
            agent=SimpleNamespace(summary_trigger_tokens=1000),
        ),
    )
    # 早期消息足够长，才会超出阈值并被挤出保留窗口
    state = {
        "messages": [
            HumanMessage("第一轮问题" * 400),
            AIMessage("第一轮回答" * 400),
            HumanMessage("第二轮问题"),
        ]
    }
    summarizer = _FakeSummarizer("早期目标：了解项目结构")

    result = await graph_module._prepare_model_input(
        state, "系统提示词", 4000, summarizer  # type: ignore[arg-type]
    )

    assert len(summarizer.calls) == 1
    assert any(
        isinstance(message, SystemMessage)
        and str(message.content).startswith(SUMMARY_MARKER)
        for message in result
    )
    assert result[-1] == state["messages"][-1]


async def test_prepare_model_input_skips_summary_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        graph_module,
        "get_settings",
        lambda: SimpleNamespace(
            agent=SimpleNamespace(summary_trigger_tokens=10),
        ),
    )
    state = {"messages": [HumanMessage("只有本轮")]}

    result = await graph_module._prepare_model_input(
        state, "系统提示词", 4000, None
    )

    assert result[-1] == state["messages"][0]
    assert all(
        not (isinstance(message, SystemMessage) and SUMMARY_MARKER in str(message.content))
        for message in result
    )
