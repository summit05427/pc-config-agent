"""上下文窗口裁剪测试：预算内保留、超预算从旧到新丢弃、工具调用不被拆散。"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.context import (
    estimate_messages_tokens,
    select_current_turn,
    trim_to_token_budget,
)


def _tool_call(message_id: str = "call-1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_current_time",
                "args": {"timezone": "UTC"},
                "id": message_id,
                "type": "tool_call",
            }
        ],
    )


def test_messages_fit_within_budget_are_kept() -> None:
    messages = [HumanMessage("你好"), AIMessage("你好，有什么可以帮你？")]

    kept = trim_to_token_budget(messages, 1000)

    assert kept == messages


def test_oldest_messages_are_dropped_first() -> None:
    messages = [HumanMessage("旧" * 200), AIMessage("旧回复"), HumanMessage("新问题")]
    budget = estimate_messages_tokens(messages[-2:])

    kept = trim_to_token_budget(messages, budget)

    assert kept[-1].content == "新问题"
    assert len(kept) < len(messages)


def test_tool_call_pair_is_never_split() -> None:
    messages = [
        HumanMessage("旧" * 200),
        _tool_call(),
        ToolMessage(content="2026-10-25 10:00:00", tool_call_id="call-1", name="get_current_time"),
        HumanMessage("新问题"),
    ]

    kept = trim_to_token_budget(messages, 100)

    # 若只保留 ToolMessage 而没有对应的 AIMessage，模型将无法理解工具结果
    assert not isinstance(kept[0], ToolMessage)
    assert any(isinstance(message, ToolMessage) for message in kept)
    assert any(
        isinstance(message, AIMessage) and message.tool_calls for message in kept
    )


def test_leading_orphan_tool_message_is_dropped() -> None:
    messages = [
        ToolMessage(content="孤立结果", tool_call_id="missing", name="get_current_time"),
        HumanMessage("新问题"),
    ]

    kept = trim_to_token_budget(messages, 1000)

    assert kept == [messages[1]]


def test_last_message_is_kept_even_when_over_budget() -> None:
    messages = [HumanMessage("非常长的问题" * 500)]

    kept = trim_to_token_budget(messages, 1)

    assert kept == messages


def test_non_positive_budget_is_rejected() -> None:
    with pytest.raises(ValueError):
        trim_to_token_budget([HumanMessage("你好")], 0)


def test_select_current_turn_keeps_only_last_turn() -> None:
    """use_history=False 时只保留最后一条用户消息及其之后的工具调用与回答。"""
    messages = [
        HumanMessage("第一轮"),
        AIMessage("第一轮回复"),
        HumanMessage("第二轮"),
        _tool_call("call-2"),
        ToolMessage(content="工具结果", tool_call_id="call-2", name="get_current_time"),
    ]

    scoped = select_current_turn(messages)

    # 工具调用配对完整保留，否则模型看不懂工具结果
    assert scoped == messages[2:]


def test_select_current_turn_falls_back_to_last_message() -> None:
    """没有用户消息时只留最后一条，绝不回退到整段历史。"""
    messages = [AIMessage("旧回复"), ToolMessage(content="结果", tool_call_id="c1", name="tool")]

    assert select_current_turn(messages) == messages[-1:]

