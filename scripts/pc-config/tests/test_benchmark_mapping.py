"""Stage 8.5 PassMark 映射：匹配方法、GPU 芯片级多对一与未匹配保留。"""

from __future__ import annotations

import map_benchmarks as mapping
import match_benchmarks as benchmarks


def test_cpu_matches_fx_series_by_model_key_tokens() -> None:
    hardware = {
        "hardware_id": "cpu-amd-fx-8350",
        "display_name": "AMD FX-8350 4.0 GHz 8-Core Processor",
    }
    rows = [
        {
            "name": "AMD FX-8350 Eight-Core",
            "model_key": "fx 8350 eight",
            "cpu_mark": "8900",
            "single_thread_mark": "1500",
            "rank_no": "300",
            "samples": "5000",
            "id": "1",
        }
    ]
    entry = benchmarks.match_cpu(hardware, rows)
    assert entry is not None
    assert entry["match_method"] == "MODEL_KEY_TOKENS"
    assert entry["score"] == 8900.0


def test_cpu_fuzzy_tie_does_not_raise() -> None:
    # 历史缺陷：相似度并列时直接比较 dict 会抛 TypeError
    hardware = {"hardware_id": "cpu-x", "display_name": "AMD Ryzen 7 9800X3D"}
    rows = [
        {"name": "AMD Ryzen 7 9800X3D", "cpu_mark": "100", "samples": "1"},
        {"name": "AMD Ryzen 7 9800X3D", "cpu_mark": "200", "samples": "2"},
    ]
    entry = benchmarks.match_cpu(hardware, rows)
    assert entry is not None
    assert entry["score"] in {100.0, 200.0}


def test_gpu_prefers_same_vram_variant() -> None:
    hardware = {
        "hardware_id": "gpu-x",
        "specifications": {"chipset": "GeForce RTX 5060 Ti", "vram_gb": 16},
    }
    rows = [
        {"name": "GeForce RTX 5060 Ti 8GB", "g3d_mark": "18000", "samples": "900"},
        {"name": "GeForce RTX 5060 Ti 16GB", "g3d_mark": "22000", "samples": "800"},
    ]
    entry = benchmarks.match_gpu(hardware, rows)
    assert entry is not None
    assert entry["match_method"] == "EXACT_CHIPSET_VRAM"
    assert entry["score"] == 22000.0


def test_unmatched_entry_keeps_record_without_score() -> None:
    record = {"hardware_id": "cpu-unknown", "category": "CPU"}
    entry = mapping.unmatched_entry(record, "CPUMARK", "PRODUCT")
    assert entry["score"] is None
    assert entry["match_status"] == "UNMATCHED"
    assert entry["match_confidence"] == 0.0


def test_storage_matches_by_capacity_and_model_tokens() -> None:
    record = {
        "hardware_id": "storage-samsung-990-pro-1-tb",
        "category": "STORAGE",
        "brand": "Samsung",
        "model_name": "Samsung 990 Pro 1 TB",
        "specifications": {"capacity_gb": 1024},
    }
    rows = [
        {
            "id": "77",
            "name": "Samsung 990 PRO 1000GB",
            "brand": "Samsung",
            "capacity_gb": "1000",
            "disk_mark": "25000",
            "rank_no": "120",
            "samples": "300",
        }
    ]
    entry = mapping.match_storage(record, rows)
    assert entry is not None
    assert entry["match_status"] == "MATCHED"
    assert entry["score"] == 25000.0


def test_storage_rejects_unrelated_capacity() -> None:
    record = {
        "hardware_id": "storage-x",
        "category": "STORAGE",
        "brand": "Samsung",
        "model_name": "Samsung 990 Pro 1 TB",
        "specifications": {"capacity_gb": 1024},
    }
    rows = [
        {
            "id": "78",
            "name": "Samsung 990 PRO 4000GB",
            "brand": "Samsung",
            "capacity_gb": "4000",
            "disk_mark": "25000",
            "samples": "300",
        }
    ]
    assert mapping.match_storage(record, rows) is None
