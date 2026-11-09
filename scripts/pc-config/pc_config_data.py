"""PC 配置数据准备的共享工具。

职责：读取 PCPartPicker / PassMark CSV，归一化原始规格字符串，生成硬件 ID。
只被 scripts/pc-config 下的脚本与测试使用，不参与运行时服务。
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "application-service" / "src" / "main" / "resources" / "pc-config"
DEFAULT_SHORTLIST_DOC = REPO_ROOT / "docs" / "pc-config" / "candidate-shortlist.md"

# 配置类别使用服务端统一命名；data_table 对应 PCPartPicker 分类 CSV。
CATEGORY_TABLES: dict[str, str] = {
    "CPU": "pcpp_cpu",
    "GPU": "pcpp_gpu",
    "MOTHERBOARD": "pcpp_motherboard",
    "MEMORY": "pcpp_memory",
    "STORAGE": "pcpp_storage",
    "COOLER": "pcpp_cooler",
    "CASE": "pcpp_case",
    "PSU": "pcpp_psu",
}

CATEGORY_ORDER: tuple[str, ...] = (
    "CPU",
    "GPU",
    "MOTHERBOARD",
    "MEMORY",
    "STORAGE",
    "COOLER",
    "CASE",
    "PSU",
)

NUMBER_PATTERN = re.compile(r"(\d+(?:\.\d+)?)")
SPEED_PATTERN = re.compile(r"DDR\d-(\d+)")
CAPACITY_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(TB|GB)", re.IGNORECASE)
MODULES_PATTERN = re.compile(r"(\d+)\s*x\s*(\d+)\s*GB", re.IGNORECASE)
EXTERNAL_POWER_PATTERN = re.compile(r"(\d+)\s*x\s*(.+)")


@dataclass(frozen=True)
class SelectedItem:
    """候选清单中的一条记录，保留原始行以便追溯。"""

    category: str
    row: dict[str, str]
    reason: str


def read_csv_rows(data_dir: Path, table: str) -> list[dict[str, str]]:
    """读取带 BOM 的 CSV，返回原始字符串行。"""

    csv_path = data_dir / "csv" / f"{table}.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"缺少数据文件：{csv_path}")
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def split_multiline(value: str | None) -> list[str]:
    """把换行分隔的多值规格拆成去空白后的列表。"""

    if not value:
        return []
    return [part.strip() for part in value.splitlines() if part.strip()]


def parse_number(value: str | None) -> float | None:
    """提取字符串中的第一个数字，无法解析返回 None。"""

    if value is None:
        return None
    match = NUMBER_PATTERN.search(value)
    return float(match.group(1)) if match else None


def parse_watts(value: str | None) -> int | None:
    """解析功耗，如 `120 W` → 120。"""

    number = parse_number(value)
    return int(round(number)) if number is not None else None


def parse_millimetres(value: str | None) -> int | None:
    """解析长度，多行值只取第一段，如 `392 mm\\n15.433"` → 392。"""

    if not value:
        return None
    first_segment = split_multiline(value)[0] if split_multiline(value) else value
    number = parse_number(first_segment)
    return int(round(number)) if number is not None else None


def parse_capacity_gb(value: str | None) -> int | None:
    """把 `2 TB` / `16 GB` 统一为 GB 整数。"""

    if not value:
        return None
    match = CAPACITY_PATTERN.search(value)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).upper()
    return int(round(amount * 1024)) if unit == "TB" else int(round(amount))


def parse_speed_mts(value: str | None) -> int | None:
    """解析内存频率，如 `DDR5-6000` → 6000。"""

    if not value:
        return None
    match = SPEED_PATTERN.search(value)
    return int(match.group(1)) if match else None


def parse_max_memory_speed(value: str | None) -> int | None:
    """主板 memory_speed 是多行列表，取支持的最高频率。"""

    speeds = [parse_speed_mts(item) for item in split_multiline(value)]
    known = [speed for speed in speeds if speed is not None]
    return max(known) if known else None


def parse_module_layout(value: str | None) -> tuple[int | None, int | None]:
    """解析内存条数，如 `2 x 16GB` → (2, 16)。"""

    if not value:
        return None, None
    match = MODULES_PATTERN.search(value)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def parse_m2_slot_count(value: str | None) -> int | None:
    """统计主板 M.2 插槽，只计 M-key 的可安装 NVMe 插槽。"""

    keys = [item for item in split_multiline(value) if "m-key" in item.lower()]
    return len(keys) if keys else None


def parse_supported_sockets(value: str | None) -> list[str]:
    """散热器插槽是多行列表，返回去重后的插槽集合。"""

    seen: list[str] = []
    for socket in split_multiline(value):
        if socket not in seen:
            seen.append(socket)
    return seen


def parse_case_form_factors(value: str | None) -> list[str]:
    """机箱支持的板型，原始值是带缩进的多行文本。"""

    return [item for item in split_multiline(value) if len(item) <= 20]


def parse_external_power(value: str | None) -> dict[str, Any] | None:
    """解析显卡外接供电，如 `3 x PCIe 8-pin`。"""

    if not value:
        return None
    match = EXTERNAL_POWER_PATTERN.search(value.strip())
    if not match:
        return None
    count = int(match.group(1))
    connector = match.group(2).strip()
    connector_type = "PCIE_12VHPWR" if "12VHPWR" in connector.upper() else "PCIE_8PIN"
    return {"connector_type": connector_type, "count": count}


def slugify(value: str) -> str:
    """生成稳定、可读的硬件 ID 片段。"""

    lowered = value.lower().replace("+", " plus ")
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def build_hardware_id(category: str, model_name: str) -> str:
    return f"{category.lower()}-{slugify(model_name)}"


def clean_model_name(name: str, suffixes: Iterable[str]) -> str:
    """去掉商品名末尾的通用后缀，得到标准型号。"""

    result = name.strip()
    for suffix in suffixes:
        if result.endswith(suffix):
            result = result[: -len(suffix)].strip()
    return result


def dedupe_by_name(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    """同名商品可能来自不同列表页，保留参考价最低的一行。"""

    kept: dict[str, dict[str, str]] = {}
    duplicates = 0
    for row in rows:
        key = row["name"].strip()
        existing = kept.get(key)
        if existing is None:
            kept[key] = row
            continue
        duplicates += 1
        if _price(existing) > _price(row):
            kept[key] = row
    return list(kept.values()), duplicates


def _price(row: dict[str, str]) -> float:
    value = parse_number(row.get("price"))
    return value if value is not None else float("inf")


def normalize_name_for_match(value: str) -> str:
    """用于跨数据源比较的名称归一化：小写、去标点、压缩空白。"""

    lowered = value.lower().replace("&", " and ")
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def normalize_cpu_name(name: str) -> str:
    """把 PCPP CPU 长名裁成标准型号，供 PassMark 精确匹配。"""

    result = name.strip()
    result = re.sub(r"\s+\d+(?:\.\d+)?\s*GHz\b.*$", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\s+(OEM/Tray|Processor)\b.*$", "", result, flags=re.IGNORECASE)
    return result.strip()


def normalize_gpu_name(chipset: str, vram_gb: int | None) -> str:
    result = chipset.strip()
    if vram_gb:
        result = f"{result} {vram_gb}GB"
    return result.strip()
