"""Stage 8.7 / 8.8 / 8.9：候选池发布、第三方映射输入导出与发布清单。

从 Hardware Master 与跑分映射生成四类发布候选池、第三方商品映射输入清单，并写出
`catalog-manifest.json`。发布前必须通过 validate_dataset.py 的全部校验。

用法：
    python scripts/pc-config/publish_candidates.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from search_queries import (
    BRAND_DICT_PATH,
    SERIES_DICT_PATH,
    build_search_queries,
    load_brand_map,
    load_series_rules,
)

CATALOG_VERSION = "2026.11.0"
DEFAULT_GENERATED_AT = "2026-11-09T00:00:00Z"
DISTRIBUTION_STATUS = "INTERNAL_ONLY"

STANDARD_POOL = "standard-build"
BUDGET_POOL = "budget-build"
LEGACY_POOL = "legacy-upgrade"
ARCHIVED_POOL = "archived"

POOL_LIFECYCLES = {
    STANDARD_POOL: {"CURRENT", "MATURE"},
    LEGACY_POOL: {"LEGACY"},
}

PERFORMANCE_CATEGORIES = {"CPU", "GPU"}
TIER_LABELS = ("ENTRY", "MID", "HIGH")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in sorted(records, key=lambda item: item["hardware_id"]):
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def performance_primary(benchmarks: list[dict[str, Any]]) -> dict[str, float]:
    """取每个硬件的可用于排序的主跑分：CPU 用 CPUMARK，其余用 G3D/DISK。"""

    primary: dict[str, float] = {}
    for entry in benchmarks:
        score = entry.get("score")
        if score is None:
            continue
        if entry["benchmark_type"] in {"CPUMARK", "G3D_MARK", "DISK_MARK"}:
            primary[entry["hardware_id"]] = float(score)
    return primary


def assign_tiers(
    records: list[dict[str, Any]], primary: dict[str, float]
) -> dict[str, str]:
    """按类别内跑分三分位给出 ENTRY / MID / HIGH，仅用于预算池分层。"""

    by_category: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for record in records:
        score = primary.get(record["hardware_id"])
        if score is not None and record["category"] in PERFORMANCE_CATEGORIES:
            by_category[record["category"]].append((score, record["hardware_id"]))

    tiers: dict[str, str] = {}
    for items in by_category.values():
        items.sort()
        for index, (_score, hardware_id) in enumerate(items):
            position = index / max(len(items) - 1, 1)
            tier = TIER_LABELS[min(int(position * len(TIER_LABELS)), len(TIER_LABELS) - 1)]
            tiers[hardware_id] = tier
    return tiers


def key_specs(record: dict[str, Any]) -> dict[str, Any]:
    """第三方映射需要的少量稳定规格，避免把整份 specifications 外传。"""

    specs = record.get("specifications") or {}
    fields = {
        "CPU": ("socket", "core_count", "tdp_w"),
        "GPU": ("chipset", "vram_gb", "length_mm"),
        "MOTHERBOARD": ("socket", "chipset", "form_factor", "memory_type"),
        "MEMORY": ("memory_type", "capacity_gb", "speed_mts"),
        "STORAGE": ("capacity_gb", "interface"),
        "COOLER": ("supported_sockets", "height_mm"),
        "CASE": ("supported_mainboard_form_factors", "max_gpu_length_mm"),
        "PSU": ("wattage_w", "length_mm"),
    }[record["category"]]
    return {field: specs.get(field) for field in fields}


def pool_entry(
    record: dict[str, Any], pool_id: str, tier: str | None
) -> dict[str, Any]:
    entry = {
        "pool_id": pool_id,
        "pool_version": CATALOG_VERSION,
        "catalog_version": CATALOG_VERSION,
        "rule_version": record.get("rule_version"),
        "hardware_id": record["hardware_id"],
        "category": record["category"],
        "brand": record["brand"],
        "model_name": record["model_name"],
        "governance_status": record["governance_status"],
        "lifecycle_status": record["lifecycle_status"],
        "recommendation_status": record["recommendation_status"],
        "key_specs": key_specs(record),
    }
    if tier:
        entry["performance_tier"] = tier
    return entry


def build_pools(
    records: list[dict[str, Any]], primary: dict[str, float]
) -> dict[str, list[dict[str, Any]]]:
    tiers = assign_tiers(records, primary)
    pools: dict[str, list[dict[str, Any]]] = {name: [] for name in
                                              (STANDARD_POOL, BUDGET_POOL, LEGACY_POOL, ARCHIVED_POOL)}

    for record in records:
        lifecycle = record["lifecycle_status"]
        recommendation = record["recommendation_status"]
        governance = record["governance_status"]

        archived = (
            recommendation == "ARCHIVED"
            or governance in {"INVALID", "CONFLICT"}
            or lifecycle == "DISCONTINUED"
        )
        if archived:
            pools[ARCHIVED_POOL].append(pool_entry(record, ARCHIVED_POOL, None))
            continue

        if recommendation == "ELIGIBLE" and lifecycle in POOL_LIFECYCLES[STANDARD_POOL]:
            pools[STANDARD_POOL].append(pool_entry(record, STANDARD_POOL, None))

        if recommendation == "ELIGIBLE":
            if record["category"] in PERFORMANCE_CATEGORIES:
                if record["hardware_id"] in primary:
                    pools[BUDGET_POOL].append(
                        pool_entry(record, BUDGET_POOL, tiers.get(record["hardware_id"]))
                    )
            else:
                pools[BUDGET_POOL].append(pool_entry(record, BUDGET_POOL, None))

        if lifecycle in POOL_LIFECYCLES[LEGACY_POOL] and recommendation in {
            "ELIGIBLE",
            "RESTRICTED",
        }:
            pools[LEGACY_POOL].append(pool_entry(record, LEGACY_POOL, None))

    return pools


def build_export(
    records: list[dict[str, Any]],
    brand_map: dict[str, str] | None = None,
    series_rules: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """第三方商品映射输入：只包含未被归档的硬件，价格与链接由 Stage 9 回填。"""

    brand_map = brand_map if brand_map is not None else load_brand_map()
    series_rules = series_rules if series_rules is not None else load_series_rules()

    export: list[dict[str, Any]] = []
    for record in records:
        if record["recommendation_status"] in {"EXCLUDED", "ARCHIVED"}:
            continue
        export.append(
            {
                "catalog_version": CATALOG_VERSION,
                "hardware_id": record["hardware_id"],
                "category": record["category"],
                "brand": record["brand"],
                "model_name": record["model_name"],
                "manufacturer_part_number": record.get("manufacturer_part_number"),
                "aliases": record.get("aliases") or [],
                # 中文电商检索键，按 zh → zh_short → model → en 降级
                "search_queries": build_search_queries(record, brand_map, series_rules),
                "key_specs": key_specs(record),
                "lifecycle_status": record["lifecycle_status"],
                "recommendation_status": record["recommendation_status"],
                # 以下字段由 Stage 9 的第三方服务回填，本阶段只定义契约
                "matched_mpn": None,
                "matched_specs": None,
                "source": None,
                "fetched_at": None,
                "match_status": "PENDING",
            }
        )
    # 按 hardware_id 排序，保证导出清单与输入记录顺序无关，重复发布字节一致
    return sorted(export, key=lambda item: item["hardware_id"])


SCRIPT_DIR = Path(__file__).resolve().parent
SAMPLE_SIZE_PER_CATEGORY = 10


def script_digests() -> list[dict[str, str]]:
    """记录参与生成的脚本摘要，便于回溯源码版本。"""

    digests: list[dict[str, str]] = []
    for path in sorted(SCRIPT_DIR.glob("*.py")):
        digests.append(
            {
                "name": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return digests


def reference_digests() -> list[dict[str, str]]:
    """记录中英检索词典的版本与摘要，便于回溯检索键由哪一版词典生成。"""

    digests: list[dict[str, str]] = []
    for path in (BRAND_DICT_PATH, SERIES_DICT_PATH):
        payload = json.loads(path.read_text(encoding="utf-8"))
        digests.append(
            {
                "name": path.name,
                "schema_version": payload["schema_version"],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return digests


def write_samples(records: list[dict[str, Any]], root: Path) -> int:
    """每类输出固定条数的真实样本；许可未确认前这是唯一入库的明细数据。"""

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_category[record["category"]].append(record)

    total = 0
    for category, items in sorted(by_category.items()):
        selected = sorted(items, key=lambda item: item["hardware_id"])[:SAMPLE_SIZE_PER_CATEGORY]
        path = root / "samples" / f"{category.lower()}.sample.jsonl"
        write_jsonl(selected, path)
        total += len(selected)
    return total


def build_manifest(
    records: list[dict[str, Any]],
    benchmarks: list[dict[str, Any]],
    pools: dict[str, list[dict[str, Any]]],
    export_count: int,
    baseline_path: Path,
    generated_at: str,
) -> dict[str, Any]:
    inputs: list[dict[str, Any]] = []
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        inputs = [
            {
                "table": item["table"],
                "path": item.get("path"),
                "rows": item.get("rows"),
                "bytes": item.get("bytes"),
                "sha256": item["sha256"],
            }
            for item in baseline.get("inputs", [])
        ]
    digest_source = "|".join(f"{item['table']}:{item['sha256']}" for item in inputs)
    input_digest = sha256_text(digest_source)[:6] if inputs else "000000"
    batch_id = f"{generated_at.replace('-', '').replace(':', '')}-{input_digest}"

    return {
        "catalog_version": CATALOG_VERSION,
        "batch_id": batch_id,
        "generated_at": generated_at,
        "distribution_status": DISTRIBUTION_STATUS,
        "inputs": inputs,
        "counts": {
            "hardware": len(records),
            "benchmarks": len(benchmarks),
            "export": export_count,
            "by_category": dict(Counter(record["category"] for record in records)),
            "pools": {name: len(entries) for name, entries in pools.items()},
            "governance": dict(Counter(record["governance_status"] for record in records)),
            "lifecycle": dict(Counter(record["lifecycle_status"] for record in records)),
            "market": dict(Counter(record["market_status"] for record in records)),
            "recommendation": dict(
                Counter(record["recommendation_status"] for record in records)
            ),
        },
        "scripts": script_digests(),
        "references": reference_digests(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 8.7/8.8/8.9 候选池发布")
    parser.add_argument("--master", default="data/pc-config/master/hardware-master.jsonl")
    parser.add_argument(
        "--benchmarks", default="data/pc-config/master/hardware-benchmarks.jsonl"
    )
    parser.add_argument("--output-root", default="data/pc-config")
    parser.add_argument("--generated-at", default=DEFAULT_GENERATED_AT)
    parser.add_argument(
        "--dry-run", action="store_true", help="只校验并打印统计，不写任何文件"
    )
    parser.add_argument(
        "--skip-validate", action="store_true", help="跳过发布前校验，仅用于本地调试"
    )
    args = parser.parse_args(argv)

    root = Path(args.output_root)
    records = read_jsonl(Path(args.master))
    benchmarks = read_jsonl(Path(args.benchmarks))
    primary = performance_primary(benchmarks)

    pools = build_pools(records, primary)
    export = build_export(records)
    manifest = build_manifest(
        records,
        benchmarks,
        pools,
        len(export),
        root / "manifest" / "baseline.json",
        args.generated_at,
    )

    # 发布门禁：任一校验失败都不写盘，避免半成品产物覆盖上一批次
    if not args.skip_validate:
        from validate_dataset import check_manifest, print_report, validate_release_data

        report = validate_release_data(records, benchmarks, pools, export)
        check_manifest(manifest, records, benchmarks, pools, report)
        if report.has_errors:
            print_report(report, as_json=False)
            print(f"[fail] 发布前校验未通过，错误 {report.error_count} 条，未写入任何文件")
            return 1

    if args.dry_run:
        print(f"[ok] dry-run 通过，批次 {manifest['batch_id']}，未写入文件")
        print(f"[ok] 候选池：{manifest['counts']['pools']}")
        print(f"[ok] 第三方映射输入：{len(export)} 条")
        return 0

    for name, entries in pools.items():
        write_jsonl(entries, root / "pools" / f"{name}-pool.jsonl")

    write_json(export, root / "export" / "third-party-mapping-input.json")
    sample_count = write_samples(records, root)

    write_json(manifest, root / "manifest" / "catalog-manifest.json")
    write_json(manifest, root / "manifest" / "history" / f"{manifest['batch_id']}.json")

    print(f"[ok] 发布批次 {manifest['batch_id']}，catalog_version {CATALOG_VERSION}")
    print(f"[ok] 候选池：{manifest['counts']['pools']}")
    print(f"[ok] 第三方映射输入：{len(export)} 条")
    print(f"[ok] 样本：{sample_count} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
