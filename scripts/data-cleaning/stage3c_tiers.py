"""Stage 3C 后处理：按品类价格分位把硬件划入候选层级。

价格使用区间中位数；只有 status=OK 的记录参与分位计算。
没有可用价格的产品标记 UNPRICED，不做价格猜测。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
CLEANING_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
PRICES = CLEANING_DIR / "stage3c-prices.jsonl"
PRODUCTS = CLEANING_DIR / "stage3a-products.jsonl"
OUTPUT = CLEANING_DIR / "stage3c-candidates.jsonl"
REPORT = CLEANING_DIR / "stage3c-tier-report.json"

TIERS = ("ENTRY", "MAINSTREAM", "HIGH")


def quantile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * ratio
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def latest_records(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        current = records.get(record["product_id"])
        if current is None or record.get("observed_at", "") >= current.get("observed_at", ""):
            records[record["product_id"]] = record
    return records


def price_of(record: dict | None) -> float | None:
    if not record or record.get("status") != "OK":
        return None
    if record.get("price_median_cny") is not None:
        return float(record["price_median_cny"])
    low, high = record.get("price_low_cny"), record.get("price_high_cny")
    if low is not None and high is not None:
        return (float(low) + float(high)) / 2
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3C 候选层级划分")
    parser.add_argument("--prices", default=str(PRICES))
    parser.add_argument("--products", default=str(PRODUCTS))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--report", default=str(REPORT))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    products = [
        json.loads(line)
        for line in Path(args.products).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    prices = latest_records(Path(args.prices))

    by_category: dict[str, list[float]] = defaultdict(list)
    for product in products:
        value = price_of(prices.get(product["product_id"]))
        if value is not None:
            by_category[product["category"]].append(value)

    boundaries: dict[str, dict[str, float]] = {}
    for category, values in by_category.items():
        boundaries[category] = {
            "q1": round(quantile(values, 0.25), 2),
            "q2": round(quantile(values, 0.5), 2),
            "q3": round(quantile(values, 0.75), 2),
            "samples": len(values),
        }

    rows: list[dict] = []
    tier_counts: dict[str, Counter] = defaultdict(Counter)
    for product in products:
        record = prices.get(product["product_id"])
        value = price_of(record)
        if value is None:
            tier = "UNPRICED"
        else:
            limits = boundaries[product["category"]]
            tier = TIERS[0] if value <= limits["q1"] else TIERS[1] if value <= limits["q3"] else TIERS[2]
        rows.append({
            "product_id": product["product_id"],
            "category": product["category"],
            "display_name": product["display_name"],
            "lifecycle_status": product.get("lifecycle_status"),
            "price_cny": round(value, 2) if value is not None else None,
            "price_status": (record or {}).get("status", "NO_RECORD"),
            "tier": tier,
        })
        tier_counts[product["category"]][tier] += 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in sorted(rows, key=lambda item: (item["category"], item["tier"], item["product_id"])):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    priced = sum(1 for row in rows if row["price_cny"] is not None)
    report = {
        "stage": "3C-tiers",
        "products": len(rows),
        "priced": priced,
        "priced_rate": round(priced / len(rows), 4) if rows else 0,
        "boundaries": boundaries,
        "tier_by_category": {
            category: dict(sorted(counter.items()))
            for category, counter in sorted(tier_counts.items())
        },
        "note": "分位基于 status=OK 的区间中位数；UNPRICED 不参与推荐预算。",
    }
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print(f"产品 {len(rows)} 条，有价 {priced} 条（{report['priced_rate']:.1%}）")
    for category, counter in sorted(tier_counts.items()):
        print(f"  {category}: " + ", ".join(f"{key}={value}" for key, value in sorted(counter.items())))
    print(f"输出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
