"""把 Stage 4 短名单的价格转换成运行时 offers.json。

Stage 4 流水线（观测账本 + 档位兜底 + 热门榜单）是当前国内参考价的唯一来源。
本轮把它直接暴露给 BuildSolver，替换掉已过期且绝大多数条目不在新目录里的旧 offers。

映射规则：
- OBSERVED_2026-11-11 →  match_status=OBSERVED（非逐件人工核验），valid_until 3 个月
- ESTIMATED_2026-11-11 →  match_status=OBSERVED，valid_until 1 个月，notes 显式标注「估算价」
- 所有条目 price_source=PLATFORM_OBSERVED，避免把非逐件观测价伪装成 OWNER_VERIFIED

生成后：
- 写入 data/pc-config/export/runtime-full/offers.json
- 同步到 application-service/src/main/resources/pc-config/offers.json
- 与 catalog.json / benchmarks.json 的 catalog_version 保持一致（2026.11.2）
"""

from __future__ import annotations

import json
from datetime import date, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
CLEANING_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
SHORTLIST = CLEANING_DIR / "stage4-shortlist.jsonl"

TARGETS = [
    BASE_DIR / "data" / "pc-config" / "export" / "runtime-full" / "offers.json",
    BASE_DIR / "application-service" / "src" / "main" / "resources" / "pc-config" / "offers.json",
]

CATALOG_VERSION = "2026.11.2"
GENERATED_AT = "2026-11-12T06:42:17Z"  # 与 catalog.json / benchmarks.json 一致
TODAY = date(2026, 11, 12)
OBSERVED_WINDOW = timedelta(days=92)      # 3 个月
ESTIMATED_WINDOW = timedelta(days=30)     # 估算价只保留 1 个月

PLATFORM = "JD"                           # 短名单参考价主要指向京东
SELLER = "参考价聚合"
SHOP_NAME = "非商家提供"
PRICE_TYPE = "NORMAL"
PRICE_SOURCE = "PLATFORM_OBSERVED"
DATA_STATUS = "PLATFORM_OBSERVED_ONLY"    # 新状态：全部来自平台观测/估算，无 OWNER_VERIFIED
SCHEMA_VERSION = "1.0.0"


def _build_offer(row: dict) -> dict:
    hardware_id = row["product_id"]
    category = row["category"]
    price_cny = row.get("price_cny") or 0
    price_fen = int(round(price_cny * 100))

    price_status = row.get("price_status") or ""
    notes_parts: list[str] = []
    if row.get("price_note"):
        notes_parts.append(str(row["price_note"]))
    if price_status.startswith("ESTIMATED"):
        notes_parts.append("[估算价，非实测]")
    if row.get("price_source"):
        notes_parts.append(f"[来源: {row['price_source']}]")

    verified_at = None
    valid_until = None
    if price_status.startswith("OBSERVED"):
        verified_at = TODAY.isoformat()
        valid_until = (TODAY + OBSERVED_WINDOW).isoformat()
    elif price_status.startswith("ESTIMATED"):
        valid_until = (TODAY + ESTIMATED_WINDOW).isoformat()

    return {
        "offer_id": f"offer-{hardware_id}-01",
        "hardware_id": hardware_id,
        "category": category,
        "platform": PLATFORM,
        "seller": SELLER,
        "shop_name": SHOP_NAME,
        "title": row.get("display_name") or row.get("model_name") or hardware_id,
        "platform_sku": None,
        "price_fen": price_fen,
        "price_type": PRICE_TYPE,
        "purchase_url": row.get("price_source_url") or None,
        "verified_at": verified_at,
        "valid_until": valid_until,
        "match_status": "OBSERVED",
        "price_source": PRICE_SOURCE,
        "notes": "；".join(notes_parts) if notes_parts else None,
    }


def main() -> int:
    shortlist = []
    for line in SHORTLIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            shortlist.append(json.loads(line))

    offers = [_build_offer(row) for row in shortlist]

    verified_count = sum(1 for o in offers if o["verified_at"])
    estimated_count = len(offers) - verified_count

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "data_status": DATA_STATUS,
        "currency": "CNY",
        "price_unit": "CNY_FEN",
        "catalog_version": CATALOG_VERSION,
        "offers": offers,
        "verified_offer_count": verified_count,
        "mock_offer_count": 0,
        "observed_offer_count": estimated_count,
        "skipped_pending": 0,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    for target in TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    print(
        f"[ok] offers={len(offers)} verified={verified_count} estimated={estimated_count} "
        f"data_status={DATA_STATUS} catalog_version={CATALOG_VERSION}"
    )
    for target in TARGETS:
        print(f"[ok] wrote {target.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
