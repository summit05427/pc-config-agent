"""Stage 8.9 幂等：同一输入重复执行，产物字节与摘要必须一致。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import publish_candidates as publish


def make_record(hardware_id: str, category: str) -> dict:
    return {
        "hardware_id": hardware_id,
        "category": category,
        "brand": "Test",
        "model_name": f"Test {hardware_id}",
        "governance_status": "VALID",
        "lifecycle_status": "CURRENT",
        "recommendation_status": "ELIGIBLE",
        "market_status": "UNVERIFIED",
        "rule_version": "1.0.0",
        "aliases": [],
        "specifications": {"socket": "AM5", "core_count": 6, "tdp_w": 65},
    }


RECORDS = [make_record("cpu-b", "CPU"), make_record("cpu-a", "CPU"), make_record("case-a", "CASE")]
BENCHMARKS = [
    {
        "hardware_id": "cpu-a",
        "benchmark_type": "CPUMARK",
        "score": 30000.0,
        "match_status": "MATCHED",
    },
    {
        "hardware_id": "cpu-b",
        "benchmark_type": "CPUMARK",
        "score": 12000.0,
        "match_status": "MATCHED",
    },
]


def digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def test_pools_and_export_are_deterministic() -> None:
    first_pools = publish.build_pools(RECORDS, publish.performance_primary(BENCHMARKS))
    second_pools = publish.build_pools(RECORDS, publish.performance_primary(BENCHMARKS))
    assert digest(first_pools) == digest(second_pools)

    first_export = publish.build_export(RECORDS)
    second_export = publish.build_export(list(reversed(RECORDS)))
    assert digest(first_export) == digest(second_export)


def test_jsonl_writes_are_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    publish.write_jsonl(RECORDS, first)
    publish.write_jsonl(list(reversed(RECORDS)), second)
    assert first.read_bytes() == second.read_bytes()


def test_samples_are_limited_and_sorted(tmp_path: Path) -> None:
    total = publish.write_samples(RECORDS, tmp_path)
    assert total == len(RECORDS)
    lines = (tmp_path / "samples" / "cpu.sample.jsonl").read_text(encoding="utf-8").splitlines()
    ids = [json.loads(line)["hardware_id"] for line in lines]
    assert ids == sorted(ids)
