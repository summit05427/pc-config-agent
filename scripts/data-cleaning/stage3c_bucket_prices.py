"""Stage 3C：按「型号族 / 规格桶」获取大致价格，再对全部硬件分档。

不追求逐 SKU 精确报价：同一芯片、同一容量规格共用价格中位数，
用于候选池划分；精度不足时后续可被精确定价覆盖。
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from stage3b_price_sample import call_search, extract_prices, load_env_value, search_endpoint
from stage3c_tiers import quantile
from zh_alias import search_name_zh

BASE_DIR = Path(__file__).resolve().parents[2]
CLEANING_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
PRODUCTS = CLEANING_DIR / "stage3a-products.jsonl"
BUCKETS = CLEANING_DIR / "stage3c-bucket-prices.json"
CANDIDATES = CLEANING_DIR / "stage3c-candidates.jsonl"
REPORT = CLEANING_DIR / "stage3c-bucket-report.json"
TIERS = ("ENTRY", "MAINSTREAM", "HIGH")
MIN_PRICE, MAX_PRICE = 30, 200000


def bucket_of(product: dict) -> tuple[str, str]:
    specs = product.get("specifications") or {}
    category = product["category"]
    if category == "CPU":
        key = f"CPU|{product['model_name']}"
        return key, f"{search_name_zh(product)} 京东 价格"
    if category == "GPU":
        chipset = str(specs.get("chipset") or product["model_name"])
        vram = int(specs.get("vram_gb") or 0)
        key = f"GPU|{chipset}|{vram}"
        return key, f"{chipset} {vram}GB 显卡 京东 价格".strip()
    if category == "MOTHERBOARD":
        chipset = str(specs.get("chipset") or "B850")
        key = f"MB|{chipset}"
        return key, f"{chipset} 主板 京东 价格"
    if category == "MEMORY":
        size = int(specs.get("capacity_gb") or 0)
        speed = int(specs.get("speed_mhz") or 0)
        kind = str(specs.get("memory_type") or "DDR5")
        key = f"MEM|{kind}|{size}|{speed}"
        return key, f"{kind} {speed} {size}GB 内存 京东 价格".strip()
    if category == "STORAGE":
        size = int(specs.get("capacity_gb") or 0)
        interface = str(specs.get("interface") or "NVMe")
        label = "机械硬盘" if specs.get("media_type") == "HDD" else "固态硬盘"
        key = f"SSD|{size}|{interface}|{label}"
        return key, f"{size}GB {interface} {label} 京东 价格"
    if category == "PSU":
        watt = int(specs.get("rated_power_w") or 0)
        watt_bucket = int(round(watt / 50.0) * 50)
        efficiency = str(specs.get("efficiency") or "金牌")
        key = f"PSU|{watt_bucket}|{efficiency}"
        return key, f"{watt_bucket}W {efficiency} 电源 京东 价格".strip()
    if category == "CASE":
        case_type = str(specs.get("case_type") or "中塔")
        key = f"CASE|{case_type}"
        return key, f"{case_type} 机箱 京东 价格"
    if category == "COOLER":
        is_water = bool(specs.get("water_cooled"))
        size = int(specs.get("radiator_size_mm") or specs.get("height_mm") or 0)
        size_bucket = size if not is_water else int(round(size / 120.0) * 120)
        label = "水冷" if is_water else "风冷"
        key = f"COOLER|{label}|{size_bucket}"
        return key, f"{label} {size_bucket} 散热器 京东 价格".strip()
    key = f"OTHER|{product['product_id']}"
    return key, f"{search_name_zh(product)} 京东 价格"


def summarize(results: list[dict]) -> dict:
    prices: list[float] = []
    for item in results:
        text = f"{item.get('title') or ''} {item.get('summary') or ''}"
        prices.extend(value for value in extract_prices(text) if MIN_PRICE <= value <= MAX_PRICE)
    prices = sorted(set(round(value, 2) for value in prices))
    if not prices:
        return {"status": "NO_PRICE", "median_cny": None, "prices": [], "samples": len(results)}
    trimmed = prices
    if len(trimmed) >= 5:
        drop = max(1, int(len(trimmed) * 0.2))
        trimmed = trimmed[drop:-drop]
    return {
        "status": "OK" if len(trimmed) >= 1 else "LOW_CONFIDENCE",
        "median_cny": round(statistics.median(trimmed), 2),
        "prices": trimmed,
        "samples": len(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3C 规格桶定价与候选分档")
    parser.add_argument("--products", default=str(PRODUCTS))
    parser.add_argument("--buckets", default=str(BUCKETS))
    parser.add_argument("--candidates", default=str(CANDIDATES))
    parser.add_argument("--report", default=str(REPORT))
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--max-requests", type=int, default=2000, help="超过上限直接中止，防止失控计费")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个桶，用于试跑")
    args = parser.parse_args()

    products = [
        json.loads(line)
        for line in Path(args.products).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    queries: dict[str, str] = {}
    product_bucket: dict[str, str] = {}
    for product in products:
        key, query = bucket_of(product)
        queries.setdefault(key, query)
        product_bucket[product["product_id"]] = key

    items = list(queries.items())
    if args.limit:
        items = items[: args.limit]
    if len(items) > args.max_requests:
        raise SystemExit(
            f"待请求 {len(items)} 个桶，超过上限 {args.max_requests}；"
            f"预计成本约 ¥{5 * len(items) / 1000:.2f}。确认后调高 --max-requests。"
        )

    api_key = load_env_value("DEEPSEEK_API_KEY") or load_env_value("LLM_API_KEY")
    if not api_key:
        raise SystemExit("缺少 DEEPSEEK_API_KEY 或 LLM_API_KEY")
    endpoint = search_endpoint(load_env_value("DEEPSEEK_BASE_URL") or load_env_value("LLM_BASE_URL"))

    bucket_result: dict[str, dict] = {}
    errors: list[dict] = []

    def work(item: tuple[str, str]) -> tuple[str, dict]:
        key, query = item
        response, _, http_calls = call_search(query, api_key, endpoint)
        summary = summarize(response.get("results") or [])
        return key, {"query": query, **summary, "http_calls": http_calls}

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = {executor.submit(work, item): item for item in items}
        for future in as_completed(futures):
            key, _ = futures[future]
            try:
                bucket_key, result = future.result()
                bucket_result[bucket_key] = result
            except Exception as error:  # noqa: BLE001
                errors.append({"bucket": key, "error": str(error)})

    Path(args.buckets).write_text(
        json.dumps(bucket_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    by_category: dict[str, list[float]] = defaultdict(list)
    price_by_product: dict[str, float] = {}
    for product in products:
        result = bucket_result.get(product_bucket[product["product_id"]])
        if result and result.get("median_cny"):
            price_by_product[product["product_id"]] = float(result["median_cny"])
            by_category[product["category"]].append(float(result["median_cny"]))

    boundaries = {
        category: {
            "q1": round(quantile(values, 0.25), 2),
            "q3": round(quantile(values, 0.75), 2),
            "samples": len(values),
        }
        for category, values in by_category.items()
    }

    rows: list[dict] = []
    tier_counts: dict[str, Counter] = defaultdict(Counter)
    for product in products:
        price = price_by_product.get(product["product_id"])
        if price is None:
            tier = "UNPRICED"
        else:
            limits = boundaries[product["category"]]
            tier = TIERS[0] if price <= limits["q1"] else TIERS[1] if price <= limits["q3"] else TIERS[2]
        rows.append({
            "product_id": product["product_id"],
            "category": product["category"],
            "display_name": product["display_name"],
            "lifecycle_status": product.get("lifecycle_status"),
            "bucket": product_bucket[product["product_id"]],
            "price_cny": price,
            "tier": tier,
        })
        tier_counts[product["category"]][tier] += 1

    with Path(args.candidates).open("w", encoding="utf-8", newline="\n") as handle:
        for row in sorted(rows, key=lambda item: (item["category"], item["tier"], item["product_id"])):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = {
        "stage": "3C-buckets",
        "buckets": len(bucket_result),
        "bucket_errors": errors,
        "http_requests": sum(int(item.get("http_calls") or 0) for item in bucket_result.values()),
        "cache_hits": sum(1 for item in bucket_result.values() if not item.get("http_calls")),
        "estimated_cost_cny": round(
            5 * sum(int(item.get("http_calls") or 0) for item in bucket_result.values()) / 1000, 3
        ),
        "priced_products": len(price_by_product),
        "priced_rate": round(len(price_by_product) / len(products), 4) if products else 0,
        "boundaries": boundaries,
        "tier_by_category": {
            category: dict(sorted(counter.items()))
            for category, counter in sorted(tier_counts.items())
        },
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "价格为规格桶中位数，仅用于候选分档；精确报价需后续单 SKU 核验覆盖。",
    }
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print(f"桶 {len(bucket_result)} 个，有价产品 {len(price_by_product)}/{len(products)}"
          f"（{report['priced_rate']:.1%}），本次请求 {report['http_requests']} 次，"
          f"估算 ¥{report['estimated_cost_cny']:.2f}")
    for category, counter in sorted(tier_counts.items()):
        print(f"  {category}: " + ", ".join(f"{key}={value}" for key, value in sorted(counter.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
