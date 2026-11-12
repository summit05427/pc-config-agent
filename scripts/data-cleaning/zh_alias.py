"""中文检索别名：只翻译已核验的品牌与系列，型号数字字母保持原文。"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

REFERENCE_DIR = Path(__file__).resolve().parents[1] / "pc-config" / "reference"


def _key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


@lru_cache(maxsize=1)
def load_brands() -> dict[str, str]:
    payload = json.loads((REFERENCE_DIR / "brand-zh.json").read_text(encoding="utf-8"))
    return {_key(name): zh for name, zh in payload["brands"].items()}


@lru_cache(maxsize=1)
def load_series_rules() -> list[dict[str, Any]]:
    payload = json.loads((REFERENCE_DIR / "series-zh.json").read_text(encoding="utf-8"))
    rules = payload["rules"]
    # 长模式优先，避免 "gaming trio" 被更短的规则抢先替换。
    return sorted(rules, key=lambda rule: len(rule["pattern"]), reverse=True)


def brand_zh(brand: str | None) -> str:
    text = (brand or "").strip()
    return load_brands().get(_key(text), text)


def model_zh(category: str, model_name: str | None) -> str:
    text = (model_name or "").strip()
    for rule in load_series_rules():
        if category not in rule["categories"]:
            continue
        pattern = r"(?<![A-Za-z0-9])" + re.escape(rule["pattern"]) + r"(?![A-Za-z0-9])"
        text = re.sub(pattern, rule["zh"], text, flags=re.IGNORECASE)
    return text


def search_name_zh(product: dict[str, Any]) -> str:
    raw_brand = (product.get("brand") or "").strip()
    zh_brand = brand_zh(raw_brand)
    model = model_zh(product.get("category", ""), product.get("model_name"))
    # 型号里常重复英文品牌（如 "Corsair 2500D"），先去重再拼中文品牌。
    if raw_brand and model.lower().startswith(raw_brand.lower()):
        model = model[len(raw_brand):].strip()
    if model.lower().startswith(zh_brand.lower()):
        return model
    return f"{zh_brand} {model}".strip()
