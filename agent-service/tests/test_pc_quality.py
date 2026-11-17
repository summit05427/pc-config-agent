"""质量评审的确定性规则测试。"""

from __future__ import annotations

from typing import Any

from app.agent.pc.quality import (
    MAX_QUALITY_RETRIES,
    NOTICE_BUDGET_RANGE,
    NOTICE_IMBALANCE,
    review_build,
)
from app.agent.pc.schemas import BuildScenario, PCRequirements


def _component(category: str, price_fen: int) -> dict[str, Any]:
    return {"category": category, "priceFen": price_fen}


def _build(cpu_fen: int, gpu_fen: int) -> dict[str, Any]:
    components = [
        _component("CPU", cpu_fen),
        _component("MOTHERBOARD", 59_900),
        _component("MEMORY", 63_900),
        _component("GPU", gpu_fen),
        _component("PSU", 37_400),
        _component("CASE", 19_900),
        _component("COOLER", 12_900),
        _component("STORAGE", 39_900),
    ]
    return {
        "components": components,
        "totalPriceFen": sum(item["priceFen"] for item in components),
    }


def test_flags_cpu_gpu_imbalance_and_requests_retry() -> None:
    review = review_build(
        requirements=PCRequirements(budget_max_fen=2_000_000, scenario=BuildScenario.GAMING),
        build=_build(76_900, 999_900),
        retry_count=0,
    )

    assert review.retry is True
    assert review.issues == ("cpu_gpu_imbalance",)
    assert review.findings[0]["target_value_fen"] == 249_975
    assert review.findings[0]["direction"] == "increase"


def test_stops_retrying_and_emits_notice_after_limit() -> None:
    review = review_build(
        requirements=PCRequirements(budget_max_fen=2_000_000, scenario=BuildScenario.GAMING),
        build=_build(76_900, 999_900),
        retry_count=MAX_QUALITY_RETRIES,
    )

    assert review.retry is False
    assert NOTICE_IMBALANCE in review.notices


def test_office_build_caps_gpu_at_budget_percentage() -> None:
    review = review_build(
        requirements=PCRequirements(budget_max_fen=600_000, scenario=BuildScenario.OFFICE),
        build=_build(76_900, 239_900),
        retry_count=0,
    )

    assert review.retry is True
    assert "office_gpu_overspend" in review.issues
    # 600000 * 15% = 90000 分，低于当前显卡价格
    assert review.findings[0]["target_value_fen"] == 90_000
    assert review.findings[0]["direction"] == "decrease"


def test_media_scenario_uses_office_gpu_policy() -> None:
    review = review_build(
        requirements=PCRequirements(budget_max_fen=2_000_000, scenario=BuildScenario.MEDIA),
        build=_build(100_000, 999_900),
        retry_count=0,
    )

    assert "office_gpu_overspend" in review.issues
    assert review.findings[0]["target_value_fen"] == 300_000


def test_below_budget_min_only_notice_not_retry() -> None:
    review = review_build(
        requirements=PCRequirements(
            budget_min_fen=2_000_000,
            budget_max_fen=3_000_000,
            scenario=BuildScenario.GAMING,
        ),
        build=_build(300_000, 1_000_000),
        retry_count=0,
    )

    assert review.retry is False
    assert "budget_below_range" in review.issues
    assert NOTICE_BUDGET_RANGE in review.notices


def test_balanced_build_passes_without_retry() -> None:
    review = review_build(
        requirements=PCRequirements(budget_max_fen=2_000_000, scenario=BuildScenario.GAMING),
        build=_build(250_000, 1_000_000),
        retry_count=0,
    )

    assert review.retry is False
    assert review.issues == ()
    assert review.notices == ()
