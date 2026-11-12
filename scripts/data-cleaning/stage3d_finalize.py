"""Stage 3D：本地收尾。补齐缺失价格、生成推荐状态、收缩候选池。

不发起任何网络请求，只使用已有规格桶价格与硬件数据。
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from stage3c_tiers import quantile

BASE_DIR = Path(__file__).resolve().parents[2]
CLEANING_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
PRODUCTS = CLEANING_DIR / "stage3e-products.jsonl"
CANDIDATES = CLEANING_DIR / "stage3c-candidates.jsonl"
FINAL = CLEANING_DIR / "stage3d-final-candidates.jsonl"
POOL = CLEANING_DIR / "stage3d-candidate-pool.jsonl"
REPORT = CLEANING_DIR / "stage3d-final-report.json"

EXCLUDED_LIFECYCLE = {"LEGACY", "UNKNOWN"}
MODERN_SOCKETS = {"AM5", "AM4", "LGA1700", "LGA1851"}
MODERN_MB_CHIPSETS = {
    "A620", "B650", "B650E", "X670", "X670E", "B840", "B850", "B850E", "X870", "X870E",
    "H610", "B660", "B760", "Z690", "Z790", "H810", "B860", "Z890",
    "A520", "B450", "B550", "X470", "X570",
}
CONSUMER_CASE_TYPES = {
    "ATX Mid Tower", "ATX Full Tower", "MicroATX Mid Tower", "MicroATX Mini Tower",
    "MicroATX Desktop", "Mini ITX Tower", "Mini ITX Desktop",
}


def is_eligible(row: dict, specs: dict) -> bool:
    """剔除无法用于现代整机的老平台与非消费形态。"""

    category = row["category"]
    if category == "CPU":
        return specs.get("socket") in MODERN_SOCKETS
    if category == "GPU":
        vram = specs.get("vram_gb") or 0
        return 6 <= vram <= 48
    if category == "MOTHERBOARD":
        chipset = str(specs.get("chipset") or "").upper()
        return specs.get("socket") in MODERN_SOCKETS and any(
            chip in chipset for chip in MODERN_MB_CHIPSETS
        )
    if category == "MEMORY":
        return specs.get("memory_type") in {"DDR4", "DDR5"} and (specs.get("capacity_gb") or 0) >= 8
    if category == "STORAGE":
        return (specs.get("capacity_gb") or 0) >= 480
    if category == "PSU":
        return (specs.get("rated_power_w") or 0) >= 450
    if category == "CASE":
        return specs.get("case_type") in CONSUMER_CASE_TYPES
    return True


def stratum_of(row: dict, specs: dict) -> str:
    """按关键规格分层，保证每个池子覆盖不同平台与用途。"""

    category = row["category"]
    if category in ("CPU", "MOTHERBOARD"):
        return f"socket:{specs.get('socket')}"
    if category == "GPU":
        vram = specs.get("vram_gb") or 0
        return f"vram:{'8' if vram <= 8 else '12' if vram <= 12 else '16+'}"
    if category == "MEMORY":
        return f"type:{specs.get('memory_type')}"
    if category == "STORAGE":
        return f"media:{specs.get('media_type') or 'SSD'}"
    if category == "PSU":
        watt = specs.get("rated_power_w") or 0
        band = "450-550" if watt < 600 else "600-700" if watt < 750 else "750-850" if watt < 1000 else "1000+"
        return f"watt:{band}"
    if category == "CASE":
        return f"form:{specs.get('case_type')}"
    if category == "COOLER":
        radiator = specs.get("radiator_size_mm")
        return f"cooling:{'water-' + str(radiator) if radiator else 'air'}"
    return "other"


def select_group(items: list[dict], limit: int, per_stratum: int | None = None, brand_cap: int = 2) -> list[dict]:
    """先按规格层各取少量，再用完整度补齐，避免单一平台垄断。"""

    strata: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        strata[item["stratum"]].append(item)

    ordered: dict[str, list[dict]] = {
        key: sorted(group, key=lambda row: row["price_cny"] or 0) for key, group in strata.items()
    }
    # 每个规格层的配额按层数均分，避免“先遍历到谁谁占满”。
    cap = per_stratum or max(3, limit // max(len(ordered), 1) + 1)
    # 单一品牌的层（如某个 CPU 插槽）不应被品牌上限卡死。
    brand_cap_by_stratum = {
        key: (brand_cap if len({row["brand"] for row in group}) > 2 else 99)
        for key, group in ordered.items()
    }
    picked: list[dict] = []
    chosen: set[str] = set()
    brand_count: Counter = Counter()
    taken: Counter = Counter()

    # 轮转取样：先保证每个规格层至少 1 条，再逐层补到上限。
    while len(picked) < limit:
        progressed = False
        for key in sorted(ordered):
            if len(picked) >= limit:
                break
            if taken[key] >= cap:
                continue
            group = ordered[key]
            while group:
                item = group.pop(0)
                if item["product_id"] in chosen:
                    continue
                if brand_count[(item["stratum"], item["brand"])] >= brand_cap_by_stratum[key]:
                    continue
                picked.append(item)
                chosen.add(item["product_id"])
                brand_count[(item["stratum"], item["brand"])] += 1
                taken[key] += 1
                progressed = True
                break
        if not progressed:
            break

    for item in sorted(items, key=lambda row: (-row["completeness"], row["price_cny"] or 0)):
        if len(picked) >= limit:
            break
        if item["product_id"] in chosen:
            continue
        if brand_count[(item["stratum"], item["brand"])] >= brand_cap_by_stratum[item["stratum"]]:
            continue
        picked.append(item)
        chosen.add(item["product_id"])
    return picked[:limit]


def completeness(specs: dict) -> float:
    """规格完整度：非空字段占比，用于同档内排序。"""

    if not specs:
        return 0.0
    filled = sum(1 for value in specs.values() if value not in (None, "", [], {}))
    return round(filled / len(specs), 4)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3D 本地收尾与候选收缩")
    parser.add_argument("--products", default=str(PRODUCTS))
    parser.add_argument("--candidates", default=str(CANDIDATES))
    parser.add_argument("--final", default=str(FINAL))
    parser.add_argument("--pool", default=str(POOL))
    parser.add_argument("--report", default=str(REPORT))
    parser.add_argument("--per-tier", type=int, default=30, help="每个品类每个档位保留数量")
    args = parser.parse_args()

    products = {
        row["product_id"]: row
        for row in (
            json.loads(line)
            for line in Path(args.products).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    candidates = [
        json.loads(line)
        for line in Path(args.candidates).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    category_prices: dict[str, list[float]] = defaultdict(list)
    for row in candidates:
        if row["price_cny"] is not None:
            category_prices[row["category"]].append(float(row["price_cny"]))
    category_median = {category: statistics.median(values) for category, values in category_prices.items()}
    category_bounds = {
        category: (quantile(values, 0.25), quantile(values, 0.75))
        for category, values in category_prices.items()
    }

    rows: list[dict] = []
    for row in candidates:
        product = products[row["product_id"]]
        price = row["price_cny"]
        price_source = "BUCKET_MEDIAN"
        if price is None:
            price = category_median.get(row["category"])
            price_source = "CATEGORY_MEDIAN"
        lifecycle = product.get("lifecycle_status")
        if lifecycle in EXCLUDED_LIFECYCLE:
            recommendation = "EXCLUDED"
        elif price_source == "CATEGORY_MEDIAN":
            recommendation = "CONDITIONAL"
        else:
            recommendation = "ELIGIBLE"
        tier = row["tier"]
        if tier == "UNPRICED" and price is not None:
            low, high = category_bounds.get(row["category"], (price, price))
            tier = "ENTRY" if price <= low else "MAINSTREAM" if price <= high else "HIGH"
        rows.append({
            "product_id": row["product_id"],
            "category": row["category"],
            "display_name": row["display_name"],
            "lifecycle_status": lifecycle,
            "tier": tier,
            "price_cny": round(price, 2) if price is not None else None,
            "price_source": price_source,
            "market_status": "NO_EVIDENCE",
            "popularity_status": "NOT_EVALUATED",
            "lifecycle_evidence": product.get("lifecycle_evidence"),
            "recommendation_status": recommendation,
            "completeness": completeness(product.get("specifications") or {}),
            "brand": product.get("brand"),
            "stratum": stratum_of(row, product.get("specifications") or {}),
        })

    final_path = Path(args.final)
    with final_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in sorted(rows, key=lambda item: (item["category"], item["tier"], item["product_id"])):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    seen_names: set[tuple[str, str]] = set()
    for row in rows:
        if row["recommendation_status"] == "EXCLUDED":
            continue
        specs = products[row["product_id"]].get("specifications") or {}
        if not is_eligible(row, specs):
            continue
        name_key = (row["category"], row["display_name"].lower())
        if name_key in seen_names:
            continue
        seen_names.add(name_key)
        grouped[(row["category"], row["tier"])].append(row)

    pool: list[dict] = []
    for (category, _), items in grouped.items():
        pool.extend(select_group(items, args.per_tier))
    pool.sort(key=lambda item: (item["category"], item["tier"], item["price_cny"] or 0))

    with Path(args.pool).open("w", encoding="utf-8", newline="\n") as handle:
        for row in pool:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def pool_specs(field: str, category: str) -> dict:
        values = [
            (products[row["product_id"]].get("specifications") or {}).get(field)
            for row in pool if row["category"] == category
        ]
        return dict(sorted(Counter(str(value) for value in values).items(), key=lambda item: item[0]))

    report = {
        "stage": "3D-final",
        "products": len(rows),
        "priced": sum(1 for row in rows if row["price_cny"] is not None),
        "bucket_median": sum(1 for row in rows if row["price_source"] == "BUCKET_MEDIAN"),
        "category_median_fallback": sum(1 for row in rows if row["price_source"] == "CATEGORY_MEDIAN"),
        "recommendation": dict(Counter(row["recommendation_status"] for row in rows)),
        "pool_size": len(pool),
        "pool_by_category": dict(Counter(row["category"] for row in pool)),
        "coverage": {
            "cpu_socket": pool_specs("socket", "CPU"),
            "gpu_vram": pool_specs("vram_gb", "GPU"),
            "mb_socket": pool_specs("socket", "MOTHERBOARD"),
            "memory_type": pool_specs("memory_type", "MEMORY"),
            "storage_media": pool_specs("media_type", "STORAGE"),
            "psu_watt": pool_specs("rated_power_w", "PSU"),
            "case_type": pool_specs("case_type", "CASE"),
            "cooler_radiator": pool_specs("radiator_size_mm", "COOLER"),
        },
        "per_tier": args.per_tier,
        "note": "价格为规格桶中位数或品类中位数，仅用于候选收缩与预算量级，不是成交价。",
    }
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print(f"全部 {len(rows)} 条，补齐后全部有价；候选池 {len(pool)} 条")
    print("推荐状态：" + ", ".join(f"{key}={value}" for key, value in sorted(report["recommendation"].items())))
    print("池内品类：" + ", ".join(f"{key}={value}" for key, value in sorted(report["pool_by_category"].items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
