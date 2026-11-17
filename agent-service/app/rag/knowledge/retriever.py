"""pgvector Hybrid 检索器。

流程固定为：
1. 从配置构造 embedding 客户端（缺失即启动失败）；
2. 查询向量与全文两个通道，两个 SQL 都先按 `user_id` / `roles` 过滤；
3. RRF 融合名次，产出既有 `Citation` 契约。

型号、芯片组、Socket 这类精确词会提高关键词通道权重，并用 OR 连接各词，
避免自然语言里的连接词把型号检索卡死。
"""

from __future__ import annotations

import asyncio
import re

import structlog

from app.core.config import Settings, get_settings
from app.rag.base import Citation, RetrievalRequest
from app.rag.knowledge.embedding import Embedder, build_embedder
from app.rag.knowledge.fusion import (
    DEFAULT_KEYWORD_WEIGHT,
    DEFAULT_VECTOR_WEIGHT,
    FusedHit,
    fuse_ranked_results,
)
from app.rag.knowledge.repository import (
    KnowledgeRepository,
    create_repository,
    require_postgres_url,
)

logger = structlog.get_logger(__name__)

# 召回池上限：request.limit 最大 20，乘以倍数后仍要有硬上限
MAX_RECALL_LIMIT = 100
# 精确词命中时提高关键词通道权重，避免被语义近似结果挤掉
EXACT_KEYWORD_WEIGHT = 2.0
MAX_TITLE_CHARS = 128
MAX_SNIPPET_CHARS = 4000
MAX_SOURCE_NAME_CHARS = 200
MAX_CONFIDENCE_CHARS = 16
MAX_EXACT_TERMS = 8
# 单文档最多进入 top-k 的切片数：长文档的相似片段不应挤掉其他文档
MAX_CHUNKS_PER_DOCUMENT = 2

# 只看 ASCII 型号/Socket/芯片组；中文由向量通道负责
EXACT_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
TS_TERM_SANITIZER = re.compile(r"[^a-z0-9_.+-]")

# 常见硬件缩写；不在此表且不含数字、非全大写的词不视为精确词
KNOWN_EXACT_TERMS = frozenset(
    {
        "cpu",
        "gpu",
        "ssd",
        "hdd",
        "psu",
        "ram",
        "ddr",
        "ddr4",
        "ddr5",
        "pcie",
        "nvme",
        "sata",
        "bios",
        "tdp",
        "atx",
        "matx",
        "itx",
        "am4",
        "am5",
        "lga",
        "rtx",
        "gtx",
        "apu",
        "igpu",
        "vrm",
        "dimm",
        "usb",
        "hdmi",
        "xmp",
        "expo",
        "ecc",
        "tbw",
        "dram",
        "hbm",
        "ipc",
    }
)


def extract_exact_terms(query: str) -> tuple[str, ...]:
    """抽取需要走关键词通道的精确词，保持出现顺序并去重。"""
    terms: list[str] = []
    seen: set[str] = set()
    for match in EXACT_TOKEN_PATTERN.finditer(query):
        raw = match.group(0).strip("._+-")
        if not raw:
            continue
        lowered = raw.lower()
        if not _is_exact_token(raw, lowered):
            continue
        sanitized = TS_TERM_SANITIZER.sub("", lowered)
        if len(sanitized) < 2 or sanitized in seen:
            continue
        seen.add(sanitized)
        terms.append(sanitized)
        if len(terms) >= MAX_EXACT_TERMS:
            break
    return tuple(terms)


def _is_exact_token(raw: str, lowered: str) -> bool:
    """数字、全大写、已知缩写三类视为精确词；普通英文单词交给语义通道。"""
    return (
        lowered in KNOWN_EXACT_TERMS
        or any(character.isdigit() for character in lowered)
        or raw.isupper()
    )


class PgvectorRetriever:
    """一个进程复用一个连接池；首次检索时建表，之后只读。"""

    def __init__(
        self,
        *,
        embedder: Embedder,
        settings: Settings,
        repository: KnowledgeRepository | None = None,
    ) -> None:
        self._embedder = embedder
        self._settings = settings
        self._repository = repository
        self._setup_lock = asyncio.Lock()
        self._is_ready = False

    async def retrieve(self, request: RetrievalRequest) -> list[Citation]:
        """检索失败时返回空列表：RAG 是增强能力，不能阻断对话。"""
        try:
            repository = await self._get_repository()
            query_vector = await self._embedder.embed_query(request.query)
            rag = self._settings.rag
            recall_limit = min(
                MAX_RECALL_LIMIT,
                max(request.limit, request.limit * rag.recall_multiplier),
            )
            exact_terms = extract_exact_terms(request.query)
            keyword_query = " OR ".join(exact_terms) if exact_terms else request.query

            vector_hits, keyword_hits = await asyncio.gather(
                repository.search_vector(
                    query_vector,
                    limit=recall_limit,
                    user_id=request.user_id,
                    roles=request.roles,
                ),
                repository.search_keyword(
                    keyword_query,
                    limit=recall_limit,
                    user_id=request.user_id,
                    roles=request.roles,
                    is_exact=bool(exact_terms),
                ),
            )
            fused = fuse_ranked_results(
                vector_hits,
                keyword_hits,
                limit=request.limit,
                k=rag.rrf_k,
                vector_weight=DEFAULT_VECTOR_WEIGHT,
                keyword_weight=(
                    EXACT_KEYWORD_WEIGHT if exact_terms else DEFAULT_KEYWORD_WEIGHT
                ),
                max_per_document=MAX_CHUNKS_PER_DOCUMENT,
            )
            citations: list[Citation] = []
            min_relevance = rag.min_relevance_score
            for item in fused:
                if not _is_relevant(
                    item, min_relevance=min_relevance, has_exact_terms=bool(exact_terms)
                ):
                    continue
                citation = _to_citation(item, min_relevance=min_relevance)
                if citation is not None:
                    citations.append(citation)
            if len(citations) < len(fused):
                logger.info(
                    "rag.relevance_filtered",
                    kept=len(citations),
                    dropped=len(fused) - len(citations),
                    min_relevance=min_relevance,
                )
            return citations
        except Exception as exc:
            logger.warning(
                "rag.retrieve_failed",
                error_type=type(exc).__name__,
                retriever="pgvector",
            )
            return []

    async def aclose(self) -> None:
        """释放连接池；由应用生命周期或测试显式调用。"""
        if self._repository is not None:
            await self._repository.aclose()
        self._repository = None
        self._is_ready = False

    async def _get_repository(self) -> KnowledgeRepository:
        """连接池必须在事件循环内创建；这也是工厂只做配置校验的原因。"""
        if self._is_ready and self._repository is not None:
            return self._repository
        async with self._setup_lock:
            if self._repository is None:
                self._repository = create_repository(self._settings)
            if not self._is_ready:
                await self._repository.setup()
                self._is_ready = True
            return self._repository


def _is_relevant(
    item: FusedHit, *, min_relevance: float, has_exact_terms: bool
) -> bool:
    """向量相似度低于阈值的片段不展示。

    例外有两种：精确型号命中（关键词通道）视为强相关，不能被语义阈值挡住；
    只有关键词分的命中没有可比较的量纲，保留但不展示相关度百分比。
    """
    if has_exact_terms and item.keyword_score is not None:
        return True
    if item.vector_score is not None:
        return item.vector_score >= min_relevance
    return item.keyword_score is not None


def _to_citation(item: FusedHit, *, min_relevance: float) -> Citation | None:
    snippet = item.hit.content.strip()
    if not snippet:
        return None
    # RRF 名次分只用于排序，不能当相关性展示；只有达到阈值的余弦相似度才进 `score`
    vector_score = item.vector_score
    score = (
        min(1.0, max(0.0, vector_score))
        if vector_score is not None and vector_score >= min_relevance
        else None
    )
    return Citation(
        source_id=item.hit.chunk_id,
        title=(item.hit.title or "无标题")[:MAX_TITLE_CHARS],
        snippet=snippet[:MAX_SNIPPET_CHARS],
        score=score,
        source_name=item.hit.source_name[:MAX_SOURCE_NAME_CHARS],
        confidence_level=item.hit.confidence_level[:MAX_CONFIDENCE_CHARS],
    )


def create_retriever() -> PgvectorRetriever:
    """`RAG__RETRIEVER_MODULE=app.rag.knowledge.retriever` 的工厂入口。

    这里只做配置校验：embedding 模型/维度缺失、存储不是 postgres 都直接失败；
    真正的连接与建表推迟到首次检索，避免在应用启动事件循环之外创建连接池。
    """
    settings = get_settings()
    require_postgres_url(settings)
    embedder = build_embedder(settings)
    return PgvectorRetriever(embedder=embedder, settings=settings)
