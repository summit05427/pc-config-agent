"""Stage 4A：按配额挑选热门优先的候选短名单。

顺序固定为：先定各品类配额 -> 用公开榜单命中热门型号 -> 未满配额用现代在售型号补足。
价格只做标记，热门条目使用榜单观测价，其余仍为规格桶参考价。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from stage3d_finalize import is_eligible

BASE_DIR = Path(__file__).resolve().parents[2]
CLEANING_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
POOL = CLEANING_DIR / "stage3d-candidate-pool.jsonl"
ALL = CLEANING_DIR / "stage3d-final-candidates.jsonl"
PRODUCTS = CLEANING_DIR / "stage3e-products.jsonl"
HOT = CLEANING_DIR / "stage4-hot-list.json"
CN_MODELS = CLEANING_DIR / "cn-models.jsonl"
OUTPUT = CLEANING_DIR / "stage4-shortlist.jsonl"
REPORT = CLEANING_DIR / "stage4-shortlist-report.json"
OBSERVATIONS = CLEANING_DIR / "stage4-price-observations.jsonl"

QUOTAS = {
    "CPU": 72,
    "GPU": 72,
    "MOTHERBOARD": 60,
    "MEMORY": 60,
    "STORAGE": 54,
    "PSU": 40,
    "COOLER": 26,
    "CASE": 26,
}

# 按部件重要性与场景覆盖分配：关键件多、兼容件少。
STRATUM_TARGETS = {
    "CPU": {"socket:AM5": 30, "socket:LGA1851": 20, "socket:LGA1700": 14, "socket:AM4": 8},
    "GPU": {"vram:8": 22, "vram:12": 14, "vram:16+": 36},
    "MOTHERBOARD": {"socket:AM5": 26, "socket:LGA1851": 16, "socket:LGA1700": 12, "socket:AM4": 6},
    "MEMORY": {"type:DDR5": 40, "type:DDR4": 20},
    "STORAGE": {"media:SSD": 40, "media:HDD": 14},
    "PSU": {"watt:450-550": 6, "watt:600-700": 14, "watt:750-850": 14, "watt:1000+": 6},
    "COOLER": {
        "cooling:air": 13,
        "cooling:water-120": 2,
        "cooling:water-240": 4,
        "cooling:water-280": 3,
        "cooling:water-360": 3,
        "cooling:water-420": 1,
    },
    "CASE": {
        "form:ATX Mid Tower": 13,
        "form:ATX Full Tower": 3,
        "form:MicroATX Mid Tower": 5,
        "form:MicroATX Mini Tower": 3,
        "form:Mini ITX Tower": 1,
        "form:Mini ITX Desktop": 1,
    },
}


NON_EXISTENT_CPU = {"AMD Ryzen 5 5500F", "AMD Ryzen 7 7700X3D", "AMD Ryzen 7 9850X3D"}

# 无国行零售价、且非主流 DIY 选择的散热器
COOLER_NO_RETAIL = {
    "cooler-thermaltake-meorb-ii",
    "cooler-thermaltake-toughliquid-ultra-429289",
    "cooler-msi-meg-coreliquid-s280",
    "cooler-be-quiet-pure-loop-2",
    "cooler-super-flower-cooldex-st4",
}

WORKSTATION_GPU_PATTERN = re.compile(r"\bQUADRO\b|RTX PRO|RTX A\d|RADEON PRO|RADEON AI PRO|ARC PRO|ADA GENERATION")

# 国内无零售渠道或已停产、只能靠推算落价的条目：剔出候选池，不再编造参考价
NO_CN_RETAIL_IDS = frozenset(
    {
        # 存储：停产 SATA / 企业盘 / 无国内渠道品牌
        "storage-intel-660p-2-048-tb",
        "storage-seagate-sv35-5-500-gb-3-5-5900-rpm-internal-hard-drive",
        "storage-seagate-constellation-es-2-3-tb-3-5-7200-rpm-internal-hard-drive",
        "storage-transcend-ssd230s-1-tb-2-5",
        "storage-addlink-s20-1-tb-2-5",
        "storage-addlink-a93-ps5-4-tb",
        "storage-hitachi-deskstar-5k3000-3-tb-3-5-5400-rpm-internal-hard-drive",
        "storage-hitachi-ultrastar-he10-10-tb-3-5-7200-rpm-internal-hard-drive-159491",
        "storage-hitachi-ultrastar-sn260-1-6-tb-pcie-nvme",
        "storage-toshiba-mg10-512e-20-tb-3-5-7200-rpm-internal-hard-drive",
        "storage-dell-k054n-600-gb-3-5-10000-rpm-internal-hard-drive",
        "storage-samsung-mz-75e4t0b-4-tb-2-5",
        "storage-pny-cs2342-1-tb",
        "storage-adata-su630-960-gb-2-5",
        "storage-gigabyte-gp-gstfs31480gntd-480-gb-2-5",
        "storage-western-digital-ultrastar-8-tb-3-5-7200-rpm-internal-hard-drive",
        # 存储：早已停产、国内无新货渠道的机械盘
        "storage-hitachi-7k1000-c-1-tb-3-5-7200-rpm-internal-hard-drive",
        # 存储：国内无零售渠道的企业级 OEM 盘、海外联名款与停产型号
        "storage-gamestop-23vg-gspl-gamestop-nvme-ssd-heatsink-2tb-2-tb",
        "storage-visiontek-pro-hxs-1-tb-2-5",
        "storage-micron-5200-ion-7-68-tb-2-5",
        "storage-hitachi-hds723030ala640-3-tb-3-5-7200-rpm-internal-hard-drive",
        "storage-seagate-constellation-es-3-1-tb-3-5-7200-rpm-internal-hard-drive",
        "storage-toshiba-mq01abd-v-1-tb-2-5-5400-rpm-internal-hard-drive",
        "storage-seagate-momentu-500-gb-2-5-7200-rpm-internal-hard-drive",
        "storage-seagate-barracuda-green-1-5-tb-3-5-5900-rpm-internal-hard-drive",
        "storage-intel-530-480-gb-2-5",
        "storage-transcend-830s-1-tb",
        "storage-teamgroup-ms30-512-gb",
        # 电源：已退出中国市场或从未引进的型号
        "psu-visiontek-900488",
        "psu-rosewill-stallion",
        "psu-rosewill-vmg",
        "psu-evga-650-bq",
        "psu-antec-basiq",
        "psu-antec-earthwatts",
        "psu-be-quiet-system-power-10",
        "psu-thermaltake-toughpower-gx2",
        "psu-thermaltake-smart-49475",
        "psu-thermaltake-toughpower-sfx",
        "psu-segotep-gn",
        # 散热：国内无零售品牌
        "cooler-darkrock-d240",
        "cooler-xilence-a250pwm",
        "cooler-alpenf-hn-black-ridge",
        "cooler-endorfy-fera-5",
        "cooler-gamdias-aura-gl360-digital",
        "cooler-fsp-group-mp7",
        # 内存：DDR4 早期低频/超高频小批量，国内无零售
        "memory-corsair-cmv8gx4m1a2133c15-8-gb-1-x-8-gb-ddr4-2133-cl15",
        "memory-corsair-valueselect-16-gb-1-x-16-gb-ddr4-2133-cl15",
        "memory-crucial-ballistix-max-16-gb-2-x-8-gb-ddr4-5100-cl19",
        "memory-crucial-ct2k16g4dfd8266-32-gb-2-x-16-gb-ddr4-2666-cl19",
        "memory-crucial-ct4k16g4dfd8213-64-gb-4-x-16-gb-ddr4-2133-cl15",
        "memory-g-skill-trident-z-rgb-32-gb-4-x-8-gb-ddr4-4266-cl17",
        "memory-pny-performance-16-gb-1-x-16-gb-ddr5-5600-cl46",
    }
)

# 国内无零售渠道的内存/硬盘品牌与退役盘型号，留着无法给出可信国行价
OVERSEAS_ONLY_TOKENS = (
    "oloy",
    "timetec",
    "v-color",
    "vcolor",
    "goodram",
    "silicon-power",
    "kingspec",
    "agi-ai",
    "intenso",
    "micron-1100",
    "cheetah",
    "momentus",
    "ssdsc2bb",
    "hitachi-s842",
    # 国内无正规零售渠道的品牌：留着只能编价，且不属于个人 DIY 常见选择
    "gamdias",
    "xilence",
    "endorfy",
    "rosewill",
    "evga",
    "patriot",
    "inland",
    "alphacool",
    "mars-gaming",
    "yeyian",
    # 只有欧美渠道、国内无零售的机电品牌
    "apevia",
    "athena power",
    "coolmax",
    "chieftec",
    "anidees",
    "hyte",
)

LIQUID_COOLER_TOKENS = (
    "liquid",
    "aqua elite",
    "coreliquid",
    "toughliquid",
    "water",
    "kraken",
    "floe",
    "galahad",
    "eisbaer",
    "levante",
    "ryujin",
    "strix lc",
    "tuf gaming lc",
    "light loop",
    "pure loop",
    "fx240",
    "aio",
)

# stage3d 对个别散热器误判分层的具名修正：优先级高于关键词规则
COOLER_STRATUM_OVERRIDES = {
    # 利民 U120 EX EVO 是单塔风冷，stage3d 从型号名误读出 120mm 冷排，错挂 water-120
    "cooler-thermalright-ultra-120-extreme-evo-rev-5": "cooling:air",
    # 利民 PA120 Digital 同为风冷，型号里的 120 是风扇尺寸
    "cooler-thermalright-peerless-assassin-120-digital": "cooling:air",
}


def fix_cooler_stratum(row: dict, specs: dict | None = None) -> dict:
    """修正散热器的「风冷 / 水冷」分层。

    stage3d 只按型号名里的数字猜冷排尺寸，会把「PA120」「U120」这类风冷型号
    误判成水冷，也会把没写尺寸的一体水冷判成风冷，价格随之错档。
    这里以 water_cooled 规格为准，缺失时才回落到名称关键词。
    """

    if row.get("category") != "COOLER":
        return row
    override = COOLER_STRATUM_OVERRIDES.get(row.get("product_id"))
    if override:
        row["stratum"] = override
        return row
    specs = specs or row.get("specifications") or {}
    name = row.get("display_name", "").lower()
    water_cooled = specs.get("water_cooled")
    if water_cooled is False:
        row["stratum"] = "cooling:air"
        return row
    if water_cooled is True:
        row["stratum"] = _water_stratum(specs.get("radiator_size_mm"), name)
        return row
    if row.get("stratum", "").startswith("cooling:water") and "None" not in row["stratum"]:
        return row
    if any(token in name for token in LIQUID_COOLER_TOKENS):
        row["stratum"] = _water_stratum(specs.get("radiator_size_mm"), name)
    return row


def _water_stratum(radiator_size_mm: int | None, name: str) -> str:
    """按冷排尺寸落层：规格优先，其次型号名，都没有时按最常见的 240。"""

    if radiator_size_mm:
        return f"cooling:water-{radiator_size_mm}"
    # ROG RYUJIN 系列没有冷排尺寸标注，默认 360
    if "ryujin" in name:
        return "cooling:water-360"
    for size in (420, 360, 280, 240, 120):
        if str(size) in name:
            return f"cooling:water-{size}"
    return "cooling:water-240"


def is_excluded(row: dict) -> bool:
    """按规则剔除服务器/工作站/非桌面件，避免新增脏数据再次进入候选池。"""

    text = f"{row.get('product_id', '')} {row.get('display_name', '')}".lower()
    # 国内无零售/已停产的具名条目：精确 id 匹配，避免误伤同品牌在售型号
    if row.get("product_id") in NO_CN_RETAIL_IDS:
        return True
    # 国内无零售渠道的海外专供型号：留着只能编价，用国行同规格替代
    if any(token in text for token in OVERSEAS_ONLY_TOKENS):
        return True

    category = row["category"]
    name = row["display_name"].upper()
    product_id = row["product_id"]
    if category == "CPU":
        if any(tag in name for tag in ("EPYC", "XEON", "THREADRIPPER")):
            return True
        return row["display_name"] in NON_EXISTENT_CPU
    if category == "GPU":
        return bool(WORKSTATION_GPU_PATTERN.search(name))
    if category == "MEMORY":
        return any(tag in product_id for tag in ("registered", "sodimm", "ecc"))
    if category == "STORAGE":
        # 企业级盘与行业监控盘（SkyHawk AI、Purple）不属于个人 DIY 选型；NAS 盘（IronWolf、Red Plus）保留
        return any(
            tag in product_id
            for tag in (
                "enterprise",
                "exos",
                "nytro",
                "savvio",
                "intel-dc",
                "intel-pro-5400s",
                "intel-d3-",
                "mx300",
                "ultrastar",
                "skyhawk",
                "purple",
                "western-digital-gold",
                "mg09",
                "st6000nm",
                "wd-black-10-tb",
                "wd-black-6-tb",
                "thinkstation",
                "0f27406",
                "sandisk-extreme",
                # 企业级 Constellation 盘、已停产的 2.5 吋 Travelstar
                "st4000nm",
                "travelstar",
            )
        )
    if category == "COOLER":
        return product_id in COOLER_NO_RETAIL
    return False


CN_STRATUM = {
    "MOTHERBOARD": lambda specs: f"socket:{specs.get('socket')}",
    "MEMORY": lambda specs: f"type:{specs.get('memory_type')}",
    "STORAGE": lambda specs: "media:SSD" if specs.get("nvme") else "media:HDD",
    "COOLER": lambda specs: (
        f"cooling:water-{specs.get('radiator_size_mm')}" if specs.get("cooler_type") == "LIQUID" else "cooling:air"
    ),
}


def load_cn_rows(path: Path) -> list[dict]:
    """把国行目录转成与 stage3d 同构的行，使其参与同一套配额与分层竞争。"""

    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        specs = dict(row.get("specifications") or {})
        # 统一字段名，复用 stage3d 的资格判断与分层规则
        if row["category"] == "PSU":
            specs.setdefault("rated_power_w", specs.get("wattage_w"))
        if row["category"] == "CASE":
            specs.setdefault("case_type", row["stratum"].replace("form:", ""))
        if row["category"] == "MEMORY":
            specs.setdefault("speed_mhz", specs.get("speed_mts"))
        row["specifications"] = specs
        normalizer = CN_STRATUM.get(row["category"])
        if normalizer:
            row["stratum"] = normalizer(specs)
        rows.append(row)
    return rows


def tokens_loose(text: str) -> list[str]:
    """切出中英文/数字片段，用于「榜单标签 ⊂ 国行标签」的宽松比对。"""

    return [chunk.lower() for chunk in re.findall(r"[0-9A-Za-z]+|[\u4e00-\u9fff]+", text)]


def prefer_priced(rows: list[dict], count: int, keep_ids: frozenset[str] = frozenset()) -> list[dict]:
    """同层补位时优先保住上一轮已入选的条目，再优先选已有真实价的条目。

    按价格分位取样对候选池增删极其敏感：剔除几条无关条目就会让整层取样点整体平移，
    把已观测价的条目挤出短名单。这里先锁定上一轮仍在同层的条目，使剔除只造成「一换一」。
    """

    kept = sorted((row for row in rows if row["product_id"] in keep_ids), key=lambda row: row["product_id"])[:count]
    remaining = [row for row in rows if row["product_id"] not in keep_ids]
    slots = count - len(kept)
    if slots <= 0:
        return kept
    priced = [row for row in remaining if row.get("price_status")]
    if len(priced) >= slots:
        return kept + pick_even(priced, slots)
    return kept + priced + pick_even([row for row in remaining if not row.get("price_status")], slots - len(priced))


def pick_even(rows: list[dict], count: int) -> list[dict]:
    """按价格分位取样，保证同一层里从低到高都有代表。"""

    ordered = sorted(rows, key=lambda row: row["price_cny"] or 0)
    if count <= 0 or not ordered:
        return []
    if count >= len(ordered):
        return ordered
    if count == 1:
        return [ordered[len(ordered) // 2]]
    indexes = sorted({round(index * (len(ordered) - 1) / (count - 1)) for index in range(count)})
    return [ordered[index] for index in indexes]


def norm(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def label_capacity(label: str) -> int | None:
    tb = re.search(r"(\d+)\s*TB", label, re.IGNORECASE)
    if tb:
        return int(tb.group(1)) * 1024
    gb = re.search(r"(\d+)\s*GB", label, re.IGNORECASE)
    return int(gb.group(1)) if gb else None


def label_speed(label: str) -> int | None:
    match = re.search(r"\b([4-8]\d{3})\b", label)
    return int(match.group(1)) if match else None


def matches(entry: dict, product: dict) -> bool:
    specs = product.get("specifications") or {}
    name = norm(product["display_name"])
    if not all(norm(token) in name for token in entry["tokens"]):
        return False
    category = entry["category"]
    if category == "GPU" and entry.get("vram_gb"):
        return specs.get("vram_gb") == entry["vram_gb"]
    if category == "MEMORY":
        if "DDR5" in entry["label"] and specs.get("memory_type") != "DDR5":
            return False
        capacity = label_capacity(entry["label"])
        speed = label_speed(entry["label"])
        if capacity and specs.get("capacity_gb") != capacity:
            return False
        if speed and specs.get("speed_mhz") != speed:
            return False
    if category == "STORAGE":
        capacity = label_capacity(entry["label"])
        if capacity and specs.get("capacity_gb") != capacity:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4A 热门优先短名单")
    parser.add_argument("--pool", default=str(POOL))
    parser.add_argument("--all", default=str(ALL))
    parser.add_argument("--products", default=str(PRODUCTS))
    parser.add_argument("--hot", default=str(HOT))
    parser.add_argument("--cn", default=str(CN_MODELS))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--report", default=str(REPORT))
    args = parser.parse_args()

    products = {
        row["product_id"]: row
        for row in (
            json.loads(line)
            for line in Path(args.products).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }

    def product_specs(product_id: str) -> dict:
        return (products.get(product_id) or {}).get("specifications") or {}

    pool = []
    for line in Path(args.pool).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        pool.append(fix_cooler_stratum(row, product_specs(row["product_id"])))
    # 观测账本作为「粘性保持集」：已落价的条目优先留在同层名额内，
    # 保证短名单是「候选池 + 账本」的确定性函数，避免每次重跑都被分位取样整体打散
    sticky_ids: frozenset[str] = frozenset()
    if OBSERVATIONS.exists():
        sticky_ids |= frozenset(
            record["product_id"]
            for record in (
                json.loads(line) for line in OBSERVATIONS.read_text(encoding="utf-8").splitlines() if line.strip()
            )
            if record.get("product_id")
        )
    hot = json.loads(Path(args.hot).read_text(encoding="utf-8"))
    all_rows = {
        row["product_id"]: row
        for row in (
            json.loads(line)
            for line in Path(args.all).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    cn_rows = [row for row in load_cn_rows(Path(args.cn)) if not is_excluded(row)]
    for row in cn_rows:
        all_rows.setdefault(row["product_id"], row)
        products.setdefault(row["product_id"], row)
    # 同上：榜单/补位走的是 stage3d 原始分层，水冷被误判成风冷时先在源头修正
    for row in all_rows.values():
        fix_cooler_stratum(row, product_specs(row["product_id"]))
    excluded_ids = {row["product_id"] for row in all_rows.values() if is_excluded(row)}
    all_rows = {key: value for key, value in all_rows.items() if key not in excluded_ids}
    pool = [row for row in pool if row["product_id"] not in excluded_ids]
    by_category: dict[str, list[dict]] = defaultdict(list)
    for row in pool:
        by_category[row["category"]].append(row)
    hot_pool: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows.values():
        hot_pool[row["category"]].append(row)
    selected: dict[str, dict] = {}
    matched_labels: dict[str, list[str]] = defaultdict(list)
    missing: dict[str, list[str]] = defaultdict(list)

    for entry in hot["items"]:
        category = entry["category"]
        candidates = [row for row in hot_pool[category] if matches(entry, products[row["product_id"]])]
        if not candidates:
            # 国行名称是中文，英文榜单 token 匹配不到，用目录里预置的 hot_label 宽松兜底
            loose_join = "".join(tokens_loose(entry["label"]))
            candidates = [
                row
                for row in hot_pool[category]
                if row.get("hot_label") and all(chunk in loose_join for chunk in tokens_loose(row["hot_label"]))
            ]
        if not candidates:
            missing[category].append(entry["label"])
            continue
        target = entry.get("price_cny")
        candidates.sort(key=lambda row: (row["lifecycle_status"] != "CURRENT", abs((row["price_cny"] or 0) - (target or 0))))
        pick = candidates[0]
        if pick["product_id"] in selected:
            continue
        row = dict(pick)
        row["popularity_status"] = "HOT_LIST"
        row["hot_label"] = entry["label"]
        row["hot_source"] = entry["source"]
        row["hot_observed_at"] = hot["observed_at"]
        if target:
            row["price_cny"] = target
            row["price_source"] = "HOT_LIST"
            row["price_status"] = f"OBSERVED_{hot['observed_at']}"
        else:
            row["price_status"] = "PROVISIONAL"
        selected[pick["product_id"]] = row
        matched_labels[category].append(entry["label"])

    eligible: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows.values():
        if row["recommendation_status"] == "EXCLUDED":
            continue
        specs = products[row["product_id"]].get("specifications") or {}
        if is_eligible(row, specs):
            eligible[row["category"]].append(row)

    for category, quota in QUOTAS.items():
        current = [row for row in selected.values() if row["category"] == category]
        for stratum, target in STRATUM_TARGETS[category].items():
            have = sum(1 for row in current if row.get("stratum") == stratum)
            if have >= target:
                continue
            candidates = [
                row for row in eligible[category]
                if row.get("stratum") == stratum and row["product_id"] not in selected
            ]
            for row in prefer_priced(candidates, target - have, sticky_ids):
                filled = dict(row)
                filled.setdefault("popularity_status", "NOT_EVALUATED")
                # 国行条目自带观测价，不能被覆盖成 PROVISIONAL
                if not filled.get("price_status"):
                    filled["price_status"] = "PROVISIONAL"
                selected[row["product_id"]] = filled
                current.append(filled)
        if len(current) < quota:
            remaining = [row for row in eligible[category] if row["product_id"] not in selected]
            for row in prefer_priced(remaining, quota - len(current), sticky_ids):
                filled = dict(row)
                filled.setdefault("popularity_status", "NOT_EVALUATED")
                # 国行条目自带观测价，不能被覆盖成 PROVISIONAL
                if not filled.get("price_status"):
                    filled["price_status"] = "PROVISIONAL"
                selected[row["product_id"]] = filled
                current.append(filled)
        if len(current) > quota:
            extras = sorted(
                [row for row in current if row["popularity_status"] == "NOT_EVALUATED"],
                key=lambda row: row["price_cny"] or 0,
                reverse=True,
            )
            for row in extras[: len(current) - quota]:
                selected.pop(row["product_id"], None)

    rows = sorted(selected.values(), key=lambda row: (row["category"], row["price_cny"] or 0))
    with Path(args.output).open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = {
        "stage": "4A-shortlist",
        "order": "配额 -> 热门榜单命中 -> 现代型号补足 -> 价格标记",
        "quotas": QUOTAS,
        "stratum_targets": STRATUM_TARGETS,
        "total": len(rows),
        "excluded": len(excluded_ids),
        "cn_candidates": len(cn_rows),
        "cn_selected": sum(1 for row in rows if row["product_id"] in {c["product_id"] for c in cn_rows}),
        "by_category": dict(Counter(row["category"] for row in rows)),
        "hot_matched": {key: len(value) for key, value in matched_labels.items()},
        "hot_missing": {key: value for key, value in missing.items() if value},
        "hot_observed_at": hot["observed_at"],
        "price_status": dict(Counter(row["price_status"] for row in rows)),
        "note": "热门=公开榜单命中，不是销量；未命中条目标注 NOT_EVALUATED，价格仍为规格桶参考价。",
    }
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"短名单 {len(rows)} 条")
    print("热门命中：" + ", ".join(f"{k}={len(v)}" for k, v in sorted(matched_labels.items())))
    print("榜单未匹配：" + ", ".join(f"{k}={len(v)}" for k, v in sorted(missing.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
