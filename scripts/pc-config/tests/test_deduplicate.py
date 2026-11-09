"""Stage 8.4 重复发现：只输出审核队列，不合并、不删除。"""

from __future__ import annotations

import deduplicate_hardware as dedupe


def make_record(**overrides):
    record = {
        "hardware_id": "cpu-a",
        "category": "CPU",
        "brand": "AMD",
        "model_name": "AMD Ryzen 5 9600X",
        "source_id": "1",
        "source": {"dataset": "pcpp_cpu"},
        "manufacturer_part_number": None,
        "specifications": {"socket": "AM5"},
    }
    record.update(overrides)
    return record


def test_model_signature_drops_own_brand_and_normalizes_separators() -> None:
    assert dedupe.model_signature(make_record()) == "5 9600x ryzen"
    assert dedupe.model_signature(
        make_record(model_name="AMD  Ryzen-5 9600X")
    ) == dedupe.model_signature(make_record())


def test_model_signature_handles_empty_brand() -> None:
    # 历史缺陷：brand 为空时取 split()[0] 会抛 IndexError
    assert dedupe.model_signature(make_record(brand="", model_name="Ryzen 5 9600X")) == "5 9600x ryzen"


def test_same_mpn_is_reported_as_manual_review_candidate() -> None:
    duplicates, conflicts = dedupe.build_report(
        [
            make_record(hardware_id="cpu-a", manufacturer_part_number="100-1"),
            make_record(hardware_id="cpu-b", manufacturer_part_number="100-1"),
        ]
    )
    reasons = {entry["reason"] for entry in duplicates}
    assert dedupe.REASON_MPN in reasons
    assert all(entry["action"] == "MANUAL_REVIEW" for entry in duplicates)
    assert conflicts == []


def test_same_mpn_with_different_compat_field_is_conflict() -> None:
    _duplicates, conflicts = dedupe.build_report(
        [
            make_record(hardware_id="cpu-a", manufacturer_part_number="100-1"),
            make_record(
                hardware_id="cpu-b",
                manufacturer_part_number="100-1",
                specifications={"socket": "AM4"},
            ),
        ]
    )
    assert conflicts
    assert conflicts[0]["conflict_fields"] == ["socket"]


def test_same_source_id_is_flagged() -> None:
    duplicates, _conflicts = dedupe.build_report(
        [
            make_record(hardware_id="cpu-a", source_id="9"),
            make_record(hardware_id="cpu-b", source_id="9"),
        ]
    )
    assert any(entry["reason"] == dedupe.REASON_SOURCE_ID for entry in duplicates)
