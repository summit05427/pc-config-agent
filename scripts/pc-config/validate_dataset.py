"""Stage 8.9：发布前的数据集校验与门禁。

校验对象：Hardware Master、跑分映射、四类发布候选池、第三方映射输入与发布清单。
只读产物，不修改任何文件；有错误时非零退出，警告只提示不阻断。

用法：
    python scripts/pc-config/validate_dataset.py
    python scripts/pc-config/validate_dataset.py --strict-compat
    python scripts/pc-config/validate_dataset.py --schema-only --samples data/pc-config/samples
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hardware_schema import (
    BENCHMARK_TYPES,
    CATEGORIES,
    GOVERNANCE_STATUSES,
    LIFECYCLE_STATUSES,
    MARKET_STATUSES,
    MATCH_SCOPES,
    MATCH_STATUSES,
    RECOMMENDATION_STATUSES,
    validate_record,
)
from publish_candidates import (
    ARCHIVED_POOL,
    BUDGET_POOL,
    LEGACY_POOL,
    STANDARD_POOL,
    build_pools,
    performance_primary,
)

POOL_FILES = {
    STANDARD_POOL: "standard-build-pool.jsonl",
    BUDGET_POOL: "budget-build-pool.jsonl",
    LEGACY_POOL: "legacy-upgrade-pool.jsonl",
    ARCHIVED_POOL: "archived-pool.jsonl",
}

EXPORT_REQUIRED_FIELDS: tuple[str, ...] = (
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
    "match_status",
)
EXPORT_BACKFILL_FIELDS: tuple[str, ...] = (
    "matched_mpn",
    "matched_specs",
    "source",
    "fetched_at",
)
DISTRIBUTION_STATUSES: tuple[str, ...] = ("PUBLISHABLE", "INTERNAL_ONLY")
BATCH_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{6}$")
ERROR_SAMPLE_LIMIT = 200


@dataclass
class Report:
    """校验结果：错误计数 + 有限明细，避免海量条目录入日志。"""

    error_count: int = 0
    errors: list[str] = field(default_factory=list)
    warning_count: int = 0
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def error(self, message: str) -> None:
        self.error_count += 1
        if len(self.errors) < ERROR_SAMPLE_LIMIT:
            self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warning_count += 1
        if len(self.warnings) < ERROR_SAMPLE_LIMIT:
            self.warnings.append(message)

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check_master(
    records: list[dict[str, Any]], report: Report, *, strict_compat: bool = False
) -> None:
    if not records:
        report.error("主数据为空")
        return

    id_counts = Counter(record.get("hardware_id") for record in records)
    for hardware_id, count in id_counts.items():
        if not hardware_id:
            report.error("存在 hardware_id 为空的记录")
        elif count > 1:
            report.error(f"hardware_id 重复 {count} 次：{hardware_id}")

    governance: Counter[str] = Counter()
    lifecycle: Counter[str] = Counter()
    recommendation: Counter[str] = Counter()
    market: Counter[str] = Counter()
    category: Counter[str] = Counter()

    for record in records:
        hardware_id = record.get("hardware_id", "?")
        for issue in validate_record(record, strict_compat=strict_compat):
            report.error(f"{hardware_id}: {issue}")
        governance[record.get("governance_status")] += 1
        lifecycle[record.get("lifecycle_status")] += 1
        recommendation[record.get("recommendation_status")] += 1
        market[record.get("market_status")] += 1
        category[record.get("category")] += 1

    report.stats["master"] = {
        "total": len(records),
        "by_category": dict(category),
        "governance": dict(governance),
        "lifecycle": dict(lifecycle),
        "recommendation": dict(recommendation),
        "market": dict(market),
    }


def check_benchmarks(
    entries: list[dict[str, Any]], master_ids: set[str], report: Report
) -> None:
    seen: set[tuple[str, str]] = set()
    by_status: Counter[str] = Counter()
    by_type: Counter[str] = Counter()

    for entry in entries:
        hardware_id = entry.get("hardware_id")
        benchmark_type = entry.get("benchmark_type")
        if hardware_id not in master_ids:
            report.error(f"跑分记录引用未知硬件：{hardware_id}")
        if benchmark_type not in BENCHMARK_TYPES:
            report.error(f"benchmark_type 非法：{hardware_id} -> {benchmark_type!r}")
        if entry.get("match_scope") not in MATCH_SCOPES:
            report.error(f"match_scope 非法：{hardware_id} -> {entry.get('match_scope')!r}")
        if entry.get("match_status") not in MATCH_STATUSES:
            report.error(
                f"match_status 非法：{hardware_id} -> {entry.get('match_status')!r}"
            )
        confidence = entry.get("match_confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            report.error(f"match_confidence 越界：{hardware_id} -> {confidence!r}")
        if entry.get("match_status") == "MATCHED" and entry.get("score") is None:
            report.error(f"MATCHED 记录缺少 score：{hardware_id}")

        key = (hardware_id, benchmark_type)
        if key in seen:
            report.error(f"同一硬件同一指标重复映射：{hardware_id} / {benchmark_type}")
        seen.add(key)
        by_status[entry.get("match_status")] += 1
        by_type[benchmark_type] += 1

    report.stats["benchmarks"] = {
        "total": len(entries),
        "by_status": dict(by_status),
        "by_type": dict(by_type),
    }


def check_pools(
    records: list[dict[str, Any]],
    benchmarks: list[dict[str, Any]],
    pools: dict[str, list[dict[str, Any]]],
    report: Report,
) -> None:
    """按发布规则复算候选池，确保池文件只含规则命中的记录。"""

    master = {record["hardware_id"]: record for record in records}
    expected = build_pools(records, performance_primary(benchmarks))

    for pool_name, expected_entries in expected.items():
        actual = pools.get(pool_name, [])
        expected_ids = {entry["hardware_id"] for entry in expected_entries}
        actual_ids = {entry["hardware_id"] for entry in actual}

        for hardware_id in sorted(expected_ids - actual_ids):
            report.error(f"候选池 {pool_name} 缺少 {hardware_id}")
        for hardware_id in sorted(actual_ids - expected_ids):
            report.error(f"候选池 {pool_name} 混入 {hardware_id}")

        seen: set[str] = set()
        for entry in actual:
            hardware_id = entry.get("hardware_id")
            if hardware_id in seen:
                report.error(f"候选池 {pool_name} 重复记录：{hardware_id}")
            seen.add(hardware_id)
            if entry.get("pool_id") != pool_name:
                report.error(
                    f"候选池 {pool_name} 的 pool_id 不一致：{hardware_id} -> {entry.get('pool_id')}"
                )
            record = master.get(hardware_id)
            if record is None:
                report.error(f"候选池 {pool_name} 引用未知硬件：{hardware_id}")
                continue
            for status_field in (
                "governance_status",
                "lifecycle_status",
                "recommendation_status",
            ):
                if entry.get(status_field) != record[status_field]:
                    report.error(
                        f"候选池 {pool_name} 的 {status_field} 与主数据不一致：{hardware_id}"
                    )

    report.stats["pools"] = {
        name: len(entries) for name, entries in sorted(pools.items())
    }


def check_export(
    export: list[dict[str, Any]],
    records: list[dict[str, Any]],
    report: Report,
) -> None:
    master_ids = {record["hardware_id"] for record in records}
    eligible_ids = {
        record["hardware_id"]
        for record in records
        if record["recommendation_status"] not in {"EXCLUDED", "ARCHIVED"}
    }

    exported_ids: set[str] = set()
    for item in export:
        hardware_id = item.get("hardware_id")
        missing = [name for name in EXPORT_REQUIRED_FIELDS if name not in item]
        if missing:
            report.error(f"导出条目缺字段 {missing}：{hardware_id}")
        if hardware_id not in master_ids:
            report.error(f"导出条目引用未知硬件：{hardware_id}")
        if hardware_id in exported_ids:
            report.error(f"导出条目重复：{hardware_id}")
        exported_ids.add(hardware_id)
        if item.get("match_status") != "PENDING":
            report.error(f"导出条目 match_status 必须为 PENDING：{hardware_id}")
        for name in EXPORT_BACKFILL_FIELDS:
            if item.get(name) is not None:
                report.error(f"导出条目的回填字段 {name} 必须为 null：{hardware_id}")

    for hardware_id in sorted(eligible_ids - exported_ids):
        report.error(f"导出清单缺少未归档硬件：{hardware_id}")

    report.stats["export"] = {"total": len(export), "expected": len(eligible_ids)}


def check_manifest(
    manifest: dict[str, Any],
    records: list[dict[str, Any]],
    benchmarks: list[dict[str, Any]],
    pools: dict[str, list[dict[str, Any]]],
    report: Report,
) -> None:
    batch_id = manifest.get("batch_id", "")
    if not isinstance(batch_id, str) or not BATCH_ID_PATTERN.match(batch_id):
        report.error(f"batch_id 格式非法：{batch_id!r}")
    if not manifest.get("catalog_version"):
        report.error("catalog_version 缺失")
    if manifest.get("distribution_status") not in DISTRIBUTION_STATUSES:
        report.error(
            f"distribution_status 非法：{manifest.get('distribution_status')!r}"
        )
    if not manifest.get("inputs"):
        report.error("manifest.inputs 不得为空")
    if not manifest.get("scripts"):
        report.error("manifest.scripts 不得为空，必须记录脚本摘要")

    counts = manifest.get("counts") or {}
    if counts.get("hardware") != len(records):
        report.error(
            f"manifest.hardware 计数不一致：{counts.get('hardware')} != {len(records)}"
        )
    if counts.get("benchmarks") != len(benchmarks):
        report.error(
            f"manifest.benchmarks 计数不一致：{counts.get('benchmarks')} != {len(benchmarks)}"
        )
    expected_pools = {name: len(entries) for name, entries in pools.items()}
    if counts.get("pools") != expected_pools:
        report.error(f"manifest.pools 计数不一致：{counts.get('pools')} != {expected_pools}")
    by_category = Counter(record["category"] for record in records)
    if counts.get("by_category") != dict(by_category):
        report.error("manifest.by_category 计数与主数据不一致")


def check_samples(samples_dir: Path, report: Report) -> None:
    if not samples_dir.is_dir():
        report.error(f"样本目录不存在：{samples_dir}")
        return

    covered: set[str] = set()
    total = 0
    for path in sorted(samples_dir.glob("*.jsonl")):
        for record in read_jsonl(path):
            total += 1
            category = record.get("category")
            covered.add(category)
            for issue in validate_record(record):
                report.error(f"{path.name} / {record.get('hardware_id', '?')}: {issue}")

    missing = sorted(set(CATEGORIES) - covered)
    if missing:
        report.error(f"样本未覆盖类别：{missing}")
    report.stats["samples"] = {"total": total, "categories": sorted(covered)}


def validate_release_data(
    records: list[dict[str, Any]],
    benchmarks: list[dict[str, Any]],
    pools: dict[str, list[dict[str, Any]]],
    export: list[dict[str, Any]],
    *,
    strict_compat: bool = False,
) -> Report:
    """发布前的内存校验，供 publish_candidates.py 在写盘前调用。"""

    report = Report()
    check_master(records, report, strict_compat=strict_compat)
    master_ids = {record["hardware_id"] for record in records}
    check_benchmarks(benchmarks, master_ids, report)
    check_pools(records, benchmarks, pools, report)
    check_export(export, records, report)
    return report


def load_release_artifacts(
    root: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    records = read_jsonl(root / "master" / "hardware-master.jsonl")
    benchmarks = read_jsonl(root / "master" / "hardware-benchmarks.jsonl")
    pools = {
        name: read_jsonl(root / "pools" / filename)
        for name, filename in POOL_FILES.items()
        if (root / "pools" / filename).is_file()
    }
    export_path = root / "export" / "third-party-mapping-input.json"
    export = read_json(export_path) if export_path.is_file() else []
    manifest_path = root / "manifest" / "catalog-manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else None
    return records, benchmarks, pools, export, manifest


def print_report(report: Report, *, as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                {
                    "errors": report.error_count,
                    "warnings": report.warning_count,
                    "stats": report.stats,
                    "error_samples": report.errors,
                    "warning_samples": report.warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    for message in report.warnings:
        print(f"[warn] {message}")
    for message in report.errors:
        print(f"[error] {message}")
    if report.error_count > len(report.errors):
        print(f"[error] 其余 {report.error_count - len(report.errors)} 条错误未展示")
    for name, value in report.stats.items():
        print(f"[stat] {name}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 8.9 数据集校验与发布门禁")
    parser.add_argument("--root", default="data/pc-config", help="治理产物根目录")
    parser.add_argument("--samples", help="样本目录，配合 --schema-only 使用")
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="只校验样本 Schema，供 CI 使用；不做全量交叉校验",
    )
    parser.add_argument(
        "--strict-compat",
        action="store_true",
        help="把兼容性关键字段缺失视为错误（发布前严格模式）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出校验结果")
    args = parser.parse_args(argv)

    report = Report()
    if args.schema_only:
        samples = Path(args.samples or (Path(args.root) / "samples"))
        check_samples(samples, report)
    else:
        root = Path(args.root)
        if not (root / "master" / "hardware-master.jsonl").is_file():
            print(f"[error] 缺少主数据：{root / 'master' / 'hardware-master.jsonl'}")
            return 1
        records, benchmarks, pools, export, manifest = load_release_artifacts(root)
        report = validate_release_data(
            records, benchmarks, pools, export, strict_compat=args.strict_compat
        )
        if manifest is None:
            report.error("缺少 manifest/catalog-manifest.json")
        else:
            check_manifest(manifest, records, benchmarks, pools, report)

    print_report(report, as_json=args.json)
    if report.has_errors:
        print(f"[fail] 校验未通过，错误 {report.error_count} 条，警告 {report.warning_count} 条")
        return 1
    print(f"[ok] 校验通过，警告 {report.warning_count} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
