"""把 Stage 4 短名单导出为运行时 catalog.json。

短名单的 hardware_id 与旧 catalog 同源，因此直接复用旧条目的归一化规格，
只补充人民币参考价与热门标记，避免重新做一遍规格归一化。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
CLEANING_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
SHORTLIST = CLEANING_DIR / "stage4-shortlist.jsonl"
CN_MODELS = CLEANING_DIR / "cn-models.jsonl"
SOURCE_CATALOG = BASE_DIR / "data" / "pc-config" / "export" / "runtime-full" / "catalog.json"
# 完整目录快照：首次运行时从现有 catalog.json 备份，后续都从这里取规格，避免重复导出后丢条目
FULL_CATALOG = BASE_DIR / "data" / "pc-config" / "export" / "runtime-full" / "catalog-full.json"
TARGETS = [
    SOURCE_CATALOG,
    BASE_DIR / "application-service" / "src" / "main" / "resources" / "pc-config" / "catalog.json",
]
BENCHMARK_MAP = CLEANING_DIR / "benchmark-map.json"
IMAGE_MAP = CLEANING_DIR / "image-map.json"
BENCHMARK_TARGETS = [
    BASE_DIR / "data" / "pc-config" / "export" / "runtime-full" / "benchmarks.json",
    BASE_DIR / "application-service" / "src" / "main" / "resources" / "pc-config" / "benchmarks.json",
]
CATALOG_VERSION = "2026.11.2"

PRICE_FIELDS = (
    "price_cny",
    "price_source",
    "price_status",
    "price_confidence",
    "price_note",
    "price_source_url",
    "popularity_status",
    "hot_label",
    "stratum",
)


def main() -> int:
    shortlist = {
        row["product_id"]: row
        for row in (json.loads(line) for line in SHORTLIST.read_text(encoding="utf-8").splitlines() if line.strip())
    }
    if not FULL_CATALOG.exists():
        FULL_CATALOG.write_text(SOURCE_CATALOG.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    catalog = json.loads(FULL_CATALOG.read_text(encoding="utf-8"))
    hardware = []
    seen: set[str] = set()
    for entry in catalog["hardware"]:
        price_row = shortlist.get(entry["hardware_id"])
        if not price_row:
            continue
        merged = dict(entry)
        for field in PRICE_FIELDS:
            if field in price_row:
                merged[field] = price_row[field]
        hardware.append(merged)
        seen.add(entry["hardware_id"])
    # 国行补充型号：源数据（PCPartPicker）不含这些品牌，单独挂到 catalog 末尾
    for row in (json.loads(line) for line in CN_MODELS.read_text(encoding="utf-8").splitlines() if line.strip()):
        if row["product_id"] not in shortlist or row["product_id"] in seen:
            continue
        # 价格一律取短名单：它是「stage4 → 观测账本 → 兜底」的唯一输出，
        # cn-models 只提供型号与规格，不再自带价格，避免两处价格各说各话
        price_row = shortlist[row["product_id"]]
        entry = {
            "hardware_id": row["product_id"],
            "category": row["category"],
            "brand": row["brand"],
            "model_name": row["model_name"],
            "display_name": row["display_name"],
            "specifications": row["specifications"],
            "source": {
                "dataset": "cn_models",
                "image_url": None,
                "license_status": "VERIFIED",
                "reference_price": price_row["price_cny"],
                "reference_price_note": "国内电商参考价，与 price_note 同源",
                "source_url": price_row["price_source_url"],
            },
            "data_quality_status": "PARTIAL",
            "lifecycle_status": row["lifecycle_status"],
            "recommendation_status": row["recommendation_status"],
            "unverified_fields": [],
            "selection_reason": "CN_RETAIL_MODEL",
        }
        for field in PRICE_FIELDS:
            if field in price_row:
                entry[field] = price_row[field]
        hardware.append(entry)
        seen.add(row["product_id"])
    missing = [product_id for product_id in shortlist if product_id not in seen]

    # 产品图回填：PCPartPicker 源里有图的条目已在 catalog-full 带 image_url，
    # 这里只补 image-map 里命中的（按 pcpp_id 映射），国行型号仍可能为空
    image_map = json.loads(IMAGE_MAP.read_text(encoding="utf-8"))["entries"] if IMAGE_MAP.exists() else {}
    image_filled = 0
    for entry in hardware:
        source = entry.setdefault("source", {})
        if not source.get("image_url") and image_map.get(entry["hardware_id"]):
            source["image_url"] = image_map[entry["hardware_id"]]
            image_filled += 1
    image_missing = sum(1 for entry in hardware if not (entry.get("source") or {}).get("image_url"))

    payload = {
        "schema_version": catalog["schema_version"],
        "catalog_version": CATALOG_VERSION,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "stage4-hot-shortlist 2026-11-11，价格为国内参考价（WEBSEARCH 观测 + 档位估算）",
        "platform_pairs": catalog.get("platform_pairs", []),
        "hardware": hardware,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    for target in TARGETS:
        target.write_text(text, encoding="utf-8", newline="\n")
    benchmark_text = build_benchmark_payload({entry["hardware_id"] for entry in hardware})
    if benchmark_text is not None:
        for target in BENCHMARK_TARGETS:
            target.write_text(benchmark_text, encoding="utf-8", newline="\n")
    print(
        f"exported={len(hardware)} missing_in_catalog={len(missing)} "
        f"image_filled={image_filled} image_missing={image_missing}"
    )
    return 0


def build_benchmark_payload(hardware_ids: set[str]) -> str | None:
    """把跑分映射裁剪到当前目录并序列化；映射文件不存在时返回 None。"""

    if not BENCHMARK_MAP.exists():
        return None
    payload = json.loads(BENCHMARK_MAP.read_text(encoding="utf-8"))
    payload["entries"] = [entry for entry in payload["entries"] if entry["hardware_id"] in hardware_ids]
    payload["unmatched"] = [item for item in payload.get("unmatched", []) if item["hardware_id"] in hardware_ids]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
