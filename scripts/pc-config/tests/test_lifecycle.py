"""Stage 8.6 生命周期与推荐资格：UNKNOWN 不阻断，CURRENT 不等于 ELIGIBLE。"""

from __future__ import annotations

import json

import pytest

import classify_lifecycle as life
from conftest import REPO_ROOT

REFERENCE = json.loads(
    (REPO_ROOT / "scripts" / "pc-config" / "reference" / "platform-generations.json").read_text(
        encoding="utf-8"
    )
)


def make_record(category: str, specifications: dict, **overrides):
    record = {
        "hardware_id": f"{category.lower()}-test",
        "category": category,
        "specifications": specifications,
        "governance_status": "VALID",
    }
    record.update(overrides)
    return record


@pytest.mark.parametrize(
    ("socket", "expected"),
    [("AM5", "CURRENT"), ("AM4", "MATURE"), ("LGA1200", "LEGACY"), ("LGA775", "DISCONTINUED")],
)
def test_cpu_lifecycle_from_socket_table(socket: str, expected: str) -> None:
    lifecycle, reason = life.lifecycle_for(make_record("CPU", {"socket": socket}), REFERENCE)
    assert lifecycle == expected
    assert reason.startswith("CPU_SOCKET:")


def test_unknown_socket_is_unknown_not_discontinued() -> None:
    lifecycle, _reason = life.lifecycle_for(make_record("CPU", {"socket": "SOCKET-999"}), REFERENCE)
    assert lifecycle == "UNKNOWN"


def test_case_lifecycle_is_always_unknown() -> None:
    lifecycle, reason = life.lifecycle_for(
        make_record("CASE", {"supported_mainboard_form_factors": ["ATX"]}), REFERENCE
    )
    assert lifecycle == "UNKNOWN"
    assert "NO_RELIABLE_RELEASE_DATA" in reason


def test_unknown_lifecycle_does_not_exclude_cpu() -> None:
    record = make_record("CPU", {"socket": "SOCKET-999"})
    recommendation, reason = life.recommendation_for(record, "UNKNOWN")
    assert recommendation == "RESTRICTED"
    assert "UNKNOWN" in reason


def test_current_lifecycle_is_not_automatically_eligible() -> None:
    record = make_record("CPU", {"socket": "AM5"}, governance_status="INCOMPLETE")
    recommendation, _reason = life.recommendation_for(record, "CURRENT")
    assert recommendation == "RESTRICTED"


def test_discontinued_lifecycle_is_excluded() -> None:
    record = make_record("CPU", {"socket": "LGA775"})
    recommendation, reason = life.recommendation_for(record, "DISCONTINUED")
    assert recommendation == "EXCLUDED"
    assert reason == "LIFECYCLE_DISCONTINUED"


def test_case_with_complete_specs_is_eligible_despite_unknown_lifecycle() -> None:
    record = make_record(
        "CASE", {"supported_mainboard_form_factors": ["ATX"], "max_gpu_length_mm": 355}
    )
    recommendation, _reason = life.recommendation_for(record, "UNKNOWN")
    assert recommendation == "ELIGIBLE"


def test_case_missing_compat_field_is_restricted() -> None:
    record = make_record("CASE", {"supported_mainboard_form_factors": []})
    recommendation, reason = life.recommendation_for(record, "UNKNOWN")
    assert recommendation == "RESTRICTED"
    assert "supported_mainboard_form_factors" in reason


def test_invalid_governance_is_excluded_regardless_of_lifecycle() -> None:
    record = make_record("CPU", {"socket": "AM5"}, governance_status="INVALID")
    recommendation, reason = life.recommendation_for(record, "CURRENT")
    assert recommendation == "EXCLUDED"
    assert reason == "GOVERNANCE_INVALID"
