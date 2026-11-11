"""用已定价硬件的粗档中位价，为剩余可售硬件补一个「差不多」的参考价。

只在「不要求真实商品链接、只要中国区大致报价」的前提下使用：
所有结果标 price_basis=FALLBACK，链接退化为淘宝检索页，不冒充具体商品。
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from pc_config_data import REPO_ROOT

MKT = REPO_ROOT / "data" / "pc-config" / "export" / "marketplace"
SELLABLE = MKT / "sellable.json"
CATALOG = REPO_ROOT / "application-service" / "src" / "main" / "resources" / "pc-config" / "catalog.json"
OFFERS = REPO_ROOT / "application-service" / "src" / "main" / "resources" / "pc-config" / "offers.json"
OUTPUT = MKT / "fallback_offers.json"

# 粗档兜底只保证数量级合理，价格仍要落在类别合理区间内。
RANGES_FEN = {
    "CPU": (20_000, 2_000_000),
    "GPU": (50_000, 4_000_000),
    "MOTHERBOARD": (20_000, 800_000),
    "MEMORY": (5_000, 600_000),
    "STORAGE": (5_000, 600_000),
    "PSU": (5_000, 500_000),
    "COOLER": (3_000, 300_000),
    "CASE": (5_000, 300_000),
}


def watt_band(watt) -> str:
    value = int(watt or 0)
    if value <= 450:
        return "<=450"
    if value <= 650:
        return "451-650"
    if value <= 850:
        return "651-850"
    return ">850"


def cpu_tier(model: str) -> str:
    text = model.upper()
    if re.search(r"I9|ULTRA\s*9|RYZEN\s*9|THREADRIPPER", text):
        return "top"
    if re.search(r"I7|ULTRA\s*7|RYZEN\s*7", text):
        return "high"
    if re.search(r"I5|ULTRA\s*5|RYZEN\s*5", text):
        return "mid"
    return "entry"


def chipset_tier(specs: dict) -> str:
    chipset = str(specs.get("chipset") or "").upper()
    if re.search(r"\bX\d{3}|\bZ\d{3}", chipset):
        return "high"
    if re.search(r"\bB\d{3}", chipset):
        return "mid"
    return "entry"


def cooler_kind(model: str) -> str:
    return "aio" if any(word in model.upper() for word in ("水冷", "AIO", "LIQUID", "LC")) else "air"


def gpu_class(model: str, specs: dict) -> str | None:
    """按型号尾数分档，避免把 16GB 的 4060 Ti 和 5080 定成同一个价。"""

    text = f"{model} {specs.get('chipset') or ''}".lower()
    arc = re.search(r"arc\s*[ab](\d)", text)
    if arc:
        # Arc 的编号不是性能序（A380 比 B570 弱），按系列首数字分档。
        return {"3": "entry", "5": "mid", "7": "high", "8": "high"}.get(arc.group(1), "mid")
    match = re.search(r"(?:rtx|rx)\s*[a-z]?(\d{3,4})", text)
    if not match:
        return None
    digits = match.group(1)
    # 四位型号不能直接 %100：7800 会被算成 00，整档价格被拉到入门级。
    # AMD RX 7xxx 的性能档在中间两位（7800 → 80），其余四位数在末两位（9070/4070 → 70）。
    if len(digits) == 4:
        tier = digits[1:3] if digits.startswith("7") else digits[2:4]
    else:
        tier = digits[1:3]
    tail = int(tier)
    if tail >= 90:
        return "top"
    if tail >= 70:
        return "high"
    if tail >= 60:
        return "mid"
    return "entry"


def coarse_key(category: str, specs: dict, model: str):
    """越具体的键越优先；同一台机器只用一个键定一次价。"""

    if category == "CPU":
        return ("cpu", cpu_tier(model))
    if category == "GPU":
        return ("gpu", specs.get("vram_gb"), gpu_class(model, specs))
    if category == "MOTHERBOARD":
        return ("mb", chipset_tier(specs), str(specs.get("memory_type") or "").lower())
    if category == "MEMORY":
        return ("mem", specs.get("capacity_gb"), str(specs.get("memory_type") or "").lower())
    if category == "STORAGE":
        return ("sto", specs.get("capacity_gb"))
    if category == "PSU":
        return ("psu", watt_band(specs.get("wattage_w")))
    if category == "COOLER":
        return ("cool", cooler_kind(model))
    if category == "CASE":
        return ("case",)
    return None


def key_chain(category: str, key) -> list[tuple]:
    """逐级放宽：具体档 → 去掉分级 → 类别中位价。"""

    if not key:
        return [(category,)]
    keys = [key]
    if category == "GPU" and len(key) == 3:
        # 少见显存（4G/6G/10G）没有同显存样本时，先退到同芯片档次，避免直接跳到类别中位价。
        keys.append(key[:2])
        keys.append(("gpu", key[2]))
    if category == "MEMORY" and len(key) == 3:
        keys.append(key[:2])
    keys.append((category,))
    return keys


def build_medians(rows: list[dict], prices: dict[str, int]) -> dict[tuple, int]:
    groups: dict[tuple, list[int]] = {}
    for row in rows:
        price = prices.get(row["hardware_id"])
        # sellable 用 key_specs，运行时目录用 specifications，两套字段都要兼容。
        specs = row.get("key_specs") or row.get("specifications") or {}
        key = coarse_key(row["category"], specs, row.get("model_name") or "")
        if not price or key is None:
            continue
        for candidate in key_chain(row["category"], key):
            groups.setdefault(candidate, []).append(price)
    return {key: int(statistics.median(values)) for key, values in groups.items()}


def capacity_subtype(category: str, specs: dict) -> str | None:
    """容量类硬件的细分维度：内存看代际，硬盘看接口。

    同一类里 16GB 内存与 128GB 内存、1TB SATA 与 4TB NVMe 价格差异数量级，
    不能共用类别中位价。
    """

    if category == "MEMORY":
        return str(specs.get("memory_type") or "").lower() or None
    if category == "STORAGE":
        return str(specs.get("interface") or "").lower() or None
    return None


def build_unit_medians(rows: list[dict], prices: dict[str, int]) -> dict[tuple, float]:
    """按「每 GB 中位单价」建模容量类硬件，用于缺档时按容量外推。

    128GB 套条在已定价样本里往往没有同容量样本，若退回类别中位价会被算成
    16GB 的价格；价格与容量近似线性，用单位价 × 容量是保守且可解释的估算。
    """

    groups: dict[tuple, list[float]] = {}
    for row in rows:
        price = prices.get(row["hardware_id"])
        if not price:
            continue
        specs = row.get("key_specs") or row.get("specifications") or {}
        subtype = capacity_subtype(row["category"], specs)
        capacity = specs.get("capacity_gb")
        if subtype is None or not capacity or capacity <= 0:
            continue
        groups.setdefault((row["category"], subtype), []).append(price / float(capacity))
    return {key: statistics.median(values) for key, values in groups.items()}


def search_url(model: str) -> str:
    return f"https://s.taobao.com/search?q={quote(model)}"


def main() -> int:
    sellable = json.loads(SELLABLE.read_text(encoding="utf-8"))["items"]
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["hardware"]
    offers = json.loads(OFFERS.read_text(encoding="utf-8"))["offers"]
    # 上一轮兜底价不能作为本轮中位价的样本，否则会自我强化。
    prices = {offer["hardware_id"]: int(offer["price_fen"])
              for offer in offers if offer.get("price_basis") != "FALLBACK"}
    medians = build_medians(catalog, prices)
    unit_medians = build_unit_medians(catalog, prices)

    offers_out = []
    skipped = 0
    for row in sellable:
        if row["hardware_id"] in prices or row["category"] not in RANGES_FEN:
            continue
        specs = row.get("key_specs") or {}
        model = row.get("model_name") or ""
        key = coarse_key(row["category"], specs, model)
        price = None
        # 只有容量类硬件禁止退回类别中位价；机箱、散热等类别内价格同量级，仍可兜底。
        is_capacity_category = row["category"] in ("MEMORY", "STORAGE")
        for candidate in key_chain(row["category"], key):
            # 容量类缺档时不退回类别中位价：那等于用 16GB 的价给大容量套条定价，
            # 改为按容量外推；外推也不可用时宁可跳过，交给上层判定无价。
            if is_capacity_category and candidate == (row["category"],):
                break
            price = medians.get(candidate)
            if price:
                key = candidate
                break
        if price is None:
            subtype = capacity_subtype(row["category"], specs)
            capacity = specs.get("capacity_gb")
            unit_price = unit_medians.get((row["category"], subtype)) if subtype else None
            if unit_price and capacity:
                price = int(round(unit_price * capacity))
                key = (row["category"], subtype, "per_gb")
        low, high = RANGES_FEN[row["category"]]
        if not price or not low <= price <= high:
            skipped += 1
            continue
        offers_out.append({
            "hardware_id": row["hardware_id"],
            "category": row["category"],
            "price_fen": price,
            "sample_count": 1,
            "spread": 0.0,
            "low_confidence": True,
            "title": f"{model}（按同档硬件中位价估算）",
            "url": search_url(model),
            "item_id": None,
            "shop": None,
            "bucket_label": "FALLBACK " + "/".join(str(part) for part in (key or ()) if part),
        })

    payload = {
        "provider": "chengkit-taobao",
        "price_basis": "FALLBACK",
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "offers": offers_out,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"兜底报价 {len(offers_out)} 条，跳过 {skipped} 条，档位 {len(medians)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
