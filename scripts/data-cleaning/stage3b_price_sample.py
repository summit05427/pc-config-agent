"""Stage 3B：分层抽样，用 DeepSeek Search 校准国内参考价的可得性。

不调用大模型：价格用确定性正则从搜索结果摘要中抽取，便于复现和审计。
输出三个文件：
- stage3b-sample.jsonl：抽样明细（含原始结果与抽取区间）
- stage3b-review.csv：人工复核表（manual_* 列留空）
- stage3b-summary.json：命中率、覆盖率、成本估算与通过判定

使用方式：
    python scripts/data-cleaning/stage3b_price_sample.py --dry-run
    python scripts/data-cleaning/stage3b_price_sample.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from zh_alias import search_name_zh

BASE_DIR = Path(__file__).resolve().parents[2]
INPUT = BASE_DIR / "data" / "pc-config" / "cleaning" / "stage2-products.jsonl"
OUTPUT_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
CACHE_DIR = OUTPUT_DIR / "search-cache"
RULES_VERSION = "stage3b-price-sample-1.0.0"

PRICE_PATTERNS = [
    re.compile(r"[¥￥]\s*(\d{2,6}(?:\.\d+)?)"),
    re.compile(r"(\d{2,6}(?:\.\d+)?)\s*元"),
]
SIGNIFICANT_TOKEN = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9-]{2,}|\d{3,}|[\u4e00-\u9fff]{2,})")
THRESHOLDS = {"model_hit_rate": 0.80, "ok_rate": 0.70, "url_date_rate": 0.95}
MODEL_HIT_MIN = 0.80


def load_env_value(name: str) -> str | None:
    if os.getenv(name):
        return os.getenv(name)
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return None
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if raw.startswith(f"{name}="):
            return raw.split("=", 1)[1].strip()
    return None


def search_endpoint(base_url: str | None) -> str:
    base = (base_url or "https://api.deepseek.com/v1").rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return f"{base}/tools/search"


def cache_key(query: str) -> str:
    return hashlib.sha1(query.encode("utf-8")).hexdigest()


def call_search(query: str, api_key: str, endpoint: str, count: int = 5) -> tuple[dict, bool, int]:
    """返回 (响应, 是否命中缓存, 实际发出的 HTTP 请求次数)。

    计费按成功请求次数，重试也会产生调用，因此必须把重试计入成本。
    """

    key = cache_key(query)
    cache_path = CACHE_DIR / f"{key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8")), True, 0

    payload = json.dumps({"query": query, "count": count, "need_content": False}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    last_error: Exception | None = None
    attempts = 0
    for attempt in range(3):
        attempts += 1
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = json.loads(response.read().decode("utf-8"))
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
            return body, False, attempts
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code in (408, 429) or error.code >= 500:
                time.sleep(1 + attempt)
                continue
            break
        except Exception as error:  # noqa: BLE001 - 网络异常统一降级
            last_error = error
            time.sleep(1 + attempt)
    raise RuntimeError(f"search failed: {last_error}")


def extract_prices(text: str) -> list[float]:
    values: set[float] = set()
    for pattern in PRICE_PATTERNS:
        for match in pattern.finditer(text or ""):
            value = float(match.group(1))
            if 20 <= value <= 200000:
                values.add(value)
    return sorted(values)


def token_hit(model_name: str, text: str) -> float:
    tokens = {token.lower() for token in SIGNIFICANT_TOKEN.findall(model_name or "")}
    if not tokens:
        return 0.0
    haystack = (text or "").lower()
    return sum(1 for token in tokens if token in haystack) / len(tokens)


def analyze(
    results: list[dict],
    model_name: str,
    spec_tokens: list[str] | None = None,
    alt_model_name: str | None = None,
) -> dict:
    spec_tokens = spec_tokens or []
    match_names = [name for name in (model_name, alt_model_name) if name]
    fresh: list[dict] = []
    for item in results:
        date_text = item.get("date")
        if date_text:
            try:
                published = datetime.fromisoformat(str(date_text).replace("Z", "+00:00"))
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - published).days > 365:
                    continue
            except ValueError:
                pass
        fresh.append(item)

    prices: list[float] = []
    domains: set[str] = set()
    dated = 0
    hits: list[float] = []
    spec_hit = False
    spec_checked: list[dict] = []
    model_checked: list[dict] = []
    for item in fresh:
        text = f"{item.get('title') or ''} {item.get('summary') or ''}"
        compact = re.sub(r"\s+", "", text).lower()
        matched_spec = any(re.sub(r"\s+", "", token).lower() in compact for token in spec_tokens)
        if spec_tokens and not matched_spec:
            continue
        spec_hit = spec_hit or matched_spec
        spec_checked.append(item)
        hit = max(token_hit(name, text) for name in match_names)
        if hit < MODEL_HIT_MIN:
            continue
        model_checked.append(item)
        hits.append(hit)
        prices.extend(extract_prices(text))
        domain = urlparse(item.get("url") or "").netloc.lower()
        if domain:
            domains.add(domain)
        if item.get("date"):
            dated += 1
    prices = sorted({round(value, 2) for value in prices})
    low: float | None = None
    high: float | None = None
    trimmed: list[float] = []
    if not results:
        status = "NO_RESULT"
    elif not fresh:
        status = "STALE_ONLY"
    elif spec_tokens and not spec_checked:
        status = "SPEC_MISMATCH"
    elif not model_checked:
        status = "MODEL_MISMATCH"
    elif not prices:
        status = "NO_PRICE"
    else:
        trimmed = prices
        if len(trimmed) >= 5:
            drop = max(1, int(len(trimmed) * 0.2))
            trimmed = trimmed[drop:-drop]
        median = statistics.median(trimmed)
        trimmed = [value for value in trimmed if median / 3 <= value <= median * 3] or trimmed
        low, high = (min(trimmed), max(trimmed)) if trimmed else (prices[0], prices[-1])
        if len(trimmed) < 2 or len(domains) < 2:
            status = "LOW_CONFIDENCE"
        elif high > low * 2:
            status = "LOW_CONFIDENCE"
        else:
            status = "OK"
    return {
        "status": status,
        "price_low_cny": round(low, 2) if prices else None,
        "price_high_cny": round(high, 2) if prices else None,
        "price_median_cny": round(statistics.median(trimmed), 2) if prices and trimmed else None,
        "distinct_prices": len(prices),
        "distinct_domains": len(domains),
        "model_hit_ratio": round(max(hits) if hits else 0.0, 3),
        "spec_hit": spec_hit,
        "dated_results": dated,
    }


def select_sample(products: list[dict], per_category: int) -> list[dict]:
    sample: list[dict] = []
    by_category: dict[str, list[dict]] = {}
    for product in products:
        by_category.setdefault(product["category"], []).append(product)
    for category in sorted(by_category):
        pool = sorted(
            (item for item in by_category[category] if item["quality_status"] == "GOOD"),
            key=lambda item: item["product_id"],
        ) or sorted(by_category[category], key=lambda item: item["product_id"])
        if len(pool) <= per_category:
            sample.extend(pool)
            continue
        step = len(pool) / per_category
        sample.extend(pool[int(index * step)] for index in range(per_category))
    return sample


def insert_spec_tokens(product: dict) -> list[str]:
    """把关键规格拼进查询与校验，避免同型号不同显存/容量互相污染。"""

    specs = product.get("specifications") or {}
    tokens: list[str] = []
    if product["category"] == "GPU" and specs.get("vram_gb"):
        size = int(specs["vram_gb"])
        tokens.extend([f"{size}GB", f"{size}G"])
    elif product["category"] == "MEMORY":
        if specs.get("capacity_gb"):
            size = int(specs["capacity_gb"])
            tokens.extend([f"{size}GB", f"{size}G"])
        if specs.get("speed_mhz"):
            tokens.append(str(int(specs["speed_mhz"])))
    elif product["category"] == "STORAGE" and specs.get("capacity_gb"):
        size = specs["capacity_gb"]
        if size >= 1024:
            tokens.extend([f"{int(size // 1024)}TB", f"{int(size // 1024)}T"])
        tokens.append(f"{int(size)}GB")
    elif product["category"] == "PSU" and specs.get("rated_power_w"):
        tokens.append(f"{int(specs['rated_power_w'])}W")
    return tokens


def build_query(product: dict, lang: str = "zh") -> str:
    if lang == "zh":
        name = search_name_zh(product)
    else:
        brand = product["brand"]
        model = product["model_name"]
        name = model if model.lower().startswith(brand.lower()) else f"{brand} {model}"
    spec_hint = " ".join(insert_spec_tokens(product)[:2])
    # 不加 after: 过滤：中文电商页普遍缺少可索引日期，会把结果挤成海外站点。
    query = f"{name} {spec_hint} 京东 价格"
    return re.sub(r"\s+", " ", query).strip()[:128]


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3B 抽样校准国内参考价可得性")
    parser.add_argument("--input", default=str(INPUT))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--per-category", type=int, default=50)
    parser.add_argument("--limit", type=int, default=0, help="只取前 N 条，0 表示全部抽样")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--query-lang", choices=("zh", "en"), default="zh")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    products = [json.loads(line) for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    sample = select_sample(products, args.per_category)
    if args.limit:
        sample = sample[: args.limit]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    errors: list[dict] = []
    started = time.time()

    if args.dry_run:
        for product in sample:
            rows.append({
                "product_id": product["product_id"],
                "category": product["category"],
                "brand": product["brand"],
                "model_name": product["model_name"],
                "query": build_query(product, args.query_lang),
                "status": "DRY_RUN",
            })
    else:
        api_key = load_env_value("DEEPSEEK_API_KEY") or load_env_value("LLM_API_KEY")
        if not api_key:
            raise SystemExit("缺少 DEEPSEEK_API_KEY 或 LLM_API_KEY，无法调用 Search API")
        endpoint = search_endpoint(load_env_value("DEEPSEEK_BASE_URL") or load_env_value("LLM_BASE_URL"))

        def run(product: dict) -> dict:
            query = build_query(product, args.query_lang)
            response, from_cache, http_calls = call_search(query, api_key, endpoint)
            results = response.get("results") or []
            analysis = analyze(
                results,
                search_name_zh(product) if args.query_lang == "zh" else product["model_name"],
                insert_spec_tokens(product),
                product["model_name"] if args.query_lang == "zh" else None,
            )
            return {
                "product_id": product["product_id"],
                "category": product["category"],
                "brand": product["brand"],
                "model_name": product["model_name"],
                "query": query,
                "from_cache": from_cache,
                "http_calls": http_calls,
                **analysis,
                "results": [
                    {
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "date": item.get("date"),
                        "summary": (item.get("summary") or "")[:400],
                    }
                    for item in results[:5]
                ],
            }

        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
            futures = {executor.submit(run, product): product for product in sample}
            for future in as_completed(futures):
                product = futures[future]
                try:
                    rows.append(future.result())
                except Exception as error:  # noqa: BLE001 - 单条失败不影响整体
                    errors.append({"product_id": product["product_id"], "error": str(error)})

    rows.sort(key=lambda item: item["product_id"])
    sample_path = output_dir / "stage3b-sample.jsonl"
    with sample_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    review_path = output_dir / "stage3b-review.csv"
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "product_id", "category", "brand", "model_name", "query", "status",
            "price_low_cny", "price_high_cny", "model_hit_ratio", "distinct_domains",
            "top1_title", "top1_url", "manual_price_cny", "manual_verdict",
        ])
        for row in rows:
            top = (row.get("results") or [{}])[0]
            writer.writerow([
                row["product_id"], row["category"], row.get("brand"), row.get("model_name"),
                row.get("query"), row.get("status"), row.get("price_low_cny"), row.get("price_high_cny"),
                row.get("model_hit_ratio"), row.get("distinct_domains"),
                top.get("title"), top.get("url"), "", "",
            ])

    total = len(rows)
    priced = [row for row in rows if row.get("price_low_cny") is not None]
    summary = {
        "stage": "3B",
        "rules_version": RULES_VERSION,
        "dry_run": args.dry_run,
        "requested": len(sample),
        "completed": len(rows),
        "error_count": len(errors),
        "per_category": args.per_category,
        "query_lang": args.query_lang,
        "errors": errors,
        "status_counts": {
            status: sum(1 for row in rows if row.get("status") == status)
            for status in sorted({row.get("status") for row in rows})
        },
        "price_extraction_rate": round(len(priced) / total, 4) if total else 0,
        "model_hit_rate": round(
            sum(1 for row in rows if (row.get("model_hit_ratio") or 0) >= MODEL_HIT_MIN) / total, 4
        ) if total else 0,
        "ok_rate": round(sum(1 for row in rows if row.get("status") == "OK") / total, 4) if total else 0,
        "url_date_rate": round(
            sum(1 for row in rows if (row.get("dated_results") or 0) > 0) / total, 4
        ) if total else 0,
        "http_requests": sum(int(row.get("http_calls") or 0) for row in rows),
        "cache_hits": sum(1 for row in rows if row.get("from_cache")),
        "estimated_cost_cny": round(5 * sum(int(row.get("http_calls") or 0) for row in rows) / 1000, 3),
        "duration_seconds": round(time.time() - started, 1),
        "thresholds": THRESHOLDS,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "价格由正则抽取，未调用大模型；manual_* 需人工填写后才能判定准确率。",
    }
    (output_dir / "stage3b-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print(f"请求 {summary['requested']} 条，完成 {summary['completed']} 条，失败 {summary['error_count']} 条")
    print(f"抽样完成 {total} 条，状态：" + json.dumps(summary["status_counts"], ensure_ascii=False))
    print(f"取价覆盖率 {summary['price_extraction_rate']:.1%}，型号命中率 {summary['model_hit_rate']:.1%}，"
          f"OK 率 {summary['ok_rate']:.1%}，费用约 ¥{summary['estimated_cost_cny']}")
    print(f"输出：{sample_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
