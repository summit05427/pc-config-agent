"""可选 RAG 模块：检索接口、引用结构与权限过滤入口。"""

from app.rag.base import (
    Citation,
    NoopRetriever,
    RagConfigError,
    RetrievalRequest,
    Retriever,
)
from app.rag.prompt import build_retrieval_prompt
from app.rag.registry import (
    discover_retriever,
    ensure_retriever_loaded,
    get_retriever,
    reset_retriever,
)

__all__ = [
    "Citation",
    "NoopRetriever",
    "RagConfigError",
    "RetrievalRequest",
    "Retriever",
    "build_retrieval_prompt",
    "discover_retriever",
    "ensure_retriever_loaded",
    "get_retriever",
    "reset_retriever",
]
