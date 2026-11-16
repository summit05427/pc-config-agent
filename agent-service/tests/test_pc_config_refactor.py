"""PC 配置重构 Stage 1：候选摘要、结构化调用与 BuildProposal Schema。

只验证新增的纯逻辑，不访问 Java 服务或真实模型。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.constants import TAG_NOSTREAM
from pydantic import ValidationError

from app.agent.pc import nodes as nodes_module
from app.agent.pc.llm import invoke_model_structured
from app.agent.pc.schemas import (
    REQUIRED_CATEGORIES,
    BuildProposal,
    SelectedComponent,
)
from app.agent.pc.status import STATUS_NO_CANDIDATES, STATUS_RETRIEVED, STATUS_UPSTREAM_ERROR

SUMMARY_KEYS = {
    "hardware_id",
    "display_name",
    "socket",
    "memory_type",
    "form_factor",
    "tdp_watt",
    "vram_gb",
    "length_mm",
    "capacity_gb",
    "price_fen",
    "data_quality_status",
    "lifecycle_status",
    "missing_fields",
}


def _candidate(category: str, index: int) -> dict[str, Any]:
    """构造带白名单外字段的候选，用于验证摘要不会整段复制。"""
    return {
        "hardwareId": f"{category}-{index:02d}",
        "brand": "示例品牌",
        "modelName": f"{category} 型号 {index}",
        "displayName": f"{category} 展示名 {index}",
        "specifications": {
            "socket": "AM5",
            "memory_type": "DDR5",
            "form_factor": "ATX",
            "tdp_w": 65 + index,
            "vram_gb": 8 + index,
            "length_mm": 250 + index,
            "capacity_gb": 1_000 + index,
            "fanless": True,
        },
        "specSummary": "一整段规格摘要不应进入 State",
        "dataQualityStatus": "VERIFIED_STRUCTURED",
        "lifecycleStatus": "ACTIVE",
        "recommendationStatus": "RECOMMENDED",
        "missingFields": ["height_mm", ""],
        "purchaseUrl": "https://example.com/item",
        "priceFen": 123_400,
    }


class _SearchTool:
    name = "search_hardware_candidates"

    def __init__(self, payloads: dict[str, Any]) -> None:
        self._payloads = payloads

    async def ainvoke(self, args: dict[str, Any]) -> str:
        payload = self._payloads[str(args.get("category"))]
        if isinstance(payload, BaseException):
            raise payload
        return json.dumps(payload, ensure_ascii=False)


def _candidate_payload(category: str, count: int) -> dict[str, Any]:
    return {
        "catalogVersion": "pc-catalog-1",
        "total": count,
        "list": [_candidate(category, index) for index in range(count)],
    }


async def test_candidate_sets_keep_whitelisted_fields_and_truncate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = {"CPU": 25, "GPU": 22, "MOTHERBOARD": 12}
    payloads = {
        category.value: _candidate_payload(
            category.value, counts.get(category.value, 1)
        )
        for category in REQUIRED_CATEGORIES
    }
    monkeypatch.setattr(
        nodes_module,
        "get_governed_tool",
        lambda name: _SearchTool(payloads) if name == _SearchTool.name else None,
    )

    result = await nodes_module.candidate_retriever({})  # type: ignore[arg-type]

    assert result["workflow_status"] == STATUS_RETRIEVED
    # 原有 candidate_pool 输出保持不变
    assert result["candidate_pool"]["category_counts"]["CPU"] == 25
    assert result["candidate_pool"]["missing_categories"] == []
    assert result["candidate_pool"]["benchmarks"] == {}
    assert result["candidate_pool"]["offer_summary"] == {}

    candidate_sets = result["candidate_sets"]
    assert len(candidate_sets["CPU"]) == 20
    assert len(candidate_sets["GPU"]) == 20
    assert len(candidate_sets["MOTHERBOARD"]) == 10
    assert len(candidate_sets["MEMORY"]) == 1
    # 超限按工具返回顺序截断，只记录真正被截断的类别
    assert result["candidate_truncated"] == {"CPU": 5, "GPU": 2, "MOTHERBOARD": 2}

    summary = candidate_sets["CPU"][0]
    assert set(summary) == SUMMARY_KEYS
    assert summary["hardware_id"] == "CPU-00"
    assert summary["display_name"] == "CPU 展示名 0"
    # Java 规格字段为 `tdp_w`，State 统一成 `tdp_watt`
    assert summary["tdp_watt"] == 65
    assert summary["price_fen"] == 123_400
    assert summary["missing_fields"] == ["height_mm"]
    # 白名单外字段（型号文本、链接、整段摘要）不得进入 State
    assert "modelName" not in summary
    assert "purchaseUrl" not in summary
    assert "specSummary" not in summary


async def test_unparseable_candidate_list_keeps_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = {
        category.value: {"catalogVersion": "pc-catalog-1", "total": 3, "list": "oops"}
        for category in REQUIRED_CATEGORIES
    }
    monkeypatch.setattr(
        nodes_module,
        "get_governed_tool",
        lambda name: _SearchTool(payloads) if name == _SearchTool.name else None,
    )

    result = await nodes_module.candidate_retriever({})  # type: ignore[arg-type]

    assert result["workflow_status"] == STATUS_UPSTREAM_ERROR
    assert result["candidate_sets"] == {}
    assert result["candidate_pool"]["category_counts"] == {}
    assert result["candidate_pool"]["missing_categories"] == []


async def test_candidate_list_with_non_object_items_is_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = {
        category.value: {"catalogVersion": "pc-catalog-1", "total": 1, "list": [1]}
        for category in REQUIRED_CATEGORIES
    }
    monkeypatch.setattr(
        nodes_module,
        "get_governed_tool",
        lambda name: _SearchTool(payloads) if name == _SearchTool.name else None,
    )

    result = await nodes_module.candidate_retriever({})  # type: ignore[arg-type]

    assert result["workflow_status"] == STATUS_UPSTREAM_ERROR


async def test_empty_candidates_keep_no_candidates_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = {
        category.value: {"catalogVersion": "pc-catalog-1", "total": 0, "list": []}
        for category in REQUIRED_CATEGORIES
    }
    monkeypatch.setattr(
        nodes_module,
        "get_governed_tool",
        lambda name: _SearchTool(payloads) if name == _SearchTool.name else None,
    )

    result = await nodes_module.candidate_retriever({})  # type: ignore[arg-type]

    assert result["workflow_status"] == STATUS_NO_CANDIDATES
    assert set(result["candidate_pool"]["missing_categories"]) == {
        category.value for category in REQUIRED_CATEGORIES
    }


def _components() -> list[dict[str, Any]]:
    return [
        {
            "category": category.value,
            "hardware_id": f"{category.value}-id",
            "reason_summary": f"{category.value} 的选型理由",
        }
        for category in REQUIRED_CATEGORIES
    ]


def test_build_proposal_accepts_exactly_one_component_per_category() -> None:
    proposal = BuildProposal.model_validate({"selected_components": _components()})

    assert {item.category for item in proposal.selected_components} == set(REQUIRED_CATEGORIES)
    assert isinstance(proposal.selected_components[0], SelectedComponent)


def test_build_proposal_rejects_duplicate_category() -> None:
    components = _components()
    components[1]["category"] = "CPU"

    with pytest.raises(ValidationError):
        BuildProposal.model_validate({"selected_components": components})


def test_build_proposal_rejects_missing_category() -> None:
    components = _components()[:-1]

    with pytest.raises(ValidationError):
        BuildProposal.model_validate({"selected_components": components})


def test_build_proposal_rejects_unknown_fields() -> None:
    with_price = _components()
    with_price[0]["price_fen"] = 100

    with_url = _components()
    with_url[0]["purchase_url"] = "https://example.com/item"

    with pytest.raises(ValidationError):
        BuildProposal.model_validate({"selected_components": with_price})
    with pytest.raises(ValidationError):
        BuildProposal.model_validate({"selected_components": with_url})
    with pytest.raises(ValidationError):
        BuildProposal.model_validate({"selected_components": _components(), "price_fen": 100})


def test_build_proposal_rejects_blank_hardware_id() -> None:
    empty = _components()
    empty[0]["hardware_id"] = ""

    blank = _components()
    blank[0]["hardware_id"] = "   "

    with pytest.raises(ValidationError):
        BuildProposal.model_validate({"selected_components": empty})
    with pytest.raises(ValidationError):
        BuildProposal.model_validate({"selected_components": blank})


class _StructuredRunnable:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.configs: list[dict[str, Any] | None] = []

    async def ainvoke(
        self, messages: Any, config: dict[str, Any] | None = None
    ) -> Any:
        self.configs.append(config)
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


class _StructuredModel:
    def __init__(self, outcome: Any) -> None:
        self.runnable = _StructuredRunnable(outcome)
        self.include_raw: bool | None = None

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False
    ) -> _StructuredRunnable:
        self.include_raw = include_raw
        return self.runnable


async def test_structured_call_returns_parsed_proposal_with_nostream_tag() -> None:
    proposal = BuildProposal.model_validate({"selected_components": _components()})
    model = _StructuredModel(
        {"raw": AIMessage(content="{}"), "parsed": proposal, "parsing_error": None}
    )

    result = await invoke_model_structured(
        model,  # type: ignore[arg-type]
        [HumanMessage(content="组装一台电脑")],
        schema=BuildProposal,
        config=None,
        agent_id="pc-config",
        purpose="build_architect",
    )

    assert result is proposal
    assert model.include_raw is True
    # 结构化调用不能进入 `stream_mode=messages` 的正文流
    assert model.runnable.configs[0] == {"tags": [TAG_NOSTREAM]}


async def test_structured_call_returns_none_when_parsing_fails() -> None:
    model = _StructuredModel(
        {
            "raw": AIMessage(content="{}"),
            "parsed": None,
            "parsing_error": ValueError("schema mismatch"),
        }
    )

    result = await invoke_model_structured(
        model,  # type: ignore[arg-type]
        [HumanMessage(content="组装一台电脑")],
        schema=BuildProposal,
        config=None,
        agent_id="pc-config",
        purpose="build_architect",
    )

    assert result is None


async def test_structured_call_returns_none_when_model_raises() -> None:
    model = _StructuredModel(RuntimeError("upstream down"))

    result = await invoke_model_structured(
        model,  # type: ignore[arg-type]
        [HumanMessage(content="组装一台电脑")],
        schema=BuildProposal,
        config=None,
        agent_id="pc-config",
        purpose="build_architect",
    )

    assert result is None


async def test_structured_call_returns_none_without_model() -> None:
    result = await invoke_model_structured(
        None,
        [HumanMessage(content="组装一台电脑")],
        schema=BuildProposal,
        config=None,
        agent_id="pc-config",
        purpose="build_architect",
    )

    assert result is None
