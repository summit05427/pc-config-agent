"""知识卡片导入：幂等、内容变化、模型变化与卡片加载。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.rag.knowledge.chunking import MAX_CHUNK_CHARS, chunk_card, split_long_text
from app.rag.knowledge.importing import (
    document_fingerprint,
    import_cards,
    load_cards,
)
from app.rag.knowledge.models import DocumentState, ImportReport, KnowledgeCard

SEED_CARD_DIR = Path(__file__).resolve().parents[1] / "knowledge" / "cards"


def _card(content: str | None = None) -> KnowledgeCard:
    return KnowledgeCard(
        document_id="kb-test",
        title="测试知识卡片",
        source_type="INTERNAL_NOTE",
        source_name="本项目知识卡片",
        confidence_level="HIGH",
        version=1,
        content=content
        or (
            "## 稳定段\n\n"
            "这一段内容在两次切片中保持一致。\n\n"
            "## 变化段\n\n"
            "这一段会被改动，用来验证指纹变化。"
        ),
    )


class FakeEmbedder:
    def __init__(self, *, model_name: str = "fake-embed", fail: bool = False) -> None:
        self._model_name = model_name
        self.fail = fail
        self.calls: list[list[str]] = []

    @property
    def model_name(self) -> str:
        return self._model_name

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail:
            return []
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FakeImportRepository:
    def __init__(self) -> None:
        self.states: dict[str, DocumentState] = {}
        self.documents: dict[str, tuple[str, list[Any]]] = {}
        self.replace_calls: list[tuple[str, str, list[Any]]] = []

    async def setup(self) -> None:
        return None

    async def aclose(self) -> None:
        return None

    async def get_document_state(self, document_id: str) -> DocumentState | None:
        return self.states.get(document_id)

    async def replace_document(
        self,
        card: KnowledgeCard,
        content_hash: str,
        chunks: list[Any],
    ) -> None:
        self.replace_calls.append((card.document_id, content_hash, list(chunks)))
        self.documents[card.document_id] = (content_hash, list(chunks))
        self.states[card.document_id] = DocumentState(
            content_hash=content_hash,
            embedding_model=chunks[0].embedding_model if chunks else None,
            chunk_count=len(chunks),
        )

    async def search_vector(self, embedding: Any, **kwargs: Any) -> list[Any]:
        raise NotImplementedError

    async def search_keyword(self, query: str, **kwargs: Any) -> list[Any]:
        raise NotImplementedError


async def test_import_is_idempotent_for_unchanged_card() -> None:
    repository = FakeImportRepository()
    embedder = FakeEmbedder()
    card = _card()

    first = await import_cards(repository, [card], embedder)
    second = await import_cards(repository, [card], embedder)

    assert first.imported == 1
    assert first.updated == 0
    assert first.chunks_written > 0
    assert second == ImportReport(skipped=1)
    # 第二次不重新切片、不重新生成向量
    assert len(embedder.calls) == 1
    assert len(repository.documents["kb-test"][1]) == first.chunks_written


async def test_import_updates_when_content_changes() -> None:
    repository = FakeImportRepository()
    embedder = FakeEmbedder()
    original = _card()
    await import_cards(repository, [original], embedder)
    old_chunk_ids = {item.chunk.chunk_id for item in repository.documents["kb-test"][1]}

    changed = original.model_copy(
        update={"content": original.content.replace("这一段会被改动", "这一段已经改动")}
    )
    report = await import_cards(repository, [changed], embedder)

    assert report.updated == 1
    assert len(embedder.calls) == 2
    new_chunk_ids = {item.chunk.chunk_id for item in repository.documents["kb-test"][1]}
    assert old_chunk_ids != new_chunk_ids
    # 未变化的段落仍得到相同的 chunk_id
    assert old_chunk_ids & new_chunk_ids


async def test_import_reembeds_when_embedding_model_changes() -> None:
    repository = FakeImportRepository()
    card = _card()
    await import_cards(repository, [card], FakeEmbedder(model_name="fake-v1"))

    report = await import_cards(repository, [card], FakeEmbedder(model_name="fake-v2"))

    assert report.updated == 1
    assert repository.states["kb-test"].embedding_model == "fake-v2"


async def test_import_rejects_embedding_count_mismatch() -> None:
    repository = FakeImportRepository()

    with pytest.raises(RuntimeError, match="embedding 条数"):
        await import_cards(repository, [_card()], FakeEmbedder(fail=True))


def test_chunk_ids_are_stable_and_change_with_content() -> None:
    card = _card()

    first = chunk_card(card)
    second = chunk_card(card)
    changed = chunk_card(
        card.model_copy(update={"content": card.content.replace("这一段会被改动", "新内容")})
    )

    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]
    assert {item.chunk_id for item in first} & {item.chunk_id for item in changed}


def test_long_paragraph_is_split_into_multiple_chunks() -> None:
    card = _card(
        content="## 长段\n\n" + "".join(f"第{index}句说明。" for index in range(80))
    )

    chunks = chunk_card(card, max_chars=120)

    assert len(chunks) > 1
    assert all("长段" in item.content for item in chunks)
    assert all(item.chunk_id.startswith("kb-test#") for item in chunks)


def test_chunk_card_rejects_invalid_max_chars() -> None:
    with pytest.raises(ValueError, match="max_chars"):
        chunk_card(_card(), max_chars=0)


def test_split_long_text_hard_splits_without_punctuation() -> None:
    pieces = split_long_text("x" * 25, max_chars=10)

    assert pieces == ["x" * 10, "x" * 10, "x" * 5]


def test_fingerprint_changes_when_metadata_changes() -> None:
    card = _card()

    renamed = card.model_copy(update={"title": "新的标题"})

    assert document_fingerprint(card) != document_fingerprint(renamed)
    assert document_fingerprint(card) == document_fingerprint(_card())


def test_load_cards_reads_markdown_and_json(tmp_path: Path) -> None:
    markdown = tmp_path / "note.md"
    markdown.write_text(
        "---\n"
        "document_id: kb-md\n"
        "title: Markdown 卡片\n"
        "source_type: INTERNAL_NOTE\n"
        "source_name: 本项目知识卡片\n"
        "confidence_level: MEDIUM\n"
        "---\n\n"
        "## 正文\n\n内容。\n",
        encoding="utf-8",
    )
    json_file = tmp_path / "note.json"
    json_file.write_text(
        '{"cards": [{"document_id": "kb-json", "title": "JSON 卡片", '
        '"source_type": "OFFICIAL_SPEC", "source_name": "规格摘录", '
        '"confidence_level": "HIGH", "content": "## 正文\\n\\n内容。"}]}',
        encoding="utf-8",
    )

    cards = load_cards([tmp_path])

    assert [card.document_id for card in cards] == ["kb-json", "kb-md"]
    assert cards[0].source_type == "OFFICIAL_SPEC"
    assert cards[1].confidence_level == "MEDIUM"


def test_load_cards_rejects_duplicate_document_id(tmp_path: Path) -> None:
    for name in ("a.md", "b.md"):
        (tmp_path / name).write_text(
            "---\n"
            "document_id: kb-dup\n"
            "title: 重复卡片\n"
            "source_name: 本项目知识卡片\n"
            "---\n\n正文。\n",
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="document_id 重复"):
        load_cards([tmp_path])


def test_load_cards_requires_front_matter(tmp_path: Path) -> None:
    (tmp_path / "bad.md").write_text("# 没有 front matter\n\n正文。", encoding="utf-8")

    with pytest.raises(ValueError, match="front matter"):
        load_cards([tmp_path])


def test_load_cards_supports_single_json_object(tmp_path: Path) -> None:
    (tmp_path / "single.json").write_text(
        '{"document_id": "kb-single", "title": "单卡", '
        '"source_name": "本项目知识卡片", "content": "正文。"}',
        encoding="utf-8",
    )

    cards = load_cards([tmp_path / "single.json"])

    assert [card.document_id for card in cards] == ["kb-single"]


def test_load_cards_rejects_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="合法 JSON"):
        load_cards([tmp_path])


def test_load_cards_rejects_unsupported_suffix(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("正文", encoding="utf-8")

    with pytest.raises(ValueError, match="不支持"):
        load_cards([tmp_path / "note.txt"])


def test_load_cards_rejects_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="没有找到"):
        load_cards([tmp_path])


def test_load_cards_reports_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_cards([tmp_path / "missing"])


def test_seed_cards_are_internal_methodology_notes() -> None:
    cards = load_cards([SEED_CARD_DIR])

    assert 8 <= len(cards) <= 10
    for card in cards:
        assert card.source_type == "INTERNAL_NOTE"
        assert card.source_name == "本项目知识卡片"
        assert card.source_url is None
        assert card.confidence_level in {"HIGH", "MEDIUM", "LOW"}
        assert "http://" not in card.content.lower()
        assert "https://" not in card.content.lower()
        assert len(chunk_card(card, max_chars=MAX_CHUNK_CHARS)) >= 1
