"""内置 pgvector 知识库实现。

模块按需导入：RAG 关闭时 `app.rag.registry` 不会引用本包，
因此不会加载 psycopg 连接池或 embedding 客户端。
"""
