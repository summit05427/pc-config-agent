"""知识库表结构：文档元数据、切片、向量索引与全文索引。

两处 DDL 必须保持一致：
- `migrations/rag/*.sql` 供 DBA 手工执行与回滚；
- 本模块的语句供 `STORAGE__AUTO_SETUP=true` 时启动期幂等建表。
维度只能作为 `vector(n)` 的类型字面量，无法参数化，因此这里只接受
范围校验后的整数；迁移文件固定为 1536，配置不同时必须同步修改。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

# pgvector 扩展与 Java 的 agent 库无关；本服务只操作自己的 agent_service 库
CREATE_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector"

CREATE_DOCUMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS kb_documents (
    document_id      TEXT PRIMARY KEY,
    title            TEXT        NOT NULL,
    source_type      TEXT        NOT NULL,
    source_url       TEXT,
    source_name      TEXT        NOT NULL,
    published_at     TIMESTAMPTZ,
    collected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until      TIMESTAMPTZ,
    confidence_level TEXT        NOT NULL,
    version          INTEGER     NOT NULL DEFAULT 1,
    content_hash     TEXT        NOT NULL,
    visibility       TEXT        NOT NULL DEFAULT 'public',
    allowed_roles    TEXT[]      NOT NULL DEFAULT '{}',
    owner_user_id    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

CREATE_DOCUMENTS_INDEXES_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_kb_documents_hash "
    "ON kb_documents (content_hash)",
    "CREATE INDEX IF NOT EXISTS idx_kb_documents_visibility "
    "ON kb_documents (visibility)",
    "CREATE INDEX IF NOT EXISTS idx_kb_documents_roles "
    "ON kb_documents USING GIN (allowed_roles)",
)

# search_vector 用 generated column：写入切片时自动维护，避免应用忘记同步
CREATE_CHUNKS_TABLE_TEMPLATE = """
CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id        TEXT PRIMARY KEY,
    document_id     TEXT        NOT NULL
                    REFERENCES kb_documents(document_id) ON DELETE CASCADE,
    content         TEXT        NOT NULL,
    content_hash    TEXT        NOT NULL,
    metadata        JSONB       NOT NULL DEFAULT '{{}}'::jsonb,
    embedding       vector({dimensions}) NOT NULL,
    embedding_model TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_vector   tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    UNIQUE (document_id, content_hash)
)
"""

# HNSW 用余弦距离，与检索 SQL 的 `<=>` 算子保持一致
CREATE_CHUNKS_INDEXES_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_kb_chunks_document "
    "ON kb_chunks (document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding "
    "ON kb_chunks USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS idx_kb_chunks_search "
    "ON kb_chunks USING GIN (search_vector)",
)

# 权限过滤必须出现在两个通道的 WHERE 中，且在 ORDER/LIMIT 之前执行
PERMISSION_FILTER_SQL = """
(
    d.visibility = 'public'
    OR (d.visibility = 'role' AND d.allowed_roles && %s::text[])
    OR (d.visibility = 'private' AND d.owner_user_id = %s)
)
"""

MIN_EMBEDDING_DIMENSIONS = 1
MAX_EMBEDDING_DIMENSIONS = 8192


def validate_dimensions(dimensions: int) -> int:
    """维度直接拼进类型字面量，必须先收窄为合法整数。"""
    if not isinstance(dimensions, int) or isinstance(dimensions, bool):
        raise ValueError("embedding 维度必须是整数")
    if not MIN_EMBEDDING_DIMENSIONS <= dimensions <= MAX_EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"embedding 维度必须在 {MIN_EMBEDDING_DIMENSIONS}-"
            f"{MAX_EMBEDDING_DIMENSIONS} 之间，当前为 {dimensions}"
        )
    return dimensions


def build_schema_statements(dimensions: int) -> tuple[str, ...]:
    """返回幂等 DDL；调用方按顺序执行即可，重复执行不会破坏已有数据。"""
    dimension = validate_dimensions(dimensions)
    return (
        CREATE_EXTENSION_SQL,
        CREATE_DOCUMENTS_TABLE_SQL,
        *CREATE_DOCUMENTS_INDEXES_SQL,
        CREATE_CHUNKS_TABLE_TEMPLATE.format(dimensions=dimension),
        *CREATE_CHUNKS_INDEXES_SQL,
    )


async def ensure_schema(connection: Any, dimensions: int) -> None:
    """在已打开的连接上执行全部 DDL；连接类型由 psycopg 提供，避免此处引入具体驱动。"""
    for statement in build_schema_statements(dimensions):
        await connection.execute(statement)


def to_vector_literal(embedding: Sequence[float]) -> str:
    """pgvector 的文本输入格式；用字符串避免 list 被适配成数组类型。"""
    if not embedding:
        raise ValueError("embedding 不能为空")
    return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"


def permission_params(user_id: str, roles: Iterable[str]) -> tuple[list[str], str]:
    """与 `PERMISSION_FILTER_SQL` 的占位符顺序一致：角色数组在前，用户在后。"""
    return list(roles), user_id
