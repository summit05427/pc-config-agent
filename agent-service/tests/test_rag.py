"""可选 RAG 模块：契约校验、注册表加载与对话接线。"""

import sys
from collections.abc import Iterator
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.security import CurrentUser
from app.rag import (
    Citation,
    NoopRetriever,
    RagConfigError,
    RetrievalRequest,
    build_retrieval_prompt,
    discover_retriever,
    ensure_retriever_loaded,
    get_retriever,
    reset_retriever,
)
from app.rag import registry as registry_module
from app.services import turn as turn_module

FAKE_MODULE_NAME = "tests.fake_retriever_module"


@pytest.fixture(autouse=True)
def _reset_retriever_registry() -> Iterator[None]:
    """注册表是进程级缓存，每个用例前后清空，避免相互污染。"""
    reset_retriever()
    yield
    reset_retriever()


class _FakeRetriever:
    """实现最小检索接口，同时记录调用参数。"""

    def __init__(
        self,
        citations: list[Citation] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.citations = citations or []
        self.error = error
        self.requests: list[RetrievalRequest] = []

    async def retrieve(self, request: RetrievalRequest) -> list[Citation]:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.citations


def _install_fake_module(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    factory: Any,
) -> ModuleType:
    """把伪模块注入 sys.modules，importlib 会直接命中而不访问磁盘。"""
    module = ModuleType(name)
    module.create_retriever = factory  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _settings(enabled: bool, module: str = "", top_k: int = 5) -> SimpleNamespace:
    rag = SimpleNamespace(enabled=enabled, retriever_module=module, top_k=top_k)
    return SimpleNamespace(rag=rag)


def test_citation_to_payload_keeps_contract_fields() -> None:
    citation = Citation(source_id="kb-1", title="示例", snippet="片段", score=0.9)

    assert citation.to_payload() == {
        "source_id": "kb-1",
        "title": "示例",
        "snippet": "片段",
        "score": 0.9,
    }


def test_citation_rejects_extra_and_invalid_fields() -> None:
    """`extra=forbid` 让契约外的字段在构造期就暴露，而不是静默进 SSE。"""
    with pytest.raises(ValidationError):
        Citation(source_id="kb-1", snippet="片段", extra_field="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Citation(source_id="", snippet="片段")
    with pytest.raises(ValidationError):
        Citation(source_id="kb-1", snippet="")
    with pytest.raises(ValidationError):
        Citation(source_id="kb-1", snippet="片段", score=1.5)


def test_retrieval_request_defaults_and_limit_bounds() -> None:
    request = RetrievalRequest(query="问题", user_id="user-1")

    assert request.roles == ()
    assert request.limit == 5
    with pytest.raises(ValidationError):
        RetrievalRequest(query="问题", user_id="user-1", limit=0)
    with pytest.raises(ValidationError):
        RetrievalRequest(query="问题", user_id="user-1", limit=21)
    with pytest.raises(ValidationError):
        RetrievalRequest(query="", user_id="user-1")


async def test_noop_retriever_returns_empty() -> None:
    retriever = NoopRetriever()

    assert await retriever.retrieve(RetrievalRequest(query="问题", user_id="user-1")) == []


def test_build_retrieval_prompt_returns_none_without_citations() -> None:
    """无引用时完全不动提示词，调用方不需要额外分支。"""
    assert build_retrieval_prompt([]) is None


def test_build_retrieval_prompt_numbers_citations_and_falls_back_title() -> None:
    prompt = build_retrieval_prompt(
        [
            Citation(source_id="kb-1", title="文档一", snippet="片段一"),
            Citation(source_id="kb-2", snippet="片段二"),
        ]
    )

    assert prompt is not None
    assert "[1] 标题：文档一" in prompt
    assert "[1] 标题：文档一\n片段：片段一" in prompt
    # 缺省标题必须给出可读占位，避免模型看到「标题：」后接编号
    assert "[2] 标题：无标题" in prompt


def test_build_retrieval_prompt_normalizes_and_truncates_snippet() -> None:
    """片段会被压缩空白并截断，防止单条引用挤占上下文预算。"""
    prompt = build_retrieval_prompt(
        [Citation(source_id="kb-1", title="文档", snippet="a\n\n  b" + "x" * 400)]
    )

    assert prompt is not None
    assert "片段：a b" in prompt
    assert "x" * 301 not in prompt


def test_discover_requires_module_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry_module, "get_settings", lambda: _settings(True, ""))

    with pytest.raises(RagConfigError, match="RAG__RETRIEVER_MODULE"):
        discover_retriever()


def test_discover_reports_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = "tests.module_that_does_not_exist"
    monkeypatch.setattr(registry_module, "get_settings", lambda: _settings(True, missing))

    with pytest.raises(RagConfigError, match="导入失败"):
        discover_retriever()


def test_discover_requires_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType(FAKE_MODULE_NAME)
    monkeypatch.setitem(sys.modules, FAKE_MODULE_NAME, module)
    monkeypatch.setattr(registry_module, "get_settings", lambda: _settings(True, FAKE_MODULE_NAME))

    with pytest.raises(RagConfigError, match="create_retriever"):
        discover_retriever()


def test_discover_rejects_factory_return_without_retrieve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_module(monkeypatch, FAKE_MODULE_NAME, lambda: object())
    monkeypatch.setattr(registry_module, "get_settings", lambda: _settings(True, FAKE_MODULE_NAME))

    with pytest.raises(RagConfigError, match="retrieve"):
        discover_retriever()


def test_discover_returns_configured_retriever(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever = _FakeRetriever()
    _install_fake_module(monkeypatch, FAKE_MODULE_NAME, lambda: retriever)
    monkeypatch.setattr(registry_module, "get_settings", lambda: _settings(True, FAKE_MODULE_NAME))

    assert discover_retriever() is retriever


def test_ensure_retriever_loaded_skips_import_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """关闭时不导入第三方模块：避免仅为「未启用」付出导入成本或网络连接。"""
    _install_fake_module(monkeypatch, FAKE_MODULE_NAME, lambda: _FakeRetriever())
    monkeypatch.setattr(registry_module, "get_settings", lambda: _settings(False, FAKE_MODULE_NAME))

    retriever = ensure_retriever_loaded()

    assert isinstance(retriever, NoopRetriever)
    assert retriever is ensure_retriever_loaded()
    assert get_retriever() is retriever


def test_ensure_retriever_loaded_caches_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def factory() -> _FakeRetriever:
        calls.append(1)
        return _FakeRetriever()

    _install_fake_module(monkeypatch, FAKE_MODULE_NAME, factory)
    monkeypatch.setattr(registry_module, "get_settings", lambda: _settings(True, FAKE_MODULE_NAME))

    first = ensure_retriever_loaded()
    second = ensure_retriever_loaded()

    assert first is second
    assert len(calls) == 1


async def test_retrieve_citations_passes_permission_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """检索请求必须携带 user_id / roles：权限过滤在检索前完成。"""
    retriever = _FakeRetriever([Citation(source_id="kb-1", snippet="片段")])
    monkeypatch.setattr(turn_module, "get_retriever", lambda: retriever)
    monkeypatch.setattr(
        turn_module,
        "get_settings",
        lambda: SimpleNamespace(rag=SimpleNamespace(enabled=True, top_k=3)),
    )
    user = CurrentUser(user_id="user-1", roles=("USER", "ADMIN"))

    citations = await turn_module._retrieve_citations("问题", user.user_id, tuple(user.roles))

    assert citations == [Citation(source_id="kb-1", snippet="片段")]
    assert len(retriever.requests) == 1
    request = retriever.requests[0]
    assert request.query == "问题"
    assert request.user_id == "user-1"
    assert request.roles == ("USER", "ADMIN")
    assert request.limit == 3


async def test_retrieve_citations_degrades_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """RAG 是增强能力：检索异常不能让整轮对话失败。"""
    retriever = _FakeRetriever(error=RuntimeError("向量库不可用"))
    monkeypatch.setattr(turn_module, "get_retriever", lambda: retriever)

    assert await turn_module._retrieve_citations("问题", "user-1", ()) == []


def test_compose_turn_prompt_merges_only_present_parts() -> None:
    assert turn_module._compose_turn_prompt(None, None) is None
    assert turn_module._compose_turn_prompt("偏好", None) == "偏好"
    assert turn_module._compose_turn_prompt(None, "检索") == "检索"
    assert turn_module._compose_turn_prompt("偏好", "检索") == "偏好\n\n检索"
