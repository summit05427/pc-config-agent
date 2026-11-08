"""对话上下文窗口管理。

为什么需要裁剪：
1. 模型有上下文上限，历史无限增长会直接报错，且费用随 token 线性上升；
2. 只按"条数"裁剪会破坏 tool_call 与 tool_result 的配对，导致模型无法理解历史；
3. 因此按「完整消息单元」从旧到新裁剪：一个单元要么全留，要么全丢。

token 估算优先用 tiktoken；离线环境取不到编码表时退化为字符数估算，
宁可保守一些，也不能因为分词器不可用就让对话失败。
"""

import json
from collections.abc import Sequence
from functools import lru_cache

import structlog
import tiktoken
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage

logger = structlog.get_logger(__name__)

# 与主流 OpenAI 兼容模型一致的分词表；不同模型略有差异，预算本身留有冗余
TOKENIZER_ENCODING = "cl100k_base"
# 取不到分词表时的粗略换算：英文约 4 字符 / token，中文会更保守
CHARS_PER_TOKEN_FALLBACK = 4
# 每条消息除正文外还有角色、分隔符等固定开销
MESSAGE_OVERHEAD_TOKENS = 4


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding | None:
    """加载分词表；失败只记录一次，后续走字符估算。"""
    try:
        return tiktoken.get_encoding(TOKENIZER_ENCODING)
    except Exception as exc:
        logger.warning("context.tokenizer_unavailable", error_type=type(exc).__name__)
        return None


def count_tokens(text: str) -> int:
    """估算文本 token 数，空文本也按 1 计，避免零成本消息无限堆积。"""
    encoding = _encoding()
    if encoding is None:
        return max(1, len(text) // CHARS_PER_TOKEN_FALLBACK)
    return max(1, len(encoding.encode(text)))


def truncate_to_token_budget(text: str, max_tokens: int) -> tuple[str, bool]:
    """把文本截到 token 预算内，返回 `(截断后文本, 是否发生截断)`。

    工具返回可能极大（如整页 HTML），必须先治理再交给模型：
    超出预算的部分直接丢弃，由调用方追加「已截断」提示。
    用二分查找定位最大可保留前缀，避免逐字符试算带来的额外开销。
    """
    if max_tokens <= 0:
        raise ValueError("输出预算必须大于 0")
    if count_tokens(text) <= max_tokens:
        return text, False

    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if count_tokens(text[:middle]) <= max_tokens:
            low = middle
        else:
            high = middle - 1
    return text[:low], True


def _has_tool_calls(message: AnyMessage) -> bool:
    """判断一条 AI 消息是否发起了工具调用。"""
    return isinstance(message, AIMessage) and bool(message.tool_calls)


def _message_text(message: AnyMessage) -> str:
    """把消息正文与工具调用参数拼成可计数的文本。"""
    content = message.content
    text = (
        content
        if isinstance(content, str)
        else json.dumps(content, ensure_ascii=False, default=str)
    )
    if isinstance(message, AIMessage) and message.tool_calls:
        # 参数同样占用上下文，漏算会导致裁剪后仍然超限
        text += json.dumps(message.tool_calls, ensure_ascii=False, default=str)
    return text


def _message_cost(message: AnyMessage) -> int:
    return MESSAGE_OVERHEAD_TOKENS + count_tokens(_message_text(message))


def estimate_messages_tokens(messages: Sequence[AnyMessage]) -> int:
    """估算一组消息的总 token 数，供日志与测试使用。"""
    return sum(_message_cost(message) for message in messages)


def group_messages(messages: Sequence[AnyMessage]) -> list[list[AnyMessage]]:
    """按「AI 工具调用 + 其结果」分组，保证配对关系不被拆散。"""
    groups: list[list[AnyMessage]] = []
    for message in messages:
        if (
            isinstance(message, ToolMessage)
            and groups
            and _has_tool_calls(groups[-1][0])
        ):
            groups[-1].append(message)
        else:
            groups.append([message])
    return groups


def select_current_turn(messages: Sequence[AnyMessage]) -> list[AnyMessage]:
    """只保留最后一轮用户消息及其之后的工具调用、工具结果与回答。

    用于 `use_history=false`：模型只能看到本轮内容，但状态本身不裁剪，
    本轮消息仍会正常写入 checkpointer 与 `session_messages`。
    找不到用户消息时退化为「只留最后一条」，绝不回退到整段历史——
    否则关闭历史就失去了意义。
    """
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return list(messages[index:])
    return list(messages[-1:])


def trim_to_token_budget(
    messages: Sequence[AnyMessage],
    max_tokens: int,
) -> list[AnyMessage]:
    """把历史裁剪到 token 预算内，保留最近的消息。

    - 最新一组消息无论多大都保留，否则模型看不到用户当前问题；
    - 裁剪后开头的孤儿 ToolMessage 必须丢弃，它的调用消息已不在上下文中。
    """
    if max_tokens <= 0:
        raise ValueError("上下文预算必须大于 0")

    groups = group_messages(messages)
    kept_groups: list[list[AnyMessage]] = []
    total_tokens = 0

    for group in reversed(groups):
        cost = sum(_message_cost(message) for message in group)
        if kept_groups and total_tokens + cost > max_tokens:
            break
        kept_groups.append(group)
        total_tokens += cost

    kept_groups.reverse()
    kept = [message for group in kept_groups for message in group]

    while kept and isinstance(kept[0], ToolMessage):
        kept.pop(0)
    return kept
