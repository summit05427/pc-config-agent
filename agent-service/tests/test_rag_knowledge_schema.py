"""知识库表结构、权限过滤与 Postgres 仓储的参数绑定。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from app.rag.base import RagConfigError
from app.rag.knowledge.models import EmbeddedChunk, KnowledgeCard, TextChunk
from app.rag.knowledge.repository import (
    KEYWORD_SEARCH_EXACT_SQL,
    KEYWORD_SEARCH_PLAIN_SQL,
    VECTOR_SEARCH_SQL,
    PostgresKnowledgeRepository,
    _to_hit,
    require_postgres_url,
)
from app.rag.knowledge.schema import (
    PERMISSION_FILTER_SQL,
    build_schema_statements,
    permission_params,
    to_vector_literal,
    validate_dimensions,
)


def test_schema_contains_vector_and_fulltext_indexes() -> None:
    statements = "\n".join(build_schema_statements(1024))

    assert "CREATE EXTENSION IF NOT EXISTS vector" in statements
    assert "vector(1024)" in statements
    assert "USING hnsw (embedding vector_cosine_ops)" in statements
    assert "USING GIN (search_vector)" in statements
    assert "GENERATED ALWAYS AS (to_tsvector('simple', content))" in statements
    assert "allowed_roles" in statements


def test_schema_rejects_invalid_dimensions() -> None:
    with pytest.raises(ValueError, match="维度"):
        build_schema_statements(0)
    with pytest.raises(ValueError, match="维度"):
        build_schema_statements(9000)
    with pytest.raises(ValueError, match="整数"):
        validate_dimensions(True)  # type: ignore[arg-type]


def test_vector_literal_uses_pgvector_text_format() -> None:
    assert to_vector_literal([0.1, 0.2]) == "[0.10000000,0.20000000]"
    with pytest.raises(ValueError, match="不能为空"):
        to_vector_literal([])


def test_permission_params_match_sql_placeholder_order() -> None:
    roles, user_id = permission_params("user-1", ("USER", "ADMIN"))

    assert roles == ["USER", "ADMIN"]
    assert user_id == "user-1"
    assert "allowed_roles && %s::text[]" in PERMISSION_FILTER_SQL
    assert "owner_user_id = %s" in PERMISSION_FILTER_SQL


def test_search_sql_applies_permission_filter_before_limit() -> None:
    for sql in (VECTOR_SEARCH_SQL, KEYWORD_SEARCH_PLAIN_SQL, KEYWORD_SEARCH_EXACT_SQL):
        assert "WHERE" in sql
        assert "visibility" in sql
        assert sql.index("visibility") < sql.index("LIMIT")
    assert "plainto_tsquery('simple', %s)" in KEYWORD_SEARCH_PLAIN_SQL
    assert "websearch_to_tsquery('simple', %s)" in KEYWORD_SEARCH_EXACT_SQL


def test_require_postgres_url_rejects_memory_backend() -> None:
    settings = SimpleNamespace(
        storage=SimpleNamespace(backend="memory", postgres_url=None)
    )

    with pytest.raises(RagConfigError, match="STORAGE__BACKEND"):
        require_postgres_url(settings)  # type: ignore[arg-type]


def test_require_postgres_url_returns_secret_value() -> None:
    settings = SimpleNamespace(
        storage=SimpleNamespace(
            backend="postgres",
            postgres_url=SecretStr("postgresql://u:p@db:5432/agent_service"),
        )
    )

    url = require_postgres_url(settings)  # type: ignore[arg-type]
    assert url == "postgresql://u:p@db:5432/agent_service"


class FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    async def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._rows)


class FakeConnection:
    def __init__(self, pool: FakePool) -> None:
        self._pool = pool

    async def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> FakeCursor:
        self._pool.calls.append((sql, params))
        return FakeCursor(self._pool.rows)

    def cursor(self) -> FakeCursorContext:
        return FakeCursorContext(self._pool)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


class FakeCursorContext:
    def __init__(self, pool: FakePool) -> None:
        self._pool = pool

    async def __aenter__(self) -> FakeCursorContext:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> None:
        self._pool.calls.append((sql, params))


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: Any) -> None:
        return None


class FakeConnectionContext:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self._connection

    async def __aexit__(self, *args: Any) -> None:
        return None


class FakePool:
    def __init__(self, rows: list[tuple[Any, ...]] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.is_opened = False
        self.is_closed = False

    def connection(self) -> FakeConnectionContext:
        return FakeConnectionContext(FakeConnection(self))

    async def open(self) -> None:
        self.is_opened = True

    async def close(self) -> None:
        self.is_closed = True


async def test_repository_setup_runs_idempotent_ddl() -> None:
    pool = FakePool()
    repository = PostgresKnowledgeRepository(
        pool,  # type: ignore[arg-type]
        dimensions=3,
        auto_setup=True,
    )

    await repository.setup()
    await repository.setup()
    await repository.aclose()

    assert pool.is_opened is True
    assert pool.is_closed is True
    statements = [sql for sql, _ in pool.calls]
    assert any("CREATE EXTENSION" in sql for sql in statements)
    assert any("vector(3)" in sql for sql in statements)


async def test_get_document_state_maps_row() -> None:
    pool = FakePool(rows=[("hash-1", "embed-v1", 4)])
    repository = PostgresKnowledgeRepository(pool, dimensions=3, auto_setup=False)  # type: ignore[arg-type]

    state = await repository.get_document_state("kb-1")

    assert state is not None
    assert state.content_hash == "hash-1"
    assert state.embedding_model == "embed-v1"
    assert state.chunk_count == 4
    assert pool.calls[0][1] == ("kb-1",)


async def test_vector_search_binds_permission_and_vector_params() -> None:
    pool = FakePool(rows=[("chunk-1", "doc-1", "标题", "内容", "项目文档", "HIGH", 1.4)])
    repository = PostgresKnowledgeRepository(pool, dimensions=3, auto_setup=False)  # type: ignore[arg-type]

    hits = await repository.search_vector(
        [0.1, 0.2, 0.3],
        limit=5,
        user_id="user-1",
        roles=("USER", "ADMIN"),
    )

    assert hits[0].chunk_id == "chunk-1"
    assert hits[0].score == 1.0
    sql, params = pool.calls[0]
    assert "visibility" in sql
    assert params is not None
    assert params[1] == ["USER", "ADMIN"]
    assert params[2] == "user-1"
    assert params[4] == 5


async def test_keyword_search_uses_exact_query_and_permission() -> None:
    pool = FakePool(rows=[("chunk-1", "doc-1", "标题", "内容", "项目文档", "HIGH", 0.2)])
    repository = PostgresKnowledgeRepository(pool, dimensions=3, auto_setup=False)  # type: ignore[arg-type]

    hits = await repository.search_keyword(
        "b650m OR am5",
        limit=5,
        user_id="user-1",
        roles=("USER",),
        is_exact=True,
    )

    assert hits[0].score == 0.2
    sql, params = pool.calls[0]
    assert "websearch_to_tsquery" in sql
    assert params is not None
    assert params[0] == "b650m OR am5"
    assert params[1] == ["USER"]
    assert params[2] == "user-1"
    assert params[3] == 5


async def test_replace_document_writes_document_then_replaces_chunks() -> None:
    pool = FakePool()
    repository = PostgresKnowledgeRepository(pool, dimensions=3, auto_setup=False)  # type: ignore[arg-type]
    card = KnowledgeCard(
        document_id="kb-1",
        title="标题",
        source_name="本项目知识卡片",
        content="正文",
    )
    chunk = TextChunk(
        chunk_id="kb-1#abc",
        document_id="kb-1",
        content="标题\n正文",
        content_hash="chunk-hash",
        metadata={"heading_path": []},
    )
    embedded = EmbeddedChunk(chunk=chunk, embedding=(0.1, 0.2, 0.3), embedding_model="m")

    await repository.replace_document(card, "doc-hash", [embedded])

    assert len(pool.calls) == 3
    upsert_sql, upsert_params = pool.calls[0]
    assert "INSERT INTO kb_documents" in upsert_sql
    assert upsert_params is not None
    assert upsert_params[0] == "kb-1"
    assert upsert_params[10] == "doc-hash"
    assert pool.calls[1] == ("DELETE FROM kb_chunks WHERE document_id = %s", ("kb-1",))
    insert_sql, insert_params = pool.calls[2]
    assert "INSERT INTO kb_chunks" in insert_sql
    assert insert_params[0][0] == "kb-1#abc"
    assert insert_params[0][5] == "[0.10000000,0.20000000,0.30000000]"


def test_to_hit_clamps_scores_and_normalizes_nulls() -> None:
    assert _to_hit(("id", "doc", None, None, None, None, -0.2)).score == 0.0
    hit = _to_hit(("id", "doc", "标题", "内容", "项目文档", "HIGH", 2.0))
    assert hit.score == 1.0
    # 来源与置信等级随命中返回，供工具告诉模型证据可信度
    assert hit.source_name == "项目文档"
    assert hit.confidence_level == "HIGH"
