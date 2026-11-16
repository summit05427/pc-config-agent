"""知识接入选型闭环：工具治理、Architect 引用注入与 SSE 去重。

全部使用假检索器与脚本化模型，不访问真实 LLM、向量库或网络。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent import registry as registry_module
from app.agent.pc import nodes as nodes_module
from app.agent.pc import tools as pc_tools
from app.agent.pc.graph import build_pc_graph
from app.agent.pc.schemas import (
    REQUIRED_CATEGORIES,
    BuildProposal,
    BuildStrategy,
    SelectedComponent,
)
from app.agent.pc.status import STATUS_SUCCESS
from app.agent.profiles import resolve_profile
from app.agent.tool_context import ToolTurn
from app.rag import Citation, NoopRetriever, RetrievalRequest

REQUIREMENT_JSON = json.dumps(
    {"budget_max_fen": 1_000_000, "scenario": "GAMING", "scenario_explicit": True}
)
KNOWLEDGE_CITATION = {
    "source_id": "kb-1",
    "title": "显卡与处理器预算分配方法",
    "snippet": "游戏场景应优先保证显卡预算占比。",
    "score": 0.9,
    "source_name": "项目文档",
    "confidence_level": "HIGH",
}


class FakeRetriever:
    """记录检索请求，并按 `limit` 截断返回，用于验证权限透传与 top_k。"""

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
        return self.citations[: request.limit]


def _citation(index: int) -> Citation:
    return Citation(
        source_id=f"kb-{index}",
        title=f"知识 {index}",
        snippet=f"片段 {index}",
        score=0.8,
        source_name="项目文档",
        confidence_level="MEDIUM",
    )


def _tool_settings(*, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(rag=SimpleNamespace(enabled=enabled))


def _knowledge_payload(
    citations: list[dict[str, Any]] | None = None,
    *,
    enabled: bool = True,
    truncated: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "enabled": enabled,
        "citations": citations or [],
        "truncated": truncated,
    }
    if error is not None:
        payload["error"] = error
    return payload


async def test_search_knowledge_returns_citation_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retriever = FakeRetriever([_citation(1)])
    monkeypatch.setattr(pc_tools, "get_retriever", lambda: retriever)
    monkeypatch.setattr(pc_tools, "get_settings", lambda: _tool_settings(enabled=True))

    with ToolTurn(("USER", "ADMIN"), user_id="user-1"):
        payload = await pc_tools.search_knowledge.ainvoke({"query": "游戏 预算 取舍"})

    assert payload["enabled"] is True
    assert payload["truncated"] is False
    assert payload["citations"] == [
        {
            "source_id": "kb-1",
            "title": "知识 1",
            "snippet": "片段 1",
            "score": 0.8,
            "source_name": "项目文档",
            "confidence_level": "MEDIUM",
        }
    ]
    request = retriever.requests[0]
    # 权限过滤必须在检索前完成：user_id / roles 原样透传
    assert (request.user_id, request.roles, request.limit) == (
        "user-1",
        ("USER", "ADMIN"),
        5,
    )


async def test_search_knowledge_disabled_returns_enabled_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retriever = FakeRetriever([_citation(1)])
    monkeypatch.setattr(pc_tools, "get_retriever", lambda: retriever)
    monkeypatch.setattr(pc_tools, "get_settings", lambda: _tool_settings(enabled=False))

    with ToolTurn(("USER",), user_id="user-1"):
        payload = await pc_tools.search_knowledge.ainvoke({"query": "取舍原则"})

    assert payload == {"enabled": False, "citations": [], "truncated": False}
    # 未启用时不得发起任何检索，也不得编造内容
    assert retriever.requests == []


async def test_search_knowledge_noop_retriever_reports_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pc_tools, "get_retriever", NoopRetriever)
    monkeypatch.setattr(pc_tools, "get_settings", lambda: _tool_settings(enabled=True))

    with ToolTurn(("USER",), user_id="user-1"):
        payload = await pc_tools.search_knowledge.ainvoke({"query": "取舍原则"})

    assert payload == {"enabled": False, "citations": [], "truncated": False}


async def test_search_knowledge_degrades_on_retriever_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retriever = FakeRetriever(error=RuntimeError("vector store down"))
    monkeypatch.setattr(pc_tools, "get_retriever", lambda: retriever)
    monkeypatch.setattr(pc_tools, "get_settings", lambda: _tool_settings(enabled=True))

    with ToolTurn(("USER",), user_id="user-1"):
        payload = await pc_tools.search_knowledge.ainvoke({"query": "取舍原则"})

    assert payload["enabled"] is True
    assert payload["citations"] == []
    assert payload["error"] == pc_tools.KNOWLEDGE_UNAVAILABLE_MESSAGE


async def test_search_knowledge_truncates_to_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retriever = FakeRetriever([_citation(index) for index in range(1, 6)])
    monkeypatch.setattr(pc_tools, "get_retriever", lambda: retriever)
    monkeypatch.setattr(pc_tools, "get_settings", lambda: _tool_settings(enabled=True))

    with ToolTurn(("USER",), user_id="user-1"):
        narrow = await pc_tools.search_knowledge.ainvoke({"query": "取舍", "top_k": 2})
        wide = await pc_tools.search_knowledge.ainvoke({"query": "取舍", "top_k": 99})

    assert [item["source_id"] for item in narrow["citations"]] == ["kb-1", "kb-2"]
    assert narrow["truncated"] is True
    assert retriever.requests[0].limit == 3
    # 越界按上限收口：多取一条后仍只返回 6 条
    assert len(wide["citations"]) == 5
    assert wide["truncated"] is False
    assert retriever.requests[1].limit == 7


async def test_search_knowledge_respects_turn_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retriever = FakeRetriever([_citation(1)])
    monkeypatch.setattr(pc_tools, "get_retriever", lambda: retriever)
    monkeypatch.setattr(pc_tools, "get_settings", lambda: _tool_settings(enabled=True))
    tool = registry_module.get_governed_tool("search_knowledge")

    with ToolTurn(("USER",), user_id="user-1"):
        for _ in range(pc_tools.MAX_KNOWLEDGE_CALLS_PER_TURN):
            assert json.loads(await tool.ainvoke({"query": "取舍"}))["enabled"] is True
        limited = await tool.ainvoke({"query": "取舍"})

    assert isinstance(limited, str)
    assert "已达上限" in limited
    assert len(retriever.requests) == pc_tools.MAX_KNOWLEDGE_CALLS_PER_TURN


# ---------------- Architect 集成 ----------------


def _proposal(overrides: dict[str, str] | None = None) -> BuildProposal:
    overrides = overrides or {}
    return BuildProposal(
        selected_components=[
            SelectedComponent(
                category=category,
                hardware_id=overrides.get(category.value, f"{category.value}-id"),
                reason_summary=f"{category.value} 的选型理由",
            )
            for category in REQUIRED_CATEGORIES
        ]
    )


def _candidate_payload(category: str) -> dict[str, Any]:
    return {
        "catalogVersion": "pc-catalog-1",
        "total": 1,
        "list": [
            {
                "hardwareId": f"{category}-id",
                "displayName": f"{category} 展示名",
                "priceFen": 100_000,
                "specifications": {"socket": "AM5"},
            }
        ],
    }


def _compose_build() -> dict[str, Any]:
    components = [
        {
            "category": category.value,
            "hardwareId": f"{category.value}-id",
            "modelName": f"{category.value} 型号",
            "specSummary": "规格摘要",
            "priceFen": 50_000,
            "priceSource": "MOCK_DEMO",
            "purchaseUrl": "https://example.com/item",
            "verifiedAt": "2026-01-01",
        }
        for category in REQUIRED_CATEGORIES
    ]
    return {
        "buildId": "build-knowledge-1",
        "requirements": {"scenario": "BALANCED", "budgetMaxFen": None},
        "components": components,
        "totalPriceFen": sum(item["priceFen"] for item in components),
        "budgetMaxFen": None,
        "budgetStatus": "NO_BUDGET",
        "compatibilityReport": {"overallStatus": "UNKNOWN", "checks": []},
        "verifiedOfferCount": 0,
        "demoOfferCount": 8,
    }


class ArchitectModel:
    """解析走 ainvoke，选型走结构化输出；记录每次选型的上下文。"""

    def __init__(self, proposals: list[BuildProposal | None]) -> None:
        self._proposals = iter(proposals)
        self.structured_prompts: list[str] = []

    async def ainvoke(self, messages: Any, config: Any = None) -> AIMessage:
        del messages, config
        return AIMessage(content=REQUIREMENT_JSON)

    def with_structured_output(self, schema: Any, *, include_raw: bool = False) -> Any:
        del include_raw
        return _StructuredRunnable(self, schema)

    async def astream(
        self, messages: Any, config: Any = None, **_kwargs: Any
    ) -> AsyncIterator[AIMessageChunk]:
        del messages, config
        yield AIMessageChunk(content="这套配置在预算内优先保证游戏性能。")


class _StructuredRunnable:
    def __init__(self, model: ArchitectModel, schema: Any) -> None:
        self._model = model
        self._schema = schema

    async def ainvoke(self, messages: Any, config: Any = None) -> Any:
        del config
        if self._schema is BuildStrategy:
            return {
                "raw": AIMessage(content="{}"),
                "parsed": BuildStrategy(strategy_id="BALANCED", rationale_summary="均衡。"),
                "parsing_error": None,
            }
        human = next(
            (str(message.content) for message in messages if isinstance(message, HumanMessage)),
            "",
        )
        self._model.structured_prompts.append(human)
        proposal = next(self._model._proposals)
        if proposal is None:
            return {
                "raw": AIMessage(content="{}"),
                "parsed": None,
                "parsing_error": ValueError("schema mismatch"),
            }
        return {"raw": AIMessage(content="{}"), "parsed": proposal, "parsing_error": None}


class FakeTool:
    def __init__(self, name: str, payload: Any) -> None:
        self.name = name
        self._payload = payload
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(self, args: dict[str, Any]) -> str:
        self.calls.append(dict(args))
        if isinstance(self._payload, list):
            index = min(len(self.calls) - 1, len(self._payload) - 1)
            payload = self._payload[index]
        else:
            payload = self._payload
        return json.dumps(payload, ensure_ascii=False)


def _install_tools(
    monkeypatch: pytest.MonkeyPatch,
    *,
    knowledge_payloads: list[dict[str, Any]] | None = None,
) -> tuple[FakeTool, FakeTool]:
    compose = FakeTool("compose_pc_build", [{"composed": True, "build": _compose_build()}])
    knowledge = FakeTool(
        "search_knowledge",
        knowledge_payloads or [_knowledge_payload([KNOWLEDGE_CITATION])],
    )
    tools: dict[str, Any] = {
        "search_hardware_candidates": FakeTool(
            "search_hardware_candidates", _candidate_payload("CPU")
        ),
        "get_benchmark_data": FakeTool("get_benchmark_data", {"list": []}),
        "get_verified_offers": FakeTool("get_verified_offers", {"list": []}),
        "compose_pc_build": compose,
        "search_knowledge": knowledge,
    }

    class SearchTool:
        name = "search_hardware_candidates"

        async def ainvoke(self, args: dict[str, Any]) -> str:
            return json.dumps(_candidate_payload(str(args.get("category"))), ensure_ascii=False)

    tools["search_hardware_candidates"] = SearchTool()
    monkeypatch.setattr(nodes_module, "get_governed_tool", tools.get)
    return knowledge, compose


def _patch_node_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    rag_enabled: bool,
    max_knowledge_calls: int = 2,
) -> None:
    """只覆盖 RAG 与知识调用上限，其余配置沿用真实 Settings。"""
    real = nodes_module.get_settings()
    fake = SimpleNamespace(
        rag=real.rag.model_copy(update={"enabled": rag_enabled}),
        agent=real.agent.model_copy(
            update={"architect_max_knowledge_calls": max_knowledge_calls}
        ),
        hitl=real.hitl,
        openui=real.openui,
    )
    monkeypatch.setattr(nodes_module, "get_settings", lambda: fake)


def _graph(model: ArchitectModel) -> Any:
    return build_pc_graph(
        model=model,  # type: ignore[arg-type]
        profile=resolve_profile("pc-config"),
        checkpointer=MemorySaver(),
        selection_mode="llm",
    )


async def _run(agent: Any, thread_id: str) -> dict[str, Any]:
    return await agent.ainvoke(
        {"messages": [HumanMessage("预算一万元，打游戏")], "use_history": True},
        {"configurable": {"thread_id": thread_id}},
    )


async def test_architect_injects_knowledge_but_keeps_proposal_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_node_settings(monkeypatch, rag_enabled=True)
    knowledge, _ = _install_tools(monkeypatch)
    model = ArchitectModel([_proposal()])

    result = await _run(_graph(model), "knowledge-on")
    prompt = model.structured_prompts[0]

    assert result["workflow_status"] == STATUS_SUCCESS
    assert "方法学依据" in prompt
    assert "游戏场景应优先保证显卡预算占比" in prompt
    assert "型号、规格、价格与兼容性只能来自候选清单" in prompt
    assert len(knowledge.calls) == 1
    assert result["knowledge_call_count"] == 1
    assert [item["source_id"] for item in result["knowledge_citations"]] == ["kb-1"]
    # 引用只进入提示词上下文，不进入最终方案字段
    assert set(result["build_proposal"]) == {"selected_components"}
    assert "snippet" not in json.dumps(result["build_proposal"], ensure_ascii=False)


async def test_architect_repair_uses_tradeoff_knowledge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_node_settings(monkeypatch, rag_enabled=True)
    knowledge, _ = _install_tools(
        monkeypatch,
        knowledge_payloads=[
            _knowledge_payload([KNOWLEDGE_CITATION]),
            _knowledge_payload(
                [
                    {
                        **KNOWLEDGE_CITATION,
                        "source_id": "kb-2",
                        "title": "兼容性修正方法",
                        "snippet": "冲突时应优先保留插槽与内存代际一致。",
                    }
                ]
            ),
        ],
    )
    model = ArchitectModel([_proposal({"CPU": "NOT-IN-POOL"}), _proposal()])

    result = await _run(_graph(model), "knowledge-repair")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert len(knowledge.calls) == 2
    assert "候选范围" in knowledge.calls[1]["query"]
    # 修正轮的提示词携带权衡原则，且不出现具体型号结论
    assert "冲突时应优先保留插槽与内存代际一致" in model.structured_prompts[1]
    assert [item["source_id"] for item in result["knowledge_citations"]] == ["kb-1", "kb-2"]


async def test_architect_knowledge_calls_capped_by_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_node_settings(monkeypatch, rag_enabled=True, max_knowledge_calls=1)
    knowledge, _ = _install_tools(monkeypatch)
    model = ArchitectModel([_proposal({"CPU": "NOT-IN-POOL"}), _proposal()])

    result = await _run(_graph(model), "knowledge-capped")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert len(knowledge.calls) == 1
    assert result["knowledge_call_count"] == 1


async def test_architect_completes_when_rag_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_node_settings(monkeypatch, rag_enabled=False)
    knowledge, _ = _install_tools(monkeypatch)

    result = await _run(_graph(ArchitectModel([_proposal()])), "knowledge-off")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert knowledge.calls == []
    assert result["knowledge_citations"] == []
    assert not any(
        event.get("name") == "search_knowledge"
        for event in result.get("tool_events", [])
    )


def test_knowledge_citations_deduped_into_existing_event() -> None:
    from app.services import turn as turn_module

    sent = {"kb-1"}
    chunk = {
        "build_architect": {
            "knowledge_citations": [
                KNOWLEDGE_CITATION,
                {**KNOWLEDGE_CITATION, "source_id": "kb-2"},
                {**KNOWLEDGE_CITATION, "source_id": "kb-2"},
                {"source_id": "kb-3"},
            ]
        }
    }

    events = turn_module._update_events(chunk, [], "", sent)

    assert [event.type for event in events] == ["citations"]
    payload = events[0].data["citations"]
    assert [item["source_id"] for item in payload] == ["kb-2"]
    # 事件字段与既有 RAG 引用完全一致，额外元数据不透传
    assert set(payload[0]) == {"source_id", "title", "snippet", "score"}
    # 同一来源再次出现时不重复下发
    assert turn_module._update_events(chunk, [], "", sent) == []


def test_turn_level_citations_share_dedupe_scope() -> None:
    from app.services import turn as turn_module

    sent: set[str] = set()
    first = turn_module._fresh_citation_payloads(
        [Citation(source_id="kb-1", snippet="片段")], sent
    )
    second = turn_module._fresh_citation_payloads(
        [Citation(source_id="kb-1", snippet="片段"), Citation(source_id="kb-2", snippet="片段")],
        sent,
    )

    assert [item["source_id"] for item in first] == ["kb-1"]
    assert [item["source_id"] for item in second] == ["kb-2"]
