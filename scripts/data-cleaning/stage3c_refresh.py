"""Stage 3C：批量刷新参考价与在售状态，支持断点续跑。

两种数据源：
- inbox：读取人工/Agent 用 WebSearch 采集的结果，适合小批量与复核
- api：调用 DeepSeek Search API，适合全量批量

只把 status=OK 的结果视为可用于预算的参考价；其余仅留档。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from stage3b_price_sample import (
    analyze,
    build_query,
    call_search,
    insert_spec_tokens,
    load_env_value,
    search_endpoint,
)
from zh_alias import search_name_zh

BASE_DIR = Path(__file__).resolve().parents[2]
CLEANING_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
PRODUCTS = CLEANING_DIR / "stage3a-products.jsonl"
INBOX = CLEANING_DIR / "websearch-inbox.jsonl"
PRICES = CLEANING_DIR / "stage3c-prices.jsonl"
REPORT = CLEANING_DIR / "stage3c-refresh-report.json"

CHANNEL_DOMAINS = [
    ("jd.com", "JD"),
    ("jd.hk", "JD"),
    ("taobao.com", "TAOBAO"),
    ("tmall.com", "TAOBAO"),
    ("zol.com.cn", "ZOL"),
    ("smzdm.com", "SMZDM"),
    ("manmanbuy.com", "MANMANBUY"),
    ("pconline.com.cn", "PCONLINE"),
]
IN_STOCK_WORDS = ("在售", "有货", "现货", "可购买")
OUT_OF_STOCK_WORDS = ("无货", "缺货", "售罄", "下架", "停售")


def channel_of(url: str | None) -> str:
    host = urlparse(url or "").netloc.lower()
    for suffix, name in CHANNEL_DOMAINS:
        if host.endswith(suffix):
            return name
    return "OTHER"


def availability_of(results: list[dict]) -> str:
    text = " ".join(f"{item.get('title') or ''} {item.get('summary') or ''}" for item in results)
    has_in = any(word in text for word in IN_STOCK_WORDS)
    has_out = any(word in text for word in OUT_OF_STOCK_WORDS)
    if has_in and not has_out:
        return "IN_STOCK"
    if has_out and not has_in:
        return "OUT_OF_STOCK"
    return "UNKNOWN"


def load_inbox(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    records: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["product_id"]] = record
    return records


def load_processed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        json.loads(line)["product_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def build_record(product: dict, query: str, results: list[dict], source: str) -> dict:
    analysis = analyze(
        results,
        search_name_zh(product),
        insert_spec_tokens(product),
        product["model_name"],
    )
    channels = sorted({channel_of(item.get("url")) for item in results})
    return {
        "product_id": product["product_id"],
        "category": product["category"],
        "display_name": product["display_name"],
        "query": query,
        "source": source,
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "price_basis": "SEARCH_RANGE",
        "availability_status": availability_of(results),
        "channels": channels,
        **analysis,
        "sources": [
            {"title": item.get("title"), "url": item.get("url"), "date": item.get("date")}
            for item in results[:5]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3C 批量刷新参考价")
    parser.add_argument("--products", default=str(PRODUCTS))
    parser.add_argument("--inbox", default=str(INBOX))
    parser.add_argument("--prices", default=str(PRICES))
    parser.add_argument("--report", default=str(REPORT))
    parser.add_argument("--source", choices=("inbox", "api"), default="inbox")
    parser.add_argument("--category", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--query-lang", choices=("zh", "en"), default="zh")
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    products = [
        json.loads(line)
        for line in Path(args.products).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    done = set() if args.force else load_processed(Path(args.prices))
    candidates = [
        product for product in products
        if product["product_id"] not in done
        and (args.category is None or product["category"] == args.category)
    ]

    inbox = load_inbox(Path(args.inbox)) if args.source == "inbox" else {}
    if args.source == "inbox":
        candidates = [product for product in candidates if product["product_id"] in inbox]
    candidates = candidates[args.offset:]
    if args.limit:
        candidates = candidates[: args.limit]

    api_key = endpoint = None
    if args.source == "api":
        api_key = load_env_value("DEEPSEEK_API_KEY") or load_env_value("LLM_API_KEY")
        if not api_key:
            raise SystemExit("缺少 DEEPSEEK_API_KEY 或 LLM_API_KEY，无法调用 Search API")
        endpoint = search_endpoint(load_env_value("DEEPSEEK_BASE_URL") or load_env_value("LLM_BASE_URL"))

    rows: list[dict] = []
    errors: list[dict] = []

    def work(product: dict) -> dict:
        query = build_query(product, args.query_lang)
        http_calls = 0
        if args.source == "inbox":
            results = inbox[product["product_id"]].get("results") or []
        else:
            response, _, http_calls = call_search(query, api_key, endpoint)
            results = response.get("results") or []
        record = build_record(product, query, results, args.source)
        record["http_calls"] = http_calls
        return record

    if args.source == "inbox":
        for product in candidates:
            try:
                rows.append(work(product))
            except Exception as error:  # noqa: BLE001
                errors.append({"product_id": product["product_id"], "error": str(error)})
    else:
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
            futures = {executor.submit(work, product): product for product in candidates}
            for future in as_completed(futures):
                product = futures[future]
                try:
                    rows.append(future.result())
                except Exception as error:  # noqa: BLE001
                    errors.append({"product_id": product["product_id"], "error": str(error)})

    prices_path = Path(args.prices)
    prices_path.parent.mkdir(parents=True, exist_ok=True)
    with prices_path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    status_by_category: dict[str, Counter] = defaultdict(Counter)
    channel_counts: Counter = Counter()
    for row in rows:
        status_by_category[row["category"]][row["status"]] += 1
        channel_counts.update(row["channels"])
    report = {
        "stage": "3C",
        "source": args.source,
        "query_lang": args.query_lang,
        "requested": len(candidates),
        "completed": len(rows),
        "errors": errors,
        "status_by_category": {
            category: dict(sorted(counter.items()))
            for category, counter in sorted(status_by_category.items())
        },
        "coverage_by_category": {
            category: round(counter["OK"] / sum(counter.values()), 4) if sum(counter.values()) else 0
            for category, counter in sorted(status_by_category.items())
        },
        "availability_counts": dict(Counter(row["availability_status"] for row in rows)),
        "channel_counts": dict(channel_counts.most_common()),
        "http_requests": sum(int(row.get("http_calls") or 0) for row in rows),
        "estimated_cost_cny": round(
            5 * sum(int(row.get("http_calls") or 0) for row in rows) / 1000, 3
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "仅 status=OK 的价格可用于预算；SEARCH_RANGE 为参考区间，不是成交价。",
    }
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print(f"处理 {len(rows)}/{len(candidates)} 条，失败 {len(errors)} 条，"
          f"请求 {report['http_requests']} 次，估算 ¥{report['estimated_cost_cny']:.2f}")
    for category, counter in sorted(status_by_category.items()):
        print(f"  {category}: " + ", ".join(f"{key}={value}" for key, value in sorted(counter.items())))
    print(f"输出：{prices_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
