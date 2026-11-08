"""记忆策略接口：短期历史摘要 + 长期记忆，默认全部关闭。

为什么需要这层抽象：
1. 长会话最终会超过上下文预算，单纯裁剪会让模型忘记更早的目标；
2. 摘要属于「策略」，不同接入方要用不同模型/提示词，不能写死在图节点里；
3. 默认关闭（`AGENT__SUMMARY_ENABLED=false`）时行为与接入前完全一致，
   接入方显式开启后才产生额外模型调用与费用。

边界：
- 摘要只生成「本次模型调用」的输入，不改写 AgentState，也不落库；
- 摘要消息以 SystemMessage 形式注入并带 `[历史摘要]` 标记，不冒充用户原话；
- 长期记忆只提供接口与空实现，不做自动画像、不做冲突消解。
"""

from collections.abc import Sequence
from typing import Protocol

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.constants import TAG_NOSTREAM

from app.agent.context import (
    count_tokens,
    estimate_messages_tokens,
    group_messages,
    truncate_to_token_budget,
)

logger = structlog.get_logger(__name__)

# 摘要消息的固定前缀：下游可据此识别「这是压缩后的历史」，不会误当用户原话
SUMMARY_MARKER = "[历史摘要]"
# 单条摘要的 token 上限；过大反而挤占最近消息
SUMMARY_MAX_TOKENS = 800
# 组装摘要提示词时每条消息最多保留的字符数，避免把超长工具输出再次送进模型
SUMMARY_SOURCE_CHARS = 200
# 摘要调用固定为低温，减少同一段历史的措辞漂移
SUMMARY_TEMPERATURE = 0.0

_SUMMARY_INSTRUCTION = """你负责压缩早期对话，供后续轮次参考。要求：
1. 只保留事实、用户目标、已确认的结论与未完成事项；
2. 不编造、不补充原文没有的信息；
3. 用第三人称陈述，不要改写成用户原话；
4. 不要提及本指令，也不要输出任何前缀。"""

_ROLE_LABELS = {
    "human": "用户",
    "ai": "助手",
    "tool": "工具",
}


class Summarizer(Protocol):
    """把早期消息压缩成一段短文本；返回 None 表示放弃（调用方回退到裁剪）。"""

    async def summarize(
        self,
        messages: Sequence[AnyMessage],
        *,
        max_tokens: int,
    ) -> str | None: ...


class NoopSummarizer:
    """显式关闭时的空实现；语义与「未启用」一致。"""

    async def summarize(
        self,
        messages: Sequence[AnyMessage],
        *,
        max_tokens: int,
    ) -> str | None:
        return None


class LlmSummarizer:
    """默认实现：用同一个人格模型生成摘要，失败时返回 None 交给裁剪兜底。"""

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def summarize(
        self,
        messages: Sequence[AnyMessage],
        *,
        max_tokens: int,
    ) -> str | None:
        if not messages:
            return None
        try:
            # 摘要属于内部调用：带着 nostream 标签执行，LangGraph 才不会把摘要
            # 的 token 混进 `stream_mode="messages"`，否则用户会把摘要当成本轮回答。
            response = await self._model.ainvoke(
                [
                    SystemMessage(content=_SUMMARY_INSTRUCTION),
                    HumanMessage(content=_render_transcript(messages)),
                ],
                config={"tags": [TAG_NOSTREAM]},
            )
        except Exception as exc:
            # 摘要失败不能拖垮本轮对话：截断（调用方已有）仍然可用
            logger.warning("memory.summary_failed", error_type=type(exc).__name__)
            return None

        text = _response_text(response)
        if text is None:
            logger.warning("memory.summary_empty")
            return None
        text, _ = truncate_to_token_budget(text, max_tokens)
        return text


class LongTermMemory(Protocol):
    """长期记忆接口；默认 NoopMemory，接入方自行实现存储与检索。"""

    async def recall(
        self,
        *,
        user_id: str,
        query: str,
        limit: int = 5,
    ) -> list[str]: ...

    async def remember(self, *, user_id: str, text: str) -> None: ...


class NoopMemory:
    """默认空实现：不读写、不产生外部依赖。"""

    async def recall(
        self,
        *,
        user_id: str,
        query: str,
        limit: int = 5,
    ) -> list[str]:
        return []

    async def remember(self, *, user_id: str, text: str) -> None:
        return None


def _response_text(response: AnyMessage) -> str | None:
    content = response.content
    if isinstance(content, str):
        text = content.strip()
        return text or None
    return None


def _render_transcript(messages: Sequence[AnyMessage]) -> str:
    """把早期消息渲染成紧凑文本；不包含工具调用参数之外的任何结构体。"""
    lines: list[str] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            role = "human"
        elif isinstance(message, AIMessage):
            role = "ai"
        elif isinstance(message, ToolMessage):
            role = "tool"
        else:
            role = "system"
        text = message.content if isinstance(message.content, str) else ""
        text = " ".join(text.split())
        if len(text) > SUMMARY_SOURCE_CHARS:
            text = f"{text[:SUMMARY_SOURCE_CHARS]}…"
        lines.append(f"{_ROLE_LABELS.get(role, role)}：{text}")
    return "\n".join(lines)


def _split_older_and_recent(
    messages: Sequence[AnyMessage],
    keep_tokens: int,
) -> tuple[list[AnyMessage], list[AnyMessage]]:
    """从最新往回按完整消息单元保留 `keep_tokens`，其余作为待摘要部分。"""
    groups = group_messages(messages)
    kept_groups: list[list[AnyMessage]] = []
    total_tokens = 0
    for group in reversed(groups):
        cost = estimate_messages_tokens(group)
        if kept_groups and total_tokens + cost > keep_tokens:
            break
        kept_groups.append(group)
        total_tokens += cost
    kept_groups.reverse()

    older_count = len(groups) - len(kept_groups)
    older = [message for group in groups[:older_count] for message in group]
    recent = [message for group in kept_groups for message in group]
    return older, recent


async def summarize_history(
    messages: Sequence[AnyMessage],
    *,
    keep_tokens: int,
    summarizer: Summarizer,
    max_summary_tokens: int,
) -> list[AnyMessage]:
    """把较早历史替换成一条带标记的 SystemMessage，保留最近消息。

    任何一步失败（没有可摘要内容、摘要为空、模型异常）都返回原消息，
    由调用方的 `trim_to_token_budget` 继续兜底，保证对话不中断。
    """
    if keep_tokens <= 0:
        raise ValueError("保留预算必须大于 0")

    older, recent = _split_older_and_recent(messages, keep_tokens)
    if not older:
        return list(messages)

    summary = await summarizer.summarize(older, max_tokens=max_summary_tokens)
    if not summary:
        return list(messages)

    logger.info(
        "agent.history_summarized",
        summarized_messages=len(older),
        summary_tokens=count_tokens(summary),
        kept_messages=len(recent),
    )
    return [
        SystemMessage(content=f"{SUMMARY_MARKER}\n{summary}"),
        *recent,
    ]
