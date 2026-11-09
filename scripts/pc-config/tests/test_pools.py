"""Stage 8.7 候选池：只收规则命中记录，预算池不读价格。"""

from __future__ import annotations

import pytest

import publish_candidates as publish


def make_record(hardware_id: str, category: str, lifecycle: str, recommendation: str, governance: str = "VALID"):
    return {
        "hardware_id": hardware_id,
        "category": category,
        "brand": "Test",
        "model_name": f"Test {hardware_id}",
        "governance_status": governance,
        "lifecycle_status": lifecycle,
        "recommendation_status": recommendation,
        "market_status": "UNVERIFIED",
        "rule_version": "1.0.0",
        "specifications": {"socket": "AM5"},
    }


def make_benchmark(hardware_id: str, benchmark_type: str, score: float):
    return {
        "hardware_id": hardware_id,
        "benchmark_type": benchmark_type,
        "score": score,
        "match_status": "MATCHED",
    }


RECORDS = [
    make_record("cpu-current", "CPU", "CURRENT", "ELIGIBLE"),
    make_record("cpu-mature", "CPU", "MATURE", "ELIGIBLE"),
    make_record("cpu-legacy", "CPU", "LEGACY", "RESTRICTED"),
    make_record("cpu-old", "CPU", "DISCONTINUED", "EXCLUDED"),
    make_record("gpu-current", "GPU", "CURRENT", "ELIGIBLE"),
    make_record("case-unknown", "CASE", "UNKNOWN", "ELIGIBLE"),
    make_record("psu-invalid", "PSU", "UNKNOWN", "EXCLUDED", governance="INVALID"),
]

BENCHMARKS = [
    make_benchmark("cpu-current", "CPUMARK", 30000),
    make_benchmark("cpu-mature", "CPUMARK", 12000),
    make_benchmark("cpu-legacy", "CPUMARK", 4000),
    make_benchmark("cpu-old", "CPUMARK", 1000),
]


@pytest.fixture
def pools() -> dict[str, list[dict]]:
    return publish.build_pools(RECORDS, publish.performance_primary(BENCHMARKS))


def pool_ids(pools: dict[str, list[dict]], name: str) -> set[str]:
    return {entry["hardware_id"] for entry in pools[name]}


def test_standard_pool_requires_eligible_current_or_mature(pools) -> None:
    assert pool_ids(pools, publish.STANDARD_POOL) == {"cpu-current", "cpu-mature", "gpu-current"}


def test_legacy_pool_collects_legacy_lifecycle(pools) -> None:
    assert pool_ids(pools, publish.LEGACY_POOL) == {"cpu-legacy"}


def test_archived_pool_holds_discontinued_and_invalid(pools) -> None:
    assert pool_ids(pools, publish.ARCHIVED_POOL) == {"cpu-old", "psu-invalid"}


def test_budget_pool_excludes_cpu_without_benchmark(pools) -> None:
    budget = pool_ids(pools, publish.BUDGET_POOL)
    assert "cpu-current" in budget
    assert "gpu-current" not in budget
    # 非性能类硬件不要求跑分
    assert "case-unknown" in budget


def test_budget_tiers_only_apply_to_performance_categories(pools) -> None:
    entries = {entry["hardware_id"]: entry for entry in pools[publish.BUDGET_POOL]}
    assert "performance_tier" in entries["cpu-current"]
    assert "performance_tier" not in entries["case-unknown"]


def test_pool_entry_carries_rule_and_catalog_version(pools) -> None:
    entry = pools[publish.STANDARD_POOL][0]
    assert entry["catalog_version"] == publish.CATALOG_VERSION
    assert entry["pool_version"] == publish.CATALOG_VERSION
    assert entry["rule_version"] == "1.0.0"
    assert entry["key_specs"]
