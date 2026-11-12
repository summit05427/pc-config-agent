"""Stage 1/2 数据审计与清洗的公共函数。

本模块只读取 PCPartPicker 原始 CSV，不读取任何跑分文件：
跑分属于 Stage 4 的性能评分，不能参与清洗、去重或质量判定。
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = Path("F:/LLM_PC_Agent/Hardware data/csv/pcpp_hardware_all.csv")
OUTPUT_DIR = REPO_ROOT / "data" / "pc-config" / "cleaning"
RULES_VERSION = "stage2-clean-1.0.0"

CATEGORY_MAP = {
    "CPU": "CPU",
    "GPU": "GPU",
    "MOTHERBOARD": "MOTHERBOARD",
    "RAM": "MEMORY",
    "SSD": "STORAGE",
    "PSU": "PSU",
    "CASE": "CASE",
    "COOLER": "COOLER",
}

# 每个品类继续推荐所需的关键兼容性字段；缺失即 INCOMPLETE，不做猜测。
REQUIRED_FIELDS = {
    "CPU": ("socket", "core_count", "tdp_w"),
    "GPU": ("chipset", "vram_gb", "tdp_w", "length_mm"),
    "MOTHERBOARD": ("socket", "chipset", "memory_type", "form_factor"),
    "MEMORY": ("memory_type", "capacity_gb", "speed_mhz"),
    "STORAGE": ("capacity_gb", "interface", "form_factor", "media_type"),
    "PSU": ("rated_power_w", "efficiency"),
    "CASE": ("supported_form_factors", "gpu_clearance_mm"),
    "COOLER": ("sockets",),
}

# 去重时必须保留的区分字段：同一型号不同规格不能被合并。
DISCRIMINATORS = {
    "CPU": ("socket", "core_count", "thread_count", "packaging"),
    "GPU": ("chipset", "vram_gb", "memory_type", "length_mm"),
    "MOTHERBOARD": ("socket", "chipset", "memory_type", "form_factor", "m2_slot_count"),
    "MEMORY": ("memory_type", "capacity_gb", "module_count", "speed_mhz", "cas_latency"),
    "STORAGE": ("capacity_gb", "interface", "form_factor", "media_type"),
    "PSU": ("rated_power_w", "efficiency", "modular", "length_mm"),
    "CASE": ("case_type", "color", "gpu_clearance_mm"),
    "COOLER": ("water_cooled", "height_mm", "radiator_size_mm"),
}

BRAND_ALIASES = {
    "g.skill": "G.SKILL",
    "teamgroup": "Team Group",
    "westerndigital": "Western Digital",
    "western digital": "Western Digital",
    "asrock": "ASRock",
    "seasonic": "Seasonic",
    "cooler master": "Cooler Master",
}


def load_rows(path: Path = DEFAULT_CSV) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"原始数据不存在：{path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def split_values(value: Any) -> list[str]:
    """把 PCPartPicker 的多值字段拆成去重列表（换行分隔，附带缩进）。"""

    if value is None:
        return []
    text = str(value).replace("\r", "\n")
    items = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n+", text)]
    seen: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.append(item)
    return seen


def first_value(value: Any) -> str | None:
    values = split_values(value)
    return values[0] if values else None


def canon(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", str(text)).strip().lower()
    return re.sub(r"[^a-z0-9]+", "", normalized)


def normalize_brand(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return BRAND_ALIASES.get(text.lower(), text)


def normalize_model(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return re.sub(r"\s*\((?:[^)]*)\)\s*$", "", text)


def normalize_socket(value: str | None) -> str | None:
    text = first_value(value)
    if not text:
        return None
    text = re.sub(r"^socket\s+", "", text, flags=re.IGNORECASE)
    return text.upper().replace(" ", "")


def parse_number(value: Any, pattern: str = r"-?\d+(?:\.\d+)?") -> float | None:
    text = first_value(value)
    if not text:
        return None
    match = re.search(pattern, text.replace(",", ""))
    return float(match.group(1) if match.groups() else match.group()) if match else None


def parse_capacity_gb(value: Any) -> float | None:
    text = first_value(value)
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(TB|GB)", text, re.IGNORECASE)
    if not match:
        return None
    size = float(match.group(1))
    return size * 1024 if match.group(2).upper() == "TB" else size


def parse_clock_mhz(value: Any) -> int | None:
    text = first_value(value)
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(GHz|MHz)", text, re.IGNORECASE)
    if not match:
        return None
    clock = float(match.group(1))
    return int(round(clock * 1000)) if match.group(2).lower() == "ghz" else int(round(clock))


def parse_memory_type(value: Any) -> str | None:
    text = first_value(value)
    if not text:
        return None
    match = re.search(r"(DDR\d|LPDDR\d)", text, re.IGNORECASE)
    return match.group(1).upper() if match else None


def parse_modules(value: Any) -> tuple[int | None, float | None]:
    text = first_value(value)
    if not text:
        return None, None
    match = re.search(r"(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*(TB|GB)", text, re.IGNORECASE)
    if not match:
        total = parse_capacity_gb(text)
        return (1 if total else None), total
    count = int(match.group(1))
    size = float(match.group(2))
    if match.group(3).upper() == "TB":
        size *= 1024
    return count, count * size


def parse_height_mm(value: Any) -> float | None:
    return parse_number(value, r"(\d+(?:\.\d+)?)\s*mm")


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def quality_of(category: str, specs: dict[str, Any]) -> tuple[str, list[str]]:
    """按 Stage 2 的质量分级给单条记录定性，不参考跑分。"""

    reasons: list[str] = []
    for field in REQUIRED_FIELDS[category]:
        value = specs.get(field)
        if value in (None, "", []):
            reasons.append(f"MISSING_{field.upper()}")
    if specs.get("anomalies"):
        reasons.extend(specs["anomalies"])
        return "ANOMALOUS", reasons
    if any(reason.startswith("MISSING_") for reason in reasons):
        return "INCOMPLETE", reasons
    return "GOOD", []


def line(value: Any) -> str:
    return "" if value is None else str(value)
