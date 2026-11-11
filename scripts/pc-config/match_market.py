"""把淘宝搜索卡片离线匹配到 sellable 硬件，产出商品索引、匹配结果与候选报价。

匹配不联网：所有判断基于标题、型号 token、品牌中文别名。
置信度：EXACT（型号+品牌+规格齐全）/ FAMILY（型号命中但品牌或规格不全）/
MULTI_MODEL（混卖多型号，展示价不可作为单型号价格）/ BRAND_ONLY 不参与逐件报价。
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from pc_config_data import REPO_ROOT

MKT = REPO_ROOT / "data" / "pc-config" / "export" / "marketplace"
RAW = MKT / "raw"
SELLABLE = MKT / "sellable.json"
MASTER = REPO_ROOT / "data" / "pc-config" / "master" / "hardware-master.jsonl"
DUPLICATE_SUFFIX = re.compile(r"-\d{4,}$")


def canonical_id(hardware_id: str, master_ids: set[str]) -> str:
    """主库对同一型号常追加纯数字去重码，聚合前收敛到规范 ID。"""

    base = DUPLICATE_SUFFIX.sub("", hardware_id)
    return base if base in master_ids else hardware_id

BRAND_CN = {
    "SAMA": ["先马"], "Jonsbo": ["乔思伯"], "Lian Li": ["联力"], "Antec": ["安钛克"],
    "Phanteks": ["追风者"], "Thermaltake": ["曜越"], "Silverstone": ["银欣"],
    "Fractal Design": ["分形工艺", "fractal"], "HYTE": ["hyte"], "be quiet!": ["bequiet", "德商必酷"],
    "MSI": ["微星"], "Asus": ["华硕"], "Gigabyte": ["技嘉"], "ASRock": ["华擎"],
    "Corsair": ["海盗船"], "Cooler Master": ["酷冷至尊"], "NZXT": ["恩杰"],
    "Noctua": ["猫头鹰"], "Thermalright": ["利民"], "DeepCool": ["九州风神"],
    "ID-COOLING": ["idcooling"], "ARCTIC": ["arctic"], "ProArtist": ["雅浚"], "Valkyrie": ["瓦尔基里"],
    "SeaSonic": ["海韵", "seasonic"], "Seasonic": ["海韵", "seasonic"],
    "Super Flower": ["振华"], "FSP Group": ["全汉"], "Montech": ["君主"],
    "Zalman": ["扎曼"], "Geometric Future": ["几何未来"], "Segotep": ["鑫谷"],
    "Great Wall": ["长城"], "Kingston": ["金士顿"], "G.Skill": ["芝奇"], "Team": ["十铨"],
    "TEAMGROUP": ["十铨"], "Crucial": ["英睿达"], "ADATA": ["威刚"], "Lexar": ["雷克沙"],
    "Samsung": ["三星"], "SK Hynix": ["海力士"], "Western Digital": ["西部数据", "西数"],
    "Seagate": ["希捷"], "SanDisk": ["闪迪"], "Toshiba": ["东芝", "铠侠"], "Solidigm": ["solidigm"],
    "PNY": ["pny"], "Acer": ["宏碁"], "Zotac": ["索泰"], "XFX": ["讯景"],
    "PowerColor": ["撼讯"], "Sapphire": ["蓝宝石"], "Palit": ["同德", "palit"],
    "Sparkle": ["憾讯", "sparkle"], "Yeston": ["盈通"], "Inno3D": ["映众"],
    "Biostar": ["映泰"], "Colorful": ["七彩虹"], "Gainward": ["耕升"], "Galax": ["影驰"],
    "Maxsun": ["铭瑄"], "Intel": ["英特尔", "intel"], "AMD": ["amd"],
}

USED_RE = re.compile(r"二手|拆机|翻新|拆封|矿卡|九成新")
BUNDLE_RE = re.compile(r"套装|整机|主机|板u|准系统|主机箱")
# 海外直购/未税不开票的商品不是中国区行货价，不能作为参考价。
GRAY_RE = re.compile(r"海外|直购|未税|不开票|无票|代购|海淘")
RAW_NAME_RE = re.compile(r"^\d+-([A-Z]+)-")

PRODUCT_WORDS = {
    "CPU": ("处理器", "cpu", "盒装", "散片"),
    "GPU": ("显卡", "gpu"),
    "MOTHERBOARD": ("主板",),
    "MEMORY": ("内存", "dimm"),
    "STORAGE": ("固态", "ssd", "硬盘"),
    "COOLER": ("散热", "水冷", "风冷"),
    "CASE": ("机箱",),
    "PSU": ("电源",),
}

# 标题含品类词但实际卖配件的商品（如「机箱风扇」「散热硅脂」），不能参与整件定价。
ACCESSORY_EXTRA = {
    "CASE": re.compile(r"风扇|配件|防尘|支架|理线|脚垫|侧板|螺丝|机箱灯"),
    "COOLER": re.compile(r"硅脂|导热|水冷液|扣具|散热片"),
}


def norm(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text).lower())


def has_token(hay: str, token: str) -> bool:
    """按边界匹配，避免 4060 命中 4060Ti；数字后紧跟数字仍视为命中（如 6000MHz）。"""

    if not token:
        return False
    # 标题删除分隔符后，容量词常写成 8GB，允许 g 后多一个 b。
    tail = r"b?(?![a-z])" if token.endswith("g") else r"(?![a-z])"
    return re.search(re.escape(token) + tail, hay) is not None


def has_model_token(hay: str, token: str) -> bool:
    """纯字母型号词（如 tomahawk）在去分隔符标题里会粘着别的单词，改用子串匹配。"""

    if token.isalpha() and len(token) >= 4:
        return token in hay
    return has_token(hay, token)


def cpu_token(model: str) -> str | None:
    match = re.search(r"i[3579][\s-]?(\d{4,5}[A-Za-z]{0,2})", model)
    if match:
        return norm(match.group(1))
    match = re.search(r"Ryzen\s*[3579]\s*(\d{4}[A-Za-z0-9]{0,3})", model)
    return norm(match.group(1)) if match else None


def gpu_token(specs: dict, model: str) -> str | None:
    chip = str(specs.get("chipset") or model)
    chip = re.sub(r"(GeForce|Radeon)\s*", "", chip, flags=re.I)
    return norm(chip) or None


def series_token(model: str, brand: str) -> str | None:
    """取型号里的序列主体：去掉品牌与容量后的第一个含数字片段。"""

    body = model.replace(brand, " ")
    body = re.sub(r"\d+\s?(GB|TB)\b", " ", body, flags=re.I)
    for piece in re.split(r"[\s/]+", body):
        token = norm(piece)
        if token and re.search(r"[0-9]", token) and len(token) >= 3:
            return token
    return None


def memory_groups(specs: dict) -> tuple[list[str], list[str]]:
    mem_type = norm(specs.get("memory_type") or "")
    speed = str(specs.get("speed_mts") or "")
    capacity = specs.get("capacity_gb")
    must = [t for t in (mem_type, speed) if t]
    optional = [f"{capacity}g"] if capacity else []
    return must, optional


# 主板链接常挂同芯片组下的多个子型号，只有标题出现具体型号词才能判定为该型号报价。
BOARD_GENERIC_TOKENS = {
    "mag", "mpg", "pro", "prime", "tuf", "rog", "strix", "gaming", "wifi", "wifi6",
    "wifi7", "wifi6e", "ax", "d4", "d5", "ddr4", "ddr5", "ii", "iii", "iv", "plus",
    "csm", "creator", "edge", "atx", "matx", "itx", "gen5", "btf", "se", "ac", "v2",
    "v3", "max", "new",
}
CHIPSET_RE = re.compile(r"(?<![0-9a-z])([abhxz]\d{3}[a-z]{0,2})(?![0-9a-z])")


def board_tokens(model: str, brand: str) -> list[str]:
    """提取能区分同芯片组子型号的型号词（如 TOMAHAWK、b760mk）。"""

    body = model.replace(brand, " ")
    chipset_like: list[str] = []
    distinctive: list[str] = []
    for piece in re.split(r"[\s/]+", body):
        token = norm(piece)
        if not token or not re.search(r"[a-z]", token):
            continue
        if re.fullmatch(r"[abhxz]\d{3}[a-z]{0,3}", token):
            chipset_like.append(token)
        elif token not in BOARD_GENERIC_TOKENS and len(token) >= 4:
            distinctive.append(token)
    return distinctive or chipset_like[:1]


def board_chipset_variants(plain: str) -> int:
    return len(set(CHIPSET_RE.findall(plain)))


def brand_tokens(brand: str) -> list[str]:
    return [norm(alias) for alias in BRAND_CN.get(brand, [brand])]


INTEL_TOKENS = ("intel", "英特尔", "i3", "i5", "i7", "i9", "奔腾", "赛扬", "ultra")
AMD_CPU_TOKENS = ("amd", "ryzen", "锐龙", "threadripper", "线程撕裂者")


def intrinsic_brand_ok(category: str, hay: str) -> bool:
    """型号本身已含厂商标识时，不再强制标题出现中文品牌名。"""

    if category == "CPU":
        return any(token in hay for token in INTEL_TOKENS + AMD_CPU_TOKENS)
    # GPU 的 hardware_id 是芯片级（如 rtx-5070-ti-16gb），AIB 品牌不影响定价。
    return category == "GPU"


def build_requirements(row: dict) -> tuple[list[str], list[str], list[str]]:
    """返回 (must, optional, brand_aliases)。"""

    category = row["category"]
    specs = row.get("key_specs") or {}
    model = row.get("model_name") or ""
    aliases = brand_tokens(row["brand"])

    if category == "CPU":
        token = cpu_token(model)
        return ([token] if token else []), [], aliases
    if category == "GPU":
        token = gpu_token(specs, model)
        vram = specs.get("vram_gb")
        return ([token] if token else []), ([f"{vram}g"] if vram else []), aliases
    if category == "MOTHERBOARD":
        chipset = norm(str(specs.get("chipset") or "").replace("Intel", "").replace("AMD", ""))
        form = specs.get("form_factor") or ""
        optional = [chipset + "m"] if "Micro" in form and chipset else []
        must = ([chipset] if chipset else []) + board_tokens(model, row["brand"])
        return must, optional, aliases
    if category == "MEMORY":
        must, optional = memory_groups(specs)
        return must, optional, aliases
    if category == "STORAGE":
        token = series_token(model, row["brand"])
        capacity = specs.get("capacity_gb")
        cap_token = f"{int(capacity / 1024)}tb" if capacity and capacity >= 1024 else f"{capacity}g"
        return ([token] if token else []), [cap_token], aliases
    if category == "COOLER" or category == "CASE":
        token = series_token(model, row["brand"])
        return ([token] if token else []), [], aliases
    if category == "PSU":
        watt = specs.get("wattage_w")
        return ([f"{int(watt)}w"] if watt else []), [], aliases
    return [], [], aliases


def count_variants(category: str, plain: str) -> int:
    """在保留分隔符的标题上统计不同型号数；≥2 说明混卖，展示价只对应最便宜那款。"""

    if category == "CPU":
        numbers = {n for n in re.findall(r"(?<!\d)(\d{4,5})(?!\d)", plain) if 3000 <= int(n) <= 15999}
        return len(numbers)
    if category == "GPU":
        numbers = {n for n in re.findall(r"(?<!\d)(\d{4})(?!\d)", plain) if 3000 <= int(n) <= 9999}
        return len(numbers)
    if category == "MEMORY":
        return len(set(re.findall(r"(\d{2,3})\s?g(?:b)?(?!\w)", plain)))
    if category == "STORAGE":
        return len(set(re.findall(r"(\d{1,3})\s?(?:tb|gb)(?!\w)", plain)))
    return 0


GPU_CAPACITY_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:gb|g)(?![0-9a-z])")
GPU_CAPACITIES = {4, 6, 8, 10, 12, 16, 20, 24, 32}


def capacity_variants(category: str, plain: str) -> int:
    """统计标题里的不同显存容量；≥2（如 16G/8G）说明展示价无法对应单一容量。"""

    if category != "GPU":
        return 0
    return len({int(value) for value in GPU_CAPACITY_RE.findall(plain)
                if int(value) in GPU_CAPACITIES})


SPEED_RE = re.compile(r"(?<!\d)([4-8]\d{3})(?!\d)")


def speed_variants(plain: str) -> int:
    """内存标题常把 5200/5600/6000 等多个频率写在一起，展示价只对应最低频那款。"""

    return len({value for value in SPEED_RE.findall(plain) if 4000 <= int(value) <= 8400})


def load_listings() -> list[dict]:
    listings: list[dict] = []
    seen: set[str] = set()
    for path in sorted(RAW.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        structured = (data.get("result") or {}).get("structuredContent") or {}
        if not structured:
            continue
        category = RAW_NAME_RE.match(path.stem).group(1) if RAW_NAME_RE.match(path.stem) else ""
        query = structured.get("query") or path.stem
        for item in structured.get("results") or []:
            pricing = item.get("pricing") or {}
            price = pricing.get("display_price")
            if not isinstance(price, (int, float)) or price <= 0:
                continue
            item_id = str(item.get("item_id") or "")
            if item_id and item_id in seen:
                continue
            seen.add(item_id)
            title = item.get("title") or ""
            plain = title.lower()
            flags = []
            if USED_RE.search(title):
                flags.append("USED")
            if BUNDLE_RE.search(title):
                flags.append("BUNDLE")
            if GRAY_RE.search(title):
                flags.append("GRAY")
            if not any(word in plain for word in PRODUCT_WORDS.get(category, ())):
                flags.append("ACCESSORY")
            if ACCESSORY_EXTRA.get(category, re.compile("$^")).search(title):
                flags.append("ACCESSORY")
            variants = count_variants(category, plain)
            listings.append({
                "query": query,
                "category_hint": category,
                "item_id": item.get("item_id"),
                "title": title,
                "url": item.get("url"),
                "price_fen": int(round(price * 100)),
                "price_label": pricing.get("price_label"),
                "price_type": pricing.get("price_type"),
                "shop": item.get("shop"),
                "sales": item.get("sales"),
                "location": item.get("location"),
                "fetched_at": structured.get("fetched_at"),
                "model_variants": variants,
                "vram_variants": capacity_variants(category, plain),
                "flags": flags,
                "norm_title": norm(title),
            })
    return listings


def match_row(row: dict, listings: list[dict]) -> list[dict]:
    must, optional, aliases = build_requirements(row)
    if not must:
        return []
    hits = []
    for listing in listings:
        if listing["category_hint"] != row["category"]:
            continue
        if {"USED", "BUNDLE", "ACCESSORY", "GRAY"} & set(listing["flags"]):
            continue
        hay = listing["norm_title"]
        if not all(has_model_token(hay, token) for token in must):
            continue
        brand_ok = any(alias and alias in hay for alias in aliases) \
            or intrinsic_brand_ok(row["category"], hay)
        spec_ok = all(has_model_token(hay, token) for token in optional) if optional else True
        # 混卖多个型号、多个显存或多芯片组的链接，展示价对应最便宜那款，不能当作该型号成交价。
        if listing.get("model_variants", 0) >= 2 or listing.get("vram_variants", 0) >= 2:
            confidence = "MULTI_MODEL"
        elif row["category"] == "MEMORY" and speed_variants(listing.get("title", "").lower()) >= 2:
            confidence = "MULTI_MODEL"
        elif row["category"] == "MOTHERBOARD" \
                and board_chipset_variants(listing.get("title", "").lower()) >= 2:
            confidence = "MULTI_MODEL"
        elif brand_ok and spec_ok:
            confidence = "EXACT"
        else:
            confidence = "FAMILY"
        hits.append({"listing": listing, "confidence": confidence})
    return hits


def main() -> int:
    sellable = json.loads(SELLABLE.read_text(encoding="utf-8"))["items"]
    master_ids = {
        json.loads(line)["hardware_id"]
        for line in MASTER.read_text(encoding="utf-8").splitlines() if line.strip()
    }
    listings = load_listings()
    print(f"商品 {len(listings)} 条，可售硬件 {len(sellable)} 条")

    by_category = defaultdict(lambda: {"total": 0, "exact": 0, "family": 0, "multi": 0})
    matches: list[dict] = []
    prices: dict[str, list[int]] = defaultdict(list)
    priced_items: set[tuple[str, str]] = set()
    for row in sellable:
        hits = match_row(row, listings)
        hardware_id = canonical_id(row["hardware_id"], master_ids)
        by_category[row["category"]]["total"] += 1
        best = "NONE"
        for hit in hits:
            confidence = hit["confidence"]
            if confidence == "EXACT":
                best = "EXACT"
            elif confidence == "FAMILY" and best == "NONE":
                best = "FAMILY"
            elif confidence == "MULTI_MODEL" and best == "NONE":
                best = "MULTI_MODEL"
            if confidence == "EXACT":
                # 同一商品会被多个重复 ID 命中，按 (规范 ID, 商品) 只计一次。
                priced = (hardware_id, str(hit["listing"]["item_id"]))
                if priced not in priced_items:
                    priced_items.add(priced)
                    prices[hardware_id].append(hit["listing"]["price_fen"])
            matches.append({
                "hardware_id": hardware_id,
                "category": row["category"],
                "model_name": row["model_name"],
                "item_id": hit["listing"]["item_id"],
                "title": hit["listing"]["title"],
                "url": hit["listing"]["url"],
                "price_fen": hit["listing"]["price_fen"],
                "confidence": confidence,
                "flags": hit["listing"]["flags"],
            })
        if best == "EXACT":
            by_category[row["category"]]["exact"] += 1
        elif best == "FAMILY":
            by_category[row["category"]]["family"] += 1
        elif best == "MULTI_MODEL":
            by_category[row["category"]]["multi"] += 1

    (MKT / "listings.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in listings), encoding="utf-8")
    (MKT / "matches.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in matches), encoding="utf-8")

    report = {}
    total = exact = family = 0
    for category, stat in by_category.items():
        covered = stat["exact"] + stat["family"]
        total += stat["total"]
        exact += stat["exact"]
        family += stat["family"]
        report[category] = {**stat, "covered": covered,
                            "rate": round(covered / stat["total"], 3) if stat["total"] else 0}
    summary = {
        "listings": len(listings),
        "sellable": len(sellable),
        "exact": exact,
        "family": family,
        "covered": exact + family,
        "rate": round((exact + family) / len(sellable), 3) if sellable else 0,
        "priced_hardware": len(prices),
        "categories": report,
    }

    candidates = []
    low_confidence = 0
    for hardware_id, values in prices.items():
        ordered = sorted(values)
        median = int(statistics.median(ordered))
        spread = (ordered[-1] - ordered[0]) / median if median else 1
        # 单样本没有交叉验证，与价差过大同样标记为低置信，入库后可被复核优先级命中。
        is_low = spread > 0.5 or len(ordered) < 2
        if is_low:
            low_confidence += 1
        candidates.append({
            "hardware_id": hardware_id,
            "price_fen": median,
            "sample_count": len(ordered),
            "price_min_fen": ordered[0],
            "price_max_fen": ordered[-1],
            "spread": round(spread, 2),
            "low_confidence": is_low,
        })
    summary["low_confidence"] = low_confidence
    (MKT / "offers_candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    (MKT / "coverage.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"覆盖 {exact + family}/{len(sellable)} = {summary['rate']:.0%}（EXACT {exact} / FAMILY {family}）")
    for category, stat in sorted(report.items()):
        print(f"  {category:<12} {stat['covered']:>4}/{stat['total']:<4} {stat['rate']:>5.0%}  "
              f"EXACT {stat['exact']:>4}")
    print(f"有价的硬件：{len(prices)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
