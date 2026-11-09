"""Stage 8.8 第三方映射输入：字段齐全，回填字段仅为占位。"""

from __future__ import annotations

import publish_candidates as publish


def make_record(hardware_id: str, recommendation: str) -> dict:
    return {
        "hardware_id": hardware_id,
        "category": "CPU",
        "brand": "AMD",
        "model_name": "AMD Ryzen 5 9600X",
        "manufacturer_part_number": "100-100001405WOF",
        "aliases": ["AMD Ryzen 5 9600X 3.9 GHz 6-Core Processor"],
        "specifications": {"socket": "AM5", "core_count": 6, "tdp_w": 65},
        "governance_status": "VALID",
        "lifecycle_status": "CURRENT",
        "recommendation_status": recommendation,
        "rule_version": "1.0.0",
    }


def test_export_contains_only_non_archived_records() -> None:
    export = publish.build_export(
        [
            make_record("cpu-ok", "ELIGIBLE"),
            make_record("cpu-restricted", "RESTRICTED"),
            make_record("cpu-excluded", "EXCLUDED"),
            make_record("cpu-archived", "ARCHIVED"),
        ]
    )
    assert {item["hardware_id"] for item in export} == {"cpu-ok", "cpu-restricted"}


def test_export_fields_and_placeholders() -> None:
    item = publish.build_export([make_record("cpu-ok", "ELIGIBLE")])[0]
    required = {
        "catalog_version",
        "hardware_id",
        "category",
        "brand",
        "model_name",
        "manufacturer_part_number",
        "aliases",
        "key_specs",
        "lifecycle_status",
        "recommendation_status",
    }
    assert required <= set(item)
    assert item["match_status"] == "PENDING"
    for field in ("matched_mpn", "matched_specs", "source", "fetched_at"):
        assert item[field] is None


def test_key_specs_do_not_leak_full_specifications() -> None:
    item = publish.build_export([make_record("cpu-ok", "ELIGIBLE")])[0]
    assert set(item["key_specs"]) == {"socket", "core_count", "tdp_w"}
    assert "raw_specs" not in item
