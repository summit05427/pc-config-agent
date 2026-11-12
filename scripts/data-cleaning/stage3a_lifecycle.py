"""Stage 3A：用确定性规则标注产品生命周期。

规则只引用插槽、芯片组、芯片代号等可追溯事实，不使用发布日期，也不读取跑分。
没有规则可依据时输出 UNKNOWN，绝不推断。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RULES_VERSION = "stage3a-lifecycle-1.0.0"
BASE_DIR = Path(__file__).resolve().parents[2]
INPUT = BASE_DIR / "data" / "pc-config" / "cleaning" / "stage2-products.jsonl"
OUTPUT_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"

CURRENT = "CURRENT"
MATURE = "MATURE"
LEGACY = "LEGACY"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"

CPU_MICROARCH_RULES: dict[str, str] = {
    "Zen 5": CURRENT,
    "Zen 4": CURRENT,
    "Arrow Lake": CURRENT,
    "Zen 3": MATURE,
    "Raptor Lake": MATURE,
    "Raptor Lake Refresh": MATURE,
    "Alder Lake": MATURE,
    "Zen 2": LEGACY,
    "Zen+": LEGACY,
    "Zen": LEGACY,
    "Excavator": LEGACY,
    "Steamroller": LEGACY,
    "Piledriver": LEGACY,
    "Bulldozer": LEGACY,
    "K10": LEGACY,
    "Lynx": LEGACY,
    "Puma+": LEGACY,
    "Rocket Lake": LEGACY,
    "Comet Lake": LEGACY,
    "Coffee Lake": LEGACY,
    "Coffee Lake Refresh": LEGACY,
    "Kaby Lake": LEGACY,
    "Skylake": LEGACY,
    "Broadwell": LEGACY,
    "Haswell": LEGACY,
    "Haswell Refresh": LEGACY,
    "Ivy Bridge": LEGACY,
    "Sandy Bridge": LEGACY,
    "Westmere": LEGACY,
    "Nehalem": LEGACY,
    "Wolfdale": LEGACY,
    "Yorkfield": LEGACY,
    "Cascade Lake": LEGACY,
    "Core": LEGACY,
}

# 微架构缺失时用核心代号兜底；仍无法识别则保持 UNKNOWN。
CPU_CORE_FAMILY_RULES: dict[str, str] = {
    "Granite Ridge": CURRENT,
    "Raphael": CURRENT,
    "Arrow Lake-S": CURRENT,
    "Vermeer": MATURE,
    "Cezanne": MATURE,
    "Raptor Lake-S": MATURE,
    "Alder Lake-S": MATURE,
    "Matisse": LEGACY,
    "Renoir": LEGACY,
    "Pinnacle Ridge": LEGACY,
    "Summit Ridge": LEGACY,
    "Bristol Ridge": LEGACY,
    "Rocket Lake-S": LEGACY,
    "Comet Lake-S": LEGACY,
    "Coffee Lake-S": LEGACY,
    "Coffee Lake Refresh": LEGACY,
    "Kaby Lake-S": LEGACY,
    "Skylake-S": LEGACY,
    "Haswell Refresh": LEGACY,
}

GPU_CHIPSET_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bRTX\s?50\d0\b", re.I), CURRENT),
    (re.compile(r"\bRX\s?9\d{3}\b", re.I), CURRENT),
    (re.compile(r"\bArc\s?(Pro\s?)?B\d{2,3}\b", re.I), CURRENT),
    (re.compile(r"\bRadeon\s?Pro\s?W7\d{3}\b", re.I), CURRENT),
    (re.compile(r"\bRadeon\s?AI\s?PRO\s?R?9\d{3}\b", re.I), CURRENT),
    (re.compile(r"\bRTX\s?PRO\s?\d{4}\b", re.I), CURRENT),
    (re.compile(r"\bRTX\s?40\d0\b", re.I), MATURE),
    (re.compile(r"\bRX\s?7\d{3}\b", re.I), MATURE),
    (re.compile(r"\bRadeon\s?Pro\s?W6\d{3}\b", re.I), MATURE),
    (re.compile(r"\bRTX\s?(30|20|16|10)\d0\b", re.I), LEGACY),
    (re.compile(r"\bRX\s?(6|5)\d{3}\b", re.I), LEGACY),
    (re.compile(r"\bArc\s?A\d{3}\b", re.I), LEGACY),
    (re.compile(r"\bGTX\b|\bGTS\b|\bRadeon\s?VII\b|\bVega\b", re.I), LEGACY),
    (re.compile(r"\bRX\s?\d{3}\b", re.I), LEGACY),
    (re.compile(r"\bR9\s?\d{3}\b", re.I), LEGACY),
    (re.compile(r"\bFirePro\b|\bQuadro\b|\bTesla\b", re.I), LEGACY),
    (re.compile(r"\bGeForce\s?(GT\s?)?\d{3,4}\b", re.I), LEGACY),
    (re.compile(r"\bRadeon\s?(HD\s?)?\d{4}\b", re.I), LEGACY),
]

AMD_CHIPSET_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(X870E?|B850|B840|A820)$"), CURRENT),
    (re.compile(r"^(X670E?|B650E?|A620A?)$"), MATURE),
    (re.compile(r"^(X570|B550|A520)$"), MATURE),
    (re.compile(r"^(X470|B450|X370|B350|A320)$"), LEGACY),
    (re.compile(r"^(A\d{2}[A-Z]?|[789]\d{2}[A-Z]{0,2})$"), LEGACY),
]

INTEL_CHIPSET_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(Z890|B860|H810|W880)$"), CURRENT),
    (re.compile(r"^(Z790|B760|H770|W680)$"), MATURE),
    (re.compile(r"^(Z690|B660|H670|H610)$"), LEGACY),
    (re.compile(r"^(Z590|B560|H510|Z490|B460|H410|Z390|B365|H370)$"), LEGACY),
    (re.compile(r"^(H\d{2}|P\d{2}|B\d{2}|Z\d{2}|X\d{2}|Q\d{2})$"), LEGACY),
    (re.compile(r"^([HBPZQX]\d{3}[A-Z]?|C\d{3})$"), LEGACY),
]

COMMODITY_CATEGORIES = {"MEMORY", "STORAGE", "PSU", "CASE", "COOLER"}


def classify_cpu(specs: dict[str, Any]) -> tuple[str, str, str | None]:
    """以微架构为主、核心代号兜底；插槽跨代太多，单独使用会误判。"""

    microarch = str(specs.get("microarchitecture") or "").strip()
    if microarch:
        status = CPU_MICROARCH_RULES.get(microarch)
        if status:
            return status, f"cpu_microarch:{microarch}", microarch
    family = str(specs.get("core_family") or "").strip()
    if family:
        status = CPU_CORE_FAMILY_RULES.get(family)
        if status:
            return status, f"cpu_core_family:{family}", family
    socket = specs.get("socket")
    if not microarch and not family and socket:
        return UNKNOWN, "cpu_identity_missing", str(socket)
    return UNKNOWN, "microarch_not_in_rules", microarch or family or None


def classify_gpu(specs: dict[str, Any]) -> tuple[str, str, str | None]:
    chipset = str(specs.get("chipset") or "")
    if not chipset:
        return UNKNOWN, "chipset_missing", None
    for pattern, status in GPU_CHIPSET_RULES:
        if pattern.search(chipset):
            return status, f"gpu_chipset:{pattern.pattern}", chipset
    return UNKNOWN, "chipset_not_in_rules", chipset


def classify_motherboard(specs: dict[str, Any]) -> tuple[str, str, str | None]:
    chipset = str(specs.get("chipset") or "").upper()
    if not chipset:
        return UNKNOWN, "chipset_missing", None
    for pattern, status in AMD_CHIPSET_RULES + INTEL_CHIPSET_RULES:
        if pattern.search(chipset):
            return status, f"mb_chipset:{pattern.pattern}", chipset
    return UNKNOWN, "chipset_not_in_rules", chipset


def classify(product: dict[str, Any]) -> tuple[str, str, str | None]:
    category = product["category"]
    specs = product.get("specifications") or {}
    if category == "CPU":
        return classify_cpu(specs)
    if category == "GPU":
        return classify_gpu(specs)
    if category == "MOTHERBOARD":
        return classify_motherboard(specs)
    if category in COMMODITY_CATEGORIES:
        return NOT_APPLICABLE, "category_has_no_generation", None
    return UNKNOWN, "category_not_covered", None


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3A 生命周期确定性标注")
    parser.add_argument("--input", default=str(INPUT))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    products = [json.loads(line) for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    status_counts: dict[str, Counter] = defaultdict(Counter)
    unknown_samples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for product in products:
        status, rule, evidence = classify(product)
        product["lifecycle_status"] = status
        product["lifecycle_evidence"] = {
            "rule": rule,
            "evidence": evidence,
            "rules_version": RULES_VERSION,
        }
        status_counts[product["category"]][status] += 1
        if status == UNKNOWN and len(unknown_samples[product["category"]]) < 5:
            unknown_samples[product["category"]].append({
                "product_id": product["product_id"],
                "display_name": product["display_name"],
                "rule": rule,
                "evidence": evidence,
            })

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "stage3a-products.jsonl"
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for product in sorted(products, key=lambda item: item["product_id"]):
            handle.write(json.dumps(product, ensure_ascii=False) + "\n")

    report = {
        "stage": "3A",
        "rules_version": RULES_VERSION,
        "input_products": len(products),
        "status_by_category": {
            category: dict(sorted(counter.items()))
            for category, counter in sorted(status_counts.items())
        },
        "unknown_samples": dict(unknown_samples),
        "note": "仅依据插槽/芯片组/芯片代号；不读取发布日期与跑分。",
    }
    (output_dir / "stage3a-lifecycle-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print(f"输入产品 {len(products)} 个")
    for category, counter in sorted(status_counts.items()):
        print(f"  {category}: " + ", ".join(f"{key}={value}" for key, value in sorted(counter.items())))
    print(f"输出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
