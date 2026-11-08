"""把检索结果渲染成模型可见的提示词片段。

片段只作为本轮提示词追加，不写进历史消息，避免检索内容被持久化后
在后续轮次里反复出现。引用编号与 `citations` 事件顺序一致。
"""

from collections.abc import Sequence

from app.rag.base import Citation

RAG_PROMPT_HEADER = "## 检索结果（仅可使用下列片段回答，引用时标注编号）"
RAG_PROMPT_RULE = "片段不足时明确说明不知道，不要编造；不要输出片段之外的事实。"
# 单条片段进入提示词的最大字符数；过长会挤占上下文预算
MAX_PROMPT_SNIPPET_CHARS = 300


def build_retrieval_prompt(citations: Sequence[Citation]) -> str | None:
    """无引用时返回 None，调用方据此完全不改动提示词。"""
    if not citations:
        return None

    lines = [RAG_PROMPT_HEADER, RAG_PROMPT_RULE]
    for index, citation in enumerate(citations, start=1):
        title = citation.title or "无标题"
        snippet = " ".join(citation.snippet.split())[:MAX_PROMPT_SNIPPET_CHARS]
        lines.append(f"[{index}] 标题：{title}\n片段：{snippet}")
    return "\n".join(lines)
