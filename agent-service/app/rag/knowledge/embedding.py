"""Embedding 出口：经 LiteLLM 调用，模型与维度只来自配置。

为什么不在检索器里直接发 HTTP：
1. 模型、维度、超时只解析一次，检索与导入共用同一实现；
2. 缺失配置在启动期失败，禁止用零向量或假向量兜底；
3. 测试可以注入任何实现 `Embedder` 协议的假对象，不产生网络请求。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from openai import AsyncOpenAI

from app.core.config import Settings
from app.rag.base import RagConfigError
from app.rag.knowledge.schema import validate_dimensions

# 与 llm.py 保持同一判定：示例密钥视为尚未配置
PLACEHOLDER_API_KEY_PREFIX = "sk-replace"
DEFAULT_MAX_RETRIES = 2


class Embedder(Protocol):
    """检索与导入只依赖这三个能力；`model_name` 用于判定向量是否过期。"""

    @property
    def model_name(self) -> str: ...

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


def _normalize_base_url(base_url: str) -> str:
    """OpenAI SDK 会在 base_url 后拼 `/embeddings`，网关需要 `/v1` 前缀。"""
    normalized = base_url.strip().rstrip("/")
    return normalized if normalized.endswith("/v1") else f"{normalized}/v1"


def _strip_provider_prefix(model: str) -> str:
    """直连模式走 OpenAI 兼容端点，模型名不能带业务 provider 前缀。"""
    _, separator, bare_name = model.partition(":")
    return bare_name if separator and bare_name else model


def _resolve_credentials(settings: Settings) -> tuple[str, str, str]:
    """返回 `(api_key, base_url, model)`；网关模式优先，其次直连模式。"""
    model = settings.rag.embedding_model.strip()
    gateway_key = settings.llm.gateway_api_key
    if gateway_key is not None and gateway_key.get_secret_value().strip():
        return (
            gateway_key.get_secret_value().strip(),
            _normalize_base_url(settings.llm.gateway_base_url),
            model,
        )

    direct_key = settings.llm.api_key
    api_key = direct_key.get_secret_value().strip() if direct_key is not None else ""
    if not api_key:
        raise RagConfigError(
            "RAG 需要 embedding 能力：请配置 LLM__GATEWAY_API_KEY 或 LLM__API_KEY"
        )
    base_url = settings.llm.base_url or "https://api.deepseek.com/v1"
    return api_key, _normalize_base_url(base_url), _strip_provider_prefix(model)


def build_embedder(settings: Settings) -> LiteLLMEmbedder:
    """启动期构造 embedding 客户端；配置缺失时直接抛 `RagConfigError`。"""
    model = settings.rag.embedding_model.strip()
    if not model:
        raise RagConfigError(
            "RAG__ENABLED=true 时必须配置 RAG__EMBEDDING_MODEL（经 LiteLLM 调用的模型名）"
        )
    if settings.rag.embedding_dimensions <= 0:
        raise RagConfigError(
            "RAG__ENABLED=true 时必须配置正整数 RAG__EMBEDDING_DIMENSIONS"
        )
    dimensions = validate_dimensions(settings.rag.embedding_dimensions)
    api_key, base_url, resolved_model = _resolve_credentials(settings)
    if api_key.lower().startswith(PLACEHOLDER_API_KEY_PREFIX):
        raise RagConfigError("LLM 密钥仍是示例占位值，无法调用 embedding 服务")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=settings.rag.embedding_timeout_seconds,
        max_retries=DEFAULT_MAX_RETRIES,
    )
    return LiteLLMEmbedder(
        client=client,
        model=resolved_model,
        dimensions=dimensions,
        batch_size=settings.rag.embedding_batch_size,
    )


class LiteLLMEmbedder:
    """OpenAI 兼容接口的薄封装；LiteLLM 负责具体 Provider 协议。"""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        dimensions: int,
        batch_size: int,
    ) -> None:
        self._client = client
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size

    @property
    def model_name(self) -> str:
        return self._model

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """按批请求并保持输入顺序；空输入不发起请求。"""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            vectors.extend(await self._embed(batch))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text])
        return vectors[0]

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=list(texts),
            dimensions=self._dimensions,
        )
        vectors = [[float(value) for value in item.embedding] for item in response.data]
        if len(vectors) != len(texts):
            raise RuntimeError("embedding 返回条数与输入不一致")
        if any(len(vector) != self._dimensions for vector in vectors):
            raise RuntimeError(
                f"embedding 维度与 RAG__EMBEDDING_DIMENSIONS={self._dimensions} 不一致"
            )
        return vectors
