"""按品类把 PCPartPicker 原始字段标准化为统一规格。

所有值都来自 CSV 的 specs 字段；解析不出来时返回 None，不做默认值填充。
"""

from __future__ import annotations

import re
from typing import Any

from cleaning_common import (
    first_value,
    normalize_model,
    normalize_socket,
    parse_capacity_gb,
    parse_clock_mhz,
    parse_height_mm,
    parse_memory_type,
    parse_modules,
    parse_number,
    split_values,
)


def _bool(value: Any) -> bool | None:
    text = (first_value(value) or "").lower()
    if text in {"yes", "true"}:
        return True
    if text in {"no", "false"}:
        return False
    return None


def _int(value: Any) -> int | None:
    number = parse_number(value)
    return int(number) if number is not None else None


def _range_anomaly(field: str, value: float | None, low: float, high: float) -> list[str]:
    if value is not None and not low <= value <= high:
        return [f"ANOMALY_{field.upper()}"]
    return []


def normalize_cpu(specs: dict[str, Any]) -> dict[str, Any]:
    cores = _int(specs.get("Core Count"))
    threads = _int(specs.get("Thread Count"))
    tdp = _int(specs.get("TDP"))
    base = parse_clock_mhz(specs.get("Performance Core Clock"))
    boost = parse_clock_mhz(specs.get("Performance Core Boost Clock"))
    anomalies = (
        _range_anomaly("core_count", cores, 1, 128)
        + _range_anomaly("thread_count", threads, 1, 256)
        + _range_anomaly("tdp_w", tdp, 5, 500)
        + _range_anomaly("base_clock_mhz", base, 500, 7000)
    )
    if cores and threads and threads < cores:
        anomalies.append("ANOMALY_THREADS_LT_CORES")
    return {
        "socket": normalize_socket(specs.get("Socket")),
        "core_count": cores,
        "thread_count": threads,
        "base_clock_mhz": base,
        "boost_clock_mhz": boost,
        "tdp_w": tdp,
        "l3_cache_mb": parse_number(specs.get("L3 Cache")),
        "max_memory_gb": parse_capacity_gb(specs.get("Maximum Supported Memory")),
        "integrated_graphics": first_value(specs.get("Integrated Graphics")),
        "packaging": first_value(specs.get("Packaging")),
        "includes_cooler": _bool(specs.get("Includes CPU Cooler")),
        "microarchitecture": first_value(specs.get("Microarchitecture")),
        "core_family": first_value(specs.get("Core Family")),
        "anomalies": anomalies,
    }


def normalize_gpu(specs: dict[str, Any]) -> dict[str, Any]:
    vram = parse_capacity_gb(specs.get("Memory"))
    length = parse_height_mm(specs.get("Length"))
    tdp = _int(specs.get("TDP"))
    slots = parse_number(specs.get("Total Slot Width"))
    anomalies = (
        _range_anomaly("vram_gb", vram, 0.5, 128)
        + _range_anomaly("length_mm", length, 80, 500)
        + _range_anomaly("tdp_w", tdp, 5, 1500)
    )
    return {
        "chipset": first_value(specs.get("Chipset")),
        "vram_gb": vram,
        "memory_type": first_value(specs.get("Memory Type")),
        "length_mm": length,
        "thickness_slots": slots,
        "tdp_w": tdp,
        "power_connector": first_value(specs.get("External Power")),
        "interface": first_value(specs.get("Interface")),
        "cooling": first_value(specs.get("Cooling")),
        "color": first_value(specs.get("Color")),
        "anomalies": anomalies,
    }


def normalize_motherboard(specs: dict[str, Any]) -> dict[str, Any]:
    slots = _int(specs.get("Memory Slots"))
    form_factor = first_value(specs.get("Form Factor"))
    chipset = first_value(specs.get("Chipset"))
    memory_type = parse_memory_type(specs.get("Memory Type"))
    m2 = split_values(specs.get("M.2 Slots"))
    anomalies = _range_anomaly("memory_slots", slots, 1, 16)
    return {
        "socket": normalize_socket(specs.get("Socket / CPU")),
        "chipset": chipset_short(chipset),
        "memory_type": memory_type,
        "memory_slots": slots,
        "memory_max_gb": parse_capacity_gb(specs.get("Memory Max")),
        "form_factor": form_factor,
        "m2_slot_count": len(m2) or None,
        "pcie_x16_slots": _int(specs.get("PCIe x16 Slots")),
        "sata_ports": _int(specs.get("SATA 6.0 Gb/s Ports")),
        "wireless": first_value(specs.get("Wireless Networking")),
        "anomalies": anomalies,
    }


def chipset_short(value: str | None) -> str | None:
    """把「AMD B850」收敛成「B850」，保留厂商前缀会破坏跨平台比较。"""

    if not value:
        return None
    match = re.search(r"\b([A-Z]\d{2,4}[A-Z]?|\d{3,4}[A-Z]{0,2})\b", value.upper())
    return match.group(1) if match else value.upper()


def normalize_memory(specs: dict[str, Any]) -> dict[str, Any]:
    module_count, capacity = parse_modules(specs.get("Modules"))
    speed_text = first_value(specs.get("Speed"))
    speed = None
    if speed_text:
        match = re.search(r"(\d{3,5})", speed_text)
        speed = int(match.group(1)) if match else None
    memory_type = parse_memory_type(speed_text) or parse_memory_type(specs.get("Form Factor"))
    anomalies = (
        _range_anomaly("capacity_gb", capacity, 0.25, 1024)
        + _range_anomaly("speed_mhz", speed, 200, 12000)
    )
    return {
        "memory_type": memory_type,
        "capacity_gb": capacity,
        "module_count": module_count,
        "speed_mhz": speed,
        "cas_latency": _int(specs.get("CAS Latency")),
        "form_factor": first_value(specs.get("Form Factor")),
        "ecc": first_value(specs.get("ECC / Registered")),
        "voltage_v": parse_number(specs.get("Voltage")),
        "color": first_value(specs.get("Color")),
        "anomalies": anomalies,
    }


def normalize_storage(specs: dict[str, Any]) -> dict[str, Any]:
    capacity = parse_capacity_gb(specs.get("Capacity"))
    read = parse_number(specs.get("Sequential Read Throughput QD4"))
    write = parse_number(specs.get("Sequential Write Throughput QD4"))
    drive_type = first_value(specs.get("Type")) or ""
    if "ssd" in drive_type.lower():
        media_type = "SSD"
    elif "rpm" in drive_type.lower():
        media_type = "HDD"
    else:
        media_type = "UNKNOWN"
    anomalies = (
        _range_anomaly("capacity_gb", capacity, 8, 40960)
        + _range_anomaly("sequential_read_mbps", read, 30, 30000)
    )
    return {
        "capacity_gb": capacity,
        "interface": first_value(specs.get("Interface")),
        "form_factor": first_value(specs.get("Form Factor")),
        "media_type": media_type,
        "nvme": _bool(specs.get("NVME")),
        "sequential_read_mbps": read,
        "sequential_write_mbps": write,
        "anomalies": anomalies,
    }


def normalize_psu(specs: dict[str, Any]) -> dict[str, Any]:
    wattage = _int(specs.get("Wattage"))
    length = parse_height_mm(specs.get("Length"))
    anomalies = (
        _range_anomaly("rated_power_w", wattage, 100, 5000)
        + _range_anomaly("length_mm", length, 80, 400)
    )
    return {
        "rated_power_w": wattage,
        "efficiency": first_value(specs.get("Efficiency Rating")),
        "modular": first_value(specs.get("Modular")),
        "atx_type": first_value(specs.get("Type")),
        "length_mm": length,
        "pcie_8pin": _int(specs.get("PCIe 8-pin Connectors")),
        "pcie_6plus2pin": _int(specs.get("PCIe 6+2-pin Connectors")),
        "pcie_12vhpwr": _int(specs.get("PCIe 16-pin 12VHPWR/12V-2x6 Connectors")),
        "anomalies": anomalies,
    }


def normalize_case(specs: dict[str, Any]) -> dict[str, Any]:
    clearance = parse_height_mm(specs.get("Maximum Video Card Length"))
    anomalies = _range_anomaly("gpu_clearance_mm", clearance, 100, 1000)
    return {
        "supported_form_factors": split_values(specs.get("Motherboard Form Factor")),
        "gpu_clearance_mm": clearance,
        "cooler_clearance_mm": None,
        "radiator_support": split_values(specs.get("Radiator Support")),
        "case_type": first_value(specs.get("Type")),
        "color": first_value(specs.get("Color")),
        "volume_l": parse_number(specs.get("Volume")),
        "anomalies": anomalies,
    }


def normalize_cooler(specs: dict[str, Any]) -> dict[str, Any]:
    model = first_value(specs.get("Model")) or ""
    radiator = None
    match = re.search(r"\b(120|240|280|360|420)\b", model)
    if match:
        radiator = int(match.group(1))
    height = parse_height_mm(specs.get("Height"))
    anomalies = _range_anomaly("height_mm", height, 10, 300)
    return {
        "sockets": split_values(specs.get("CPU Socket")),
        "height_mm": height,
        "water_cooled": _bool(specs.get("Water Cooled")),
        "radiator_size_mm": radiator,
        "radiator_size_source": "model_name_parse" if radiator else None,
        "fan_rpm": first_value(specs.get("Fan RPM")),
        "noise_db": parse_number(specs.get("Noise Level")),
        "anomalies": anomalies,
    }


NORMALIZERS = {
    "CPU": normalize_cpu,
    "GPU": normalize_gpu,
    "MOTHERBOARD": normalize_motherboard,
    "MEMORY": normalize_memory,
    "STORAGE": normalize_storage,
    "PSU": normalize_psu,
    "CASE": normalize_case,
    "COOLER": normalize_cooler,
}


def normalize(category: str, raw_specs: dict[str, Any]) -> dict[str, Any]:
    return NORMALIZERS[category](raw_specs)


def clean_model_name(category: str, list_name: str, specs: dict[str, Any]) -> str:
    """型号名只做空白与尾部括注清理，不删除区分 SKU 的数字或后缀。"""

    name = normalize_model(list_name)
    if category == "GPU":
        chipset = first_value(specs.get("Chipset"))
        if chipset and chipset.lower() not in name.lower():
            return f"{name} ({chipset})"
    return name
