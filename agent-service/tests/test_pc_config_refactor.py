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
from app.agent.pc.llm import (
    extract_json_object,
    invoke_model_structured,
    invoke_model_structured_outcome,
)
from app.agent.pc.schemas import (
    REQUIRED_CATEGORIES,
    BuildProposal,
    SelectedComponent,
)
from app.agent.pc.status import (
    FAILURE_STAGE_PROVIDER_UNSUPPORTED,
    STATUS_NO_CANDIDATES,
    STATUS_RETRIEVED,
    STATUS_UPSTREAM_ERROR,
)
from app.services.model_resolver import ResolvedRuntime

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


class _UnsupportedStructuredRunnable:
    """模拟不支持结构化输出的 Provider：直接返回 None。"""

    def __init__(self, model: _FallbackModel) -> None:
        self._model = model

    async def ainvoke(self, messages: Any, config: Any = None) -> Any:
        del messages, config
        self._model.structured_calls += 1
        return None


class _FallbackModel:
    """结构化输出不可用，文本调用返回脚本化内容，用于验证一次性兜底。"""

    def __init__(self, text: str | None) -> None:
        self._text = text
        self.structured_calls = 0
        self.text_prompts: list[str] = []

    def with_structured_output(self, schema: Any, *, include_raw: bool = False) -> Any:
        del schema, include_raw
        return _UnsupportedStructuredRunnable(self)

    async def ainvoke(self, messages: Any, config: Any = None) -> AIMessage:
        del config
        self.text_prompts.append(str(messages[-1].content))
        return AIMessage(content=self._text or "")


async def test_structured_output_none_falls_back_to_text_json() -> None:
    """Provider 不支持结构化输出时，用注入 JSON Schema 的文本调用补齐。"""
    model = _FallbackModel(
        json.dumps({"selected_components": _components()}, ensure_ascii=False)
    )

    result = await invoke_model_structured(
        model,  # type: ignore[arg-type]
        [HumanMessage(content="组装一台电脑")],
        schema=BuildProposal,
        config=None,
        agent_id="pc-config",
        purpose="build_architect",
    )

    assert isinstance(result, BuildProposal)
    assert model.structured_calls == 1
    assert len(model.text_prompts) == 1
    # Schema 必须真正注入提示词，否则自由文本无法稳定产出八类 ID
    assert "selected_components" in model.text_prompts[0]
    assert "只输出一个 JSON 对象" in model.text_prompts[0]


async def test_structured_output_none_and_fallback_invalid_returns_stage() -> None:
    """兜底解析失败时必须返回 None，并保留第一次失败阶段用于诊断。"""
    model = _FallbackModel("抱歉，我无法给出配置。")

    outcome = await invoke_model_structured_outcome(
        model,  # type: ignore[arg-type]
        [HumanMessage(content="组装一台电脑")],
        schema=BuildProposal,
        config=None,
        agent_id="pc-config",
        purpose="build_architect",
    )

    assert outcome.value is None
    assert outcome.failure_stage == FAILURE_STAGE_PROVIDER_UNSUPPORTED
    assert model.structured_calls == 1
    # 兜底只允许一次，不允许循环重试
    assert len(model.text_prompts) == 1


def test_extract_json_object_repairs_premature_root_close() -> None:
    """模型把根括号写早时，解析应删掉多余的 `}`，而不是整段降级。

    真实样本：`{"role":...,"recommendations":[...]},"risks":[...]}`，
    这个多出来的根闭合括号曾让平台分析师的报告整条丢失。
    """
    text = (
        '{"role":"PLATFORM","summary":"平台分析。"},'
        '"risks":["限高未知"],"affected_categories":["CASE"]}'
    )

    payload = extract_json_object(text)

    assert payload == {
        "role": "PLATFORM",
        "summary": "平台分析。",
        "risks": ["限高未知"],
        "affected_categories": ["CASE"],
    }


def test_extract_json_object_removes_trailing_commas() -> None:
    """尾随逗号是 LLM 另一类高频语法失误，修复后应能正常解析。"""
    payload = extract_json_object('{"a":[1,2,],"b":{"c":3,},}')

    assert payload == {"a": [1, 2], "b": {"c": 3}}


def test_extract_json_object_keeps_valid_payload_untouched() -> None:
    """合法 JSON 必须原样解析，修复逻辑不能改坏嵌套对象与字符串内容。"""
    text = '{"a":{"b":"带,逗号与}括号的文本"},"c":[{"d":1}]}'

    payload = extract_json_object(text)

    assert payload == {"a": {"b": "带,逗号与}括号的文本"}, "c": [{"d": 1}]}


def test_extract_json_object_returns_none_when_unrepairable() -> None:
    """无法确定的损坏不做猜测：宁可降级，也不能产出半真半假的配置。"""
    assert extract_json_object('{"a": [1, 2') is None
    assert extract_json_object("抱歉，我无法给出配置。") is None


class _NamedDeepSeekFallbackModel(_FallbackModel):
    """带网关模型名的替身，用于验证无运行时也能按 provider 前缀预判。"""

    model_name = "deepseek:deepseek-flash"


async def test_deepseek_provider_skips_json_schema_before_first_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预置 Provider 后首次结构化调用直接走文本兜底，不再白付一次 400。

    BYOK 的模型名是网关占位符 `byok-model`，只能依赖运行时 provider 判断。
    """
    records: list[Any] = []

    async def capture(record: Any) -> None:
        records.append(record)

    monkeypatch.setattr("app.agent.pc.llm.record_usage", capture)
    model = _FallbackModel(
        json.dumps({"selected_components": _components()}, ensure_ascii=False)
    )
    runtime = ResolvedRuntime(
        task_id="task-skip",
        provider="deepseek",
        model_key="deepseek:deepseek-flash",
        credential_source="BYOK",
    )

    outcome = await invoke_model_structured_outcome(
        model,  # type: ignore[arg-type]
        [HumanMessage(content="组装一台电脑")],
        schema=BuildProposal,
        config={"configurable": {"thread_id": "skip", "model_runtime": runtime}},
        agent_id="pc-config",
        purpose="build_architect",
    )

    assert isinstance(outcome.value, BuildProposal)
    assert model.structured_calls == 0
    assert len(model.text_prompts) == 1
    # 跳过结构化调用后，用量只有兜底那次文本调用
    assert len(records) == 1


async def test_deepseek_model_name_presets_unsupported_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无运行时配置时，模型名的 `deepseek:` 前缀同样触发预置跳过。"""
    records: list[Any] = []

    async def capture(record: Any) -> None:
        records.append(record)

    monkeypatch.setattr("app.agent.pc.llm.record_usage", capture)
    model = _NamedDeepSeekFallbackModel(
        json.dumps({"selected_components": _components()}, ensure_ascii=False)
    )

    outcome = await invoke_model_structured_outcome(
        model,  # type: ignore[arg-type]
        [HumanMessage(content="组装一台电脑")],
        schema=BuildProposal,
        config=None,
        agent_id="pc-config",
        purpose="build_architect",
    )

    assert isinstance(outcome.value, BuildProposal)
    assert model.structured_calls == 0


class _FakeAuthError(Exception):
    """模拟上游鉴权失败；异常文本含密钥片段，用于验证诊断只取类型与状态码。"""

    status_code = 401

    def __init__(self) -> None:
        super().__init__("Authentication Fails, Your api key: sk-secret-1234 is invalid")


class _AuthFailingRunnable:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, messages: Any, config: Any = None) -> Any:
        del messages, config
        self.calls += 1
        raise _FakeAuthError()


class _AuthFailingModel:
    """结构化与文本通道都失败；文本兜底才是「没有模型输出」的直接原因。"""

    def __init__(self) -> None:
        self.structured_calls = 0
        self.runnable = _AuthFailingRunnable()

    def with_structured_output(self, schema: Any, *, include_raw: bool = False) -> Any:
        del schema, include_raw
        return self.runnable

    async def ainvoke(self, messages: Any, config: Any = None) -> AIMessage:
        del messages, config
        self.runnable.calls += 1
        raise _FakeAuthError()


async def test_structured_failure_exposes_error_type_and_status() -> None:
    """两次都抛错时必须带回异常类型与状态码，且不得透出异常文本。"""
    model = _AuthFailingModel()

    outcome = await invoke_model_structured_outcome(
        model,  # type: ignore[arg-type]
        [HumanMessage(content="组装一台电脑")],
        schema=BuildProposal,
        config=None,
        agent_id="pc-config",
        purpose="build_architect",
    )

    assert outcome.value is None
    assert outcome.error_type == "_FakeAuthError"
    assert outcome.http_status == 401
    # 结构化调用 + 文本兜底各一次
    assert model.runnable.calls == 2


def test_candidate_summary_keeps_blocking_compatibility_fields() -> None:
    """列表型兼容字段必须进入摘要：否则模型只能靠型号猜插槽，compose 必冲突。"""
    cooler = nodes_module._candidate_summary(
        {
            "hardwareId": "cooler-x",
            "displayName": "示例散热器",
            "specifications": {
                "supported_sockets": ["AM4", "AM5"],
                "height_mm": 160,
            },
            "dataQualityStatus": "VERIFIED_STRUCTURED",
            "lifecycleStatus": "CURRENT",
            "missingFields": [],
        }
    )
    assert cooler["supported_sockets"] == "AM4/AM5"
    line = nodes_module.candidate_summary_line(cooler)
    assert "支持插槽=AM4/AM5" in line
    assert "高MM=160" in line

    gpu = nodes_module._candidate_summary(
        {
            "hardwareId": "gpu-x",
            "displayName": "示例显卡",
            "specifications": {
                "external_power": {"connector_type": "PCIE_8PIN", "count": 1}
            },
        }
    )
    assert gpu["external_power"] == "PCIE_8PIN×1"


def test_partial_check_covers_cooler_socket() -> None:
    """散热器必须在增量校验范围内：插槽冲突要在 compose 前暴露并驱动修正。"""
    proposal = BuildProposal(
        selected_components=[
            SelectedComponent(
                category=category,
                hardware_id=f"{category.value.lower()}-x",
                reason_summary="示例理由",
            )
            for category in REQUIRED_CATEGORIES
        ]
    )

    assert "cooler" in nodes_module._partial_check_args(proposal)
