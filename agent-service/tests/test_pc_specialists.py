"""多 Agent 骨架测试：确定性开关、并行降级与 Critic 评审/受限修正请求。

全部使用模型替身，不访问真实 LLM、Java 服务或数据库。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from app.agent.pc import specialists
from app.agent.pc.schemas import (
    CriticDecision,
    CriticIssue,
    CriticReport,
    HardwareCategory,
    SpecialistReport,
    SpecialistRole,
)
from app.agent.pc.status import STATUS_RETRY, STATUS_SUCCESS

ALL_CATEGORIES = ("CPU", "MOTHERBOARD", "MEMORY", "GPU", "PSU", "CASE", "COOLER", "STORAGE")


def _patch_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    multi_agent_enabled: bool,
    critic_enabled: bool = True,
) -> None:
    agent = SimpleNamespace(
        multi_agent_enabled=multi_agent_enabled,
        critic_enabled=critic_enabled,
    )
    monkeypatch.setattr(specialists, "get_settings", lambda: SimpleNamespace(agent=agent))


def _candidates(*, per_category: int = 1, name_length: int = 4) -> dict[str, Any]:
    return {
        category: [
            {
                "hardware_id": f"{category}-{index}",
                "display_name": "型" * name_length,
                "price_fen": 100_000 + index,
            }
            for index in range(per_category)
        ]
        for category in ALL_CATEGORIES
    }


def _state(
    *,
    scenario: str = "GAMING",
    candidate_sets: dict[str, Any] | None = None,
    status: str = STATUS_SUCCESS,
    repair_count: int = 0,
) -> dict[str, Any]:
    return {
        "requirements": {
            "scenario": scenario,
            "scenario_explicit": True,
            "budget_max_fen": 1_000_000,
        },
        "build_strategy": {"strategy_id": "BALANCED", "rationale_summary": "按均衡策略组装。"},
        "candidate_sets": _candidates() if candidate_sets is None else candidate_sets,
        "workflow_status": status,
        "architect_repair_count": repair_count,
        "build_result": {
            "components": [
                {
                    "category": category,
                    "modelName": f"{category} 型号",
                    "hardwareId": f"{category}-id",
                    "priceFen": 100_000,
                }
                for category in ALL_CATEGORIES
            ]
        },
        "quality_review": {"issues": [], "notices": []},
    }


def _report(role: SpecialistRole) -> SpecialistReport:
    return SpecialistReport(
        role=role,
        summary="基于给定候选的性能与负载适配分析。",
        recommendations=["优先选择更高显存的显卡"],
        risks=["部分候选缺少跑分数据"],
        affected_categories=[HardwareCategory.GPU],
        evidence=["GPU-0"],
    )


def _critic_report() -> CriticReport:
    return CriticReport(
        decision=CriticDecision.PASS_WITH_DISCLOSURE,
        summary="方案合理，但部分价格来源未核验。",
        issues=[],
    )


@pytest.mark.parametrize(
    ("multi_agent_enabled", "scenario", "candidate_sets", "expected"),
    [
        (False, "GAMING", None, False),
        (True, "GAMING", None, True),
        (True, "OFFICE", None, False),
        (True, "GAMING", {"CPU": []}, False),
    ],
)
def test_should_run_specialists_reads_config_and_enum_only(
    monkeypatch: pytest.MonkeyPatch,
    multi_agent_enabled: bool,
    scenario: str,
    candidate_sets: dict[str, Any] | None,
    expected: bool,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=multi_agent_enabled)
    state = _state(scenario=scenario, candidate_sets=candidate_sets)

    assert specialists.should_run_specialists(state) is expected


def test_should_run_specialists_returns_false_for_invalid_requirements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=True)
    state = {"requirements": {"scenario": "NOT_A_SCENARIO"}, "candidate_sets": _candidates()}

    assert specialists.should_run_specialists(state) is False


async def test_specialist_panel_runs_both_roles_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=True)
    calls: list[tuple[str, list[Any]]] = []

    async def fake_invoke(model: Any, messages: list[Any], **kwargs: Any) -> SpecialistReport:
        del model
        purpose = str(kwargs["purpose"])
        calls.append((purpose, messages))
        role = (
            SpecialistRole.PERFORMANCE
            if purpose.endswith("performance")
            else SpecialistRole.PLATFORM
        )
        return _report(role)

    monkeypatch.setattr(specialists, "invoke_model_structured", fake_invoke)
    prompts = {
        SpecialistRole.PERFORMANCE: "性能分析师提示词",
        SpecialistRole.PLATFORM: "平台分析师提示词",
    }

    update = await specialists.specialist_panel(
        _state(), {}, model=None, agent_id="pc-config", prompts=prompts
    )

    assert update["specialist_roles_used"] == ["PERFORMANCE", "PLATFORM"]
    assert set(update["specialist_reports"]) == {"PERFORMANCE", "PLATFORM"}
    assert {purpose for purpose, _ in calls} == {
        "specialist_performance",
        "specialist_platform",
    }
    context = next(
        str(message.content)
        for message in calls[0][1]
        if isinstance(message, HumanMessage)
    )
    assert "CPU-0" in context
    assert len(context) <= specialists.SPECIALIST_MAX_CONTEXT_CHARS


async def test_specialist_panel_truncates_long_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=True)
    captured: list[str] = []

    async def fake_invoke(model: Any, messages: list[Any], **kwargs: Any) -> SpecialistReport:
        del model, kwargs
        captured.extend(
            str(message.content) for message in messages if isinstance(message, HumanMessage)
        )
        return _report(SpecialistRole.PERFORMANCE)

    monkeypatch.setattr(specialists, "invoke_model_structured", fake_invoke)
    state = _state(candidate_sets=_candidates(per_category=20, name_length=200))

    await specialists.specialist_panel(
        state,
        {},
        model=None,
        agent_id="pc-config",
        prompts={SpecialistRole.PERFORMANCE: "提示词"},
    )

    assert captured
    assert all(len(context) <= specialists.SPECIALIST_MAX_CONTEXT_CHARS for context in captured)


async def test_specialist_panel_keeps_successful_role_when_peer_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=True)

    async def fake_invoke(model: Any, messages: list[Any], **kwargs: Any) -> Any:
        del model, messages
        if str(kwargs["purpose"]).endswith("performance"):
            return _report(SpecialistRole.PERFORMANCE)
        return None

    monkeypatch.setattr(specialists, "invoke_model_structured", fake_invoke)

    update = await specialists.specialist_panel(
        _state(),
        {},
        model=None,
        agent_id="pc-config",
        prompts={
            SpecialistRole.PERFORMANCE: "性能提示词",
            SpecialistRole.PLATFORM: "平台提示词",
        },
    )

    assert update["specialist_roles_used"] == ["PERFORMANCE"]
    assert set(update["specialist_reports"]) == {"PERFORMANCE"}


async def test_specialist_panel_returns_empty_when_all_roles_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=True)

    async def fake_invoke(model: Any, messages: list[Any], **kwargs: Any) -> Any:
        del model, messages, kwargs
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(specialists, "invoke_model_structured", fake_invoke)

    update = await specialists.specialist_panel(
        _state(),
        {},
        model=None,
        agent_id="pc-config",
        prompts={
            SpecialistRole.PERFORMANCE: "性能提示词",
            SpecialistRole.PLATFORM: "平台提示词",
        },
    )

    assert update == {}


async def test_specialist_panel_skips_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=False)

    async def fake_invoke(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("关闭时不得调用模型")

    monkeypatch.setattr(specialists, "invoke_model_structured", fake_invoke)

    update = await specialists.specialist_panel(
        _state(),
        {},
        model=None,
        agent_id="pc-config",
        prompts={SpecialistRole.PERFORMANCE: "性能提示词"},
    )

    assert update == {}


async def test_critic_review_skips_when_status_is_not_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=True)

    async def fake_invoke(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("非成功状态不得调用 Critic")

    monkeypatch.setattr(specialists, "invoke_model_structured", fake_invoke)

    update = await specialists.critic_review(
        _state(status=STATUS_RETRY), {}, model=None, agent_id="pc-config", critic_prompt="评审"
    )

    assert update == {}


async def test_critic_review_skips_when_switched_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=False, critic_enabled=True)

    async def fake_invoke(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("开关关闭时不得调用 Critic")

    monkeypatch.setattr(specialists, "invoke_model_structured", fake_invoke)

    update = await specialists.critic_review(
        _state(), {}, model=None, agent_id="pc-config", critic_prompt="评审"
    )

    assert update == {}


async def test_critic_review_skips_after_repair_to_stay_within_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """修正已占用最后 1 次调用预算时，Critic 不得继续追加调用。"""
    _patch_settings(monkeypatch, multi_agent_enabled=True, critic_enabled=True)

    async def fake_invoke(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("已发生修正时不得再调用 Critic")

    monkeypatch.setattr(specialists, "invoke_model_structured", fake_invoke)

    update = await specialists.critic_review(
        _state(repair_count=1), {}, model=None, agent_id="pc-config", critic_prompt="评审"
    )

    assert update == {}


async def test_critic_review_returns_report_without_touching_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=True, critic_enabled=True)
    captured: list[str] = []

    async def fake_invoke(model: Any, messages: list[Any], **kwargs: Any) -> CriticReport:
        del model, kwargs
        captured.extend(
            str(message.content) for message in messages if isinstance(message, HumanMessage)
        )
        return _critic_report()

    monkeypatch.setattr(specialists, "invoke_model_structured", fake_invoke)
    state = _state()

    update = await specialists.critic_review(
        state, {}, model=None, agent_id="pc-config", critic_prompt="评审提示词"
    )

    assert set(update) == {"critic_report", "critic_revision_requested"}
    assert update["critic_report"]["decision"] == CriticDecision.PASS_WITH_DISCLOSURE.value
    assert update["critic_revision_requested"] is False
    assert captured and "CPU-id" in captured[0]
    assert len(captured[0]) <= specialists.CRITIC_MAX_CONTEXT_CHARS


@pytest.mark.parametrize(
    ("decision", "severity", "expected"),
    [
        (CriticDecision.REVISE, "HIGH", True),
        (CriticDecision.REVISE, "MEDIUM", True),
        # LOW 只披露，不再追加一次选型调用
        (CriticDecision.REVISE, "LOW", False),
        (CriticDecision.PASS, "HIGH", False),
        (CriticDecision.PASS_WITH_DISCLOSURE, "HIGH", False),
    ],
)
async def test_critic_requests_revision_only_for_actionable_issues(
    monkeypatch: pytest.MonkeyPatch,
    decision: CriticDecision,
    severity: str,
    expected: bool,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=True, critic_enabled=True)
    report = CriticReport(
        decision=decision,
        summary="评审结论",
        issues=[
            CriticIssue(
                severity=severity,  # type: ignore[arg-type]
                categories=[HardwareCategory.GPU],
                description="显卡与机箱存在冲突风险",
            )
        ],
    )

    async def fake_invoke(*args: Any, **kwargs: Any) -> CriticReport:
        del args, kwargs
        return report

    monkeypatch.setattr(specialists, "invoke_model_structured", fake_invoke)

    update = await specialists.critic_review(
        _state(), {}, model=None, agent_id="pc-config", critic_prompt="评审提示词"
    )

    assert update["critic_revision_requested"] is expected


async def test_critic_review_returns_empty_when_model_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, multi_agent_enabled=True, critic_enabled=True)

    async def fake_invoke(model: Any, messages: list[Any], **kwargs: Any) -> None:
        del model, messages, kwargs
        return None

    monkeypatch.setattr(specialists, "invoke_model_structured", fake_invoke)

    update = await specialists.critic_review(
        _state(), {}, model=None, agent_id="pc-config", critic_prompt="评审提示词"
    )

    assert update == {}
