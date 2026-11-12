"""Stage 1：对 8,238 条原始硬件做只读审计，输出质量报告与问题清单。

使用方式：
    python scripts/data-cleaning/stage1_audit.py
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cleaning_common import (
    CATEGORY_MAP,
    DEFAULT_CSV,
    OUTPUT_DIR,
    REQUIRED_FIELDS,
    canon,
    first_value,
    load_rows,
    normalize_brand,
    normalize_model,
    quality_of,
    split_values,
)
from spec_normalizer import clean_model_name, normalize


def build_record(row: dict[str, Any]) -> dict[str, Any]:
    raw_specs = json.loads(row.get("specs_json") or "{}")
    category = CATEGORY_MAP.get(row.get("type") or "")
    record = {
        "pcpp_id": str(row["pcpp_id"]),
        "source_type": row.get("type"),
        "category": category,
        "brand": normalize_brand(row.get("brand")),
        "model_name": "",
        "mpn": first_value(raw_specs.get("Part #")),
        "image_url": row.get("image_url") or None,
        "source_url": row.get("source_url") or None,
        "reference_price_usd": row.get("price") or None,
        "raw_specs": raw_specs,
        "specifications": {},
        "quality_status": "UNIDENTIFIED",
        "quality_reasons": [],
    }
    if category is None:
        record["quality_reasons"] = ["UNKNOWN_CATEGORY"]
        return record
    if not record["brand"] or not row.get("list_name"):
        record["quality_reasons"] = ["MISSING_IDENTITY"]
        return record
    record["model_name"] = clean_model_name(category, row.get("list_name") or "", raw_specs)
    record["specifications"] = normalize(category, raw_specs)
    record["quality_status"], record["quality_reasons"] = quality_of(category, record["specifications"])
    return record


def signature(record: dict[str, Any]) -> str:
    from cleaning_common import DISCRIMINATORS

    if not record["category"]:
        return ""
    parts = [str(record["specifications"].get(field)) for field in DISCRIMINATORS[record["category"]]]
    return canon("|".join(parts))


def duplicate_groups(records: list[dict[str, Any]]) -> dict[str, list[list[str]]]:
    exact: dict[tuple, list[str]] = defaultdict(list)
    model: dict[tuple, list[str]] = defaultdict(list)
    alias: dict[tuple, list[str]] = defaultdict(list)
    by_id = {record["pcpp_id"]: record for record in records}
    for record in records:
        if record["quality_status"] == "UNIDENTIFIED":
            continue
        category = record["category"]
        brand_key = canon(record["brand"])
        model_key = canon(record["model_name"])
        sig = signature(record)
        if record["mpn"]:
            exact[(category, brand_key, canon(record["mpn"]))].append(record["pcpp_id"])
        model[(category, brand_key, model_key, sig)].append(record["pcpp_id"])
        alias[(category, model_key, sig)].append(record["pcpp_id"])
    return {
        "exact_duplicate_groups": [ids for ids in exact.values() if len(ids) > 1],
        "same_model_groups": [ids for ids in model.values() if len(ids) > 1],
        "cross_brand_alias_groups": [
            ids for ids in alias.values()
            if len(ids) > 1 and len({canon(by_id[i]["brand"]) for i in ids}) > 1
        ],
    }


def missing_rates(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["category"]:
            by_category[record["category"]].append(record)
    for category, items in sorted(by_category.items()):
        total = len(items)
        fields = set(REQUIRED_FIELDS[category]) | set(items[0]["specifications"])
        stats[category] = {
            field: round(
                sum(1 for item in items if item["specifications"].get(field) in (None, "", [])) / total,
                4,
            )
            for field in sorted(fields)
        }
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 1 原始硬件数据审计")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    records = [build_record(row) for row in load_rows(Path(args.csv))]
    groups = duplicate_groups(records)
    by_category = Counter(record["category"] or "UNKNOWN" for record in records)
    brand_by_category: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        if record["category"]:
            brand_by_category[record["category"]][record["brand"] or "UNKNOWN"] += 1

    summary = {
        "stage": 1,
        "source_csv": str(args.csv),
        "total_records": len(records),
        "category_counts": dict(sorted(by_category.items())),
        "top_brands": {
            category: counter.most_common(10)
            for category, counter in sorted(brand_by_category.items())
        },
        "quality_counts": dict(sorted(Counter(record["quality_status"] for record in records).items())),
        "missing_rates_by_category": missing_rates(records),
        "duplicate_stats": {
            "exact_duplicate_groups": len(groups["exact_duplicate_groups"]),
            "exact_duplicate_records": sum(len(ids) for ids in groups["exact_duplicate_groups"]),
            "same_model_groups": len(groups["same_model_groups"]),
            "same_model_records": sum(len(ids) for ids in groups["same_model_groups"]),
            "cross_brand_alias_groups": len(groups["cross_brand_alias_groups"]),
        },
        "anomaly_records": sum(1 for record in records if record["quality_status"] == "ANOMALOUS"),
        "unidentified_records": sum(1 for record in records if record["quality_status"] == "UNIDENTIFIED"),
        "duplicate_group_ids": groups,
        "note": "本阶段只读，不修改原始 CSV，也不读取任何跑分数据。",
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stage1-audit-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    issues_path = output_dir / "stage1-issues.csv"
    with issues_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pcpp_id", "category", "brand", "model_name", "issue_type", "field", "detail"])
        for record in records:
            for reason in record["quality_reasons"]:
                issue_type, _, field = reason.partition("_")
                writer.writerow([
                    record["pcpp_id"], record["category"] or "", record["brand"],
                    record["model_name"], issue_type, field.lower(), reason,
                ])
        for kind, groups_list in groups.items():
            for ids in groups_list:
                writer.writerow([
                    "|".join(ids), "", "", "", kind.upper(), "identity", f"group_size={len(ids)}",
                ])

    print(f"总记录数：{len(records)}")
    print("品类分布：" + ", ".join(f"{key}={value}" for key, value in sorted(by_category.items())))
    print("质量分布：" + json.dumps(summary["quality_counts"], ensure_ascii=False))
    print(f"确定重复组：{summary['duplicate_stats']['exact_duplicate_groups']}，"
          f"同型号组：{summary['duplicate_stats']['same_model_groups']}，"
          f"跨品牌别名组：{summary['duplicate_stats']['cross_brand_alias_groups']}")
    print(f"报告：{output_dir / 'stage1-audit-summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
