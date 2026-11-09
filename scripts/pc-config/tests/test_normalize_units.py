"""Stage 8.3 单位规范化与缺失值处理：不补造、不猜测兼容性关键字段。"""

from __future__ import annotations

import normalize_specs as norms
from hardware_schema import validate_record

CPU_ROW = {
    "pcpp_id": "537109",
    "name": "AMD Ryzen 5 9600X 3.9 GHz 6-Core Processor",
    "brand": "AMD",
    "socket": "AM5",
    "core_count": "6",
    "thread_count": "12",
    "tdp": "65 W",
    "integrated_graphics": "Radeon",
    "includes_cooler": "No",
    "maximum_supported_memory": "256 GB",
    "price": "199.00",
    "source_url": "https://example.test/cpu",
    "image_url": "https://example.test/cpu.png",
    "part_number": "100-100001405WOF",
}

GPU_ROW = {
    "pcpp_id": "gpu-1",
    "name": "Test GeForce RTX 5060 Ti 16 GB Video Card",
    "brand": "Test",
    "chipset": "GeForce RTX 5060 Ti",
    "memory": "16 GB",
    "memory_type": "GDDR7",
    "tdp": "180 W",
    "length": "",
    "total_slot_width": "2.5-slot",
    "external_power": "1 x PCIe 8-pin",
    "price": "429.99",
}


def make_master(category: str, row: dict[str, str]):
    return norms.build_master_record(
        category,
        row,
        hardware_id=f"{category.lower()}-test",
        source_version="pcpp-2026-10-05",
        collected_at="2026-10-05T00:00:00Z",
        updated_at="2026-11-09T00:00:00Z",
    )


def test_memory_type_derived_from_speed_covers_old_generations() -> None:
    assert norms._memory_type_from_speed("DDR5-6000") == "DDR5"
    assert norms._memory_type_from_speed("DDR4-3200") == "DDR4"
    assert norms._memory_type_from_speed("DDR3-1600") == "DDR3"
    assert norms._memory_type_from_speed("DDR2-800") == "DDR2"
    assert norms._memory_type_from_speed("") is None


def test_memory_normalizer_converts_units() -> None:
    specs = norms.normalize_memory(
        {"modules": "2 x 16GB", "speed": "DDR5-6000", "form_factor": "DIMM"}
    )
    assert specs["memory_type"] == "DDR5"
    assert specs["capacity_gb"] == 32
    assert specs["speed_mts"] == 6000


def test_master_record_keeps_raw_specs_and_initial_status() -> None:
    record = make_master("CPU", CPU_ROW)
    assert record["raw_specs"] == CPU_ROW
    assert record["governance_status"] == "VALID"
    assert record["lifecycle_status"] == "UNKNOWN"
    assert record["market_status"] == "UNVERIFIED"
    assert record["recommendation_status"] == "RESTRICTED"
    assert validate_record(record) == []


def test_missing_critical_field_marks_incomplete_without_guessing() -> None:
    row = {**CPU_ROW, "tdp": ""}
    record = make_master("CPU", row)
    assert record["specifications"]["tdp_w"] is None
    assert record["data_quality_status"] == "BLOCKED"
    assert record["governance_status"] == "INCOMPLETE"


def test_gpu_without_length_is_incomplete_but_schema_valid() -> None:
    record = make_master("GPU", GPU_ROW)
    assert record["specifications"]["length_mm"] is None
    assert record["governance_status"] == "INCOMPLETE"
    assert validate_record(record) == []


def test_reference_price_is_not_exposed_as_cny_amount() -> None:
    record = make_master("CPU", CPU_ROW)
    assert "price_cny_fen" not in record
    assert record["source"]["reference_price"] == 199.0
    assert record["source"]["reference_price_note"]
