"""Stage 8.4：重复数据与硬件实体治理。

按来源 ID、厂商 Part Number、品牌+型号、型号令牌签名四类线索发现重复或相似候选，
输出人工审核队列。本脚本**只发现、不合并、不删除**任何记录（Stage 8 方案 §8.4）。

用法：
    python scripts/pc-config/deduplicate_hardware.py \
        --master data/pc-config/master/hardware-master.jsonl \
        --output-dir data/pc-config/staging
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from hardware_schema import COMPAT_CRITICAL

REASON_SOURCE_ID = "SOURCE_ID"
REASON_MPN = "MPN"
REASON_BRAND_MODEL = "BRAND_MODEL"
REASON_MODEL_SIGNATURE = "MODEL_SIGNATURE"

# 仅用于比较的令牌黑名单：这些词出现在几乎所有型号里，不携带区分度
STOP_TOKENS = {
    "the",
    "with",
    "and",
    "series",
    "edition",
    "version",
    "gaming",
    "graphics",
    "card",
    "video",
    "memory",
    "motherboard",
    "processor",
    "cpu",
    "gpu",
    "ssd",
    "hdd",
    "drive",
    "power",
    "supply",
    "psu",
    "case",
    "cooler",
    "liquid",
    "air",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: Iterable[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_key(value: str | None) -> str:
    """统一大小写与分隔符，用于 MPN 与型号比较。"""

    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def model_signature(record: dict[str, Any]) -> str:
    """去掉品牌与通用词后的令牌签名，用于发现「换牌同款」候选。"""

    brand_tokens = set(normalize_key(record.get("brand")).split())
    tokens = {
        token
        for token in normalize_key(record.get("model_name")).split()
        if token and token not in STOP_TOKENS and token not in brand_tokens
    }
    return " ".join(sorted(tokens))


def spec_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    specs = record.get("specifications") or {}
    return {field: specs.get(field) for field in COMPAT_CRITICAL.get(record["category"], ())}


def conflict_fields(members: list[dict[str, Any]]) -> list[str]:
    """同组内兼容性关键字段取值不一致的字段名。"""

    fields: set[str] = set()
    for field in COMPAT_CRITICAL.get(members[0]["category"], ()):
        values = {json.dumps(spec_snapshot(member).get(field), sort_keys=True) for member in members}
        if len(values) > 1:
            fields.add(field)
    return sorted(fields)


def group_by(
    records: list[dict[str, Any]],
    key_func,
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = key_func(record)
        if key:
            groups[key].append(record)
    return {key: members for key, members in groups.items() if len(members) > 1}


def build_report(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """返回 (重复候选, 冲突记录)。所有条目都需要人工审核，不自动合并。"""

    duplicates: list[dict[str, Any]] = []

    def collect(reason: str, groups: dict[str, list[dict[str, Any]]]) -> None:
        for key, members in groups.items():
            members = sorted(members, key=lambda item: item["hardware_id"])
            duplicates.append(
                {
                    "reason": reason,
                    "group_key": key,
                    "category": members[0]["category"],
                    "hardware_ids": [member["hardware_id"] for member in members],
                    "source_ids": [member["source_id"] for member in members],
                    "conflict_fields": conflict_fields(members),
                    "action": "MANUAL_REVIEW",
                }
            )

    collect(
        REASON_SOURCE_ID,
        group_by(records, lambda record: f"{record['source']['dataset']}:{record['source_id']}"),
    )
    collect(
        REASON_MPN,
        group_by(
            records,
            lambda record: f"{record['category']}:{normalize_key(record.get('manufacturer_part_number'))}",
        ),
    )
    collect(
        REASON_BRAND_MODEL,
        group_by(
            records,
            lambda record: (
                f"{record['category']}:{normalize_key(record.get('brand'))}:"
                f"{normalize_key(record.get('model_name'))}"
            ),
        ),
    )
    collect(
        REASON_MODEL_SIGNATURE,
        group_by(records, lambda record: f"{record['category']}:{model_signature(record)}"),
    )

    duplicates.sort(key=lambda item: (item["reason"], item["group_key"]))
    conflicts = [entry for entry in duplicates if entry["conflict_fields"]]
    return duplicates, conflicts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 8.4 重复与实体治理")
    parser.add_argument("--master", default="data/pc-config/master/hardware-master.jsonl")
    parser.add_argument("--output-dir", default="data/pc-config/staging")
    args = parser.parse_args(argv)

    records = read_jsonl(Path(args.master))
    duplicates, conflicts = build_report(records)
    output_dir = Path(args.output_dir)
    write_jsonl(duplicates, output_dir / "duplicates.jsonl")
    write_jsonl(conflicts, output_dir / "conflicts.jsonl")

    by_reason: dict[str, int] = defaultdict(int)
    for entry in duplicates:
        by_reason[entry["reason"]] += 1
    print(f"[ok] 扫描 {len(records)} 条，重复候选组 {len(duplicates)}，冲突组 {len(conflicts)}")
    print(f"[ok] 分组明细：{dict(sorted(by_reason.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
