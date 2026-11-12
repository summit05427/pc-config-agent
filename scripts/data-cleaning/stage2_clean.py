"""Stage 2：清洗、标准化与安全去重。

规则边界：
- 只读取 PCPartPicker 原始 CSV 与旧主数据（仅用于复用稳定 hardware_id）。
- 不读取跑分文件，跑分不参与清洗、去重和质量判定。
- 只有「品牌 + 品类 + MPN」或「品牌 + 品类 + 型号 + 关键规格」完全一致才自动合并。
- 跨品牌的同型号、同芯片不同 AIB、不同显存/容量一律不合并，只记录别名建议。

使用方式：
    python scripts/data-cleaning/stage2_clean.py
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cleaning_common import (
    CATEGORY_MAP,
    DEFAULT_CSV,
    DISCRIMINATORS,
    OUTPUT_DIR,
    RULES_VERSION,
    canon,
    load_rows,
    normalize_brand,
    quality_of,
    split_values,
)
from spec_normalizer import clean_model_name, normalize

MASTER_PATH = Path(__file__).resolve().parents[2] / "data" / "pc-config" / "master" / "hardware-master.jsonl"
QUALITY_ORDER = {"UNIDENTIFIED": 4, "ANOMALOUS": 3, "INCOMPLETE": 2, "GOOD": 1}


def slugify(value: str, limit: int = 48) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text[:limit].strip("-") or "unknown"


def build_record(row: dict[str, Any]) -> dict[str, Any]:
    raw_specs = json.loads(row.get("specs_json") or "{}")
    category = CATEGORY_MAP.get(row.get("type") or "")
    brand = normalize_brand(row.get("brand"))
    record: dict[str, Any] = {
        "pcpp_id": str(row["pcpp_id"]),
        "category": category,
        "brand": brand,
        "model_name": "",
        "mpn_values": split_values(raw_specs.get("Part #")),
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
    if not brand or not row.get("list_name"):
        record["quality_reasons"] = ["MISSING_IDENTITY"]
        return record
    record["model_name"] = clean_model_name(category, row.get("list_name") or "", raw_specs)
    record["specifications"] = normalize(category, raw_specs)
    record["quality_status"], record["quality_reasons"] = quality_of(category, record["specifications"])
    return record


def signature(record: dict[str, Any]) -> str:
    values = [str(record["specifications"].get(field)) for field in DISCRIMINATORS[record["category"]]]
    return "|".join(values)


def group_records(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """先按 MPN 精确合并，再按品牌+型号+关键规格合并；跨品牌不合并。"""

    assigned: set[str] = set()
    groups: list[list[dict[str, Any]]] = []

    exact: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["quality_status"] == "UNIDENTIFIED" or not record["mpn_values"]:
            continue
        for mpn in record["mpn_values"]:
            exact[(record["category"], canon(record["brand"]), canon(mpn))].append(record)

    for key, items in sorted(exact.items()):
        unique = {item["pcpp_id"]: item for item in items if item["pcpp_id"] not in assigned}
        if len(unique) < 2:
            continue
        group = sorted(unique.values(), key=lambda item: int(item["pcpp_id"]))
        groups.append(group)
        assigned.update(item["pcpp_id"] for item in group)

    model_groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["pcpp_id"] in assigned or record["quality_status"] == "UNIDENTIFIED":
            continue
        key = (record["category"], canon(record["brand"]), canon(record["model_name"]), signature(record))
        model_groups[key].append(record)

    for key, items in sorted(model_groups.items()):
        if len(items) > 1:
            groups.append(sorted(items, key=lambda item: int(item["pcpp_id"])))
            assigned.update(item["pcpp_id"] for item in items)

    for record in records:
        if record["pcpp_id"] not in assigned:
            groups.append([record])
    return groups


def load_old_id_index() -> tuple[dict[str, str], dict[tuple[str, str, str], list[str]]]:
    """旧目录只用来复用 hardware_id；不读取任何状态或跑分字段。"""

    by_url: dict[str, str] = {}
    by_identity: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    if not MASTER_PATH.exists():
        return by_url, by_identity
    with MASTER_PATH.open(encoding="utf-8") as handle:
        for raw in handle:
            if not raw.strip():
                continue
            item = json.loads(raw)
            source_url = (item.get("source") or {}).get("source_url")
            if source_url:
                by_url[source_url] = item["hardware_id"]
            identity = (
                item.get("category") or "",
                canon(item.get("brand")),
                canon(item.get("model_name")),
            )
            by_identity[identity].append(item["hardware_id"])
    return by_url, by_identity


def make_product(group: list[dict[str, Any]], by_url: dict[str, str],
                 by_identity: dict[tuple[str, str, str], list[str]]) -> tuple[dict[str, Any], str]:
    head = group[0]
    old_id = by_url.get(head["source_url"] or "")
    if not old_id:
        candidates = by_identity.get((head["category"], canon(head["brand"]), canon(head["model_name"])), [])
        old_id = candidates[0] if len(candidates) == 1 else None
    product_id = old_id or (
        f"{head['category'].lower()}-{slugify(head['brand'], 24)}-"
        f"{slugify(head['model_name'], 48)}-{head['pcpp_id']}"
    )

    reasons: list[str] = []
    quality = "GOOD"
    specs: dict[str, Any] = {}
    for item in group:
        quality = item["quality_status"] if QUALITY_ORDER[item["quality_status"]] > QUALITY_ORDER[quality] else quality
        reasons.extend(item["quality_reasons"])
        if not specs:
            specs = item["specifications"]

    product = {
        "product_id": product_id,
        "category": head["category"],
        "brand": head["brand"],
        "model_name": head["model_name"],
        "display_name": (
            head["model_name"] if head["model_name"].lower().startswith(head["brand"].lower())
            else f"{head['brand']} {head['model_name']}".strip()
        ),
        "identifiers": {
            "mpn": sorted({mpn for item in group for mpn in item["mpn_values"]}),
            "pcpp_ids": [item["pcpp_id"] for item in group],
        },
        "specifications": specs,
        "quality_status": quality,
        "quality_reasons": sorted(set(reasons)),
        "stage2_confidence": "MEDIUM" if quality == "GOOD" else "LOW",
        "source": {
            "dataset": "pcpp",
            "source_urls": sorted({item["source_url"] for item in group if item["source_url"]}),
            "image_url": next((item["image_url"] for item in group if item["image_url"]), None),
            "reference_price_usd": next(
                (item["reference_price_usd"] for item in group if item["reference_price_usd"]), None
            ),
        },
        "lifecycle_status": None,
        "market_status": None,
        "availability_status": None,
        "recommendation_status": None,
        "status_note": "Stage 3 未执行；空状态不代表不可用，也不得用于推荐。",
        "rules_version": RULES_VERSION,
    }
    return product, quality


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 2 硬件清洗与安全去重")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    rows = load_rows(Path(args.csv))
    records = [build_record(row) for row in rows]
    groups = group_records(records)
    by_url, by_identity = load_old_id_index()

    products: list[dict[str, Any]] = []
    skus: list[dict[str, Any]] = []
    merge_map: list[dict[str, Any]] = []
    change_log: list[dict[str, Any]] = []
    id_map: list[dict[str, str]] = []

    for group in groups:
        product, _ = make_product(group, by_url, by_identity)
        products.append(product)
        for index, item in enumerate(group):
            action = "CANONICAL" if index == 0 else "MERGED"
            old_hardware_id = by_url.get(item["source_url"] or "")
            id_map.append({
                "old_hardware_id": old_hardware_id or "",
                "product_id": product["product_id"],
                "pcpp_id": item["pcpp_id"],
            })
            skus.append({
                "sku_id": f"pcpp:{item['pcpp_id']}",
                "product_id": product["product_id"],
                "old_hardware_id": old_hardware_id,
                "pcpp_id": item["pcpp_id"],
                "brand": item["brand"],
                "model_name": item["model_name"],
                "mpn_values": item["mpn_values"],
                "specifications": item["specifications"],
                "quality_status": item["quality_status"],
                "quality_reasons": item["quality_reasons"],
                "source_url": item["source_url"],
                "image_url": item["image_url"],
                "reference_price_usd": item["reference_price_usd"],
            })
            if action == "MERGED":
                merge_map.append({
                    "pcpp_id": item["pcpp_id"],
                    "product_id": product["product_id"],
                    "old_hardware_id": old_hardware_id,
                    "merged_into_pcpp_id": group[0]["pcpp_id"],
                    "reason": "EXACT_MPN",
                })
            change_log.append({
                "pcpp_id": item["pcpp_id"],
                "product_id": product["product_id"],
                "action": action,
                "quality_status": item["quality_status"],
                "quality_reasons": item["quality_reasons"],
            })

    products.sort(key=lambda item: item["product_id"])
    skus.sort(key=lambda item: int(item["pcpp_id"]))
    merge_map.sort(key=lambda item: int(item["pcpp_id"]))
    change_log.sort(key=lambda item: int(item["pcpp_id"]))
    id_map.sort(key=lambda item: int(item["pcpp_id"]))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows_payload in (
        ("stage2-products.jsonl", products),
        ("stage2-skus.jsonl", skus),
        ("stage2-merge-map.jsonl", merge_map),
        ("stage2-change-log.jsonl", change_log),
        ("stage2-id-map.jsonl", id_map),
    ):
        path = output_dir / name
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for item in rows_payload:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    quality_counts = Counter(product["quality_status"] for product in products)
    per_category = Counter(product["category"] for product in products)
    report = {
        "stage": 2,
        "rules_version": RULES_VERSION,
        "input_records": len(records),
        "output_products": len(products),
        "output_skus": len(skus),
        "merged_records": len(merge_map),
        "products_by_category": dict(sorted(per_category.items())),
        "quality_counts": dict(sorted(quality_counts.items())),
        "merge_reasons": dict(sorted(Counter(item["reason"] for item in merge_map).items())),
        "note": "未读取跑分数据；lifecycle/market/recommendation 留空，等待 Stage 3。",
    }
    (output_dir / "stage2-cleaning-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print(f"输入 {len(records)} 条 → 产品 {len(products)} 个，SKU {len(skus)} 条，合并 {len(merge_map)} 条")
    print("品类产品数：" + json.dumps(report["products_by_category"], ensure_ascii=False))
    print("质量分布：" + json.dumps(report["quality_counts"], ensure_ascii=False))
    print(f"输出目录：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
