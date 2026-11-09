"""为电商检索生成中英检索键。

只做命名映射：品牌与系列走受控词典，型号数字与字母保持原文。未登记品牌直接
沿用英文原名，不机器翻译、不生成电商不存在的译名——「不猜测」同样适用于命名。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from normalize_specs import derive_model_name

REFERENCE_DIR = Path(__file__).resolve().parent / "reference"
BRAND_DICT_PATH = REFERENCE_DIR / "brand-zh.json"
SERIES_DICT_PATH = REFERENCE_DIR / "series-zh.json"

# 京东/淘宝标题里这些前缀通常省略，保留会让检索串变长
GPU_PREFIXES: tuple[str, ...] = ("geforce ", "radeon ")


def normalize_key(value: str) -> str:
    """品牌名归一化：忽略大小写、空格与标点，如 `G.Skill` → `gskill`。"""

    return re.sub(r"[^a-z0-9]", "", value.lower())


def load_brand_map(path: Path = BRAND_DICT_PATH) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["brands"]


def load_series_rules(path: Path = SERIES_DICT_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["rules"]


def brand_display(brand: str, brand_map: dict[str, str]) -> str:
    """命中词典返回中文名，否则原样返回英文，保证检索链不中断。"""

    return brand_map.get(normalize_key(brand), brand.strip())


def strip_brand(model_name: str, brand: str) -> str:
    """去掉型号名开头的品牌，避免中文串里出现两次品牌。"""

    if not brand:
        return model_name.strip()
    pattern = re.compile(rf"^{re.escape(brand)}\s+", re.IGNORECASE)
    return pattern.sub("", model_name).strip()


def localize_series(text: str, category: str, rules: list[dict[str, Any]]) -> str:
    """按类别替换系列名，只做整词匹配，避免误改型号中的字母。"""

    result = text
    for rule in rules:
        if category not in rule["categories"]:
            continue
        result = re.sub(
            rf"\b{re.escape(rule['pattern'])}\b", rule["zh"], result, flags=re.IGNORECASE
        )
    return result


def gpu_short_name(chipset: str, vram_gb: int | None) -> str:
    """GPU 短检索名：去掉 GeForce/Radeon 前缀，保留 RTX/RX 与显存。"""

    lowered = chipset.lower()
    for prefix in GPU_PREFIXES:
        if lowered.startswith(prefix):
            chipset = chipset[len(prefix):]
            break
    return f"{chipset} {vram_gb}GB" if vram_gb else chipset


def short_core(record: dict[str, Any]) -> str:
    """短检索核心：去品牌、去 GeForce/Radeon 前缀，用于品牌+型号的精确检索。"""

    if record["category"] == "GPU":
        specs = record.get("specifications") or {}
        chipset = specs.get("chipset") or record["model_name"]
        return gpu_short_name(chipset, specs.get("vram_gb"))

    return strip_brand(record["model_name"], record["brand"]) or record["model_name"].strip()


def model_core(record: dict[str, Any]) -> str:
    """纯型号检索键：只剩一个词时保留全名，避免 `Bolt` 这类过短串淹没结果。"""

    core = short_core(record)
    return record["model_name"].strip() if len(core.split()) <= 1 else core


def full_core(record: dict[str, Any]) -> str:
    """完整型号串（保留板卡系列）：GPU 取原始商品名，其余复用标准型号推导。"""

    raw = record.get("raw_specs") or {}
    if record["category"] == "GPU":
        name = raw.get("name") or record["model_name"]
        core = strip_brand(name, record["brand"])
        return re.sub(r"\s+Video Card$", "", core, flags=re.IGNORECASE).strip()

    if not raw.get("name"):
        return record["model_name"].strip()
    # derive_model_name 会保留品牌，这里统一剥离，避免中文串里出现两次品牌
    derived = derive_model_name(record["category"], raw)
    return strip_brand(derived, record["brand"]) or derived


def build_search_queries(
    record: dict[str, Any],
    brand_map: dict[str, str] | None = None,
    rules: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """返回四级检索键，调用方按 zh → zh_short → model → en 的顺序降级。"""

    brand_map = brand_map if brand_map is not None else load_brand_map()
    rules = rules if rules is not None else load_series_rules()

    brand = brand_display(record["brand"], brand_map)
    core = model_core(record)
    short = short_core(record)
    full = full_core(record) or short

    english = record["model_name"].strip()
    if normalize_key(record["brand"]) not in normalize_key(english):
        english = f"{record['brand'].strip()} {english}".strip()

    return {
        "zh": f"{brand} {localize_series(full, record['category'], rules)}".strip(),
        "zh_short": f"{brand} {localize_series(short, record['category'], rules)}".strip(),
        "model": core,
        "en": english,
    }
