"""内置 pgvector 检索器：融合顺序、精确词、权限参数与降级。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from app.rag import registry
from app.rag.base import RagConfigError, RetrievalRequest
from app.rag.knowledge import retriever as retriever_module
from app.rag.knowledge.fusion import fuse_ranked_results
from app.rag.knowledge.models import SearchHit
from app.rag.knowledge.retriever import (
    EXACT_KEYWORD_WEIGHT,
    PgvectorRetriever,
    create_retriever,
    extract_exact_terms,
)


def _hit(
    chunk_id: str,
    *,
    title: str = "文档",
    content: str | None = None,
    document_id: str | None = None,
) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        document_id=document_id or f"doc-{chunk_id}",
        title=title,
        content=content or f"片段-{chunk_id}",
        score=0.5,
    )


def _settings(
    *,
    rrf_k: int = 60,
    recall_multiplier: int = 4,
    min_relevance_score: float = 0.2,
) -> SimpleNamespace:
    return SimpleNamespace(
        rag=SimpleNamespace(
            rrf_k=rrf_k,
            recall_multiplier=recall_multiplier,
            min_relevance_score=min_relevance_score,
        )
    )


class FakeEmbedder:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.query_calls: list[str] = []

    @property
    def model_name(self) -> str:
        return "fake-embed"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        if self.error is not None:
            raise self.error
        return [0.1, 0.2, 0.3]


class FakeRepository:
    def __init__(
        self,
        *,
        vector_hits: list[SearchHit] | None = None,
        keyword_hits: list[SearchHit] | None = None,
        search_error: Exception | None = None,
    ) -> None:
        self.vector_hits = vector_hits or []
        self.keyword_hits = keyword_hits or []
        self.search_error = search_error
        self.setup_calls = 0
        self.close_calls = 0
        self.vector_calls: list[dict[str, Any]] = []
        self.keyword_calls: list[dict[str, Any]] = []

    async def setup(self) -> None:
        self.setup_calls += 1

    async def aclose(self) -> None:
        self.close_calls += 1

    async def get_document_state(self, document_id: str) -> None:
        return None

    async def replace_document(self, card: Any, content_hash: str, chunks: Any) -> None:
        return None

    async def search_vector(
        self,
        embedding: list[float],
        *,
        limit: int,
        user_id: str,
        roles: tuple[str, ...],
    ) -> list[SearchHit]:
        self.vector_calls.append(
            {"embedding": embedding, "limit": limit, "user_id": user_id, "roles": roles}
        )
        if self.search_error is not None:
            raise self.search_error
        return self.vector_hits

    async def search_keyword(
        self,
        query: str,
        *,
        limit: int,
        user_id: str,
        roles: tuple[str, ...],
        is_exact: bool,
    ) -> list[SearchHit]:
        self.keyword_calls.append(
            {
                "query": query,
                "limit": limit,
                "user_id": user_id,
                "roles": roles,
                "is_exact": is_exact,
            }
        )
        if self.search_error is not None:
            raise self.search_error
        return self.keyword_hits


def _request(
    query: str = "怎么选",
    *,
    limit: int = 5,
    roles: tuple[str, ...] = ("USER",),
) -> RetrievalRequest:
    return RetrievalRequest(query=query, user_id="user-1", roles=roles, limit=limit)


async def test_retrieve_fuses_two_channels_by_rank() -> None:
    repository = FakeRepository(
        vector_hits=[_hit("a"), _hit("b")],
        keyword_hits=[_hit("b"), _hit("c")],
    )
    retriever = PgvectorRetriever(
        embedder=FakeEmbedder(),
        settings=_settings(),
        repository=repository,
    )

    citations = await retriever.retrieve(_request())

    # b 同时命中两个通道，必须排在最前；a 与 c 同分时按 chunk_id 稳定排序
    assert [item.source_id for item in citations] == ["b", "a", "c"]
    # 引用分展示向量相似度，不能把 RRF 名次分当成相关度百分比
    assert citations[0].score == pytest.approx(0.5)
    assert citations[1].score == pytest.approx(0.5)
    # 仅关键词命中没有可比量纲，不展示相关度
    assert citations[2].score is None


async def test_low_relevance_vector_hits_are_filtered_out() -> None:
    low = SearchHit(
        chunk_id="low",
        document_id="doc-low",
        title="弱相关",
        content="弱相关片段",
        score=0.05,
    )
    repository = FakeRepository(vector_hits=[_hit("strong"), low])
    retriever = PgvectorRetriever(
        embedder=FakeEmbedder(),
        settings=_settings(min_relevance_score=0.2),
        repository=repository,
    )

    citations = await retriever.retrieve(_request(limit=5))

    assert [item.source_id for item in citations] == ["strong"]


async def test_exact_keyword_hit_bypasses_relevance_threshold() -> None:
    weak_vector = SearchHit(
        chunk_id="b650",
        document_id="doc-b650",
        title="B650 说明",
        content="B650 需要更新 BIOS",
        score=0.05,
    )
    repository = FakeRepository(vector_hits=[weak_vector], keyword_hits=[weak_vector])
    retriever = PgvectorRetriever(
        embedder=FakeEmbedder(),
        settings=_settings(min_relevance_score=0.2),
        repository=repository,
    )

    citations = await retriever.retrieve(_request("B650 装 9000 系 CPU 要刷 BIOS 吗"))

    # 精确型号命中属于强相关，不能被语义阈值挡掉；低向量分也不展示为百分比
    assert [item.source_id for item in citations] == ["b650"]
    assert citations[0].score is None


async def test_exact_terms_boost_keyword_and_use_or_query() -> None:
    repository = FakeRepository(vector_hits=[_hit("v")], keyword_hits=[_hit("k")])
    retriever = PgvectorRetriever(
        embedder=FakeEmbedder(),
        settings=_settings(),
        repository=repository,
    )

    citations = await retriever.retrieve(_request("B650M 和 AM5 怎么选"))

    assert extract_exact_terms("B650M 和 AM5 怎么选") == ("b650m", "am5")
    assert repository.keyword_calls[0]["query"] == "b650m OR am5"
    assert repository.keyword_calls[0]["is_exact"] is True
    # 关键词通道权重更高，只命中关键词的结果应排在只命中向量的结果之前
    assert [item.source_id for item in citations] == ["k", "v"]
    assert EXACT_KEYWORD_WEIGHT > 1


async def test_permission_scope_is_passed_to_both_channels() -> None:
    repository = FakeRepository()
    retriever = PgvectorRetriever(
        embedder=FakeEmbedder(),
        settings=_settings(recall_multiplier=4),
        repository=repository,
    )

    await retriever.retrieve(_request(limit=5, roles=("USER", "ADMIN")))
    await retriever.retrieve(_request(limit=5, roles=("USER", "ADMIN")))

    # 连接池与建表只初始化一次
    assert repository.setup_calls == 1
    for call in repository.vector_calls + repository.keyword_calls:
        assert call["user_id"] == "user-1"
        assert call["roles"] == ("USER", "ADMIN")
        assert call["limit"] == 20


async def test_recall_limit_has_hard_cap() -> None:
    repository = FakeRepository()
    retriever = PgvectorRetriever(
        embedder=FakeEmbedder(),
        settings=_settings(recall_multiplier=20),
        repository=repository,
    )

    await retriever.retrieve(_request(limit=20))

    assert repository.vector_calls[0]["limit"] == 100


async def test_empty_results_return_empty_list() -> None:
    retriever = PgvectorRetriever(
        embedder=FakeEmbedder(),
        settings=_settings(),
        repository=FakeRepository(),
    )

    assert await retriever.retrieve(_request()) == []


async def test_repository_failure_degrades_to_no_citations() -> None:
    retriever = PgvectorRetriever(
        embedder=FakeEmbedder(),
        settings=_settings(),
        repository=FakeRepository(search_error=RuntimeError("database down")),
    )

    assert await retriever.retrieve(_request()) == []


async def test_embedding_failure_degrades_before_search() -> None:
    repository = FakeRepository()
    retriever = PgvectorRetriever(
        embedder=FakeEmbedder(error=RuntimeError("model down")),
        settings=_settings(),
        repository=repository,
    )

    assert await retriever.retrieve(_request()) == []
    assert repository.vector_calls == []
    assert repository.keyword_calls == []


async def test_aclose_releases_repository() -> None:
    repository = FakeRepository()
    retriever = PgvectorRetriever(
        embedder=FakeEmbedder(),
        settings=_settings(),
        repository=repository,
    )

    await retriever.aclose()
    await retriever.aclose()

    # 第二次调用没有可释放的仓储，不得重复关闭
    assert repository.close_calls == 1


async def test_registry_close_retriever_calls_optional_aclose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Closable:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    retriever = Closable()
    monkeypatch.setattr(registry, "_retriever", retriever)

    await registry.close_retriever()

    assert retriever.closed is True
    assert registry._retriever is None


def _app_settings(
    *,
    backend: str = "postgres",
    embedding_model: str = "text-embedding-3-small",
    dimensions: int = 1536,
) -> SimpleNamespace:
    return SimpleNamespace(
        storage=SimpleNamespace(
            backend=backend,
            postgres_url=SecretStr("postgresql://u:p@db:5432/agent_service")
            if backend == "postgres"
            else None,
            pool_size=5,
            auto_setup=True,
        ),
        rag=SimpleNamespace(
            embedding_model=embedding_model,
            embedding_dimensions=dimensions,
            embedding_batch_size=32,
            embedding_timeout_seconds=30.0,
            rrf_k=60,
            recall_multiplier=4,
            min_relevance_score=0.2,
        ),
        llm=SimpleNamespace(
            gateway_api_key=SecretStr("sk-real-gateway-key"),
            gateway_base_url="http://litellm:4000",
            api_key=None,
            base_url=None,
        ),
    )


def test_create_retriever_requires_embedding_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retriever_module, "get_settings", lambda: _app_settings(embedding_model=""))

    with pytest.raises(RagConfigError, match="RAG__EMBEDDING_MODEL"):
        create_retriever()


def test_create_retriever_requires_positive_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        retriever_module,
        "get_settings",
        lambda: _app_settings(dimensions=0),
    )

    with pytest.raises(RagConfigError, match="RAG__EMBEDDING_DIMENSIONS"):
        create_retriever()


def test_create_retriever_requires_postgres_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        retriever_module,
        "get_settings",
        lambda: _app_settings(backend="memory"),
    )

    with pytest.raises(RagConfigError, match="STORAGE__BACKEND"):
        create_retriever()


def test_create_retriever_builds_lazy_retriever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retriever_module, "get_settings", lambda: _app_settings())

    retriever = create_retriever()

    assert isinstance(retriever, PgvectorRetriever)
    # 工厂只做配置校验，不应在事件循环之外打开连接池
    assert retriever._repository is None


def test_rrf_validation_and_weighting() -> None:
    vector = [_hit("v")]
    keyword = [_hit("k")]

    fused = fuse_ranked_results(vector, keyword, limit=2, keyword_weight=2.0)
    assert [item.hit.chunk_id for item in fused] == ["k", "v"]

    with pytest.raises(ValueError):
        fuse_ranked_results(vector, keyword, limit=0)
    with pytest.raises(ValueError):
        fuse_ranked_results(vector, keyword, limit=1, k=0)
    with pytest.raises(ValueError):
        fuse_ranked_results(vector, keyword, limit=1, vector_weight=0)


def test_rrf_limits_chunks_per_document() -> None:
    first = _hit("a1", document_id="doc-a")
    second = _hit("a2", document_id="doc-a")
    third = _hit("a3", document_id="doc-a")
    other = _hit("b1", document_id="doc-b")

    fused = fuse_ranked_results(
        [first, second, third, other],
        [],
        limit=3,
        max_per_document=2,
    )

    assert [item.hit.chunk_id for item in fused] == ["a1", "a2", "b1"]
    with pytest.raises(ValueError):
        fuse_ranked_results([first], [], limit=1, max_per_document=0)


def test_extract_exact_terms_skips_plain_english() -> None:
    assert extract_exact_terms("推荐一台适合游戏的电脑") == ()
    assert extract_exact_terms("recommend a motherboard") == ()
    assert extract_exact_terms("PCIe 4.0 与 DDR5 的区别") == ("pcie", "4.0", "ddr5")
