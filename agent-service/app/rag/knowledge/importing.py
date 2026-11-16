"""知识卡片导入：加载 → 切片 → embedding → 幂等 upsert。

幂等判定使用「文档指纹」：正文、标题、版本、来源与权限任一变化都会
触发替换；相同卡片重复导入时直接跳过，不产生新切片、不重复调用 embedding。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.rag.knowledge.chunking import MAX_CHUNK_CHARS, chunk_card, normalize_text
from app.rag.knowledge.embedding import Embedder
from app.rag.knowledge.models import (
    DocumentState,
    EmbeddedChunk,
    ImportReport,
    KnowledgeCard,
)
from app.rag.knowledge.repository import KnowledgeRepository

FRONT_MATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
CARD_SUFFIXES = frozenset({".md", ".json"})


def document_fingerprint(card: KnowledgeCard) -> str:
    """指纹覆盖全部会改变展示或切片文本的字段，避免元数据变更被跳过。"""
    payload = card.model_dump(mode="json")
    payload["content"] = normalize_text(card.content)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_cards(paths: Sequence[str | Path]) -> list[KnowledgeCard]:
    """读取 Markdown（front matter）或 JSON（单卡/数组/`cards` 字段）。"""
    cards: list[KnowledgeCard] = []
    owners: dict[str, Path] = {}
    for path in _collect_card_paths(paths):
        for card in _load_file(path):
            if card.document_id in owners:
                raise ValueError(
                    f"document_id 重复：{card.document_id}（{owners[card.document_id]} 与 {path}）"
                )
            owners[card.document_id] = path
            cards.append(card)
    return cards


async def import_cards(
    repository: KnowledgeRepository,
    cards: Sequence[KnowledgeCard],
    embedder: Embedder,
    *,
    max_chars: int = MAX_CHUNK_CHARS,
) -> ImportReport:
    """逐张卡片比对指纹；只对新增或变化的卡片生成向量。"""
    imported = 0
    updated = 0
    skipped = 0
    chunks_written = 0

    for card in cards:
        fingerprint = document_fingerprint(card)
        state = await repository.get_document_state(card.document_id)
        if _is_current(state, fingerprint, embedder.model_name):
            skipped += 1
            continue

        chunks = chunk_card(card, max_chars=max_chars)
        vectors = await embedder.embed_documents([chunk.content for chunk in chunks])
        if len(vectors) != len(chunks):
            raise RuntimeError(
                f"{card.document_id} 的 embedding 条数 {len(vectors)} 与切片数 {len(chunks)} 不一致"
            )
        embedded = [
            EmbeddedChunk(
                chunk=chunk,
                embedding=tuple(vector),
                embedding_model=embedder.model_name,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        await repository.replace_document(card, fingerprint, embedded)
        if state is None:
            imported += 1
        else:
            updated += 1
        chunks_written += len(embedded)

    return ImportReport(
        imported=imported,
        updated=updated,
        skipped=skipped,
        chunks_written=chunks_written,
    )


def _is_current(
    state: DocumentState | None,
    fingerprint: str,
    embedding_model: str,
) -> bool:
    """内容、模型与切片数量都一致才算已是最新。"""
    return (
        state is not None
        and state.content_hash == fingerprint
        and state.embedding_model == embedding_model
        and state.chunk_count > 0
    )


def _collect_card_paths(paths: Sequence[str | Path]) -> list[Path]:
    collected: set[Path] = set()
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            collected.update(
                item for item in path.rglob("*") if item.suffix.lower() in CARD_SUFFIXES
            )
        elif path.is_file():
            if path.suffix.lower() not in CARD_SUFFIXES:
                raise ValueError(f"不支持的卡片格式：{path}")
            collected.add(path)
        else:
            raise FileNotFoundError(f"卡片路径不存在：{path}")
    if not collected:
        raise ValueError("没有找到任何 .md 或 .json 知识卡片")
    return sorted(collected)


def _load_file(path: Path) -> list[KnowledgeCard]:
    if path.suffix.lower() == ".json":
        return _load_json(path)
    return [_load_markdown(path)]


def _load_markdown(path: Path) -> KnowledgeCard:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_PATTERN.match(text)
    if match is None:
        raise ValueError(f"{path}: Markdown 卡片必须以 --- front matter 开头")
    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: front matter 不是合法 YAML：{exc}") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"{path}: front matter 必须是键值对象")

    payload: dict[str, Any] = dict(metadata)
    payload["content"] = match.group(2).strip()
    return _validate_card(payload, path)


def _load_json(path: Path) -> list[KnowledgeCard]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: 不是合法 JSON：{exc}") from exc

    if isinstance(data, dict) and isinstance(data.get("cards"), list):
        items = data["cards"]
    elif isinstance(data, list):
        items = data
    else:
        items = [data]
    return [_validate_card(item, path) for item in items]


def _validate_card(payload: object, path: Path) -> KnowledgeCard:
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: 每条知识卡片必须是对象")
    try:
        return KnowledgeCard.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"{path}: 知识卡片校验失败：{exc}") from exc
