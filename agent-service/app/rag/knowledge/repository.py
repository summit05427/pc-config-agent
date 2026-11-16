"""知识库仓储：Postgres 适配器与检索 SQL。

权限过滤写进两个通道的 WHERE，而不是先查再筛：
`visibility=public` 对所有人开放，`role` 取角色交集，`private` 只对 owner 开放。
所有 SQL 参数化；向量以文本字面量绑定，避免 list 被适配成数组类型。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

import structlog
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.core.config import Settings
from app.rag.base import RagConfigError
from app.rag.knowledge.models import (
    DocumentState,
    EmbeddedChunk,
    KnowledgeCard,
    SearchHit,
)
from app.rag.knowledge.schema import (
    PERMISSION_FILTER_SQL,
    ensure_schema,
    permission_params,
    to_vector_literal,
)

logger = structlog.get_logger(__name__)

GET_DOCUMENT_STATE_SQL = """
SELECT
    d.content_hash,
    (SELECT c.embedding_model FROM kb_chunks c
     WHERE c.document_id = d.document_id LIMIT 1),
    (SELECT COUNT(*) FROM kb_chunks c WHERE c.document_id = d.document_id)
FROM kb_documents d
WHERE d.document_id = %s
"""

UPSERT_DOCUMENT_SQL = """
INSERT INTO kb_documents (
    document_id, title, source_type, source_url, source_name,
    published_at, collected_at, valid_until, confidence_level, version,
    content_hash, visibility, allowed_roles, owner_user_id
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (document_id) DO UPDATE SET
    title = EXCLUDED.title,
    source_type = EXCLUDED.source_type,
    source_url = EXCLUDED.source_url,
    source_name = EXCLUDED.source_name,
    published_at = EXCLUDED.published_at,
    collected_at = EXCLUDED.collected_at,
    valid_until = EXCLUDED.valid_until,
    confidence_level = EXCLUDED.confidence_level,
    version = EXCLUDED.version,
    content_hash = EXCLUDED.content_hash,
    visibility = EXCLUDED.visibility,
    allowed_roles = EXCLUDED.allowed_roles,
    owner_user_id = EXCLUDED.owner_user_id,
    updated_at = now()
"""

DELETE_CHUNKS_SQL = "DELETE FROM kb_chunks WHERE document_id = %s"

INSERT_CHUNK_SQL = """
INSERT INTO kb_chunks (
    chunk_id, document_id, content, content_hash, metadata, embedding, embedding_model
)
VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
"""

VECTOR_SEARCH_SQL = f"""
SELECT c.chunk_id, c.document_id, d.title, c.content,
       d.source_name, d.confidence_level,
       1 - (c.embedding <=> %s::vector) AS score
FROM kb_chunks c
JOIN kb_documents d ON d.document_id = c.document_id
WHERE {PERMISSION_FILTER_SQL}
ORDER BY c.embedding <=> %s::vector
LIMIT %s
"""


def _keyword_search_sql(is_exact: bool) -> str:
    """精确词用 OR 连接（型号之间不一定同时出现），自然语言用 plainto。

    `websearch_to_tsquery` 接受 `OR` 且不会因型号里的点号/加号报语法错误，
    比手工拼 `to_tsquery` 更稳妥。
    """
    query_expression = (
        "websearch_to_tsquery('simple', %s)"
        if is_exact
        else "plainto_tsquery('simple', %s)"
    )
    return f"""
SELECT c.chunk_id, c.document_id, d.title, c.content,
       d.source_name, d.confidence_level,
       ts_rank_cd(c.search_vector, q.query) AS score
FROM kb_chunks c
JOIN kb_documents d ON d.document_id = c.document_id
CROSS JOIN (SELECT {query_expression} AS query) q
WHERE c.search_vector @@ q.query AND {PERMISSION_FILTER_SQL}
ORDER BY score DESC, c.chunk_id
LIMIT %s
"""


KEYWORD_SEARCH_PLAIN_SQL = _keyword_search_sql(is_exact=False)
KEYWORD_SEARCH_EXACT_SQL = _keyword_search_sql(is_exact=True)


class KnowledgeRepository(Protocol):
    """检索器与导入流程共用的仓储接口；测试只需实现这个协议。"""

    async def setup(self) -> None: ...

    async def aclose(self) -> None: ...

    async def get_document_state(self, document_id: str) -> DocumentState | None: ...

    async def replace_document(
        self,
        card: KnowledgeCard,
        content_hash: str,
        chunks: Sequence[EmbeddedChunk],
    ) -> None: ...

    async def search_vector(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
        user_id: str,
        roles: Sequence[str],
    ) -> list[SearchHit]: ...

    async def search_keyword(
        self,
        query: str,
        *,
        limit: int,
        user_id: str,
        roles: Sequence[str],
        is_exact: bool,
    ) -> list[SearchHit]: ...


def require_postgres_url(settings: Settings) -> str:
    """RAG 表在 agent_service 库内，必须走 postgres 后端；memory 无法承载向量。"""
    if settings.storage.backend != "postgres" or settings.storage.postgres_url is None:
        raise RagConfigError(
            "RAG__ENABLED=true 时 STORAGE__BACKEND 必须为 postgres，"
            "并提供 STORAGE__POSTGRES_URL"
        )
    return settings.storage.postgres_url.get_secret_value()


def create_repository(settings: Settings) -> PostgresKnowledgeRepository:
    """构造仓储但不建连；连接池在首次 `setup()` 时于事件循环内打开。"""
    pool = AsyncConnectionPool(
        conninfo=require_postgres_url(settings),
        min_size=1,
        max_size=max(1, settings.storage.pool_size),
        kwargs={"autocommit": True},
        open=False,
    )
    return PostgresKnowledgeRepository(
        pool,
        dimensions=settings.rag.embedding_dimensions,
        auto_setup=settings.storage.auto_setup,
    )


class PostgresKnowledgeRepository:
    """pgvector + tsvector 的唯一写入与查询实现。"""

    def __init__(
        self,
        pool: AsyncConnectionPool,
        *,
        dimensions: int,
        auto_setup: bool,
    ) -> None:
        self._pool = pool
        self._dimensions = dimensions
        self._auto_setup = auto_setup
        self._is_open = False
        self._is_schema_ready = False

    async def setup(self) -> None:
        """打开连接池并按配置幂等建表；无 DDL 权限时由运维先执行迁移。"""
        if self._is_open and self._is_schema_ready:
            return
        if not self._is_open:
            await self._pool.open()
            self._is_open = True
        if not self._auto_setup:
            self._is_schema_ready = True
            logger.info("rag.schema_ready", auto_setup=False)
            return
        # DDL 失败时保持 _is_schema_ready=False，下一次检索会重试而不是带病查询
        async with self._pool.connection() as connection:
            await ensure_schema(connection, self._dimensions)
        self._is_schema_ready = True
        logger.info("rag.schema_ready", auto_setup=True, dimensions=self._dimensions)

    async def aclose(self) -> None:
        if not self._is_open:
            return
        await self._pool.close()
        self._is_open = False
        self._is_schema_ready = False

    async def get_document_state(self, document_id: str) -> DocumentState | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(GET_DOCUMENT_STATE_SQL, (document_id,))
            row = await cursor.fetchone()
        if row is None:
            return None
        return DocumentState(
            content_hash=str(row[0]),
            embedding_model=row[1],
            chunk_count=int(row[2]),
        )

    async def replace_document(
        self,
        card: KnowledgeCard,
        content_hash: str,
        chunks: Sequence[EmbeddedChunk],
    ) -> None:
        """文档行与切片在同一事务里替换；内容变化时不保留旧切片。"""
        collected_at = card.collected_at or datetime.now(UTC)
        document_params = (
            card.document_id,
            card.title,
            card.source_type,
            card.source_url,
            card.source_name,
            card.published_at,
            collected_at,
            card.valid_until,
            card.confidence_level,
            card.version,
            content_hash,
            card.visibility,
            list(card.allowed_roles),
            card.owner_user_id,
        )
        chunk_params = [
            (
                embedded.chunk.chunk_id,
                embedded.chunk.document_id,
                embedded.chunk.content,
                embedded.chunk.content_hash,
                Jsonb(embedded.chunk.metadata),
                to_vector_literal(embedded.embedding),
                embedded.embedding_model,
            )
            for embedded in chunks
        ]

        async with self._pool.connection() as connection, connection.transaction():
            await connection.execute(UPSERT_DOCUMENT_SQL, document_params)
            await connection.execute(DELETE_CHUNKS_SQL, (card.document_id,))
            if chunk_params:
                async with connection.cursor() as cursor:
                    await cursor.executemany(INSERT_CHUNK_SQL, chunk_params)

    async def search_vector(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
        user_id: str,
        roles: Sequence[str],
    ) -> list[SearchHit]:
        vector = to_vector_literal(embedding)
        role_params, user_param = permission_params(user_id, roles)
        params = (vector, role_params, user_param, vector, limit)
        async with self._pool.connection() as connection:
            cursor = await connection.execute(VECTOR_SEARCH_SQL, params)
            rows = await cursor.fetchall()
        return [_to_hit(row) for row in rows]

    async def search_keyword(
        self,
        query: str,
        *,
        limit: int,
        user_id: str,
        roles: Sequence[str],
        is_exact: bool,
    ) -> list[SearchHit]:
        sql = KEYWORD_SEARCH_EXACT_SQL if is_exact else KEYWORD_SEARCH_PLAIN_SQL
        role_params, user_param = permission_params(user_id, roles)
        params = (query, role_params, user_param, limit)
        async with self._pool.connection() as connection:
            cursor = await connection.execute(sql, params)
            rows = await cursor.fetchall()
        return [_to_hit(row) for row in rows]


def _to_hit(row: Sequence[Any]) -> SearchHit:
    """统一裁剪分数：Citation.score 只接受 0-1，余弦相似度可能略超边界。"""
    chunk_id, document_id, title, content, source_name, confidence_level, raw_score = row
    return SearchHit(
        chunk_id=str(chunk_id),
        document_id=str(document_id),
        title=str(title or ""),
        content=str(content or ""),
        score=max(0.0, min(1.0, float(raw_score))),
        source_name=str(source_name or ""),
        confidence_level=str(confidence_level or ""),
    )
