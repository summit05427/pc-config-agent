-- 20261116_001 回滚：删除 RAG 知识库表与索引
-- 执行：
--   psql "$STORAGE__POSTGRES_URL" -v ON_ERROR_STOP=1 \
--     -f migrations/rag/20261116_001_create_knowledge_tables_rollback.sql
-- 不删除 vector 扩展：同一库可能还有其他向量表在用。

DROP INDEX IF EXISTS idx_kb_chunks_search;
DROP INDEX IF EXISTS idx_kb_chunks_embedding;
DROP INDEX IF EXISTS idx_kb_chunks_document;
DROP TABLE IF EXISTS kb_chunks;

DROP INDEX IF EXISTS idx_kb_documents_roles;
DROP INDEX IF EXISTS idx_kb_documents_visibility;
DROP INDEX IF EXISTS idx_kb_documents_hash;
DROP TABLE IF EXISTS kb_documents;
