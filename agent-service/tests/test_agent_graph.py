"""PC 配置推荐图测试：固定六节点、五类失败路径与确定性渲染。

测试统一使用假工具与脚本化模型，不访问 Java 服务或真实 LLM。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent import graph as graph_module
from app.agent import pc as pc_package  # noqa: F401  确保包可导入
from app.agent.pc import nodes as nodes_module
from app.agent.pc.graph import PC_GRAPH_NODES, build_pc_graph
from app.agent.pc.nodes import build_result_payload
from app.agent.pc.renderer import OBSERVED_PRICE_NOTICE, render_build_markdown
from app.agent.pc.schemas import (
    REQUIRED_CATEGORIES,
    BuildProposal,
    BuildScenario,
    BuildStrategy,
    Preference,
    RenderMode,
    SelectedComponent,
)
from app.agent.profiles import resolve_profile
from app.agent.registry import ToolExecutionError
from app.core.exceptions import AppError
from app.services.model_resolver import ResolvedRuntime

REQUIREMENT_JSON = json.dumps(
    {"budget_max_fen": 1_000_000, "scenario": "GAMING", "scenario_explicit": True}
)


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


class _StructuredRunnable:
    """按 Schema 分派：策略调用返回固定策略，其余视为选型提案。"""

    def __init__(self, model: PipelineModel, schema: Any) -> None:
        self._model = model
        self._schema = schema

    async def ainvoke(self, messages: Any, config: Any = None) -> Any:
        del messages, config
        if self._schema is BuildStrategy:
            return {
                "raw": AIMessage(content="{}"),
                "parsed": BuildStrategy(
                    strategy_id="BALANCED", rationale_summary="按均衡策略组装。"
                ),
                "parsing_error": None,
            }
        self._model.structured_calls += 1
        return {
            "raw": AIMessage(content="{}"),
            "parsed": self._model.proposal,
            "parsing_error": None,
        }


class PipelineModel:
    """解析走文本，策略与选型走结构化输出，正文走流式调用。"""

    def __init__(
        self,
        *,
        proposal: BuildProposal | None = None,
        reason: str = "这套配置在预算内优先保证了游戏性能与散热余量。",
        requirements: list[str] | None = None,
    ) -> None:
        self.proposal = proposal or _proposal()
        self._reason = reason
        # 解析结果按顺序返回；最后一轮之后复用最后一条（HITL 恢复会重新解析）
        scripted = list(requirements or [REQUIREMENT_JSON])
        self._requirements = iter(scripted)
        self._last_requirement = scripted[-1]
        self.structured_calls = 0

    async def ainvoke(self, messages: Any, config: Any = None) -> AIMessage:
        del messages, config
        try:
            self._last_requirement = next(self._requirements)
        except StopIteration:
            pass
        return AIMessage(content=self._last_requirement)

    def with_structured_output(self, schema: Any, *, include_raw: bool = False) -> Any:
        del include_raw
        return _StructuredRunnable(self, schema)

    async def astream(
        self, messages: Any, config: Any = None, **_kwargs: Any
    ) -> AsyncIterator[AIMessageChunk]:
        """说明节点走流式调用：先给思考分片，再给正文分片。"""
        del messages, config
        yield AIMessageChunk(
            content="", additional_kwargs={"reasoning_content": "先比较取舍。"}
        )
        yield AIMessageChunk(content=self._reason)


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


def _build(
    status: str = "UNKNOWN",
    *,
    workload_profile: str | None = None,
    risk_level: str | None = None,
    scoring_version: str | None = None,
) -> dict[str, Any]:
    components = [
        _component(category.value, 100_000 + index * 10_000)
        for index, category in enumerate(REQUIRED_CATEGORIES)
    ]
    requirements: dict[str, Any] = {
        "budgetMaxFen": 1_000_000,
        "scenario": "GAMING",
        "minMemoryGb": 32,
        "minStorageGb": 1_000,
        "requireVerifiedOffers": False,
    }
    if workload_profile is not None:
        requirements["workloadProfile"] = workload_profile
    check: dict[str, Any] = {
        "ruleId": "case_clearance",
        "ruleName": "机箱散热高度",
        "status": status,
        "message": "缺少机箱最大散热高度数据",
    }
    if risk_level is not None:
        check["riskLevel"] = risk_level
    build: dict[str, Any] = {
        "buildId": "build-1",
        "requirements": requirements,
        "components": components,
        "totalPriceFen": sum(item["priceFen"] for item in components),
        "budgetStatus": "WITHIN_BUDGET",
        "compatibilityReport": {
            "overallStatus": status,
            "checks": [check],
        },
        "verifiedOfferCount": 0,
        "demoOfferCount": 8,
    }
    if scoring_version is not None:
        build["scoringVersion"] = scoring_version
    return build


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
    compose_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """装配查询、组装与增量校验工具替身，返回可观测的调用计数。"""
    counters = {"compose": 0, "partial": 0}
    payloads = compose_payloads or [{"composed": True, "build": _build()}]

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

    class ComposeTool:
        name = "compose_pc_build"

        async def ainvoke(self, args: dict[str, Any]) -> str:
            index = min(counters["compose"], len(payloads) - 1)
            counters["compose"] += 1
            return json.dumps(payloads[index], ensure_ascii=False)

    class PartialTool:
        name = "check_partial_compatibility"

        async def ainvoke(self, args: dict[str, Any]) -> str:
            counters["partial"] += 1
            return json.dumps({"overallStatus": "PASS", "checks": []}, ensure_ascii=False)

    registry: dict[str, Any] = {
        "search_hardware_candidates": SearchTool(),
        "get_benchmark_data": BenchmarkTool(),
        "get_verified_offers": OfferTool(),
        "compose_pc_build": ComposeTool(),
        "check_partial_compatibility": PartialTool(),
    }
    monkeypatch.setattr(nodes_module, "get_governed_tool", registry.get)
    return counters


def _graph(model: PipelineModel | None = None):
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


def test_graph_contains_pipeline_and_hitl_gates() -> None:
    graph = _graph().get_graph()
    assert set(PC_GRAPH_NODES) <= set(graph.nodes)
    assert {"clarification_gate", "compatibility_gate"} <= set(graph.nodes)
    assert "tools" not in graph.nodes
    assert {"build_solver", "build_validator"} & set(graph.nodes) == set()


async def test_clarification_path_skips_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    counters = _install_tools(monkeypatch)
    result = await _invoke(_graph(), "帮我配台电脑", "clarify")
    assert result["workflow_status"] == "clarification"
    assert "预算" in result["messages"][-1].content
    assert counters["compose"] == 0


async def test_success_path_renders_deterministic_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_tools(monkeypatch)
    result = await _invoke(_graph(PipelineModel()), "预算一万元，打游戏", "success")
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


async def test_streams_reasoning_and_chunks_final_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成功路径以 custom 流下发思考与正文分片，拼接结果必须等于最终消息。"""
    _install_tools(monkeypatch)
    agent = _graph(PipelineModel())
    events = [
        event
        async for event in agent.astream(
            {"messages": [HumanMessage("预算一万元，打游戏")], "use_history": True},
            {"configurable": {"thread_id": "stream"}},
            stream_mode=["messages", "updates", "custom"],
        )
    ]
    custom = [payload for mode, payload in events if mode == "custom"]
    final = next(
        message.content
        for mode, update in events
        if mode == "updates" and "response_generator" in update
        for message in update["response_generator"]["messages"]
    )

    kinds = [payload["kind"] for payload in custom]
    # 思考必须先于正文：用户先看到思考过程，思考结束后才出现最终结果
    assert kinds.index("reasoning") < kinds.index("token")
    assert len([p for p in custom if p["kind"] == "token"]) > 1
    assert "".join(p["text"] for p in custom if p["kind"] == "token") == final


async def test_platform_observed_prices_are_not_reported_as_demo() -> None:
    """平台观测价是真实在售参考价，不能沿用演示价文案。"""
    build = _build()
    build["offerDataStatus"] = "PLATFORM_OBSERVED_ONLY"
    # Java 的 demoOfferCount 把「非 OWNER_VERIFIED」都计入，这里刻意保留以验证不误判
    build["demoOfferCount"] = 8
    for component in build["components"]:
        component["priceSource"] = "PLATFORM_OBSERVED"

    content = render_build_markdown(build, "推荐说明。")

    assert "演示价格" not in content
    assert OBSERVED_PRICE_NOTICE in content


async def test_model_reason_with_digits_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_tools(monkeypatch)
    model = PipelineModel(reason="这套配置售价 8299 元，显卡型号很强。")
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


@pytest.mark.parametrize(
    ("text", "expected_min", "expected_max", "expected_scenario"),
    [
        ("预算：12000–20000 元", 1_200_000, 2_000_000, BuildScenario.BALANCED),
        ("预算：20000 元以上", 2_000_000, None, BuildScenario.BALANCED),
        ("6000 元办公和网课，安静优先", None, 600_000, BuildScenario.OFFICE),
        ("20000 元家庭影音 / HTPC", None, 2_000_000, BuildScenario.MEDIA),
        ("1.5 万元打游戏", None, 1_500_000, BuildScenario.GAMING),
    ],
)
def test_fallback_budget_keeps_range_and_open_ended_semantics(
    text: str,
    expected_min: int | None,
    expected_max: int | None,
    expected_scenario: BuildScenario,
) -> None:
    requirements = nodes_module.fallback_requirements(text)

    assert requirements.budget_min_fen == expected_min
    assert requirements.budget_max_fen == expected_max
    assert requirements.scenario is expected_scenario


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("预算 20000 元，用 CPU 渲染", RenderMode.CPU),
        ("预算 20000 元，用 GPU 渲染", RenderMode.GPU),
        ("预算 20000 元，CPU 和 GPU 都要，主要渲染", RenderMode.BOTH),
        ("预算 20000 元，只要渲染快一点", None),
    ],
)
def test_fallback_rendering_records_render_mode_only_when_explicit(
    text: str, expected: RenderMode | None
) -> None:
    requirements = nodes_module.fallback_requirements(text)

    assert requirements.scenario is BuildScenario.RENDERING
    assert requirements.render_mode is expected


async def test_rendering_without_render_mode_asks_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counters = _install_tools(monkeypatch)

    result = await _invoke(_graph(None), "我想配台做渲染的机器", "render-clarify")

    assert result["workflow_status"] == "clarification"
    assert "CPU 还是 GPU" in result["messages"][-1].content
    assert result["requirements"]["render_mode"] is None
    assert "render_mode" in result["requirements"]["missing_fields"]
    assert counters["compose"] == 0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8000 元，打游戏，性价比优先", Preference.VALUE),
        ("10000 元，打游戏，性能优先", Preference.PERFORMANCE),
        ("8000 元，打游戏", None),
    ],
)
def test_preference_is_detected_only_from_explicit_wording(
    text: str, expected: Preference | None
) -> None:
    """偏好只取用户原话中的明确措辞，不按场景或预算猜测。"""
    requirements = nodes_module.fallback_requirements(text)

    assert requirements.preference is expected


def test_build_result_payload_projects_java_workload_and_risk() -> None:
    build = _build(
        workload_profile="AI_INFERENCE",
        risk_level="ADVISORY",
        scoring_version="scoring-2026-11",
    )

    payload = build_result_payload(
        {
            "workflow_status": "success",
            "build_result": build,
            "requirements": {"scenario": "AI_INFERENCE"},
            "reason_summary": None,
        }
    )

    assert payload is not None
    assert payload["workload_profile"] == "AI_INFERENCE"
    assert payload["scoring_version"] == "scoring-2026-11"
    assert payload["compatibility"][0]["risk_level"] == "ADVISORY"


def test_build_result_payload_falls_back_without_fabricating_java_fields() -> None:
    build = _build()

    payload = build_result_payload(
        {
            "workflow_status": "success",
            "build_result": build,
            "requirements": {"scenario": "RENDERING"},
            "reason_summary": None,
        }
    )

    assert payload is not None
    # Java 未返回 workloadProfile 时用本地场景兜底
    assert payload["workload_profile"] == "RENDERING"
    # 缺失字段必须省略，不能补默认值冒充 Java 结论
    assert "scoring_version" not in payload
    assert "component_reasons" not in payload
    assert "risk_level" not in payload["compatibility"][0]


def test_build_result_payload_passes_through_component_reasons() -> None:
    build = _build()
    component_reasons = {
        "CPU": "多核性能满足编译与多任务需求",
        "GPU": "显存容量符合本地推理要求",
    }
    build["componentReasons"] = component_reasons

    payload = build_result_payload(
        {
            "workflow_status": "success",
            "build_result": build,
            "requirements": {"scenario": "PROGRAMMING"},
            "reason_summary": None,
        }
    )

    assert payload is not None
    # Java 生成的理由原样透传，Agent 不改写也不补写
    assert payload["component_reasons"] == component_reasons


@pytest.mark.parametrize(
    ("scenario", "needle"),
    [
        ("RENDERING", "多核吞吐"),
        ("AI_INFERENCE", "显存"),
        ("VIDEO_EDITING", "剪辑"),
    ],
)
def test_deterministic_reason_covers_new_workload_profiles(
    scenario: str, needle: str
) -> None:
    build = _build()
    build["requirements"]["scenario"] = scenario

    reason = nodes_module._deterministic_reason(
        {"build_result": build, "requirements": {"scenario": scenario}}
    )

    assert needle in reason


def test_deterministic_reason_distinguishes_preference() -> None:
    build = _build()

    def reason_of(preference: Preference | None) -> str:
        requirements: dict[str, Any] = {"scenario": "GAMING"}
        if preference is not None:
            requirements["preference"] = preference
        return nodes_module._deterministic_reason(
            {"build_result": build, "requirements": requirements}
        )

    assert "按性价比优先" in reason_of(Preference.VALUE)
    assert "按性能总分优先" in reason_of(Preference.PERFORMANCE)
    neutral = reason_of(None)
    assert "按性价比优先" not in neutral
    assert "按性能总分优先" not in neutral
    assert "没有指定" in neutral


def test_value_preference_without_budget_uses_neutral_wording() -> None:
    build = _build()
    build["requirements"]["budgetMaxFen"] = None

    reason = nodes_module._deterministic_reason(
        {"build_result": build, "requirements": {"preference": Preference.VALUE}}
    )

    # 没有预算时 Java 不会按性价比排序，兜底说明不得声称做了该优化
    assert "按性价比优先" not in reason
    assert "按默认性能排序" in reason


async def test_runtime_is_not_persisted(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_tools(monkeypatch)
    agent = _graph(PipelineModel())
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
    """带运行时模型时，解析、策略、选型与说明四次调用各上报一条用量。"""
    _install_tools(monkeypatch)
    records: list[Any] = []

    async def capture(record: Any) -> None:
        records.append(record)

    monkeypatch.setattr("app.agent.pc.llm.record_usage", capture)
    model = PipelineModel(reason="这套配置更偏向游戏性能。")
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
    assert len(records) == 4
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
