"""PC 配置推荐图测试：固定六节点、五类失败路径与确定性渲染。

测试统一使用假工具与脚本化模型，不访问 Java 服务或真实 LLM。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent import graph as graph_module
from app.agent import pc as pc_package  # noqa: F401  确保包可导入
from app.agent.pc import nodes as nodes_module
from app.agent.pc.graph import PC_GRAPH_NODES, build_pc_graph
from app.agent.pc.nodes import build_result_payload
from app.agent.pc.schemas import REQUIRED_CATEGORIES
from app.agent.profiles import resolve_profile
from app.agent.registry import ToolExecutionError
from app.core.exceptions import AppError
from app.services.model_resolver import ResolvedRuntime


class ScriptedModel:
    """按调用顺序返回预设内容；解析节点与说明节点各调用一次。"""

    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.calls: list[list[Any]] = []

    async def ainvoke(self, messages: Any, config: Any = None) -> AIMessage:
        self.calls.append(list(messages))
        return AIMessage(content=next(self._responses))


class FakeTool:
    """返回预设 JSON 或抛出预设异常的工具替身。"""

    def __init__(self, name: str, payload: Any) -> None:
        self.name = name
        self._payload = payload

    async def ainvoke(self, args: dict[str, Any]) -> str:
        if isinstance(self._payload, BaseException):
            raise self._payload
        return json.dumps(self._payload, ensure_ascii=False)


def _component(category: str, price_fen: int, source: str = "MOCK_DEMO") -> dict[str, Any]:
    return {
        "category": category,
        "hardwareId": f"{category}-id",
        "modelName": f"{category} 型号",
        "specSummary": "规格摘要",
        "priceFen": price_fen,
        "priceSource": source,
        "purchaseUrl": "https://example.com/item",
        "verifiedAt": "2026-01-01T00:00:00Z",
        "benchmarkType": "PASSMARK" if category in {"CPU", "GPU"} else None,
        "benchmarkScore": 20000 if category in {"CPU", "GPU"} else None,
    }


def _build(status: str = "UNKNOWN") -> dict[str, Any]:
    components = [
        _component(category.value, 100_000 + index * 10_000)
        for index, category in enumerate(REQUIRED_CATEGORIES)
    ]
    return {
        "buildId": "build-1",
        "requirements": {
            "budgetMaxFen": 1_000_000,
            "scenario": "GAMING",
            "minMemoryGb": 32,
            "minStorageGb": 1_000,
            "requireVerifiedOffers": False,
        },
        "components": components,
        "totalPriceFen": sum(item["priceFen"] for item in components),
        "budgetStatus": "WITHIN_BUDGET",
        "compatibilityReport": {
            "overallStatus": status,
            "checks": [
                {
                    "ruleId": "case_clearance",
                    "ruleName": "机箱散热高度",
                    "status": status,
                    "message": "缺少机箱最大散热高度数据",
                }
            ],
        },
        "verifiedOfferCount": 0,
        "demoOfferCount": 8,
    }


def _candidate_payload(category: str) -> dict[str, Any]:
    return {
        "catalogVersion": "pc-catalog-1",
        "total": 1,
        "list": [
            {
                "hardwareId": f"{category}-id",
                "brand": "示例品牌",
                "modelName": f"{category} 型号",
                "specSummary": "规格摘要",
            }
        ],
    }


def _benchmark_payload(category: str) -> dict[str, Any]:
    return {
        "total": 1,
        "list": [
            {
                "hardwareId": f"{category}-id",
                "benchmarkType": "PASSMARK",
                "score": 20000,
            }
        ],
    }


def _offer_payload() -> dict[str, Any]:
    return {
        "dataStatus": "MIXED",
        "total": 8,
        "verifiedOfferCount": 0,
        "mockOfferCount": 8,
        "list": [],
    }


def _install_tools(
    monkeypatch: pytest.MonkeyPatch,
    *,
    search_fail: bool = False,
    empty_category: str | None = None,
    solve_payload: dict[str, Any] | None = None,
    validate_payloads: list[dict[str, Any] | BaseException] | None = None,
) -> dict[str, int]:
    """装配五类工具替身，返回可观测的调用计数。"""
    counters = {"solve": 0, "validate": 0}
    validate_payloads = validate_payloads or [
        {"valid": True, "report": _build("PASS")["compatibilityReport"]}
    ]

    tools: dict[str, FakeTool] = {}
    for category in REQUIRED_CATEGORIES:
        search_payload: Any = (
            ToolExecutionError("配置数据暂时不可用，请稍后重试")
            if search_fail
            else _candidate_payload(category.value)
        )
        if empty_category == category.value:
            search_payload = {"catalogVersion": "pc-catalog-1", "total": 0, "list": []}
        tools[f"search:{category.value}"] = FakeTool("search_hardware_candidates", search_payload)

    class SearchTool:
        name = "search_hardware_candidates"

        async def ainvoke(self, args: dict[str, Any]) -> str:
            category = str(args.get("category"))
            return await tools[f"search:{category}"].ainvoke(args)

    class BenchmarkTool:
        name = "get_benchmark_data"

        async def ainvoke(self, args: dict[str, Any]) -> str:
            return json.dumps(_benchmark_payload(str(args.get("category"))), ensure_ascii=False)

    class OfferTool:
        name = "get_verified_offers"

        async def ainvoke(self, args: dict[str, Any]) -> str:
            return json.dumps(_offer_payload(), ensure_ascii=False)

    class SolveTool:
        name = "solve_pc_build"

        async def ainvoke(self, args: dict[str, Any]) -> str:
            counters["solve"] += 1
            payload = solve_payload or {"solved": True, "build": _build(), "failure": None}
            return json.dumps(payload, ensure_ascii=False)

    class ValidateTool:
        name = "validate_pc_build"

        async def ainvoke(self, args: dict[str, Any]) -> str:
            index = min(counters["validate"], len(validate_payloads) - 1)
            counters["validate"] += 1
            payload = validate_payloads[index]
            if isinstance(payload, BaseException):
                raise payload
            return json.dumps(payload, ensure_ascii=False)

    registry: dict[str, Any] = {
        "search_hardware_candidates": SearchTool(),
        "get_benchmark_data": BenchmarkTool(),
        "get_verified_offers": OfferTool(),
        "solve_pc_build": SolveTool(),
        "validate_pc_build": ValidateTool(),
    }
    monkeypatch.setattr(nodes_module, "get_governed_tool", registry.get)
    return counters


def _graph(model: ScriptedModel | None = None):
    return build_pc_graph(
        model=model,
        profile=resolve_profile("pc-config"),
        checkpointer=MemorySaver(),
    )


async def _invoke(agent: Any, text: str, thread_id: str = "pc-thread") -> dict[str, Any]:
    return await agent.ainvoke(
        {"messages": [HumanMessage(text)], "use_history": True},
        {"configurable": {"thread_id": thread_id}},
    )


def test_graph_has_exactly_six_nodes() -> None:
    graph = _graph().get_graph()
    assert set(PC_GRAPH_NODES) <= set(graph.nodes)
    assert "tools" not in graph.nodes


async def test_clarification_path_skips_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    counters = _install_tools(monkeypatch)
    result = await _invoke(_graph(), "帮我配台电脑", "clarify")
    assert result["workflow_status"] == "clarification"
    assert "预算" in result["messages"][-1].content
    assert counters["solve"] == 0


async def test_success_path_renders_deterministic_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_tools(monkeypatch)
    model = ScriptedModel(
        [
            json.dumps(
                {
                    "budget_max_fen": 1_000_000,
                    "scenario": "GAMING",
                    "scenario_explicit": True,
                }
            ),
            "这套配置在预算内优先保证了游戏性能与散热余量。",
        ]
    )
    result = await _invoke(_graph(model), "预算一万元，打游戏", "success")
    answer = result["messages"][-1].content
    assert result["workflow_status"] == "success"
    assert "## 推荐配置" in answer
    assert "演示价格，非真实在售" in answer
    # UNKNOWN 保持未验证，不能被写成通过
    assert "未验证" in answer
    assert "**兼容性：未验证**" in answer
    payload = build_result_payload(result)
    assert payload is not None
    assert len(payload["components"]) == len(REQUIRED_CATEGORIES)
    assert payload["total_price_fen"] == result["build_result"]["totalPriceFen"]


async def test_model_reason_with_digits_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_tools(monkeypatch)
    model = ScriptedModel(
        [
            json.dumps({"budget_max_fen": 1_000_000, "scenario": "GAMING"}),
            "这套配置售价 8299 元，显卡型号很强。",
        ]
    )
    result = await _invoke(_graph(model), "预算一万元，打游戏", "unsafe-reason")
    assert "8299" not in result["messages"][-1].content
    assert result["reason_summary"] == nodes_module._deterministic_reason(result)


async def test_no_candidates_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_tools(monkeypatch, empty_category="GPU")
    result = await _invoke(_graph(), "8000 元，打游戏", "no-candidates")
    assert result["workflow_status"] == "no_candidates"
    assert "缺少类别" in result["messages"][-1].content


async def test_upstream_error_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_tools(monkeypatch, search_fail=True)
    result = await _invoke(_graph(), "8000 元，打游戏", "upstream")
    assert result["workflow_status"] == "upstream_error"
    assert "暂时不可用" in result["messages"][-1].content


async def test_no_solution_path_keeps_budget_hard(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_tools(
        monkeypatch,
        solve_payload={
            "solved": False,
            "build": None,
            "failure": {
                "reason": "BUDGET_EXCEEDED",
                "minimumRequiredBudgetFen": 9_500_000,
                "message": "预算不足",
            },
        },
    )
    result = await _invoke(_graph(), "3000 元，打游戏", "no-solution")
    answer = result["messages"][-1].content
    assert result["workflow_status"] == "no_solution"
    assert "预算不足" in answer
    assert "没有放宽你的预算" in answer
    assert build_result_payload(result) is None


async def test_validation_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    counters = _install_tools(
        monkeypatch,
        validate_payloads=[
            {
                "valid": False,
                "report": {
                    "overallStatus": "FAIL",
                    "checks": [{"ruleId": "case", "status": "FAIL", "message": "冲突"}],
                    "hasFailure": True,
                },
            },
            {
                "valid": True,
                "report": _build("PASS")["compatibilityReport"],
            },
        ],
    )
    result = await _invoke(_graph(), "10000 元，打游戏", "retry")
    assert counters["solve"] == 2
    assert result["retry_count"] == 1
    assert result["workflow_status"] == "success"


async def test_validation_failure_after_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    failing = {
        "valid": False,
        "report": {
            "overallStatus": "FAIL",
            "checks": [{"ruleId": "case", "status": "FAIL", "message": "冲突"}],
            "hasFailure": True,
        },
    }
    counters = _install_tools(monkeypatch, validate_payloads=[failing, failing])
    result = await _invoke(_graph(), "10000 元，打游戏", "retry-fail")
    assert counters["solve"] == 2
    assert result["workflow_status"] == "compatibility_failed"
    assert "没有找到兼容的配置" in result["messages"][-1].content


async def test_validation_upstream_failure_keeps_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_tools(
        monkeypatch,
        validate_payloads=[ToolExecutionError("配置数据暂时不可用，请稍后重试")],
    )
    result = await _invoke(_graph(), "10000 元，打游戏", "validate-down")
    assert result["workflow_status"] == "success"
    assert result["compatibility_report"]["overallStatus"] == "UNKNOWN"
    assert "未验证" in result["messages"][-1].content
    assert "兼容性：通过" not in result["messages"][-1].content


async def test_fallback_parser_when_model_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_tools(monkeypatch)
    result = await _invoke(_graph(None), "8000 元，主要打游戏", "fallback")
    assert result["requirements"]["budget_max_fen"] == 800_000
    assert result["requirements"]["scenario"] == "GAMING"
    assert result["workflow_status"] == "success"


async def test_runtime_is_not_persisted(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_tools(monkeypatch)
    agent = _graph(None)
    config = {
        "configurable": {
            "thread_id": "runtime-state",
            "model_runtime": object(),
        }
    }
    await agent.ainvoke({"messages": [HumanMessage("8000 元，打游戏")]}, config)
    snapshot = await agent.aget_state({"configurable": {"thread_id": "runtime-state"}})
    assert "model_runtime" not in snapshot.values


async def test_model_usage_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    """带运行时模型时，解析与说明两次调用各上报一条用量。"""
    _install_tools(monkeypatch)
    records: list[Any] = []

    async def capture(record: Any) -> None:
        records.append(record)

    monkeypatch.setattr("app.agent.pc.llm.record_usage", capture)
    model = ScriptedModel(
        [
            json.dumps({"budget_max_fen": 1_000_000, "scenario": "GAMING"}),
            "这套配置更偏向游戏性能。",
        ]
    )
    runtime = ResolvedRuntime(
        task_id="task-usage",
        provider="openai",
        model_key="openai:gpt-4o-mini",
        credential_source="MANAGED",
    )
    await _graph(model).ainvoke(
        {"messages": [HumanMessage("预算一万元，打游戏")], "use_history": True},
        {"configurable": {"thread_id": "usage", "model_runtime": runtime}},
    )
    assert len(records) == 2
    assert all(record["prompt_tokens"] is None for record in records)
    assert all(record["task_id"] == "task-usage" for record in records)


def test_build_agent_falls_back_when_model_configuration_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_app_error(*args: Any, **kwargs: Any) -> Any:
        raise AppError("未配置模型密钥", code="llm_unavailable", status_code=503)

    monkeypatch.setattr(graph_module, "get_chat_model", raise_app_error)
    agent = graph_module.build_agent(profile=resolve_profile("pc-config"))
    assert set(PC_GRAPH_NODES) <= set(agent.get_graph().nodes)
