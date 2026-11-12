"""Stage 4B：给短名单里仍无观测价的条目补国内参考价。

优先级：WEBSEARCH 观测价 > 型号锚点（同系列已搜到的国行价）> 规格档位价。
所有兜底价格都带 confidence=LOW/MEDIUM 与 price_note，供预算估算时降权使用。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from stage4_hot_shortlist import is_excluded

BASE_DIR = Path(__file__).resolve().parents[2]
CLEANING_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
SHORTLIST = CLEANING_DIR / "stage4-shortlist.jsonl"
REPORT = CLEANING_DIR / "stage4-price-fallback-report.json"

SOURCE = "https://detail.zol.com.cn/"

# 型号锚点：同系列已通过 WebSearch 确认的国行价，按定位微调
CPU_ANCHORS: dict[str, tuple[int, str, str]] = {
    "Intel Pentium Gold G7400": (499, "LOW", "2 核入门档位 ¥499"),
    "AMD Ryzen 5 8400F": (749, "LOW", "8700F ¥998 下浮"),
    "AMD Ryzen 5 5600": (699, "LOW", "5600X ¥949 下浮（散片为主）"),
    "AMD Ryzen 5 7500": (899, "LOW", "7500F ¥1239 下浮"),
    "AMD Ryzen 7 5700X": (1049, "MEDIUM", "5700X 盒装行情 ¥1000-1100"),
    "AMD Ryzen 5 8600G": (1299, "MEDIUM", "8600G 盒装行情 ¥1299"),
    "AMD Ryzen 5 7500X3D": (1399, "LOW", "7600X3D 下浮"),
    "AMD Ryzen 7 8700G": (1699, "MEDIUM", "8700G 盒装行情 ¥1699"),
    "AMD Ryzen 7 7700X": (1499, "MEDIUM", "9700X ¥1729 下浮"),
    "AMD Ryzen 9 5900XT": (1899, "LOW", "5900X 库存价 ¥1900"),
    "AMD Ryzen 5 7600X3D": (1799, "LOW", "7800X3D ¥1891 下浮"),
    "AMD Ryzen 9 7900X": (2299, "MEDIUM", "7900 ¥2789 相邻档"),
    "AMD Ryzen 9 7900X3D": (2699, "MEDIUM", "7900X 上浮"),
    "AMD Ryzen 9 9900X3D": (3799, "MEDIUM", "9900X ¥2379 与 9950X3D ¥4399 之间"),
    "Intel Core i5-14500": (1499, "MEDIUM", "i5-14400 ¥1599 相邻档"),
    "Intel Core i5-12600KF": (1099, "LOW", "12 代盒装/散片混合价"),
    "Intel Core i5-13400F": (1049, "LOW", "13400F 较 13400 低约 ¥200"),
    "Intel Core i9-14900F": (3199, "LOW", "14900F 较 14900K 低约 ¥400"),
    "AMD Ryzen 7 7700": (1299, "MEDIUM", "京东盒装 ¥1299"),
    "Intel Core i7-12700KF": (1699, "LOW", "12 代高端清库存价"),
    "Intel Core i5-14600K": (1899, "MEDIUM", "京东 ¥1899"),
    "Intel Core i7-14700KF": (2399, "MEDIUM", "14700K 无核显版"),
    "Intel Core i7-12700": (1599, "LOW", "12 代盒装"),
    "Intel Core i7-14700F": (2099, "LOW", "14700 无核显版"),
    "Intel Core i7-14700K": (2499, "MEDIUM", "京东 ¥2499"),
    "Intel Core i9-14900KF": (3799, "MEDIUM", "14900K ¥3569 无核显邻近档"),
    "Intel Core i7-14700": (2199, "LOW", "14700K 下浮"),
    "Intel Core i9-13900KS": (4299, "LOW", "13900K 特挑版"),
    "AMD Ryzen 9 7950X3D": (3499, "MEDIUM", "7800X3D ¥1891 与 9950X3D ¥4399 之间"),
}

GPU_ANCHORS: dict[str, tuple[int, str, str]] = {
    "GeForce RTX 5050": (3099, "MEDIUM", "ZOL 京东 ¥3099-3399"),
    "GeForce RTX 5060": (3399, "MEDIUM", "11/11 行情 ¥3500-3700"),
    "GeForce RTX 4060": (2399, "HIGH", "ZOL 盈通 8G ¥2399"),
    "Radeon RX 9060 XT 8": (2699, "HIGH", "ZOL 京东 8G ¥2699"),
    "Radeon RX 9060 XT 16": (3599, "HIGH", "ZOL 蓝宝石 NITRO+ 16G ¥3599"),
    "GeForce RTX 5060 Ti 8": (3399, "HIGH", "ZOL 京东 8G ¥3399"),
    "GeForce RTX 5060 Ti 16": (4149, "MEDIUM", "16G ¥4149-4529"),
    "Radeon RX 7800 XT": (3999, "LOW", "上代 16G 档位 ¥3999"),
    "GeForce RTX 4070 Ti SUPER": (6299, "MEDIUM", "4070 Ti ¥6899 下浮"),
    "GeForce RTX 5070": (5299, "MEDIUM", "RTX 5070 主流 ¥5049-5599"),
}

MOTHERBOARD_BANDS: list[tuple[str, int, str]] = [
    ("X870E", 2999, "X870E 高端档"),
    ("X870", 2499, "X870 主流档"),
    ("B860", 1299, "B860 京东 ¥1299"),
    ("B850", 1699, "B850 主流档"),
    ("B840", 1399, "B840 入门档"),
    ("B760", 1199, "B760 档位 ¥1189-1199"),
    ("B650E", 1899, "B650E 高端档"),
    ("B650", 1099, "B650 主流档"),
    ("A620", 799, "A620 入门档"),
    ("H810", 799, "H810 入门档"),
    ("Z890", 2049, "Z890 入门 ¥2049"),
    ("Z790", 1999, "Z790 档位 ¥1999"),
]

# 硬盘兜底：按容量档位，仅在前面的精确型号/接口规则都没命中时使用
STORAGE_CAPACITY_BANDS: list[tuple[int, int, str]] = [
    (20000, 6999, "20TB 以上企业级/监控盘"),
    (12000, 3999, "14TB 大容量盘"),
    (8000, 1999, "8-12TB 大容量盘"),
    (1500, 1299, "1.5-3TB 容量档"),
    (900, 949, "1TB NVMe 档"),
    (0, 269, "480-900GB 容量档"),
]

# 机械盘不能套用 NVMe 容量档：同为 2TB，HDD 与 NVMe 价差可达 4 倍
HDD_CAPACITY_BANDS: list[tuple[int, int, str]] = [
    (16000, 3999, "16TB 以上大容量机械盘"),
    (10000, 1999, "10-16TB 大容量机械盘"),
    (6000, 1099, "6-8TB 机械盘"),
    (3000, 799, "3-4TB 机械盘"),
    (2000, 549, "2TB 机械盘"),
    (1000, 399, "1TB 机械盘"),
    (0, 269, "500GB 机械盘"),
]


def spec_capacity_gb(product_id: str) -> int | None:
    tb = re.search(r"-(\d+(?:-\d+)?)-tb", product_id)
    if tb:
        return round(float(tb.group(1).replace("-", ".")) * 1024)
    gb = re.search(r"-(\d+)-gb", product_id) or re.search(r"-(\d+)gb", product_id)
    return int(gb.group(1)) if gb else None

BANDS: list[tuple[str, str, int, str, str]] = [
    ("MEMORY", "ddr5", 2800, "MEDIUM", "2026 涨价周期 DDR5 32G 约 ¥2300-3800"),
    ("MEMORY", "ddr4", 718, "MEDIUM", "DDR4 32G(16G×2) 套装 ¥718"),
    ("STORAGE", "-1-tb", 949, "HIGH", "金士顿 NV3 1TB 京东 ¥949"),
    ("STORAGE", "-2-tb", 1799, "MEDIUM", "2TB NVMe 涨价后 ¥1759-1859"),
    ("STORAGE", "-500-gb", 549, "MEDIUM", "500GB NVMe ¥549"),
    ("STORAGE", "-512-gb", 549, "MEDIUM", "512GB NVMe ¥549"),
    ("STORAGE", "-4-tb", 3199, "MEDIUM", "4TB SSD 约 ¥3200"),
    ("STORAGE", "-3-tb", 799, "LOW", "机械盘 3TB ¥799"),
    ("STORAGE", "-6-tb", 1099, "LOW", "机械盘 6TB ¥1099"),
    ("STORAGE", "-8-tb", 1399, "LOW", "机械盘 8TB ¥1399"),
    ("PSU", "watt:450-550", 399, "MEDIUM", "550W 金牌 ¥359-499"),
    ("PSU", "watt:600-700", 449, "MEDIUM", "650W 金牌 ¥323-549"),
    ("PSU", "watt:750-850", 549, "MEDIUM", "750/850W 金牌 ¥389-929"),
    ("PSU", "watt:1000+", 799, "MEDIUM", "1000W 金牌 ¥549-799"),
    ("COOLER", "cooling:air", 219, "MEDIUM", "双塔风冷 ¥162-299"),
    ("COOLER", "cooling:water-120", 269, "LOW", "120 水冷 ¥269"),
    ("COOLER", "cooling:water-240", 349, "MEDIUM", "240 水冷 ¥279-490"),
    ("COOLER", "cooling:water-280", 449, "LOW", "280 水冷 ¥449"),
    ("COOLER", "cooling:water-360", 399, "MEDIUM", "360 水冷 ¥285-669"),
    ("COOLER", "cooling:water-420", 899, "LOW", "420 水冷 ¥899"),
    ("CASE", "form:MicroATX Mini Tower", 219, "MEDIUM", "mATX 小机箱 ¥199-219"),
    ("CASE", "form:MicroATX Mid Tower", 239, "MEDIUM", "mATX 中塔 ¥199-239"),
    ("CASE", "form:ATX Mid Tower", 599, "MEDIUM", "ATX 中塔 ¥499-899"),
    ("CASE", "form:Mini ITX", 649, "LOW", "ITX 机箱 ¥139-649"),
    ("CASE", "form:ATX Full Tower", 999, "LOW", "全塔 ¥949-1299"),
]

# 内存套装必须按容量分档：原实现把 DDR5 全线按 ¥2800、DDR4 全线按 ¥718 一刀切，
# 既把 96GB/128GB 套装低估数倍，也把 8GB 单条高估一倍以上
DDR5_CAPACITY_BANDS: list[tuple[int, int, str, str]] = [
    (128, 14999, "LOW", "128GB DDR5 套装无国行单品页，按 96GB 实测 ¥9979 上浮估，仅供预算上限参考"),
    (96, 9979, "MEDIUM", "96GB DDR5 套装 京东实测 ¥9979（芝奇皇家戟 DDR5-6400）"),
    (64, 7999, "MEDIUM", "64GB DDR5 套装 京东实测 ¥4399-8999"),
    (48, 5500, "MEDIUM", "48GB DDR5 套装 京东实测 ¥5459-6279"),
]

# DDR4 已无电商单品链接可查，取值来自 ZOL 参考价与淘宝/京东现价的交叉核对
DDR4_CAPACITY_BANDS: list[tuple[int, int, str, str]] = [
    (128, 6600, "LOW", "128GB DDR4 套装 ZOL 参考价 ¥6666（皇家戟 4×32GB）"),
    (64, 2800, "LOW", "64GB DDR4 套装 ZOL 参考价 ¥2699-2890"),
    (32, 1300, "MEDIUM", "32GB DDR4 套装 ZOL 参考价 ¥1199-1620，淘宝 16G×2 现价约 ¥1000"),
    (16, 750, "MEDIUM", "16GB DDR4 套装 ZOL 参考价 ¥699-799，英睿达 2×8 京东 ¥569"),
    (0, 280, "MEDIUM", "8GB DDR4 单条 京东约 ¥229-306"),
]


GPU_BANDS: list[tuple[str, int, str, str]] = [
    ("vram:16+", 4599, "LOW", "16G 及以上显卡 2026 主流档 ¥4200-5200"),
    ("vram:12", 3299, "LOW", "12G 显卡 ¥3000-3600"),
    ("vram:8", 2699, "LOW", "8G 显卡 ¥2400-3000"),
]


def gpu_anchor_key(row: dict) -> str | None:
    name = row["display_name"]
    model = name.split("(")[-1].rstrip(")") if "(" in name else name
    vram = "16" if "16gb" in row["product_id"] else "8"
    if model == "Radeon RX 9060 XT":
        return f"{model} {vram}"
    if model == "GeForce RTX 5060 Ti":
        return f"{model} {vram}"
    return model


def ddr5_band(product_id: str) -> tuple[int, str, str] | None:
    """返回 DDR5 套装的兜底价与置信度。

    48GB 以上以容量为主（频率对整机预算的影响小于容量）；32GB 以下再按频率分档，
    否则 7000/8000 高频条会和 6000 普通条同价，被低估近一倍。
    """

    capacity = spec_capacity_gb(product_id)
    if capacity is None:
        return None
    if capacity >= 48:
        for threshold, band_price, band_confidence, band_note in DDR5_CAPACITY_BANDS:
            if capacity >= threshold:
                return band_price, band_confidence, band_note
        return None
    # 16GB 单条/双条与 32GB 套装不是一个价位，不能被 32GB 基准价抬高
    if capacity < 32:
        return 2000, "MEDIUM", "16GB DDR5 京东实测 ¥1974-2039"
    freq_match = re.search(r"-ddr5-(\d{4})-", product_id)
    speed = int(freq_match.group(1)) if freq_match else 0
    if speed >= 8000:
        return 5400, "LOW", "32GB DDR5-8000 无同规格实测，取 7600 的 ¥4879 与 8000 48GB 的 ¥6279 之间"
    if speed >= 7200:
        return 4900, "MEDIUM", "32GB DDR5-7200~7600 京东实测 ¥4579-4879"
    if speed >= 6800:
        return 4300, "MEDIUM", "32GB DDR5-6800 京东实测 ¥4099"
    return None


def main() -> int:
    rows = [json.loads(line) for line in SHORTLIST.read_text(encoding="utf-8").splitlines() if line.strip()]
    applied = 0
    for row in rows:
        if row["price_status"] == "OBSERVED_2026-11-11":
            continue
        # 降级为 ESTIMATED 的 WEBSEARCH 记录仍是「搜到的市场价」，优先于本地档位表，
        # 否则会被 BANDS 里更粗的档位价覆盖（如显卡区间价被 8G 通用档拉低）
        if row.get("price_source") == "WEBSEARCH":
            continue
        # 估价是派生的，必须每轮重算：候选池里可能残留上一版权重的 ESTIMATED 值与旧说明
        if is_excluded(row):
            continue
        price = confidence = note = None
        if row["category"] == "CPU":
            hit = CPU_ANCHORS.get(row["display_name"])
            if hit:
                price, confidence, note = hit
        elif row["category"] == "GPU":
            key = gpu_anchor_key(row)
            hit = GPU_ANCHORS.get(key) if key else None
            if hit:
                price, confidence, note = hit
            elif "4060 Ti" in row["display_name"]:
                price, confidence, note = 3599, "MEDIUM", "4060 Ti 16G 较 8G 高约 ¥300"
            if price is None:
                # 老架构或未收录型号：按显存分层兜底，避免整份目录出现无价条目
                for token, band_price, band_confidence, band_note in GPU_BANDS:
                    if row["stratum"] == token:
                        price, confidence, note = band_price, band_confidence, band_note
                        break
        else:
            if row["category"] == "MEMORY" and "-ddr5-" in row["product_id"]:
                hit = ddr5_band(row["product_id"])
                if hit:
                    price, confidence, note = hit
            if price is None and row["category"] == "MEMORY" and "-ddr4-" in row["product_id"]:
                capacity = spec_capacity_gb(row["product_id"])
                for threshold, band_price, band_confidence, band_note in DDR4_CAPACITY_BANDS:
                    if capacity and capacity >= threshold:
                        price, confidence, note = band_price, band_confidence, band_note
                        break
            if price is None and row["category"] == "STORAGE" and row["stratum"] == "media:HDD":
                capacity = spec_capacity_gb(row["product_id"])
                for threshold, band_price, band_note in HDD_CAPACITY_BANDS:
                    if capacity and capacity >= threshold:
                        price, confidence, note = band_price, "LOW", band_note
                        break
            if price is None:
                for category, token, band_price, band_confidence, band_note in BANDS:
                    if row["category"] != category:
                        continue
                    is_hit = (
                        row["stratum"].startswith(token)
                        if token.startswith(("form:", "watt:", "cooling:"))
                        else token in row["product_id"]
                    )
                    if is_hit:
                        price, confidence, note = band_price, band_confidence, band_note
                        break
            if price is None and row["category"] == "MOTHERBOARD":
                for chip, chip_price, chip_note in MOTHERBOARD_BANDS:
                    if chip in row["product_id"].upper():
                        price, confidence, note = chip_price, "MEDIUM", chip_note
                        break
            if price is None and row["category"] == "STORAGE":
                capacity = spec_capacity_gb(row["product_id"])
                if capacity:
                    for threshold, cap_price, cap_note in STORAGE_CAPACITY_BANDS:
                        if capacity >= threshold:
                            price, confidence, note = cap_price, "LOW", cap_note
                            break
        if price is None:
            continue
        row["price_cny"] = price
        row["price_source"] = "MODEL_ANCHOR" if row["category"] in {"CPU", "GPU"} else "SPEC_BAND"
        row["price_status"] = "ESTIMATED_2026-11-11"
        row["price_confidence"] = confidence
        row["price_source_url"] = SOURCE
        row["price_note"] = note
        applied += 1

    with SHORTLIST.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    provisional_ids = [row["product_id"] for row in rows if row["price_status"] == "PROVISIONAL"]
    report = {
        "applied": applied,
        "still_provisional": len(provisional_ids),
        "still_provisional_ids": provisional_ids,
        "total": len(rows),
        "price_status": dict(Counter(row["price_status"] for row in rows)),
        "confidence": dict(Counter(row.get("price_confidence", "NONE") for row in rows)),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
