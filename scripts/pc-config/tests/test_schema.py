"""Stage 8.2 统一 Schema：必填、枚举、未知键与严格兼容模式。"""

from __future__ import annotations

import pytest

from hardware_schema import CATEGORIES, DATA_QUALITY_STATUSES, category_json_schema, validate_record

BASE_SPECS: dict[str, dict[str, object]] = {
    "CPU": {"socket": "AM5", "core_count": 6, "thread_count": 12, "tdp_w": 65},
    "GPU": {"chipset": "GeForce RTX 5060 Ti", "vram_gb": 16, "tdp_w": 180},
    "MOTHERBOARD": {
        "socket": "AM5",
        "chipset": "B650",
        "form_factor": "ATX",
        "memory_type": "DDR5",
    },
    "MEMORY": {"memory_type": "DDR5", "capacity_gb": 32, "speed_mts": 6000},
    "STORAGE": {"capacity_gb": 1024, "interface": "M.2 PCIe 4.0 X4"},
    "COOLER": {"supported_sockets": ["AM5", "LGA1700"], "cooler_type": "AIR"},
    "CASE": {"supported_mainboard_form_factors": ["ATX"], "max_gpu_length_mm": 355},
    "PSU": {"wattage_w": 650, "pcie_8pin_count": 2},
}


def make_record(category: str, *, specifications: dict[str, object] | None = None, **overrides):
    record = {
        "hardware_id": f"{category.lower()}-test",
        "source_id": "123",
        "source": {"dataset": "pcpp", "license_status": "UNVERIFIED"},
        "category": category,
        "brand": "Test",
        "model_name": "Test Model",
        "specifications": specifications if specifications is not None else dict(BASE_SPECS[category]),
        "raw_specs": {"name": "Test Model"},
        "data_quality_status": "VERIFIED_STRUCTURED",
        "governance_status": "VALID",
        "lifecycle_status": "CURRENT",
        "market_status": "UNVERIFIED",
        "recommendation_status": "ELIGIBLE",
        "source_version": "pcpp-2026-10-05",
        "collected_at": "2026-10-05T00:00:00Z",
        "updated_at": "2026-11-09T00:00:00Z",
    }
    record.update(overrides)
    return record


@pytest.mark.parametrize("category", CATEGORIES)
def test_minimal_record_passes(category: str) -> None:
    assert validate_record(make_record(category)) == []


@pytest.mark.parametrize("category", CATEGORIES)
def test_missing_required_spec_is_reported(category: str) -> None:
    specs = dict(BASE_SPECS[category])
    dropped = next(iter(specs))
    specs.pop(dropped)
    issues = validate_record(make_record(category, specifications=specs))
    assert any(dropped in issue for issue in issues), issues


def test_unknown_specification_key_is_rejected() -> None:
    specs = {**BASE_SPECS["CPU"], "unknown_field": 1}
    issues = validate_record(make_record("CPU", specifications=specs))
    assert any("unknown_field" in issue for issue in issues)


def test_illegal_governance_status_is_rejected() -> None:
    issues = validate_record(make_record("CPU", governance_status="OK"))
    assert any("governance_status" in issue for issue in issues)


def test_missing_common_field_is_rejected() -> None:
    record = make_record("CPU")
    record.pop("source")
    issues = validate_record(record)
    assert any("source" in issue for issue in issues)


def test_empty_raw_specs_is_rejected() -> None:
    issues = validate_record(make_record("CPU", raw_specs={}))
    assert any("raw_specs" in issue for issue in issues)


def test_gpu_length_is_optional_but_strict_mode_flags_it() -> None:
    record = make_record("GPU")
    assert record["specifications"].get("length_mm") is None
    assert validate_record(record) == []
    strict_issues = validate_record(record, strict_compat=True)
    assert any("length_mm" in issue for issue in strict_issues)


def test_json_schema_requires_public_fields() -> None:
    schema = category_json_schema("CPU")
    assert "hardware_id" in schema["required"]
    assert schema["properties"]["category"]["enum"] == ["CPU"]
    assert schema["additionalProperties"] is False


def test_legacy_blocked_status_stays_valid_enum_for_compatibility() -> None:
    # 历史夹具使用 BLOCKED；主数据不得写入，但枚举必须保留以兼容现有 catalog.json
    assert "BLOCKED" in DATA_QUALITY_STATUSES
