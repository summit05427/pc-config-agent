"""用同档商品的中位价补齐无法精确匹配到具体型号的硬件报价。

适用前提：报价只作为中国区参考价，不强制与某个真实商品一一对应。
档位按品类区分（芯片组×板型×内存类型、芯片×显存、容量×频率等），
只有样本数 ≥3 且价差 ≤60% 的档位才出价，避免把混卖展示价摊平给整个档位。
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

from match_market import norm
from pc_config_data import REPO_ROOT

MKT = REPO_ROOT / "data" / "pc-config" / "export" / "marketplace"
SELLABLE = MKT / "sellable.json"
LISTINGS = MKT / "listings.jsonl"
OUTPUT = MKT / "bucket_offers.json"

MIN_SAMPLES = 3
MAX_SPREAD = 0.6
# 机箱/散热/电源/内存属于规格主导的通用件，同档价格带宽天然更大；
# 放宽阈值并在备注里显式标注价差，让前端知道这是「同档参考价」。
SPREAD_BY_CATEGORY = {"CASE": 3.0, "COOLER": 2.5, "PSU": 2.0, "MEMORY": 1.3}
RANGES_FEN = {
    "GPU": (50_000, 4_000_000),
    "MOTHERBOARD": (20_000, 800_000),
    "MEMORY": (5_000, 600_000),
    "STORAGE": (5_000, 600_000),
    "PSU": (5_000, 500_000),
    "COOLER": (3_000, 300_000),
    "CASE": (5_000, 300_000),
}
CHIPSET_RE = re.compile(r"([abhxz]\d{3})(?:m|i)?(?![0-9])")
GPU_CHIP_RE = re.compile(r"(rtx|rx|arc)([a-z]?\d{3,4})(ti|super|xt|xtx)?")
GPU_VRAM_RE = re.compile(r"(?<!\d)(\d{1,2})g(?:b)?")
MEM_CAP_RE = re.compile(r"(?<!\d)(\d{2,3})g(?:b)?")
SPEED_RE = re.compile(r"(?<!\d)([4-8]\d{3})(?!\d)")
STORAGE_RE = re.compile(r"(?<!\d)(\d{1,4})(gb|g|tb|t)")
WATT_RE = re.compile(r"(?<!\d)(\d{3,4})w")


def unique(values):
    items = set(values)
    return items.pop() if len(items) == 1 else None


def watt_band(watt) -> str:
    """电源按瓦数分档：单瓦数样本太少，档内价格差异小于跨档差异。"""

    value = int(watt)
    if value <= 450:
        return "<=450"
    if value <= 650:
        return "451-650"
    if value <= 850:
        return "651-850"
    return ">850"


def candidate_keys(category: str, key: tuple) -> list[tuple]:
    """从精确档位逐级放宽，优先使用样本更充分的粗档位。"""

    keys = [key]
    if category == "MOTHERBOARD" and len(key) == 3:
        keys += [key[:2], key[:1]]
    elif category == "MEMORY" and len(key) == 3:
        keys.append(key[:2])
    elif category == "STORAGE" and len(key) == 2:
        keys.append(key[:1])
    return keys


def listing_key(category: str, title: str):
    """从商品标题解析档位键；解析不唯一时返回 None，宁可不出价。

    这里保留原始分隔符再解析：去分隔符后 `850W`、`DDR5 6000` 会粘成一片，
    数字边界判断失效，导致整类档位样本为空。
    """

    plain = title.lower()
    if category == "MOTHERBOARD":
        codes = CHIPSET_RE.findall(plain)
        code = unique(codes)
        if not code:
            return None
        if "itx" in plain:
            form = "itx"
        elif f"{code}m" in plain or "matx" in plain or "小板" in plain:
            form = "matx"
        elif "atx" in plain or "大板" in plain:
            form = "atx"
        else:
            return None
        memory = "ddr5" if "ddr5" in plain else "ddr4" if "ddr4" in plain else None
        return (code, form, memory) if memory else None
    if category == "GPU":
        chips = {"".join(part for part in match if part) for match in GPU_CHIP_RE.findall(plain)}
        chip = unique(chips)
        vram = unique(int(value) for value in GPU_VRAM_RE.findall(plain)
                      if 4 <= int(value) <= 48)
        return (chip, vram) if chip and vram else None
    if category == "MEMORY":
        memory = "ddr5" if "ddr5" in plain else "ddr4" if "ddr4" in plain else None
        capacity = unique(int(value) for value in MEM_CAP_RE.findall(plain)
                          if 4 <= int(value) <= 256)
        speed = unique(int(value) for value in SPEED_RE.findall(plain)
                       if 4000 <= int(value) <= 8400)
        return (memory, capacity, speed) if memory and capacity and speed else None
    if category == "STORAGE":
        capacity = unique(int(value) * (1024 if unit.startswith("t") else 1)
                          for value, unit in STORAGE_RE.findall(plain)
                          if 60 <= int(value) * (1024 if unit.startswith("t") else 1) <= 8192)
        if not capacity:
            return None
        return (capacity, "nvme" if ("nvme" in plain or "m2" in plain or "pcie" in plain) else "sata")
    if category == "PSU":
        watt = unique(int(value) for value in WATT_RE.findall(plain)
                      if 200 <= int(value) <= 2000)
        return (watt_band(watt),) if watt else None
    if category == "COOLER":
        return ("aio" if ("水冷" in plain or "aio" in plain) else "air",)
    if category == "CASE":
        return ("itx" if "itx" in plain else "atx",)
    return None


def spec_key(category: str, specs: dict, model: str):
    """用硬件自身规格推导同一套档位键。"""

    if category == "MOTHERBOARD":
        chipset = str(specs.get("chipset") or "").split()[-1].lower()
        chipset = re.sub(r"^([ab]\d{3})a$", r"\1", chipset)
        form = specs.get("form_factor") or ""
        form_key = "itx" if "Mini" in form else "matx" if "Micro" in form else "atx"
        memory = str(specs.get("memory_type") or "").lower()
        return (chipset, form_key, memory) if chipset and memory else None
    if category == "GPU":
        chipset = re.sub(r"(GeForce|Radeon)\s*", "", str(specs.get("chipset") or model), flags=re.I)
        vram = specs.get("vram_gb")
        return (norm(chipset), int(vram)) if chipset and vram else None
    if category == "MEMORY":
        return (str(specs.get("memory_type") or "").lower(), specs.get("capacity_gb"),
                specs.get("speed_mts"))
    if category == "STORAGE":
        interface = str(specs.get("interface") or "")
        kind = "nvme" if ("M.2" in interface or "PCIe" in interface) else "sata"
        return (specs.get("capacity_gb"), kind)
    if category == "PSU":
        watt = specs.get("wattage_w")
        return (watt_band(watt),) if watt else None
    if category == "COOLER":
        is_aio = any(word in model.upper() for word in ("水冷", "AIO", "LIQUID", "LC"))
        return ("aio" if is_aio else "air",)
    if category == "CASE":
        forms = specs.get("supported_mainboard_form_factors") or []
        return ("atx" if any("ATX" in str(form) for form in forms) else "itx",)
    return None


def load_buckets() -> dict[tuple[str, tuple], list[dict]]:
    buckets: dict[tuple[str, tuple], list[dict]] = {}
    for line in LISTINGS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        listing = json.loads(line)
        key = listing_key(listing["category_hint"], listing["title"])
        if key is None:
            continue
        for candidate in candidate_keys(listing["category_hint"], key):
            buckets.setdefault((listing["category_hint"], candidate), []).append(listing)
    return buckets


def trim_outliers(prices: list[int]) -> list[int]:
    """用 Tukey 围栏剔除极端值，避免个别异常商品拉大整个档位的价差。"""

    if len(prices) < 4:
        return prices
    q1, _, q3 = statistics.quantiles(prices, n=4)
    fence = 1.5 * (q3 - q1)
    kept = [price for price in prices if q1 - fence <= price <= q3 + fence]
    return kept or prices


def build_offer(row: dict, samples: list[dict], key: tuple) -> dict | None:
    if len(samples) < MIN_SAMPLES:
        return None
    prices = trim_outliers(sorted(sample["price_fen"] for sample in samples))
    median = int(statistics.median(prices))
    low, high = RANGES_FEN.get(row["category"], (1, 10_000_000))
    spread = (prices[-1] - prices[0]) / median if median else 1
    if spread > SPREAD_BY_CATEGORY.get(row["category"], MAX_SPREAD) or not low <= median <= high:
        return None
    # 取最接近中位价的商品作为代表链接；它不一定就是该型号本身。
    representative = min(samples, key=lambda sample: abs(sample["price_fen"] - median))
    return {
        "hardware_id": row["hardware_id"],
        "category": row["category"],
        "price_fen": median,
        "sample_count": len(prices),
        "spread": round(spread, 4),
        "low_confidence": len(prices) < 5 or spread > 0.3,
        "title": representative.get("title"),
        "url": representative.get("url"),
        "item_id": representative.get("item_id"),
        "shop": representative.get("shop"),
        "bucket_label": bucket_label(row["category"], key),
    }


def bucket_label(category: str, key) -> str:
    parts = [str(part) for part in (key or ()) if part is not None]
    return f"{category} {'/'.join(parts)}"


def main() -> int:
    sellable = json.loads(SELLABLE.read_text(encoding="utf-8"))["items"]
    buckets = load_buckets()
    offers = []
    for row in sellable:
        if row["category"] not in RANGES_FEN:
            continue
        key = spec_key(row["category"], row.get("key_specs") or {}, row.get("model_name") or "")
        if key is None:
            continue
        samples = []
        for candidate in candidate_keys(row["category"], key):
            samples = buckets.get((row["category"], candidate), [])
            if len(samples) >= MIN_SAMPLES:
                key = candidate
                break
        offer = build_offer(row, samples, key)
        if offer:
            offers.append(offer)
    payload = {
        "provider": "chengkit-taobao",
        "price_basis": "BUCKET",
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "offers": offers,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"档位报价 {len(offers)} 条，来自 {len(sellable)} 条可售硬件 / {len(buckets)} 个档位")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
