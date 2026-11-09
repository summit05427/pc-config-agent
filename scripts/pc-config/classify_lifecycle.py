"""Stage 8.6：生命周期与推荐资格分类。

依据人工维护的 `reference/platform-generations.json` 判定生命周期，再按类别分组规则
判定推荐资格。分类理由与规则版本写回主数据，便于回溯（Stage 8 方案 §6、ADR 0015）。

用法：
    python scripts/pc-config/classify_lifecycle.py \
        --master data/pc-config/master/hardware-master.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from hardware_schema import CATEGORY_FIELDS, COMPAT_CRITICAL

RULE_VERSION = "1.0.0"
REFERENCE_PATH = Path(__file__).resolve().parent / "reference" / "platform-generations.json"
OVERRIDES_PATH = Path(__file__).resolve().parent / "reference" / "manual-overrides.json"

GENERATION_GROUP = {"CPU", "GPU"}
PLATFORM_GROUP = {"MOTHERBOARD", "MEMORY", "STORAGE"}
SPEC_COMPLETENESS_GROUP = {"COOLER", "CASE", "PSU"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in sorted(records, key=lambda item: item["hardware_id"]):
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def load_overrides(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def lifecycle_for(record: dict[str, Any], reference: dict[str, Any]) -> tuple[str, str]:
    """返回 (lifecycle_status, reason)。无法判定一律 UNKNOWN，不做推测。"""

    category = record["category"]
    specs = record.get("specifications") or {}

    if category in {"CPU", "MOTHERBOARD"}:
        socket = (specs.get("socket") or "").strip().upper()
        table = {key.upper(): value for key, value in reference["cpu_socket"].items()}
        if socket and socket in table:
            return table[socket], f"CPU_SOCKET:{socket}"
        chipset = (specs.get("chipset") or "").strip().upper()
        if category == "MOTHERBOARD" and chipset:
            # 芯片组本身不携带代际信息，只能标记未知
            return "UNKNOWN", f"MOTHERBOARD_CHIPSET_UNMAPPED:{chipset}"
        return "UNKNOWN", f"CPU_SOCKET_UNMAPPED:{socket or 'EMPTY'}"

    if category == "GPU":
        chipset = (specs.get("chipset") or "").strip()
        for rule in reference["gpu_chipset_patterns"]:
            if re.match(rule["pattern"], chipset):
                return rule["lifecycle"], f"GPU_CHIPSET:{rule['pattern']}"
        return "UNKNOWN", f"GPU_CHIPSET_UNMAPPED:{chipset or 'EMPTY'}"

    if category == "MEMORY":
        memory_type = (specs.get("memory_type") or "").strip().upper()
        table = reference["memory_type"]
        if memory_type in table:
            return table[memory_type], f"MEMORY_TYPE:{memory_type}"
        return "UNKNOWN", f"MEMORY_TYPE_UNMAPPED:{memory_type or 'EMPTY'}"

    if category == "STORAGE":
        interface = (specs.get("interface") or "").strip()
        for rule in reference["storage_interface"]:
            if rule["contains"].lower() in interface.lower():
                return rule["lifecycle"], f"STORAGE_INTERFACE:{rule['contains']}"
        return "UNKNOWN", f"STORAGE_INTERFACE_UNMAPPED:{interface or 'EMPTY'}"

    return "UNKNOWN", f"NO_RELIABLE_RELEASE_DATA:{category}"


def missing_required_specs(record: dict[str, Any]) -> list[str]:
    category = record["category"]
    specs = record.get("specifications") or {}
    missing = [
        field for field in COMPAT_CRITICAL.get(category, ()) if specs.get(field) in (None, "", [])
    ]
    for spec in CATEGORY_FIELDS[category]:
        if spec.required and specs.get(spec.name) in (None, "", []):
            missing.append(spec.name)
    return sorted(set(missing))


def recommendation_for(
    record: dict[str, Any], lifecycle: str
) -> tuple[str, str]:
    """按类别分组判定推荐资格；CURRENT 不等于 ELIGIBLE，UNKNOWN 不等于 EXCLUDED。"""

    category = record["category"]
    governance = record["governance_status"]

    if governance in {"INVALID", "CONFLICT"}:
        return "EXCLUDED", f"GOVERNANCE_{governance}"

    if category in GENERATION_GROUP:
        if lifecycle == "DISCONTINUED":
            return "EXCLUDED", "LIFECYCLE_DISCONTINUED"
        if lifecycle == "LEGACY":
            return "RESTRICTED", "LIFECYCLE_LEGACY"
        if lifecycle == "UNKNOWN":
            return "RESTRICTED", "LIFECYCLE_UNKNOWN"
        if governance == "INCOMPLETE":
            return "RESTRICTED", f"GOVERNANCE_INCOMPLETE_WITH_{lifecycle}"
        return "ELIGIBLE", f"GOVERNANCE_VALID_WITH_{lifecycle}"

    missing = missing_required_specs(record)
    if category in PLATFORM_GROUP:
        if missing:
            return "RESTRICTED", "MISSING_COMPAT_FIELDS:" + ",".join(missing)
        if lifecycle == "DISCONTINUED":
            return "EXCLUDED", "LIFECYCLE_DISCONTINUED"
        return "ELIGIBLE", f"SPEC_COMPLETE_WITH_{lifecycle}"

    # 散热器 / 机箱 / 电源：关键规格齐全即可推荐，生命周期 UNKNOWN 不阻断
    if missing:
        return "RESTRICTED", "MISSING_KEY_SPECS:" + ",".join(missing)
    return "ELIGIBLE", f"SPEC_COMPLETE_WITH_{lifecycle}"


def classify(
    records: list[dict[str, Any]], reference: dict[str, Any], overrides: dict[str, dict[str, str]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lifecycle_counts: dict[str, Counter[str]] = defaultdict(Counter)
    recommendation_counts: dict[str, Counter[str]] = defaultdict(Counter)
    override_count = 0

    for record in records:
        lifecycle, lifecycle_reason = lifecycle_for(record, reference)
        recommendation, recommendation_reason = recommendation_for(record, lifecycle)

        override = overrides.get(record["hardware_id"])
        if override:
            lifecycle = override.get("lifecycle_status", lifecycle)
            recommendation = override.get("recommendation_status", recommendation)
            lifecycle_reason = override.get("reason", lifecycle_reason)
            recommendation_reason = override.get("reason", recommendation_reason)
            override_count += 1

        record["lifecycle_status"] = lifecycle
        record["lifecycle_reason"] = lifecycle_reason
        record["recommendation_status"] = recommendation
        record["recommendation_reason"] = recommendation_reason
        record["rule_version"] = RULE_VERSION

        lifecycle_counts[record["category"]][lifecycle] += 1
        recommendation_counts[record["category"]][recommendation] += 1

    summary = {
        "rule_version": RULE_VERSION,
        "overrides_applied": override_count,
        "lifecycle": {category: dict(counts) for category, counts in lifecycle_counts.items()},
        "recommendation": {
            category: dict(counts) for category, counts in recommendation_counts.items()
        },
        "unknown_ratio": {
            category: round(counts.get("UNKNOWN", 0) / sum(counts.values()), 4)
            for category, counts in lifecycle_counts.items()
        },
    }
    return records, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 8.6 生命周期与推荐资格分类")
    parser.add_argument("--master", default="data/pc-config/master/hardware-master.jsonl")
    parser.add_argument("--reference", default=str(REFERENCE_PATH))
    parser.add_argument("--overrides", default=str(OVERRIDES_PATH))
    parser.add_argument("--summary", default="data/pc-config/manifest/classification.json")
    args = parser.parse_args(argv)

    master_path = Path(args.master)
    records = read_jsonl(master_path)
    reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
    overrides = load_overrides(Path(args.overrides))

    records, summary = classify(records, reference, overrides)
    write_jsonl(records, master_path)

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"[ok] 已分类 {len(records)} 条，人工覆盖 {summary['overrides_applied']} 条")
    for category in sorted(summary["lifecycle"]):
        print(f"    {category}: {summary['lifecycle'][category]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
