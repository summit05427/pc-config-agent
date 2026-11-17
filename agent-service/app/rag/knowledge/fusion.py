"""RRF（Reciprocal Rank Fusion）融合。

只使用各通道的名次，不比较余弦相似度与 ts_rank 的量纲：
`score = weight / (k + rank)`，同一 chunk 命中多个通道时累加。
`k` 越大，头部与尾部的分差越小；精确词查询会提高关键词通道权重。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.rag.knowledge.models import SearchHit

DEFAULT_RRF_K = 60
DEFAULT_VECTOR_WEIGHT = 1.0
DEFAULT_KEYWORD_WEIGHT = 1.0


@dataclass(frozen=True)
class FusedHit:
    """融合后的命中。

    `score` 是 RRF 名次分，只用于排序；它随 k 与通道数变化，不能当作
    相关性百分比展示。`vector_score` / `keyword_score` 保留各通道原始分：
    向量分即余弦相似度，可用于相关性阈值与前端展示。
    """

    hit: SearchHit
    score: float
    vector_score: float | None = None
    keyword_score: float | None = None


def fuse_ranked_results(
    vector_hits: Sequence[SearchHit],
    keyword_hits: Sequence[SearchHit],
    *,
    limit: int,
    k: int = DEFAULT_RRF_K,
    vector_weight: float = DEFAULT_VECTOR_WEIGHT,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    max_per_document: int | None = None,
) -> list[FusedHit]:
    """按名次累加融合两个通道；同一 chunk 只输出一次。

    排序规则：分数降序，其次 chunk_id 升序。加入 chunk_id 是为了让
    相同分数下输出稳定，避免数据库返回顺序变化导致引用编号抖动。

    `max_per_document` 限制单文档进入结果的切片数：长文档切出的多个相似
    片段会挤占 top-k，让其他文档失去引用机会。
    """
    if limit < 1:
        raise ValueError("limit 必须大于 0")
    if k < 1:
        raise ValueError("rrf k 必须大于 0")
    if vector_weight <= 0 or keyword_weight <= 0:
        raise ValueError("通道权重必须大于 0")
    if max_per_document is not None and max_per_document < 1:
        raise ValueError("max_per_document 必须大于 0")

    scores: dict[str, float] = {}
    hits: dict[str, SearchHit] = {}
    vector_scores: dict[str, float] = {}
    keyword_scores: dict[str, float] = {}
    for weight, channel, channel_scores in (
        (vector_weight, vector_hits, vector_scores),
        (keyword_weight, keyword_hits, keyword_scores),
    ):
        for rank, hit in enumerate(channel, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + weight / (k + rank)
            hits.setdefault(hit.chunk_id, hit)
            # 同名切片只保留首个通道分；同一通道内 chunk_id 不应重复
            channel_scores.setdefault(hit.chunk_id, hit.score)

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    fused: list[FusedHit] = []
    per_document: dict[str, int] = {}
    for chunk_id, score in ordered:
        if len(fused) >= limit:
            break
        hit = hits[chunk_id]
        used = per_document.get(hit.document_id, 0)
        if max_per_document is not None and used >= max_per_document:
            continue
        per_document[hit.document_id] = used + 1
        fused.append(
            FusedHit(
                hit=hit,
                score=score,
                vector_score=vector_scores.get(chunk_id),
                keyword_score=keyword_scores.get(chunk_id),
            )
        )
    return fused
