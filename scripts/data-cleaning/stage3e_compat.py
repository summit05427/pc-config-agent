"""Stage 3E：把源 CSV 中被丢弃的兼容性字段补回规格层。

只做归一化，不联网、不生成价格。字段缺失保持 None，不做推测。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
CLEANING_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
SOURCE_DIR = Path(r"F:\LLM_PC_Agent\Hardware data\csv")

PRODUCTS = CLEANING_DIR / "stage3a-products.jsonl"
SKUS = CLEANING_DIR / "stage2-skus.jsonl"
OUTPUT = CLEANING_DIR / "stage3e-products.jsonl"
REPORT = CLEANING_DIR / "stage3e-compat-report.json"

# 目标字段 -> 源 CSV 列名
FIELD_MAP = {
    "CASE": {
        "supported_motherboard_form_factors": "motherboard_form_factor",
        "max_gpu_length_mm": "maximum_video_card_length",
        "radiator_support": "radiator_support",
        "expansion_slots": "expansion_slots",
    },
    "GPU": {
        "length_mm": "length",
        "slot_width": "total_slot_width",
        "case_slot_width": "case_expansion_slot_width",
    },
    "PSU": {
        "pcie_8pin_count": "pcie_8_pin_connectors",
        "pcie_12vhpwr_count": "pcie_16_pin_12_vhpwr_12_v_2x6_connectors",
        "sata_count": "sata_connectors",
        "length_mm": "length",
    },
    "MOTHERBOARD": {
        "m2_slots": "m_2_slots",
        "memory_slots": "memory_slots",
        "pcie_x16_slots": "pcie_x16_slots",
    },
    "COOLER": {"height_mm": "height"},
}
CSV_BY_CATEGORY = {
    "CASE": "pcpp_case.csv",
    "GPU": "pcpp_gpu.csv",
    "PSU": "pcpp_psu.csv",
    "MOTHERBOARD": "pcpp_motherboard.csv",
    "COOLER": "pcpp_cooler.csv",
}


def parse_number(value: str | None) -> int | float | None:
    """从 "288 mm"、"2" 这类文本里取数值，取不到返回 None。"""

    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    number = float(match.group())
    return int(number) if number.is_integer() else number


def load_source(category: str) -> dict[str, dict]:
    path = SOURCE_DIR / CSV_BY_CATEGORY[category]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["pcpp_id"]: row for row in csv.DictReader(handle)}


def build_specs(category: str, row: dict) -> dict:
    specs: dict = {}
    for target, column in FIELD_MAP[category].items():
        value = parse_number(row.get(column))
        specs[target] = value if value is not None else (row.get(column) or None)
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(description="补回兼容性字段")
    parser.add_argument("--products", default=str(PRODUCTS))
    parser.add_argument("--skus", default=str(SKUS))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--report", default=str(REPORT))
    args = parser.parse_args()

    products = {
        row["product_id"]: row
        for row in (
            json.loads(line)
            for line in Path(args.products).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    skus_by_product: dict[str, list[dict]] = defaultdict(list)
    for line in Path(args.skus).read_text(encoding="utf-8").splitlines():
        if line.strip():
            sku = json.loads(line)
            skus_by_product[sku["product_id"]].append(sku)

    sources = {category: load_source(category) for category in FIELD_MAP}
    filled = Counter()
    total = Counter()

    enriched: dict[str, dict] = {}
    for product_id, product in products.items():
        category = product["category"]
        if category not in FIELD_MAP:
            enriched[product_id] = product
            continue
        best: dict = {}
        best_score = -1
        for sku in skus_by_product.get(product_id, []):
            source = sources[category].get(str(sku.get("pcpp_id")))
            if not source:
                continue
            specs = build_specs(category, source)
            score = sum(1 for value in specs.values() if value is not None)
            if score > best_score:
                best, best_score = specs, score
        merged = dict(product)
        merged["specifications"] = {**(product.get("specifications") or {}), **best}
        enriched[product_id] = merged
        total[category] += 1
        filled[category] += sum(1 for value in best.values() if value is not None)

    with Path(args.output).open("w", encoding="utf-8", newline="\n") as handle:
        for product in enriched.values():
            handle.write(json.dumps(product, ensure_ascii=False) + "\n")

    report = {
        "stage": "3E-compat",
        "products": len(enriched),
        "compat_fields_filled": dict(filled),
        "products_by_category": dict(total),
        "note": "仅补源 CSV 已有字段；缺失保持 None，未做推断。",
    }
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"补全产品 {len(enriched)} 条")
    for category in sorted(filled):
        print(f"  {category}: 填充 {filled[category]}/{total[category]} 个字段值")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
