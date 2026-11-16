"""PC 配置重构 Stage 2：配置策略节点与增量兼容性校验。

全部使用脚本化模型与工具替身，不访问真实 LLM、Java 服务或数据库。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError

from app.agent.pc import nodes as nodes_module
from app.agent.pc import tools as pc_tools
from app.agent.pc.graph import _route_after_validation, build_pc_graph
from app.agent.pc.schemas import (
    REQUIRED_CATEGORIES,
    BudgetTendency,
    BuildProposal,
    BuildStrategy,
    HardwareCategory,
    SelectedComponent,
    StrategyId,
)
from app.agent.pc.status import (
    FAILURE_COMPATIBILITY_CONFLICT,
    STATUS_ARCHITECT_FAILED,
    STATUS_SUCCESS,
    STATUS_VALIDATED,
    STRATEGY_SOURCE_DEFAULT,
    STRATEGY_SOURCE_MODEL,
)
from app.agent.profiles import resolve_profile
from app.agent.registry import ToolExecutionError
from app.core.config import AuthSettings, Settings, get_settings
from app.services.pc_client import PcApiClient

REQUIREMENT_JSON = json.dumps(
    {"budget_max_fen": 1_000_000, "scenario": "GAMING", "scenario_explicit": True}
)


def _strategy(**overrides: Any) -> BuildStrategy:
    payload: dict[str, Any] = {
        "strategy_id": "GPU_FIRST",
        "rationale_summary": "游戏负载为主，图形性能优先。",
        "budget_allocation_guidance": [
            {"category": "GPU", "tendency": "HIGHER", "note": "显卡档位优先"},
        ],
        "component_priorities": [
            {"category": "GPU", "focus": "显存容量"},
        ],
        "tradeoff_policy": ["预算冲突时先保显卡，其次保证内存容量。"],
        "retrieval_notes": ["关注显卡长度与机箱限高"],
        "activation_plan": "deferred",
    }
    payload.update(overrides)
    return BuildStrategy.model_validate(payload)


def _proposal() -> BuildProposal:
    return BuildProposal(
        selected_components=[
            SelectedComponent(
                category=category,
                hardware_id=f"{category.value}-id",
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
            "priceFen": 100_000,
            "priceSource": "MOCK_DEMO",
            "purchaseUrl": "https://example.com/item",
            "verifiedAt": "2026-01-01",
        }
        for category in REQUIRED_CATEGORIES
    ]
    return {
        "buildId": "build-stage2",
        "requirements": {"scenario": "GAMING", "budgetMaxFen": 1_000_000},
        "components": components,
        "totalPriceFen": sum(item["priceFen"] for item in components),
        "budgetMaxFen": 1_000_000,
        "budgetStatus": "WITHIN_BUDGET",
        "compatibilityReport": {"overallStatus": "PASS", "checks": []},
        "verifiedOfferCount": 0,
        "demoOfferCount": 8,
    }


def _partial_report(status: str, rule_id: str = "cpu_socket_match") -> dict[str, Any]:
    return {
        "overallStatus": status,
        "checks": [
            {
                "ruleId": rule_id,
                "status": status,
                "componentIds": ["CPU-id", "MOTHERBOARD-id"],
                "missingFields": [],
            }
        ],
    }


class StrategyArchitectModel:
    """按 Schema 分派：策略调用返回 `BuildStrategy`，选型调用返回 `BuildProposal`。"""

    def __init__(
        self,
        *,
        strategies: list[BuildStrategy | None],
        proposals: list[BuildProposal | None],
    ) -> None:
        self._strategies = iter(strategies)
        self._proposals = iter(proposals)
        self.strategy_calls = 0
        self.proposal_calls = 0
        self.prompts: dict[str, list[str]] = {"strategy": [], "architect": []}

    async def ainvoke(self, messages: Any, config: Any = None) -> AIMessage:
        del messages, config
        return AIMessage(content=REQUIREMENT_JSON)

    def with_structured_output(self, schema: Any, *, include_raw: bool = False) -> Any:
        del include_raw
        return _Dispatcher(self, schema)

    async def astream(
        self, messages: Any, config: Any = None, **_kwargs: Any
    ) -> AsyncIterator[AIMessageChunk]:
        del messages, config
        yield AIMessageChunk(content="这套配置在预算内优先保证游戏性能与散热余量。")


class _Dispatcher:
    def __init__(self, model: StrategyArchitectModel, schema: Any) -> None:
        self._model = model
        self._schema = schema

    async def ainvoke(self, messages: Any, config: Any = None) -> Any:
        del config
        human = next(
            (str(message.content) for message in messages if isinstance(message, HumanMessage)),
            "",
        )
        if self._schema is BuildStrategy:
            self._model.strategy_calls += 1
            self._model.prompts["strategy"].append(human)
            return _structured(next(self._model._strategies, None))
        self._model.proposal_calls += 1
        self._model.prompts["architect"].append(human)
        return _structured(next(self._model._proposals, None))


def _structured(parsed: Any) -> dict[str, Any]:
    return {
        "raw": AIMessage(content="{}"),
        "parsed": parsed,
        "parsing_error": None if parsed is not None else ValueError("schema mismatch"),
    }


class StubTool:
    def __init__(self, name: str, payloads: list[Any]) -> None:
        self.name = name
        self._payloads = payloads
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(self, args: dict[str, Any]) -> str:
        self.calls.append(dict(args))
        index = min(len(self.calls) - 1, len(self._payloads) - 1)
        payload = self._payloads[index]
        if isinstance(payload, BaseException):
            raise payload
        return json.dumps(payload, ensure_ascii=False)


def _settings_with_partial_checks(limit: int) -> Settings:
    """只替换增量校验上限，避免改动全局 Settings 单例。"""
    settings = get_settings()
    return settings.model_copy(
        update={"agent": settings.agent.model_copy(update={"architect_max_partial_checks": limit})}
    )


def _install_tools(
    monkeypatch: pytest.MonkeyPatch,
    *,
    partial: list[dict[str, Any]] | None = None,
    compose: list[dict[str, Any]] | None = None,
) -> tuple[StubTool, StubTool]:
    partial_tool = StubTool(
        "check_partial_compatibility", partial or [_partial_report("PASS")]
    )
    compose_tool = StubTool(
        "compose_pc_build", compose or [{"composed": True, "build": _compose_build()}]
    )

    class SearchTool:
        name = "search_hardware_candidates"

        async def ainvoke(self, args: dict[str, Any]) -> str:
            return json.dumps(_candidate_payload(str(args.get("category"))), ensure_ascii=False)

    tools = {
        "search_hardware_candidates": SearchTool(),
        "get_benchmark_data": StubTool("get_benchmark_data", [{"list": []}]),
        "get_verified_offers": StubTool("get_verified_offers", [{"list": []}]),
        "compose_pc_build": compose_tool,
        "check_partial_compatibility": partial_tool,
    }
    monkeypatch.setattr(nodes_module, "get_governed_tool", tools.get)
    return partial_tool, compose_tool


def _graph(model: StrategyArchitectModel, selection_mode: str = "llm") -> Any:
    return build_pc_graph(
        model=model,  # type: ignore[arg-type]
        profile=resolve_profile("pc-config"),
        checkpointer=MemorySaver(),
        selection_mode=selection_mode,
    )


async def _run(agent: Any, thread_id: str) -> dict[str, Any]:
    return await agent.ainvoke(
        {"messages": [HumanMessage("预算一万元，打游戏")], "use_history": True},
        {"configurable": {"thread_id": thread_id}},
    )


def test_build_strategy_accepts_soft_guidance_without_amounts() -> None:
    strategy = _strategy()

    assert strategy.strategy_id is StrategyId.GPU_FIRST
    assert strategy.budget_allocation_guidance[0].tendency is BudgetTendency.HIGHER
    assert strategy.component_priorities[0].category is HardwareCategory.GPU
    assert strategy.activation_plan == "deferred"


def test_build_strategy_rejects_unknown_strategy_id() -> None:
    with pytest.raises(ValidationError):
        _strategy(strategy_id="MAGIC_FIRST")


def test_build_strategy_rejects_activation_plan_other_than_deferred() -> None:
    with pytest.raises(ValidationError):
        _strategy(activation_plan="activate performance specialist")


def test_build_strategy_rejects_extra_fields_and_duplicates() -> None:
    with pytest.raises(ValidationError):
        _strategy(price_fen=100)
    with pytest.raises(ValidationError):
        _strategy(
            component_priorities=[
                {"category": "GPU", "focus": "显存容量"},
                {"category": "GPU", "focus": "频率"},
            ]
        )


async def test_strategy_is_injected_into_architect_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_tools(monkeypatch)
    model = StrategyArchitectModel(strategies=[_strategy()], proposals=[_proposal()])

    result = await _run(_graph(model), "stage2-strategy-context")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert result["strategy_source"] == STRATEGY_SOURCE_MODEL
    assert result["build_strategy"]["strategy_id"] == "GPU_FIRST"
    prompt = model.prompts["architect"][0]
    assert "配置策略（软规划）" in prompt
    assert "GPU_FIRST" in prompt
    assert "显存容量" in prompt
    assert "预算倾向" in prompt
    # 策略只给方向，不得把金额写进提示词
    assert "元" not in prompt.split("## 候选清单")[0].split("## 配置策略")[1]


async def test_strategy_falls_back_to_default_when_model_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_tools(monkeypatch)
    model = StrategyArchitectModel(strategies=[None], proposals=[_proposal()])

    result = await _run(_graph(model), "stage2-strategy-default")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert result["strategy_source"] == STRATEGY_SOURCE_DEFAULT
    assert result["build_strategy"]["strategy_id"] == StrategyId.BALANCED.value
    assert "确定性默认策略" in model.prompts["architect"][0]


def test_llm_mode_routes_through_strategist_and_solver_does_not() -> None:
    """路由只读枚举状态与配置：llm 先定策略，solver 校验后直接检索。"""
    model = StrategyArchitectModel(strategies=[_strategy()], proposals=[_proposal()])
    llm_edges = {(edge.source, edge.target) for edge in _graph(model).get_graph().edges}

    assert ("build_strategist", "candidate_retriever") in llm_edges
    assert "build_strategist" in _graph(model).get_graph().nodes
    validated = {"workflow_status": STATUS_VALIDATED}
    assert _route_after_validation(validated, selection_mode="llm") == "build_strategist"
    assert _route_after_validation(validated, selection_mode="solver") == "candidate_retriever"


async def test_partial_fail_repairs_and_never_composes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partial_tool, compose_tool = _install_tools(
        monkeypatch, partial=[_partial_report("FAIL")]
    )
    monkeypatch.setattr(
        nodes_module, "get_settings", lambda: _settings_with_partial_checks(3)
    )
    model = StrategyArchitectModel(
        strategies=[_strategy()],
        proposals=[_proposal(), _proposal(), _proposal()],
    )

    result = await _run(_graph(model), "stage2-partial-fail")

    assert result["workflow_status"] == STATUS_ARCHITECT_FAILED
    assert compose_tool.calls == []
    assert result["build_result"] is None
    assert result["build_failure"]["failure_type"] == FAILURE_COMPATIBILITY_CONFLICT
    assert "cpu_socket_match" in model.prompts["architect"][1]
    assert "受影响类别：CPU、MOTHERBOARD" in model.prompts["architect"][1]
    assert "必须保持不变" in model.prompts["architect"][1]
    # 三次提案全部先校验，修正次数用尽后失败，从未提交整机
    assert len(partial_tool.calls) == 3
    assert result["partial_check_count"] == 3


async def test_partial_fail_then_pass_composes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partial_tool, compose_tool = _install_tools(
        monkeypatch, partial=[_partial_report("FAIL"), _partial_report("PASS")]
    )
    model = StrategyArchitectModel(
        strategies=[_strategy()], proposals=[_proposal(), _proposal()]
    )

    result = await _run(_graph(model), "stage2-partial-repair")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert len(partial_tool.calls) == 2
    assert len(compose_tool.calls) == 1
    assert result["architect_repair_count"] == 1
    # 增量校验只提交核心组件，ID 来自提案
    assert set(partial_tool.calls[0]) == {"cpu", "motherboard", "memory", "gpu"}


async def test_partial_unknown_does_not_block_compose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partial_tool, compose_tool = _install_tools(
        monkeypatch, partial=[_partial_report("UNKNOWN", "missing_height")]
    )
    model = StrategyArchitectModel(strategies=[_strategy()], proposals=[_proposal()])

    result = await _run(_graph(model), "stage2-partial-unknown")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert len(partial_tool.calls) == 1
    assert len(compose_tool.calls) == 1
    assert result["partial_compatibility_reports"][0]["overallStatus"] == "UNKNOWN"
    assert result["architect_repair_count"] == 0


async def test_partial_checks_stop_at_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partial_tool, compose_tool = _install_tools(
        monkeypatch, partial=[_partial_report("FAIL"), _partial_report("PASS")]
    )
    monkeypatch.setattr(
        nodes_module, "get_settings", lambda: _settings_with_partial_checks(1)
    )
    model = StrategyArchitectModel(
        strategies=[_strategy()], proposals=[_proposal(), _proposal(), _proposal()]
    )

    result = await _run(_graph(model), "stage2-partial-limit")

    assert result["workflow_status"] == STATUS_SUCCESS
    # 超过配置上限后不再调用；整机校验仍由 compose 负责
    assert len(partial_tool.calls) == 1
    assert len(compose_tool.calls) == 1
    assert result["partial_check_count"] == 1


async def test_partial_tool_forwards_selected_subset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class Client:
        async def validate_partial(self, components: dict[str, str]) -> dict[str, Any]:
            captured["components"] = components
            return {"overallStatus": "PASS", "checks": []}

    monkeypatch.setattr(pc_tools, "get_pc_client", lambda: Client())

    result = await pc_tools.check_partial_compatibility.ainvoke(
        {"cpu": "CPU-id", "gpu": "GPU-id"}
    )

    assert result["overallStatus"] == "PASS"
    assert captured["components"] == {"cpu": "CPU-id", "gpu": "GPU-id"}


async def test_partial_tool_rejects_empty_subset() -> None:
    with pytest.raises(ToolExecutionError):
        await pc_tools.check_partial_compatibility.ainvoke({})


async def test_pc_client_posts_partial_validation_payload(public_key_pem: str) -> None:
    class Response:
        status_code = 200
        is_success = True

        def json(self) -> dict[str, Any]:
            return {"code": 0, "data": {"overallStatus": "PASS", "checks": []}}

    class Http:
        def __init__(self) -> None:
            self.requests: list[dict[str, Any]] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> Response:
            self.requests.append({"method": method, "url": url, **kwargs})
            return Response()

    class ControlPlane:
        async def get_service_token(self) -> str:
            return "service-token"

        def _authorized_headers(
            self, service_token: str, user_token: str | None
        ) -> dict[str, str]:
            del user_token
            return {"Authorization": f"Bearer {service_token}"}

    http = Http()
    settings = Settings(_env_file=None, auth=AuthSettings(jwt_public_key=public_key_pem))
    client = PcApiClient(settings, ControlPlane(), client=http)  # type: ignore[arg-type]

    data = await client.validate_partial({"cpu": "CPU-id"})

    assert data["overallStatus"] == "PASS"
    assert http.requests[0]["url"].endswith("/internal/v1/pc/builds/validate-partial")
    assert http.requests[0]["json"] == {"components": {"cpu": "CPU-id"}}
    assert http.requests[0]["headers"]["Authorization"] == "Bearer service-token"
