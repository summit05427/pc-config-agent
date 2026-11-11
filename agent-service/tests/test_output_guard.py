"""输出层事实校验：只做可判定的确定性检查。"""

from app.agent.pc.output_guard import (
    RULE_BUDGET_STATUS_MISMATCH,
    RULE_PRICE_TOTAL_MISMATCH,
    RULE_REASON_UNSAFE,
    RULE_UNKNOWN_CLAIMED_COMPATIBLE,
    GuardViolation,
    check_build_output,
    record_violations,
    render_guard_notice,
    sanitize_reason,
)
from app.core.metrics import OUTPUT_GUARD_VIOLATIONS

PASS_REPORT = {"overallStatus": "PASS"}
UNKNOWN_REPORT = {"checks": [{"status": "PASS"}, {"status": "UNKNOWN"}]}


def _build(**overrides: object) -> dict[str, object]:
    build: dict[str, object] = {
        "components": [
            {"category": "CPU", "modelName": "Ryzen 5 7500F", "brand": "AMD", "priceFen": 100000},
            {"category": "GPU", "modelName": "RTX 4060", "brand": "NVIDIA", "priceFen": 200000},
        ],
        "totalPriceFen": 300000,
        "budgetMaxFen": 400000,
        "budgetStatus": "WITHIN_BUDGET",
    }
    build.update(overrides)
    return build


def _rules(violations: list[GuardViolation]) -> list[str]:
    return [violation.rule for violation in violations]


def test_consistent_build_passes() -> None:
    violations = check_build_output(
        build=_build(),
        compatibility_report=PASS_REPORT,
        reason="在预算内优先保证图形性能。",
        markdown="**总价：3000 元**",
    )
    assert violations == []


def test_price_mismatch_is_detected() -> None:
    violations = check_build_output(
        build=_build(totalPriceFen=310000),
        compatibility_report=PASS_REPORT,
        reason="在预算内优先保证图形性能。",
        markdown="**总价：3100 元**",
    )
    assert _rules(violations) == [RULE_PRICE_TOTAL_MISMATCH]


def test_budget_status_mismatch_is_detected() -> None:
    violations = check_build_output(
        build=_build(
            components=[
                {
                    "category": "CPU",
                    "modelName": "Ryzen 5 7500F",
                    "brand": "AMD",
                    "priceFen": 500000,
                }
            ],
            totalPriceFen=500000,
            budgetMaxFen=400000,
        ),
        compatibility_report=PASS_REPORT,
        reason="在预算内优先保证图形性能。",
        markdown="**总价：5000 元**",
    )
    assert _rules(violations) == [RULE_BUDGET_STATUS_MISMATCH]


def test_unknown_compatibility_cannot_be_claimed_as_confirmed() -> None:
    violations = check_build_output(
        build=_build(),
        compatibility_report=UNKNOWN_REPORT,
        reason="这套配置完全兼容，可以直接下单。",
        markdown="**兼容性：未验证**",
    )
    assert _rules(violations) == [RULE_UNKNOWN_CLAIMED_COMPATIBLE]


def test_unknown_compatibility_does_not_flag_explicit_warning() -> None:
    violations = check_build_output(
        build=_build(),
        compatibility_report=UNKNOWN_REPORT,
        reason="机箱散热高度等少数规格尚未验证，装机前请再次确认。",
        markdown="存在未验证项，不能视为已确认兼容。",
    )
    assert violations == []


def test_reason_with_digits_or_model_names_is_unsafe() -> None:
    by_digits = check_build_output(
        build=_build(),
        compatibility_report=PASS_REPORT,
        reason="这套配置大约 3000 元。",
        markdown="",
    )
    by_model = check_build_output(
        build=_build(),
        compatibility_report=PASS_REPORT,
        reason="推荐选择 RTX 4060，性能足够。",
        markdown="",
    )
    assert _rules(by_digits) == [RULE_REASON_UNSAFE]
    assert _rules(by_model) == [RULE_REASON_UNSAFE]


def test_guard_notice_deduplicates_messages() -> None:
    violations = check_build_output(
        build=_build(totalPriceFen=310000, budgetStatus="WITHIN_BUDGET", budgetMaxFen=300000),
        compatibility_report=PASS_REPORT,
        reason="在预算内优先保证图形性能。",
        markdown="",
    )

    notice = render_guard_notice(violations)

    assert notice.count("价格分项与总价不一致") == 1
    assert "预算状态与总价不一致" in notice


def test_sanitize_reason_strips_whitespace_and_rejects_violations() -> None:
    build = _build()

    assert sanitize_reason("  在预算内   优先保证图形性能  ", build) == "在预算内 优先保证图形性能"
    assert sanitize_reason("大约 3000 元", build) is None
    assert sanitize_reason("推荐 RTX 4060", build) is None
    assert sanitize_reason("详见 https://example.com", build) is None
    assert sanitize_reason("长" * 301, build) is None
    assert sanitize_reason("", build) is None


def test_record_violations_increments_metric() -> None:
    before = _guard_count(RULE_REASON_UNSAFE)
    violations = check_build_output(
        build=_build(),
        compatibility_report=PASS_REPORT,
        reason="推荐 3 款。",
        markdown="",
    )

    record_violations(violations, agent_id="pc-config")

    assert _guard_count(RULE_REASON_UNSAFE) == before + 1


def _guard_count(rule: str) -> float:
    for metric in OUTPUT_GUARD_VIOLATIONS.collect():
        for sample in metric.samples:
            if (
                sample.name == "agent_output_guard_violations_total"
                and sample.labels == {"rule": rule}
            ):
                return float(sample.value)
    return 0.0
