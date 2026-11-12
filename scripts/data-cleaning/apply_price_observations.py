"""把 WebSearch 观测价合并进候选短名单。

一条观测可命中多个 SKU：同一型号的不同品牌显卡在国内零售价差异有限，
因此支持用 product_id_prefix 或 display_name 批量落价，避免逐 SKU 重复搜索。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
CLEANING_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
SHORTLIST = CLEANING_DIR / "stage4-shortlist.jsonl"
OBSERVATIONS = CLEANING_DIR / "stage4-price-observations.jsonl"
REPORT = CLEANING_DIR / "stage4-price-report.json"

OBSERVED_PREFIX = "OBSERVED"
OBSERVED_STATUS = "OBSERVED_2026-11-11"
ESTIMATED_STATUS = "ESTIMATED_2026-11-11"

# 栏目/列表页只代表「该品类某档位的市场价」，不是单品价。
# 这类记录若写成 OBSERVED，会让预算估算误以为拿到了精确单价，因此统一降级为 ESTIMATED。
CATEGORY_LIST_URLS = frozenset(
    {
        "https://detail.zol.com.cn/",
        "https://detail.zol.com.cn/cpu/",
        "https://detail.zol.com.cn/vga/",
        "https://detail.zol.com.cn/motherboard/",
        "https://detail.zol.com.cn/memory/",
        "https://detail.zol.com.cn/harddrivers/",
        "https://detail.zol.com.cn/power/",
        "https://detail.zol.com.cn/case/",
        "https://detail.zol.com.cn/cooling/",
        "https://dir.jd.com/guide/jd-geo-guide-360-shui-leng-san-re-qi-v1",
        "https://dir.jd.com/guide/jd-geo-guide-m-2-gu-tai-ying-pan-1tb-v1",
    }
)
BAND_NOTE_TOKENS = ("档位", "档 ", "上浮", "下浮", "之间", "锚点", "库存价", "区间")
PRICE_RANGE_PATTERN = re.compile(r"¥\s*\d+\s*[-~]\s*\d+")


def is_band_price(observation: dict) -> bool:
    """判断该记录是档位/区间推导价而非单品实际售价。"""

    if observation.get("source_url", "") not in CATEGORY_LIST_URLS:
        return False
    note = observation.get("note", "")
    return any(token in note for token in BAND_NOTE_TOKENS) or bool(PRICE_RANGE_PATTERN.search(note))


def select_rows(observation: dict, rows: list[dict]) -> list[dict]:
    """按观测里的选择器挑出目标行，优先级 product_ids > product_id_prefix > display_name。"""
    if observation.get("product_ids"):
        wanted = set(observation["product_ids"])
        return [row for row in rows if row["product_id"] in wanted]
    if observation.get("product_id_prefix"):
        prefix = observation["product_id_prefix"]
        return [row for row in rows if row["product_id"].startswith(prefix)]
    if observation.get("display_name"):
        name = observation["display_name"]
        category = observation.get("category")
        return [
            row
            for row in rows
            if row["display_name"] == name and (category is None or row["category"] == category)
        ]
    if observation.get("product_id"):
        return [row for row in rows if row["product_id"] == observation["product_id"]]
    return []


def main() -> int:
    rows = [json.loads(line) for line in SHORTLIST.read_text(encoding="utf-8").splitlines() if line.strip()]
    observations = [
        json.loads(line)
        for line in OBSERVATIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    applied = 0
    skipped_observed = 0
    unmatched: list[str] = []
    for observation in observations:
        targets = select_rows(observation, rows)
        if not targets:
            unmatched.append(
                observation.get("product_id")
                or observation.get("product_id_prefix")
                or observation.get("display_name")
                or "<unknown>"
            )
            continue
        for row in targets:
            # 已落地的真实观测价优先，避免后续批次用同型号均价覆盖
            if row["price_status"].startswith(OBSERVED_PREFIX) and not observation.get("overwrite"):
                skipped_observed += 1
                continue
            row["price_cny"] = observation["price_cny"]
            row["price_source"] = "WEBSEARCH"
            row["price_status"] = ESTIMATED_STATUS if is_band_price(observation) else OBSERVED_STATUS
            row["price_confidence"] = observation["confidence"]
            row["price_source_url"] = observation.get("source_url", "")
            row["price_note"] = observation.get("note", "")
            applied += 1

    with SHORTLIST.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = {
        "applied": applied,
        "skipped_already_observed": skipped_observed,
        "unmatched_observations": unmatched,
        "total": len(rows),
        "price_status": dict(Counter(row["price_status"] for row in rows)),
        "confidence": dict(Counter(row.get("price_confidence", "NONE") for row in rows)),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
