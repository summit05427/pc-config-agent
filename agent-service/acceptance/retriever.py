"""内存检索器：返回固定引用，用于验证 RAG 接线与 `citations` 事件。

启用方式：`RAG__ENABLED=true` + `RAG__RETRIEVER_MODULE=acceptance.retriever`。
"""

from app.rag.base import Citation, RetrievalRequest

FACT = "蓝鲸计划代号是 BLUE-42。"


class AcceptanceRetriever:
    """忽略查询内容，始终返回同一条引用，便于断言。"""

    async def retrieve(self, request: RetrievalRequest) -> list[Citation]:
        return [
            Citation(
                source_id="acceptance-kb",
                title="验收知识库",
                snippet=FACT,
                score=0.95,
            )
        ]


def create_retriever() -> AcceptanceRetriever:
    return AcceptanceRetriever()
