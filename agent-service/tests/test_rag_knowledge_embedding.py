"""Embedding 客户端：配置解析、批量调用与维度校验。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from app.rag.base import RagConfigError
from app.rag.knowledge.embedding import LiteLLMEmbedder, build_embedder


class FakeEmbeddings:
    def __init__(self, *, dimensions: int = 3, wrong_dimensions: bool = False) -> None:
        self.dimensions = dimensions
        self.wrong_dimensions = wrong_dimensions
        self.calls: list[dict[str, Any]] = []

    async def create(
        self,
        *,
        model: str,
        input: list[str],
        dimensions: int,
    ) -> SimpleNamespace:
        self.calls.append({"model": model, "input": input, "dimensions": dimensions})
        size = dimensions + 1 if self.wrong_dimensions else dimensions
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1] * size) for _ in input]
        )


class FakeClient:
    def __init__(self, embeddings: FakeEmbeddings | None = None) -> None:
        self.embeddings = embeddings or FakeEmbeddings()


def _settings(
    *,
    gateway_key: str | None = "sk-real-gateway-key",
    direct_key: str | None = None,
    model: str = "text-embedding-3-small",
    dimensions: int = 3,
    base_url: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        rag=SimpleNamespace(
            embedding_model=model,
            embedding_dimensions=dimensions,
            embedding_batch_size=2,
            embedding_timeout_seconds=30.0,
        ),
        llm=SimpleNamespace(
            gateway_api_key=SecretStr(gateway_key) if gateway_key else None,
            gateway_base_url="http://litellm:4000",
            api_key=SecretStr(direct_key) if direct_key else None,
            base_url=base_url,
        ),
    )


async def test_embed_documents_batches_and_preserves_order() -> None:
    client = FakeClient()
    embedder = LiteLLMEmbedder(
        client=client,  # type: ignore[arg-type]
        model="embed",
        dimensions=3,
        batch_size=2,
    )

    vectors = await embedder.embed_documents(["a", "b", "c"])

    assert len(vectors) == 3
    assert [len(call["input"]) for call in client.embeddings.calls] == [2, 1]
    assert client.embeddings.calls[0]["dimensions"] == 3


async def test_embed_documents_empty_input_skips_request() -> None:
    client = FakeClient()
    embedder = LiteLLMEmbedder(
        client=client,  # type: ignore[arg-type]
        model="embed",
        dimensions=3,
        batch_size=2,
    )

    assert await embedder.embed_documents([]) == []
    assert client.embeddings.calls == []


async def test_embed_query_returns_single_vector() -> None:
    client = FakeClient()
    embedder = LiteLLMEmbedder(
        client=client,  # type: ignore[arg-type]
        model="embed",
        dimensions=3,
        batch_size=2,
    )

    assert await embedder.embed_query("问题") == [0.1, 0.1, 0.1]


async def test_embedding_dimension_mismatch_raises() -> None:
    client = FakeClient(FakeEmbeddings(wrong_dimensions=True))
    embedder = LiteLLMEmbedder(
        client=client,  # type: ignore[arg-type]
        model="embed",
        dimensions=3,
        batch_size=2,
    )

    with pytest.raises(RuntimeError, match="维度"):
        await embedder.embed_query("问题")


def test_build_embedder_uses_gateway_and_keeps_model_name() -> None:
    embedder = build_embedder(_settings(model="openai:text-embedding-3-small"))  # type: ignore[arg-type]

    assert embedder.model_name == "openai:text-embedding-3-small"
    assert str(embedder._client.base_url) == "http://litellm:4000/v1/"


def test_build_embedder_direct_mode_strips_provider_prefix() -> None:
    embedder = build_embedder(
        _settings(
            gateway_key=None,
            direct_key="sk-real-direct-key",
            model="openai:text-embedding-3-small",
            base_url="https://api.example.com/v1",
        )  # type: ignore[arg-type]
    )

    assert embedder.model_name == "text-embedding-3-small"
    assert str(embedder._client.base_url) == "https://api.example.com/v1/"


def test_build_embedder_rejects_placeholder_key() -> None:
    with pytest.raises(RagConfigError, match="占位"):
        build_embedder(
            _settings(gateway_key="sk-replace-with-strong-litellm-master-key")  # type: ignore[arg-type]
        )


def test_build_embedder_rejects_missing_api_key() -> None:
    with pytest.raises(RagConfigError, match="LLM__GATEWAY_API_KEY"):
        build_embedder(_settings(gateway_key=None, direct_key=None))  # type: ignore[arg-type]
