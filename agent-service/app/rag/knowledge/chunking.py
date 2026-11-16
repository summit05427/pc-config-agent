"""Markdown 切片：按标题与段落切分，chunk_id 由内容哈希稳定派生。

切片正文会带上「文档标题 / 标题路径」前缀，让每个片段脱离上下文后
仍能被模型理解；因此同一内容的重复导入会得到完全相同的 chunk_id。
"""

from __future__ import annotations

import hashlib
import re

from app.rag.knowledge.models import KnowledgeCard, TextChunk

# 单切片上限：太大挤占提示词预算，太小则语义不完整
MAX_CHUNK_CHARS = 600
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SENTENCE_PATTERN = re.compile(r"[^。！？!?\n]+[。！？!?]?")


def normalize_text(text: str) -> str:
    """统一换行并去掉首尾空白，保证哈希不受编辑器差异影响。"""
    return text.replace("\r\n", "\n").strip()


def hash_text(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def split_markdown_sections(content: str) -> list[tuple[tuple[str, ...], str]]:
    """返回 `(标题路径, 正文)`；标题自身不进入正文，由调用方拼前缀。"""
    sections: list[tuple[tuple[str, ...], str]] = []
    heading_stack: list[tuple[int, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append((tuple(title for _, title in heading_stack), body))
        buffer.clear()

    for line in content.splitlines():
        match = HEADING_PATTERN.match(line)
        if match is None:
            buffer.append(line)
            continue
        flush()
        level = len(match.group(1))
        # 新标题只保留层级更浅的祖先，形成当前标题路径
        heading_stack = [item for item in heading_stack if item[0] < level]
        heading_stack.append((level, match.group(2).strip()))
    flush()
    return sections


def chunk_card(card: KnowledgeCard, *, max_chars: int = MAX_CHUNK_CHARS) -> list[TextChunk]:
    """把一张卡片切成稳定切片；同一文档内完全相同的内容只保留一次。"""
    if max_chars < 1:
        raise ValueError("max_chars 必须大于 0")

    chunks: list[TextChunk] = []
    seen_hashes: set[str] = set()
    for headings, body in split_markdown_sections(card.content):
        prefix = " / ".join([card.title, *headings])
        for piece in pack_paragraphs(paragraphs(body), max_chars=max_chars):
            content = f"{prefix}\n{piece}"
            digest = hash_text(content)
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            chunks.append(
                TextChunk(
                    chunk_id=f"{card.document_id}#{digest[:16]}",
                    document_id=card.document_id,
                    content=content,
                    content_hash=digest,
                    metadata={
                        "heading_path": list(headings),
                        "document_title": card.title,
                        "source_type": card.source_type,
                        "source_name": card.source_name,
                        "confidence_level": card.confidence_level,
                        "version": card.version,
                        "chunk_index": len(chunks),
                    },
                )
            )
    return chunks


def paragraphs(text: str) -> list[str]:
    """空行分段；段内保留原有换行，列表与代码片段不会被压成一行。"""
    return [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]


def pack_paragraphs(items: list[str], *, max_chars: int) -> list[str]:
    """把段落顺序装箱到不超过 max_chars 的切片；超长段落先按句子拆开。"""
    packed: list[str] = []
    current = ""
    for item in items:
        for piece in split_long_text(item, max_chars=max_chars):
            if not current:
                current = piece
            elif len(current) + len(piece) + 2 <= max_chars:
                current = f"{current}\n\n{piece}"
            else:
                packed.append(current)
                current = piece
    if current:
        packed.append(current)
    return packed


def split_long_text(text: str, *, max_chars: int) -> list[str]:
    """优先按中英文句末标点切分；没有任何标点时按字符硬切。"""
    if len(text) <= max_chars:
        return [text]
    sentences = [piece for piece in SENTENCE_PATTERN.findall(text) if piece.strip()]
    if not sentences:
        return _hard_split(text, max_chars)

    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_hard_split(sentence, max_chars))
            continue
        if current and len(current) + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        pieces.append(current)
    return pieces


def _hard_split(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]
