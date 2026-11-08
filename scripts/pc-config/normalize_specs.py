"""Stage 1.2 / 1.5：把候选原始行归一化为 Java 侧可消费的 catalog.json。

原则：只做字段解析与状态标注，不补造缺失值；无法确认的字段写 null 并记录原因。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pc_config_data import (
    DEFAULT_OUTPUT_DIR,
    CATEGORY_TABLES,
    SelectedItem,
    build_hardware_id,
    clean_model_name,
    normalize_cpu_name,
    parse_capacity_gb,
    parse_external_power,
    parse_max_memory_speed,
    parse_m2_slot_count,
    parse_millimetres,
    parse_module_layout,
    parse_number,
    parse_speed_mts,
    parse_supported_sockets,
    parse_watts,
    split_multiline,
)
from select_candidates import load_selection, resolve_data_dir

SCHEMA_VERSION = "1.0.0"

MODEL_PATTERNS: dict[str, tuple[str, ...]] = {
    "MOTHERBOARD": (r"\s+(?:ATX|Micro ATX|Mini ITX|EATX)\s+(?:AM5|AM4|LGA1851|LGA1700)$",),
    "STORAGE": (r"\s+M\.2-\d{4}.*$",),
    "COOLER": (r"\s+\d+(?:\.\d+)?\s+CFM.*$", r"\s+Liquid$"),
    "CASE": (r"\s+(?:ATX|Micro ATX|Mini ITX|EATX)(?:\s+\w+)?\s+Tower$",),
    "PSU": (r"\s+\d+\s+W\s+.*$",),
}

# 参与求解的必需字段；缺失即 BLOCKED，不允许进入推荐。
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "CPU": ("socket", "core_count", "thread_count", "tdp_w"),
    "GPU": ("vram_gb", "tdp_w", "length_mm", "external_power"),
    "MOTHERBOARD": ("socket", "form_factor", "memory_type", "memory_slots",
                    "max_memory_speed_mts", "m2_slot_count"),
    "MEMORY": ("memory_type", "capacity_gb", "module_count", "speed_mts"),
    "STORAGE": ("capacity_gb", "interface", "form_factor"),
    "COOLER": ("cooler_type", "supported_sockets"),
    "CASE": ("supported_mainboard_form_factors", "max_gpu_length_mm"),
    "PSU": ("wattage_w", "pcie_8pin_count"),
}


def _int_or_none(value: str | None) -> int | None:
    number = parse_number(value)
    return int(round(number)) if number is not None else None


def _yes_no(value: str | None) -> bool | None:
    if value is None or not value.strip():
        return None
    return value.strip().lower() in {"yes", "true", "1"}


def _memory_type_from_speed(speed: str | None) -> str | None:
    if not speed:
        return None
    for token in split_multiline(speed):
        if "DDR5" in token.upper():
            return "DDR5"
        if "DDR4" in token.upper():
            return "DDR4"
    return None


def normalize_cpu(row: dict[str, str]) -> dict[str, Any]:
    return {
        "socket": row["socket"].strip() or None,
        "platform": row["socket"].strip() or None,
        "core_count": _int_or_none(row.get("core_count")),
        "thread_count": _int_or_none(row.get("thread_count")),
        "tdp_w": parse_watts(row.get("tdp")),
        "integrated_graphics": row.get("integrated_graphics", "").strip() or None,
        "includes_cooler": _yes_no(row.get("includes_cooler")),
        "max_memory": row.get("maximum_supported_memory", "").strip() or None,
    }


def normalize_gpu(row: dict[str, str]) -> dict[str, Any]:
    return {
        "chipset": row["chipset"].strip() or None,
        "vram_gb": parse_capacity_gb(row.get("memory")),
        "memory_type": row.get("memory_type", "").strip() or None,
        "tdp_w": parse_watts(row.get("tdp")),
        "length_mm": parse_millimetres(row.get("length")),
        "slot_width": _int_or_none(row.get("total_slot_width")),
        "external_power": parse_external_power(row.get("external_power")),
    }


def normalize_motherboard(row: dict[str, str]) -> dict[str, Any]:
    return {
        "socket": row["socket_cpu"].strip() or None,
        "platform": row["socket_cpu"].strip() or None,
        "form_factor": row.get("form_factor", "").strip() or None,
        "chipset": row.get("chipset", "").strip() or None,
        "memory_type": row.get("memory_type", "").strip() or None,
        "memory_slots": _int_or_none(row.get("memory_slots")),
        "max_memory_speed_mts": parse_max_memory_speed(row.get("memory_speed")),
        "m2_slot_count": parse_m2_slot_count(row.get("m_2_slots")),
        "sata_ports": _int_or_none(row.get("sata_6_0_gb_s_ports")),
        "pcie_x16_slots": _int_or_none(row.get("pcie_x16_slots")),
    }


def normalize_memory(row: dict[str, str]) -> dict[str, Any]:
    module_count, module_size = parse_module_layout(row.get("modules"))
    capacity = (
        module_count * module_size
        if module_count and module_size
        else parse_capacity_gb(row.get("name"))
    )
    form_factor = row.get("form_factor", "")
    return {
        "memory_type": _memory_type_from_speed(row.get("speed")),
        "capacity_gb": capacity,
        "module_count": module_count,
        "module_size_gb": module_size,
        "speed_mts": parse_speed_mts(row.get("speed")),
        "form_factor": "SODIMM" if "SODIMM" in form_factor.upper() else "DIMM",
        "cas_latency": _int_or_none(row.get("cas_latency")),
    }


def normalize_storage(row: dict[str, str]) -> dict[str, Any]:
    return {
        "capacity_gb": parse_capacity_gb(row.get("capacity")) or parse_capacity_gb(row.get("name")),
        "interface": row.get("interface", "").strip() or None,
        "form_factor": row.get("form_factor", "").strip() or None,
        "nvme": _yes_no(row.get("nvme")),
    }


def normalize_cooler(row: dict[str, str]) -> dict[str, Any]:
    height = parse_millimetres(row.get("height"))
    name = row.get("name", "")
    radiator = None
    for size in (240, 280, 360, 420):
        if f" {size} " in f" {name} ":
            radiator = size
            break
    return {
        "cooler_type": "LIQUID" if radiator or "liquid" in name.lower() else "AIR",
        "height_mm": height,
        "radiator_size_mm": radiator,
        "supported_sockets": parse_supported_sockets(row.get("cpu_socket")),
        "fanless": _yes_no(row.get("fanless")),
    }


def normalize_case(row: dict[str, str]) -> dict[str, Any]:
    psu_form_factor = row.get("power_supply", "").strip()
    if psu_form_factor.lower() in {"", "none"}:
        psu_form_factor = ""
    radiator_support = " / ".join(split_multiline(row.get("radiator_support")))
    return {
        "supported_mainboard_form_factors": parse_case_form_factors(row.get("motherboard_form_factor")),
        "max_gpu_length_mm": parse_millimetres(row.get("maximum_video_card_length")),
        # 机箱 CSV 没有最大散热器高度字段，按 UNKNOWN 处理，不猜测数值。
        "max_cooler_height_mm": None,
        "psu_form_factor": psu_form_factor or None,
        "radiator_support": radiator_support or None,
        "expansion_slots": _int_or_none(row.get("expansion_slots")),
    }


def parse_case_form_factors(value: str | None) -> list[str]:
    """机箱板型是多行缩进文本，过滤掉纯缩进产生的碎片。"""

    result: list[str] = []
    for item in split_multiline(value):
        normalized = item.replace("\t", " ").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    # 原始值中夹带的换行缩进会产生超长残片，这里只保留白名单板型。
    allowed = {"ATX", "Micro ATX", "Mini ITX", "EATX", "XL ATX"}
    return [item for item in result if item in allowed]


def normalize_psu(row: dict[str, str]) -> dict[str, Any]:
    name = row.get("name", "").upper()
    form_factor = "SFX" if " SFX " in f" {name} " else "ATX"
    return {
        "wattage_w": parse_watts(row.get("wattage")),
        "efficiency": row.get("efficiency_rating", "").strip() or None,
        "modular": row.get("modular", "").strip() or None,
        "form_factor": form_factor,
        "pcie_8pin_count": _int_or_none(row.get("pcie_6_2_pin_connectors")) or 0,
        "pcie_12vhpwr_count": _int_or_none(
            row.get("pcie_16_pin_12_vhpwr_12_v_2x6_connectors")
        ) or 0,
        "length_mm": parse_millimetres(row.get("length")),
        "sata_connectors": _int_or_none(row.get("sata_connectors")),
    }


NORMALIZERS = {
    "CPU": normalize_cpu,
    "GPU": normalize_gpu,
    "MOTHERBOARD": normalize_motherboard,
    "MEMORY": normalize_memory,
    "STORAGE": normalize_storage,
    "COOLER": normalize_cooler,
    "CASE": normalize_case,
    "PSU": normalize_psu,
}


def evaluate_quality(category: str, specifications: dict[str, Any]) -> tuple[str, str, list[str]]:
    """返回 (data_quality_status, recommendation_status, unverified_fields)。"""

    missing = [field for field in REQUIRED_FIELDS[category] if specifications.get(field) in (None, "", [])]
    unverified: list[str] = []
    if category == "CASE" and specifications.get("max_cooler_height_mm") is None:
        unverified.append("max_cooler_height_mm")
    if missing:
        return "BLOCKED", "BLOCKED", sorted(set(missing + unverified))
    if unverified:
        return "PARTIAL", "ELIGIBLE", unverified
    return "VERIFIED_STRUCTURED", "ELIGIBLE", unverified


def derive_model_name(category: str, row: dict[str, str]) -> str:
    """从商品名推导标准型号；型号里不保留频率、板型、供电等规格碎片。"""

    display = row["name"].strip()
    if category == "CPU":
        return normalize_cpu_name(display)
    if category == "GPU":
        chipset = row.get("chipset", "").strip() or display
        vram_gb = parse_capacity_gb(row.get("memory"))
        return f"{chipset} {vram_gb}GB" if vram_gb else chipset

    suffix = {
        "MOTHERBOARD": " Motherboard",
        "MEMORY": " Memory",
        "STORAGE": " Solid State Drive",
        "COOLER": " CPU Cooler",
        "CASE": " Case",
        "PSU": " Power Supply",
    }[category]
    result = clean_model_name(display, (suffix,))
    for pattern in MODEL_PATTERNS.get(category, ()):
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    return result.strip()


def normalize_item(item: SelectedItem) -> dict[str, Any]:
    row = item.row
    model_name = derive_model_name(item.category, row)
    specifications = NORMALIZERS[item.category](row)
    quality, recommendation, unverified = evaluate_quality(item.category, specifications)
    reference_price = parse_number(row.get("price"))
    return {
        "hardware_id": build_hardware_id(item.category, model_name),
        "category": item.category,
        "brand": row["brand"].strip(),
        "model_name": model_name,
        "display_name": row["name"].strip(),
        "specifications": specifications,
        "source": {
            "dataset": CATEGORY_TABLES[item.category],
            "pcpp_id": row["pcpp_id"],
            "source_url": row.get("source_url") or None,
            "image_url": row.get("image_url") or None,
            "reference_price": reference_price,
            "reference_price_note": "PCPartPicker 2026-10 快照；币种标注与实际量级不一致，仅作参考，不参与预算",
        },
        "data_quality_status": quality,
        "lifecycle_status": "CURRENT",
        "recommendation_status": recommendation,
        "unverified_fields": unverified,
        "selection_reason": item.reason,
    }


def build_catalog(config: dict, selected: list[SelectedItem], generated_at: str) -> dict[str, Any]:
    hardware = [normalize_item(item) for item in selected]
    _assert_unique_ids(hardware)
    return {
        "schema_version": SCHEMA_VERSION,
        "catalog_version": config["catalog_version"],
        "generated_at": generated_at,
        "source": {
            "hardware_dataset": "pcpartpicker",
            "snapshot_date": "2026-10-05",
            "raw_rows": len({item.row["pcpp_id"] for item in selected}),
        },
        "platform_pairs": config.get("platform_pairs", []),
        "hardware": hardware,
    }


def _assert_unique_ids(hardware: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for entry in hardware:
        hardware_id = entry["hardware_id"]
        if hardware_id in seen:
            raise ValueError(f"硬件 ID 冲突：{hardware_id}")
        seen.add(hardware_id)


def write_json(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="归一化候选硬件并生成 catalog.json")
    parser.add_argument("--data-dir", help="Hardware data 根目录，也可用 PC_DATA_DIR")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args(argv)

    data_dir = resolve_data_dir(args.data_dir)
    config, selected = load_selection(
        Path(__file__).resolve().parent / "candidate_selection.json", data_dir
    )
    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    catalog = build_catalog(config, selected, generated_at)
    output_path = Path(args.output_dir) / "catalog.json"
    write_json(catalog, output_path)

    blocked = [entry["hardware_id"] for entry in catalog["hardware"]
               if entry["recommendation_status"] == "BLOCKED"]
    print(f"[ok] catalog.json 已写入 {output_path}，共 {len(catalog['hardware'])} 条")
    if blocked:
        raise SystemExit(f"以下硬件缺少必需字段，已标记 BLOCKED：{blocked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
