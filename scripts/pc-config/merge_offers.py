"""合并多路观测价，同一硬件按来源精度取一条。

来源优先级：SKU_PANEL（详情规格面板）> LISTING_MATCH（详情标题拆解）> SEARCH_LIST（搜索卡片）。
低精度来源的价格只作补充，不覆盖已有高精度报价。
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fallback_pricing import coarse_key
from pc_config_data import REPO_ROOT

MKT = REPO_ROOT / "data" / "pc-config" / "export" / "marketplace"
DEFAULT_OUTPUT = MKT / "merged_offers.json"
CATALOG = (
    REPO_ROOT / "application-service" / "src" / "main" / "resources" / "pc-config" / "catalog.json"
)

PRIORITY = {"FALLBACK": -1, "BUCKET": 0, "SEARCH_LIST": 1, "LISTING_MATCH": 2, "SKU_PANEL": 3}
PRICE_RANGES_FEN = {"CPU": (10_000, 2_000_000), "GPU": (50_000, 4_000_000)}

# 单样本低置信观测常是「定金价」「SKU 最低价」或多型号混卖页，价格会低到离谱
# （实测：RX 7800 XT 被观测成 ¥1000）。低于同档高置信中位价该比例时直接丢弃，
# 让它回落到兜底估算，而不是拿一个不可能的价格去求解。
LOW_CONFIDENCE_FLOOR_RATIO = 0.4
# 同档样本太少时中位价本身不可信，不做剔除。
MIN_TIER_SAMPLES = 3


def load_payload(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    default_basis = str(payload.get("price_basis") or "SEARCH_LIST")
    for offer in payload.get("offers") or []:
        if offer.get("price_fen"):
            yield {**offer, "price_basis": str(offer.get("price_basis") or default_basis)}


def load_hardware() -> dict[str, dict]:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {row["hardware_id"]: row for row in payload.get("hardware") or []}


def tier_of(offer: dict, hardware: dict[str, dict]) -> tuple | None:
    row = hardware.get(offer.get("hardware_id"))
    if row is None:
        return None
    return coarse_key(
        row.get("category"),
        row.get("specifications") or {},
        row.get("model_name") or "",
    )


def drop_implausible(
    offers: list[dict],
    reference: list[dict],
    hardware: dict[str, dict],
) -> tuple[list[dict], int]:
    """剔除价格明显不可能是真的低置信观测，返回保留列表与被剔除条数。

    档位中位价必须用**全量观测**计算：去重后每个型号只剩一条报价，
    同档样本会少到无法判断，等于没有守卫。
    """

    trusted: dict[tuple, list[int]] = defaultdict(list)
    for offer in reference:
        if offer.get("low_confidence") or offer["price_basis"] == "FALLBACK":
            continue
        key = tier_of(offer, hardware)
        # 同时登记父档（去掉末级维度）：精确档样本不足时用「同显存/同容量」的中位价兜底，
        # 否则冷门档位永远凑不够样本，守卫形同虚设。
        while key:
            trusted[key].append(offer["price_fen"])
            key = key[:-1]
    medians = {
        key: statistics.median(values)
        for key, values in trusted.items()
        if len(values) >= MIN_TIER_SAMPLES
    }

    kept: list[dict] = []
    dropped = 0
    for offer in offers:
        key = tier_of(offer, hardware)
        median = None
        while key and median is None:
            median = medians.get(key)
            key = key[:-1]
        if (
            offer.get("low_confidence")
            and median
            and offer["price_fen"] < median * LOW_CONFIDENCE_FLOOR_RATIO
        ):
            dropped += 1
            continue
        kept.append(offer)
    return kept, dropped


def main() -> int:
    parser = argparse.ArgumentParser(description="合并观测价文件")
    parser.add_argument("inputs", nargs="+", help="待合并的 offers JSON")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    strongest: dict[str, dict] = {}
    all_offers: list[dict] = []
    dropped = 0
    total = 0
    for raw_path in args.inputs:
        path = REPO_ROOT / raw_path
        if not path.is_file():
            raise SystemExit(f"缺少文件：{path}")
        offers = list(load_payload(path))
        total += len(offers)
        all_offers.extend(offers)
        for offer in offers:
            low, high = PRICE_RANGES_FEN.get(offer["category"], (1, 10_000_000))
            if not low <= offer["price_fen"] <= high:
                dropped += 1
                continue
            current = strongest.get(offer["hardware_id"])
            if current is None or PRIORITY[offer["price_basis"]] > PRIORITY[current["price_basis"]]:
                strongest[offer["hardware_id"]] = offer

    merged, implausible = drop_implausible(
        list(strongest.values()), all_offers, load_hardware()
    )
    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "provider": "chengkit-taobao",
        "price_basis": "MIXED",
        "observed_at": observed_at,
        "offers": merged,
    }
    print(
        f"合并 {total} 条，去重后 {len(payload['offers'])} 条，"
        f"越界丢弃 {dropped} 条，价格异常丢弃 {implausible} 条"
    )
    if not args.dry_run:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
