"""把 EXACT 匹配结果整理成可导入的 market_offers.json。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pc_config_data import REPO_ROOT

MKT = REPO_ROOT / "data" / "pc-config" / "export" / "marketplace"


def main() -> int:
    candidates = {item["hardware_id"]: item
                  for item in json.loads((MKT / "offers_candidates.json").read_text(encoding="utf-8"))}
    rows = [json.loads(line) for line in
            (MKT / "matches.jsonl").read_text(encoding="utf-8").splitlines() if line]

    best: dict[str, dict] = {}
    for row in rows:
        if row["hardware_id"] not in candidates or row["confidence"] != "EXACT":
            continue
        target = candidates[row["hardware_id"]]["price_fen"]
        current = best.get(row["hardware_id"])
        if current is None or abs(row["price_fen"] - target) < abs(current["price_fen"] - target):
            best[row["hardware_id"]] = row

    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    offers = []
    for hardware_id, row in best.items():
        stat = candidates[hardware_id]
        offers.append({
            "hardware_id": hardware_id,
            "category": row["category"],
            "title": row["title"],
            "url": row["url"],
            "item_id": row["item_id"],
            "price_fen": row["price_fen"],
            "sample_count": stat["sample_count"],
            "spread": stat["spread"],
            "low_confidence": bool(stat.get("low_confidence")),
            "observed_at": observed_at,
        })
    payload = {
        "provider": "chengkit-taobao",
        "price_basis": "SEARCH_LIST",
        "observed_at": observed_at,
        "offers": offers,
    }
    (MKT / "market_offers.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"导出 {len(offers)} 条 market offer")
    missing_url = [item for item in offers if not item["url"]]
    print("缺少链接：", len(missing_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
