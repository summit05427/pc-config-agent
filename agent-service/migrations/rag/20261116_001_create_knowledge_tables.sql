-- 20261116_001：agent_service 库内的 RAG 知识库表
-- 与 Java 的 agent 库完全隔离；不要在本库创建用户或会话业务表。
-- 执行：
--   psql "$STORAGE__POSTGRES_URL" -v ON_ERROR_STOP=1 \
--     -f migrations/rag/20261116_001_create_knowledge_tables.sql
-- 维度必须与 RAG__EMBEDDING_DIMENSIONS 一致；默认 1024（百炼 text-embedding-v4）。
-- 若配置为其他维度，请同步替换下方 vector(1024)；已建表需先清空或重建再切换维度。

CREATE EXTENSION IF NOT EXISTS vector;

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
);

CREATE INDEX IF NOT EXISTS idx_kb_documents_hash
    ON kb_documents (content_hash);
CREATE INDEX IF NOT EXISTS idx_kb_documents_visibility
    ON kb_documents (visibility);
CREATE INDEX IF NOT EXISTS idx_kb_documents_roles
    ON kb_documents USING GIN (allowed_roles);

CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id        TEXT PRIMARY KEY,
    document_id     TEXT        NOT NULL
                    REFERENCES kb_documents(document_id) ON DELETE CASCADE,
    content         TEXT        NOT NULL,
    content_hash    TEXT        NOT NULL,
    metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    embedding       vector(1024) NOT NULL,
    embedding_model TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_vector   tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    UNIQUE (document_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_kb_chunks_document
    ON kb_chunks (document_id);
-- HNSW 余弦索引；与检索 SQL 的 <=> 算子一致
CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding
    ON kb_chunks USING hnsw (embedding vector_cosine_ops);
-- 全文索引：型号/Socket/芯片组等精确词走关键词通道
CREATE INDEX IF NOT EXISTS idx_kb_chunks_search
    ON kb_chunks USING GIN (search_vector);
