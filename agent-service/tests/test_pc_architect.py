"""LLM 选型闭环（Build Architect）的路由、校验与有限修正测试。

全部使用脚本化模型与工具替身，不访问真实 LLM、Java 服务或数据库。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent.pc import nodes as nodes_module
from app.agent.pc import tools as pc_tools
from app.agent.pc.graph import (
    _route_after_quality_review,
    _route_after_retrieval,
    build_pc_graph,
)
from app.agent.pc.nodes import ARCHITECT_MAX_REPAIRS, build_result_payload
from app.agent.pc.renderer import render_failure_markdown
from app.agent.pc.schemas import (
    REQUIRED_CATEGORIES,
    BuildProposal,
    BuildStrategy,
    SelectedComponent,
)
from app.agent.pc.status import (
    FAILURE_BUDGET_EXCEEDED,
    FAILURE_CANDIDATE_NOT_IN_POOL,
    FAILURE_MODEL_UNAVAILABLE,
    FAILURE_QUALITY_CONSTRAINT,
    STATUS_ARCHITECT_FAILED,
    STATUS_RETRIEVED,
    STATUS_RETRY,
    STATUS_SUCCESS,
)
from app.agent.profiles import resolve_profile
from app.agent.prompts import load_pc_prompt
from app.agent.tool_context import ToolTurn
from app.core.config import AuthSettings, Settings
from app.services import control_plane
from app.services.control_plane import ControlPlaneError

REQUIREMENT_JSON = json.dumps(
    {"budget_max_fen": 1_000_000, "scenario": "GAMING", "scenario_explicit": True}
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


def _strategy() -> BuildStrategy:
    """策略调用固定返回合法策略；本文件的断言只关心选型行为。"""
    return BuildStrategy(strategy_id="BALANCED", rationale_summary="按均衡策略组装。")


def _compose_build() -> dict[str, Any]:
    """与 Java compose 成功分支同构的 build；UNKNOWN 用于覆盖兼容性门控。"""
    prices = {"CPU": 300_000, "GPU": 1_000_000}
    components = [
        {
            "category": category.value,
            "hardwareId": f"{category.value}-id",
            "modelName": f"{category.value} 型号",
            "specSummary": "规格摘要",
            "priceFen": prices.get(category.value, 50_000),
            "priceSource": "MOCK_DEMO",
            "purchaseUrl": "https://example.com/item",
            "verifiedAt": "2026-01-01",
        }
        for category in REQUIRED_CATEGORIES
    ]
    return {
        "buildId": "build-llm-1",
        "requirements": {"scenario": "BALANCED", "budgetMaxFen": None},
        "components": components,
        "totalPriceFen": sum(item["priceFen"] for item in components),
        "budgetMaxFen": None,
        "budgetStatus": "NO_BUDGET",
        "compatibilityReport": {
            "overallStatus": "UNKNOWN",
            "checks": [
                {
                    "ruleId": "case_clearance",
                    "ruleName": "机箱散热高度",
                    "status": "UNKNOWN",
                    "message": "缺少机箱最大散热高度数据",
                }
            ],
        },
        "verifiedOfferCount": 0,
        "demoOfferCount": 8,
    }


def _build_with_prices(cpu_fen: int, gpu_fen: int) -> dict[str, Any]:
    """在成功构型骨架上替换 CPU/GPU 价格，用于触发质量评审与重解。"""
    build = _compose_build()
    prices = {"CPU": cpu_fen, "GPU": gpu_fen}
    for component in build["components"]:
        component["priceFen"] = prices.get(component["category"], component["priceFen"])
    build["totalPriceFen"] = sum(item["priceFen"] for item in build["components"])
    return build


class ArchitectModel:
    """解析走 ainvoke，选型走结构化输出，正文走 astream。"""

    def __init__(self, proposals: list[BuildProposal | None]) -> None:
        self._proposals = iter(proposals)
        self.structured_calls = 0
        self.structured_prompts: list[str] = []

    async def ainvoke(self, messages: Any, config: Any = None) -> AIMessage:
        return AIMessage(content=REQUIREMENT_JSON)

    def with_structured_output(self, schema: Any, *, include_raw: bool = False) -> Any:
        del include_raw
        return _StructuredRunnable(self, schema)

    async def astream(
        self, messages: Any, config: Any = None, **_kwargs: Any
    ) -> AsyncIterator[AIMessageChunk]:
        yield AIMessageChunk(content="这套配置在预算内优先保证游戏性能与散热余量。")


class _StructuredRunnable:
    """按 Schema 分派：策略调用不占用提案队列，也不计入选型调用次数。"""

    def __init__(self, model: ArchitectModel, schema: Any) -> None:
        self._model = model
        self._schema = schema

    async def ainvoke(self, messages: Any, config: Any = None) -> Any:
        del config
        if self._schema is BuildStrategy:
            return {"raw": AIMessage(content="{}"), "parsed": _strategy(), "parsing_error": None}
        self._model.structured_calls += 1
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
        if isinstance(self._payload, BaseException):
            raise self._payload
        return json.dumps(self._payload, ensure_ascii=False)


class ComposeTool:
    def __init__(
        self, outcomes: list[dict[str, Any]], *, name: str = "compose_pc_build"
    ) -> None:
        self.name = name
        self._outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(self, args: dict[str, Any]) -> str:
        self.calls.append(dict(args))
        index = min(len(self.calls) - 1, len(self._outcomes) - 1)
        return json.dumps(self._outcomes[index], ensure_ascii=False)


def _install_tools(
    monkeypatch: pytest.MonkeyPatch,
    *,
    compose_outcomes: list[dict[str, Any]] | None = None,
    solve_outcomes: list[dict[str, Any]] | None = None,
) -> tuple[ComposeTool, ComposeTool]:
    solve = ComposeTool(
        solve_outcomes
        or [{"solved": True, "build": _compose_build(), "failure": None}],
        name="solve_pc_build",
    )
    compose = ComposeTool(
        compose_outcomes or [{"composed": True, "build": _compose_build()}]
    )
    tools: dict[str, Any] = {
        "search_hardware_candidates": FakeTool(
            "search_hardware_candidates", _candidate_payload("CPU")
        ),
        "get_benchmark_data": FakeTool("get_benchmark_data", {"list": []}),
        "get_verified_offers": FakeTool("get_verified_offers", {"list": []}),
        "solve_pc_build": solve,
        "compose_pc_build": compose,
        "validate_pc_build": FakeTool(
            "validate_pc_build",
            {"valid": True, "report": {"overallStatus": "PASS", "checks": []}},
        ),
    }

    class SearchTool:
        name = "search_hardware_candidates"

        async def ainvoke(self, args: dict[str, Any]) -> str:
            category = str(args.get("category"))
            return json.dumps(_candidate_payload(category), ensure_ascii=False)

    tools["search_hardware_candidates"] = SearchTool()
    monkeypatch.setattr(nodes_module, "get_governed_tool", tools.get)
    return solve, compose


def _graph(model: ArchitectModel | None, selection_mode: str) -> Any:
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


def test_default_selection_mode_is_llm(public_key_pem: str, monkeypatch: Any) -> None:
    """默认走 LLM 选型；solver 只能由配置显式选择。"""
    monkeypatch.delenv("AGENT__PC_SELECTION_MODE", raising=False)
    settings = Settings(_env_file=None, auth=AuthSettings(jwt_public_key=public_key_pem))

    assert settings.agent.pc_selection_mode == "llm"


async def test_solver_mode_keeps_solver_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式 solver 模式不得触发 Build Architect，节点序列保持原状。"""
    solve, compose = _install_tools(monkeypatch)
    model = ArchitectModel([_proposal()])

    result = await _run(_graph(model, "solver"), "mode-solver")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert len(solve.calls) == 1
    assert model.structured_calls == 0
    assert compose.calls == []


async def test_llm_mode_composes_valid_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, compose = _install_tools(monkeypatch)
    model = ArchitectModel([_proposal()])

    result = await _run(_graph(model, "llm"), "mode-llm")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert result["selection_mode"] == "llm"
    assert result["build_result"]["buildId"] == "build-llm-1"
    assert result["compatibility_report"]["overallStatus"] == "UNKNOWN"
    assert len(result["build_proposal"]["selected_components"]) == len(REQUIRED_CATEGORIES)
    assert result["architect_repair_count"] == 0
    # 候选清单是紧凑摘要，且明确要求只能从其中选择
    assert "只能选择以下硬件 ID" in model.structured_prompts[0]
    assert "CPU-id" in model.structured_prompts[0]
    # 预算上限与八类 ID 原样传给 Java；价格不由模型提供
    assert compose.calls[0]["budget_max_fen"] == 1_000_000
    assert compose.calls[0]["cpu"] == "CPU-id"
    assert compose.calls[0]["case"] == "CASE-id"
    assert "price_fen" not in compose.calls[0]
    assert build_result_payload(result) is not None


async def test_out_of_pool_id_repairs_without_calling_compose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_tools(monkeypatch)
    model = ArchitectModel(
        [_proposal({"CPU": "NOT-IN-POOL"}), _proposal()]
    )

    result = await _run(_graph(model, "llm"), "repair-out-of-pool")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert model.structured_calls == 2
    assert result["architect_repair_count"] == 1
    # 越界提案不能交给 Java：只有修正后的合法提案会组装
    assert FAILURE_CANDIDATE_NOT_IN_POOL in model.structured_prompts[1]
    assert "NOT-IN-POOL" in model.structured_prompts[1]


async def test_budget_exceeded_repairs_once_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, compose = _install_tools(
        monkeypatch,
        compose_outcomes=[
            {
                "composed": False,
                "failure": {
                    "reason": FAILURE_BUDGET_EXCEEDED,
                    "message": "配置总价超过预算上限",
                    "retryable": True,
                },
            },
            {"composed": True, "build": _compose_build()},
        ],
    )
    model = ArchitectModel([_proposal(), _proposal()])

    result = await _run(_graph(model, "llm"), "repair-budget")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert len(compose.calls) == 2
    assert result["architect_repair_count"] == 1
    assert FAILURE_BUDGET_EXCEEDED in model.structured_prompts[1]


async def test_repair_limit_fails_without_returning_unverified_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, compose = _install_tools(monkeypatch)
    model = ArchitectModel([_proposal({"CPU": "BAD"})] * (ARCHITECT_MAX_REPAIRS + 1))

    result = await _run(_graph(model, "llm"), "repair-limit")

    assert result["workflow_status"] == STATUS_ARCHITECT_FAILED
    assert model.structured_calls == ARCHITECT_MAX_REPAIRS + 1
    assert compose.calls == []
    assert result["build_result"] is None
    assert result["build_failure"]["failure_type"] == FAILURE_CANDIDATE_NOT_IN_POOL
    assert result["architect_repair_count"] == ARCHITECT_MAX_REPAIRS
    assert build_result_payload(result) is None
    assert "暂时没有生成可用配置" in render_failure_markdown(result)


async def test_llm_quality_retry_injects_structured_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 模式质量重解回到 Architect，并把结构化反馈注入提示词。"""
    _install_tools(
        monkeypatch,
        compose_outcomes=[
            {"composed": True, "build": _build_with_prices(50_000, 1_000_000)},
            {"composed": True, "build": _compose_build()},
        ],
    )
    model = ArchitectModel([_proposal(), _proposal()])

    result = await _run(_graph(model, "llm"), "quality-llm")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert model.structured_calls == 2
    assert result["quality_retry_count"] == 1
    assert result["architect_repair_count"] == 0
    assert result["quality_feedback"]["failure_type"] == FAILURE_QUALITY_CONSTRAINT
    retry_prompt = model.structured_prompts[1]
    assert FAILURE_QUALITY_CONSTRAINT in retry_prompt
    assert "受影响类别：CPU" in retry_prompt
    assert "当前值：¥500.00" in retry_prompt
    assert "目标值：¥2,500.00" in retry_prompt
    assert "必须保持不变" in retry_prompt
    assert "提高（不低于目标值）" in retry_prompt
    # 求解器参数不得原样进入模型上下文
    assert "minCpuPriceFen" not in retry_prompt
    assert "maxGpuPriceFen" not in retry_prompt


async def test_solver_quality_retry_keeps_solver_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """solver 模式质量重解仍走 build_solver，并携带原有价格约束参数。"""
    solve, _ = _install_tools(
        monkeypatch,
        solve_outcomes=[
            {
                "solved": True,
                "build": _build_with_prices(50_000, 1_000_000),
                "failure": None,
            },
            {"solved": True, "build": _compose_build(), "failure": None},
        ],
    )

    result = await _run(_graph(None, "solver"), "quality-solver")

    assert result["workflow_status"] == STATUS_SUCCESS
    assert len(solve.calls) == 2
    assert solve.calls[1]["min_cpu_price_fen"] == 250_000
    assert result.get("quality_feedback") is None


async def test_model_none_fails_without_solver_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    solve, compose = _install_tools(monkeypatch)
    model = ArchitectModel([None])

    result = await _run(_graph(model, "llm"), "model-none")

    assert result["workflow_status"] == STATUS_ARCHITECT_FAILED
    assert model.structured_calls == 1
    assert compose.calls == []
    assert solve.calls == []
    assert result["build_failure"]["failure_type"] == FAILURE_MODEL_UNAVAILABLE
    assert build_result_payload(result) is None


async def test_compose_tool_returns_structured_business_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingClient:
        async def compose(self, request: dict[str, Any], *, user_token: str) -> Any:
            del request, user_token
            raise ControlPlaneError(
                control_plane.PC_BUDGET_EXCEEDED, 422, "配置总价超过预算上限"
            )

    monkeypatch.setattr(pc_tools, "get_pc_client", lambda: FailingClient())
    with ToolTurn(("USER",), user_token="user-token"):
        result = await pc_tools.compose_pc_build.ainvoke(
            {category.value.lower(): f"{category.value}-id" for category in REQUIRED_CATEGORIES}
        )

    assert result["composed"] is False
    assert result["failure"]["reason"] == FAILURE_BUDGET_EXCEEDED
    assert result["failure"]["retryable"] is True


async def test_compose_tool_requires_user_token() -> None:
    result = await pc_tools.compose_pc_build.ainvoke(
        {category.value.lower(): f"{category.value}-id" for category in REQUIRED_CATEGORIES}
    )

    assert result["composed"] is False
    assert result["failure"]["reason"] == "USER_TOKEN_MISSING"
    assert result["failure"]["retryable"] is False


async def test_compose_tool_forwards_user_token_and_eight_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class Client:
        async def compose(
            self, request: dict[str, Any], *, user_token: str
        ) -> dict[str, Any]:
            captured["request"] = request
            captured["user_token"] = user_token
            return {"buildId": "composed-1"}

    monkeypatch.setattr(pc_tools, "get_pc_client", lambda: Client())
    args = {category.value.lower(): f"{category.value}-id" for category in REQUIRED_CATEGORIES}
    args["budget_max_fen"] = 500_000

    with ToolTurn(("USER",), user_token="user-token"):
        result = await pc_tools.compose_pc_build.ainvoke(args)

    assert result == {"composed": True, "build": {"buildId": "composed-1"}}
    assert captured["user_token"] == "user-token"
    assert captured["request"]["components"]["case"] == "CASE-id"
    assert captured["request"]["budgetMaxFen"] == 500_000


def test_selection_mode_only_changes_configured_edges() -> None:
    """路由只读枚举状态与配置：solver 不经过 Architect，llm 走 Architect。"""
    retrieved = {"workflow_status": STATUS_RETRIEVED}
    assert _route_after_retrieval(retrieved, selection_mode="solver") == "build_solver"
    assert _route_after_retrieval(retrieved, selection_mode="llm") == "build_architect"
    # 质量重解同样按模式回流，回环上限由 quality.py 与 ARCHITECT_MAX_REPAIRS 控制
    retry = {"workflow_status": STATUS_RETRY}
    assert _route_after_quality_review(retry, selection_mode="solver") == "build_solver"
    assert _route_after_quality_review(retry, selection_mode="llm") == "build_architect"


def test_pc_build_error_codes_keep_business_semantics() -> None:
    error = control_plane._map_error(422, {"code": 40309})

    assert error.code == control_plane.PC_BUDGET_EXCEEDED
    assert error.status_code == 422


def test_build_architect_prompt_is_loaded_from_pc_subdirectory() -> None:
    content = load_pc_prompt("build-architect")

    assert "BuildProposal" in content
    assert "只能选择候选清单中出现的" in content
