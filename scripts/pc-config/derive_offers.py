"""从已采集的详情页 SKU 矩阵派生平台观测价。

LLM 拆解不可用时，用规则从「规格 → 价格」矩阵直接抽取型号；所有结果仍要过主库
唯一命中与价格区间校验，未命中的 SKU 一律丢弃，不做猜测。
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKET_DIR = REPO_ROOT / "data" / "pc-config" / "export" / "marketplace"
DETAIL_DIR = MARKET_DIR / "detail"
MASTER_PATH = REPO_ROOT / "data" / "pc-config" / "master" / "hardware-master.jsonl"
CATALOG_PATH = REPO_ROOT / "application-service" / "src" / "main" / "resources" / "pc-config" / "catalog.json"
OUTPUT_PATH = MARKET_DIR / "llm_offers.json"

PRICE_RANGES = {"CPU": (200_00, 20_000_00), "GPU": (500_00, 40_000_00)}
# 显卡按芯片分档定价；区间锚定 2026-11 已有的 4 条人工核验价（5060 Ti 16GB 6649、
# 5070 Ti 16GB 13999、9060 XT 16GB 5199、9070 XT 16GB 7299），未列出的芯片一律不采信。
GPU_PRICE_BANDS = {
    "gpu-geforce-rtx-5060-8gb": (2_800_00, 4_600_00),
    "gpu-geforce-rtx-5060-ti-8gb": (4_200_00, 6_400_00),
    "gpu-geforce-rtx-5060-ti-16gb": (5_000_00, 8_500_00),
    "gpu-geforce-rtx-5070-12gb": (9_000_00, 13_500_00),
    "gpu-geforce-rtx-5070-ti-16gb": (11_000_00, 17_000_00),
    "gpu-geforce-rtx-5080-16gb": (16_000_00, 24_000_00),
    "gpu-geforce-rtx-4080-16gb": (7_500_00, 14_000_00),
    "gpu-geforce-rtx-4090-24gb": (18_000_00, 32_000_00),
    "gpu-radeon-rx-9060-xt-16gb": (4_000_00, 6_500_00),
    "gpu-radeon-rx-9070-xt-16gb": (5_800_00, 9_000_00),
}
EXCLUDE_KEYWORDS = ("涡轮", "无货", "定金", "维修", "亮机")
PROVIDER = "chengkit-taobao"


def log(message: str) -> None:
    print(f"[{date.today().isoformat()}] {message}", flush=True)


def cpu_key(name: str) -> str | None:
    """把 CPU 名称归一为 i5-14600kf / r5-5600 这类可比较的键。"""

    text = name.lower()
    match = re.search(r"(i[3579])[\s-]*(\d{4,5})([a-z]*)", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}{match.group(3)}"
    match = re.search(r"(?:ryzen\s*)?([3579])\s*(\d{4})([a-z0-9]*)", text)
    if match:
        return f"r{match.group(1)}-{match.group(2)}{match.group(3)}"
    return None


def gpu_key(name: str) -> str | None:
    """把显卡名称归一为 5060ti-8 / 9070xt-16 这类芯片 + 显存键。"""

    text = name.lower().replace("geforce", "").replace("radeon", "")
    model = re.search(r"(rtx|rx|arc)\s*([a-z]?\d{3,4})\s*(ti|super|xt|xtx)?", text)
    vram = re.search(r"(\d{1,2})\s*gb", text)
    if not model or not vram:
        return None
    return f"{model.group(1)}{model.group(2)}{model.group(3) or ''}-{vram.group(1)}"


def build_master_index(master: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for item in master:
        category = item["category"]
        key = cpu_key(item["model_name"]) if category == "CPU" else gpu_key(item["model_name"]) if category == "GPU" else None
        if key:
            index[(category, key)].append(item["hardware_id"])
    return index


def load_details() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(DETAIL_DIR.glob("*.json")):
        if path.name.endswith((".item.json", ".sku.json", ".args.json")) or path.name.startswith("_"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload.get("item"), dict):
            rows.append(payload)
    return rows


def derive(details: list[dict[str, Any]], master: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """按 hardware_id 聚合 SKU 价格，取中位价作为观测价。"""

    index = build_master_index(master)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stats = {"sku_total": 0, "sku_keyed": 0, "sku_matched": 0, "sku_rejected": 0}

    for payload in details:
        item = payload["item"]
        category = item.get("category")
        if category not in PRICE_RANGES:
            continue
        for sku in payload.get("skus") or []:
            spec = (sku.get("spec") or "").strip()
            price_fen = int(sku.get("fen") or 0)
            if not spec or price_fen <= 0:
                continue
            stats["sku_total"] += 1
            if any(word in spec for word in EXCLUDE_KEYWORDS):
                stats["sku_rejected"] += 1
                continue
            key = cpu_key(spec) if category == "CPU" else gpu_key(spec)
            if not key:
                stats["sku_rejected"] += 1
                continue
            stats["sku_keyed"] += 1
            hits = index.get((category, key), [])
            if not hits:
                stats["sku_rejected"] += 1
                continue
            stats["sku_matched"] += 1
            samples[hits[0]].append({
                "price_fen": price_fen,
                "spec": spec,
                "item_id": item.get("item_id"),
                "url": item.get("url"),
                "shop": item.get("shop"),
                "title": item.get("title"),
                "category": category,
                "ambiguous": len(hits) > 1,
            })

    low, high = 0, 0
    offers: list[dict[str, Any]] = []
    for hardware_id, rows in sorted(samples.items()):
        category = rows[0]["category"]
        prices = sorted(row["price_fen"] for row in rows)
        median = int(statistics.median(prices))
        lowest, highest = PRICE_RANGES[category]
        if not lowest <= median <= highest:
            stats["sku_rejected"] += len(rows)
            continue
        spread = (prices[-1] - prices[0]) / median if median else 0.0
        picked = min(rows, key=lambda row: abs(row["price_fen"] - median))
        offers.append({
            "hardware_id": hardware_id,
            "category": category,
            "title": f"{picked['title']}｜{picked['spec']}",
            "price_fen": median,
            "url": picked["url"],
            "item_id": picked["item_id"],
            "shop": picked["shop"],
            "sample_count": len(prices),
            "spread": round(spread, 3),
            "low_confidence": spread > 0.5 or (category == "GPU" and len(prices) < 2),
            "brand_ambiguous": any(row["ambiguous"] for row in rows),
        })
    return offers, stats


def sync_catalog(extra_ids: set[str], master: list[dict[str, Any]]) -> tuple[int, str]:
    """把派生报价涉及的硬件并入运行时目录，避免报价因目录缺失被丢弃。"""

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    existing = {item["hardware_id"]: item for item in catalog["hardware"]}
    by_id = {item["hardware_id"]: item for item in master}
    added = 0
    for hardware_id in sorted(extra_ids - set(existing)):
        source = by_id.get(hardware_id)
        if not source:
            continue
        existing[hardware_id] = {
            "hardware_id": hardware_id,
            "category": source["category"],
            "brand": source["brand"],
            "model_name": source["model_name"],
            "display_name": source["model_name"],
            "specifications": source["specifications"],
            "data_quality_status": source["data_quality_status"],
            "lifecycle_status": source["lifecycle_status"],
            "recommendation_status": source["recommendation_status"],
        }
        added += 1
    version = catalog["catalog_version"]
    match = re.search(r"-(\d+)$", version)
    version = f"{version[:match.start()]}-{int(match.group(1)) + 1}" if match else f"{version}-2"
    catalog = {
        "catalog_version": version,
        "platform_pairs": catalog.get("platform_pairs") or [],
        "hardware": list(existing.values()),
    }
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return added, version


def load_allowed_ids() -> set[str]:
    """只允许可售池或已在运行时目录中的硬件，避免把旧代产品带进发布集。"""

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    sellable = json.loads((MARKET_DIR / "sellable.json").read_text(encoding="utf-8"))
    return ({item["hardware_id"] for item in catalog["hardware"]}
            | {item["hardware_id"] for item in sellable["items"]})


def filter_offers(offers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], str]]]:
    allowed = load_allowed_ids()
    kept: list[dict[str, Any]] = []
    dropped: list[tuple[dict[str, Any], str]] = []
    for offer in offers:
        if offer["hardware_id"] not in allowed:
            dropped.append((offer, "不在可售池/目录"))
            continue
        if offer["category"] == "GPU":
            band = GPU_PRICE_BANDS.get(offer["hardware_id"])
            if not band:
                dropped.append((offer, "显卡未配置价格区间"))
                continue
            if not band[0] <= offer["price_fen"] <= band[1]:
                dropped.append((offer, "超出显卡价格区间"))
                continue
        kept.append(offer)
    return kept, dropped


def main() -> int:
    parser = argparse.ArgumentParser(description="从详情页 SKU 派生平台观测价")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    parser.add_argument("--sync-catalog", action="store_true", help="把涉及硬件并入运行时目录")
    args = parser.parse_args()

    master = [json.loads(line) for line in MASTER_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    details = load_details()
    offers, stats = derive(details, master)
    raw_count = len(offers)
    offers, dropped = filter_offers(offers)
    log(f"详情 {len(details)} 条，SKU {stats['sku_total']} 条，可归一 {stats['sku_keyed']} 条，"
        f"主库命中 {stats['sku_matched']} 条，丢弃 {stats['sku_rejected']} 条")
    log(f"派生硬件 {raw_count} 个，通过门禁 {len(offers)} 个，剔除 {len(dropped)} 个")
    for offer, reason in dropped:
        log(f"  剔除 {offer['category']:<3} {offer['hardware_id']:<42} ¥{offer['price_fen'] / 100:>8.2f}：{reason}")
    for offer in offers:
        log(f"  {offer['category']:<3} {offer['hardware_id']:<42} ¥{offer['price_fen'] / 100:>8.2f} "
            f"样本{offer['sample_count']} 价差{offer['spread']:.0%}")

    if args.dry_run:
        return 0
    OUTPUT_PATH.write_text(json.dumps({
        "provider": PROVIDER,
        "price_basis": "SKU_PANEL",
        "observed_at": date.today().isoformat(),
        "offers": offers,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"已写入 {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    if args.sync_catalog:
        extra_ids = {offer["hardware_id"] for offer in offers}
        # 搜索匹配价与档位价也带硬件进入目录，否则 ingest 会因 hardware_id 不在目录而拒收。
        for source in ("market_offers.json", "bucket_offers.json", "fallback_offers.json"):
            source_path = MARKET_DIR / source
            if not source_path.is_file():
                continue
            source_offers = json.loads(source_path.read_text(encoding="utf-8")).get("offers") or []
            # 任何已定价硬件都必须进入目录，价格区间已由上游与 merge_offers 两级门禁校验。
            extra_ids |= {
                offer["hardware_id"]
                for offer in source_offers
                if int(offer.get("price_fen") or 0) > 0
            }
        added, version = sync_catalog(extra_ids, master)
        log(f"目录新增 {added} 条，catalog_version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
