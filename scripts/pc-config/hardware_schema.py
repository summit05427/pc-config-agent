"""Stage 8.2：统一 Hardware Schema。

定义八类硬件的公共字段与类别专属规格字段（类型、单位、必填性、枚举），并提供
运行时校验与 JSON Schema 导出。字段名与现有 `catalog.json` 的 specifications 键保持
一致，新增键只增不改（Stage 8 方案 §5）。

用法：
    python scripts/pc-config/hardware_schema.py --export-dir data/pc-config/schema
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"

CATEGORIES: tuple[str, ...] = (
    "CPU",
    "GPU",
    "MOTHERBOARD",
    "MEMORY",
    "STORAGE",
    "COOLER",
    "CASE",
    "PSU",
)

# BLOCKED 是现有 normalize_specs.evaluate_quality 的历史取值，仅为兼容既有夹具保留，
# 主数据产物不得再写入该值（缺关键字段一律表达为 governance_status=INCOMPLETE）
DATA_QUALITY_STATUSES: tuple[str, ...] = ("VERIFIED_STRUCTURED", "PARTIAL", "BLOCKED")

GOVERNANCE_STATUSES: tuple[str, ...] = ("VALID", "INCOMPLETE", "INVALID", "CONFLICT")

LIFECYCLE_STATUSES: tuple[str, ...] = (
    "CURRENT",
    "MATURE",
    "LEGACY",
    "DISCONTINUED",
    "UNKNOWN",
)

MARKET_STATUSES: tuple[str, ...] = ("AVAILABLE", "UNAVAILABLE", "UNVERIFIED")

RECOMMENDATION_STATUSES: tuple[str, ...] = ("ELIGIBLE", "RESTRICTED", "EXCLUDED", "ARCHIVED")

BENCHMARK_TYPES: tuple[str, ...] = ("CPUMARK", "SINGLE_THREAD", "G3D_MARK", "DISK_MARK")

MATCH_SCOPES: tuple[str, ...] = ("PRODUCT", "CHIPSET")

MATCH_STATUSES: tuple[str, ...] = ("MATCHED", "UNMATCHED", "AMBIGUOUS", "CONFLICT")

ENUM_FIELDS: dict[str, tuple[str, ...]] = {
    "category": CATEGORIES,
    "data_quality_status": DATA_QUALITY_STATUSES,
    "governance_status": GOVERNANCE_STATUSES,
    "lifecycle_status": LIFECYCLE_STATUSES,
    "market_status": MARKET_STATUSES,
    "recommendation_status": RECOMMENDATION_STATUSES,
}

# 缺失即无法判定兼容性的字段，发布候选池前必须为 null 之外的值
COMPAT_CRITICAL: dict[str, tuple[str, ...]] = {
    "CPU": ("socket",),
    "GPU": ("chipset", "length_mm"),
    "MOTHERBOARD": ("socket", "chipset", "form_factor", "memory_type"),
    "MEMORY": ("memory_type", "capacity_gb", "speed_mts"),
    "STORAGE": ("capacity_gb", "interface"),
    "COOLER": ("supported_sockets",),
    "CASE": ("supported_mainboard_form_factors",),
    "PSU": ("wattage_w",),
}


@dataclass(frozen=True)
class FieldSpec:
    """单个字段的契约。`unit` 只对数值字段有意义，`nullable` 表示允许缺失。"""

    name: str
    value_type: str
    required: bool
    unit: str = ""
    nullable: bool = True
    description: str = ""

    def as_json_schema(self) -> dict[str, Any]:
        type_map = {
            "string": {"type": "string"},
            "integer": {"type": "integer"},
            "number": {"type": "number"},
            "boolean": {"type": "boolean"},
            "array": {"type": "array", "items": {"type": "string"}},
            "object": {"type": "object"},
        }
        schema = dict(type_map[self.value_type])
        if self.unit:
            schema["x-unit"] = self.unit
        if self.description:
            schema["description"] = self.description
        if self.nullable:
            schema["type"] = [schema["type"], "null"]
        return schema


COMMON_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("hardware_id", "string", True, nullable=False, description="稳定主键，沿用现有生成规则"),
    FieldSpec("source_id", "string", True, nullable=False, description="来源数据集内的原始 ID"),
    FieldSpec("source", "object", True, nullable=False, description="来源数据集、URL、图片与采集信息"),
    FieldSpec("category", "string", True, nullable=False, description="八类之一"),
    FieldSpec("brand", "string", True, nullable=False),
    FieldSpec("model_name", "string", True, nullable=False),
    FieldSpec("manufacturer_part_number", "string", False, nullable=True),
    FieldSpec("aliases", "array", False, description="展示名与历史名称，用于检索与第三方匹配"),
    FieldSpec("specifications", "object", True, nullable=False, description="规范化后的类别专属规格"),
    FieldSpec("raw_specs", "object", True, nullable=False, description="原始行键值，不允许改写"),
    FieldSpec("data_quality_status", "string", True, nullable=False, description="现有字段完整度语义"),
    FieldSpec("governance_status", "string", True, nullable=False, description="本次治理结论"),
    FieldSpec("lifecycle_status", "string", True, nullable=False),
    FieldSpec("market_status", "string", True, nullable=False),
    FieldSpec("recommendation_status", "string", True, nullable=False),
    FieldSpec("source_version", "string", True, nullable=False, description="来源快照版本"),
    FieldSpec("collected_at", "string", True, nullable=False, description="来源采集时间（ISO 8601）"),
    FieldSpec("updated_at", "string", True, nullable=False, description="本次治理写入时间（ISO 8601）"),
    FieldSpec("lifecycle_reason", "string", False, description="生命周期判定规则与依据"),
    FieldSpec("recommendation_reason", "string", False, description="推荐资格判定规则与依据"),
    FieldSpec("rule_version", "string", False, description="分类规则版本，便于回溯"),
)

CATEGORY_FIELDS: dict[str, tuple[FieldSpec, ...]] = {
    "CPU": (
        FieldSpec("socket", "string", True, nullable=False),
        FieldSpec("core_count", "integer", True, nullable=False),
        FieldSpec("tdp_w", "integer", True, unit="W", nullable=False),
        FieldSpec("platform", "string", False),
        FieldSpec("thread_count", "integer", False),
        FieldSpec("integrated_graphics", "string", False),
        FieldSpec("includes_cooler", "boolean", False),
        FieldSpec("max_memory", "string", False),
    ),
    "GPU": (
        FieldSpec("chipset", "string", True, nullable=False, description="芯片型号，跑分按此粒度映射"),
        FieldSpec("vram_gb", "integer", True, unit="GB", nullable=False),
        FieldSpec("tdp_w", "integer", True, unit="W", nullable=False),
        # 部分老卡与工作站卡原始数据没有长度，缺失由 governance_status=INCOMPLETE
        # 表达，并保留在 COMPAT_CRITICAL 中供发布前的严格模式检查
        FieldSpec("length_mm", "integer", False, unit="mm"),
        FieldSpec("memory_type", "string", False),
        FieldSpec("slot_width", "integer", False, unit="slot"),
        FieldSpec("external_power", "object", False, description="供电接口，如 {pcie_8pin: 2}"),
    ),
    "MOTHERBOARD": (
        FieldSpec("socket", "string", True, nullable=False),
        FieldSpec("chipset", "string", True, nullable=False),
        FieldSpec("form_factor", "string", True, nullable=False),
        FieldSpec("memory_type", "string", True, nullable=False),
        FieldSpec("platform", "string", False),
        FieldSpec("memory_slots", "integer", False),
        FieldSpec("max_memory_speed_mts", "integer", False, unit="MT/s"),
        FieldSpec("m2_slot_count", "integer", False),
        FieldSpec("sata_ports", "integer", False),
        FieldSpec("pcie_x16_slots", "integer", False),
    ),
    "MEMORY": (
        FieldSpec("memory_type", "string", True, nullable=False, description="DDR5/DDR4/DDR3，由 speed 派生"),
        FieldSpec("capacity_gb", "integer", True, unit="GB", nullable=False),
        FieldSpec("speed_mts", "integer", True, unit="MT/s", nullable=False),
        FieldSpec("module_count", "integer", False),
        FieldSpec("module_size_gb", "integer", False, unit="GB"),
        FieldSpec("form_factor", "string", False),
        FieldSpec("cas_latency", "integer", False),
    ),
    "STORAGE": (
        FieldSpec("capacity_gb", "integer", True, unit="GB", nullable=False),
        FieldSpec("interface", "string", True, nullable=False),
        FieldSpec("form_factor", "string", False),
        FieldSpec("nvme", "boolean", False),
    ),
    "COOLER": (
        FieldSpec("supported_sockets", "array", True, nullable=False),
        FieldSpec("cooler_type", "string", False),
        FieldSpec("height_mm", "integer", False, unit="mm", description="缺失时风冷限高规则返回 UNKNOWN"),
        FieldSpec("radiator_size_mm", "integer", False, unit="mm", description="仅水冷有效"),
        FieldSpec("fanless", "boolean", False),
    ),
    "CASE": (
        FieldSpec("supported_mainboard_form_factors", "array", True, nullable=False),
        FieldSpec("max_gpu_length_mm", "integer", False, unit="mm"),
        FieldSpec("max_cooler_height_mm", "integer", False, unit="mm"),
        FieldSpec("psu_form_factor", "string", False),
        FieldSpec("radiator_support", "string", False),
        FieldSpec("expansion_slots", "integer", False),
        FieldSpec("dimensions_mm", "array", False, unit="mm", description="长/宽/高三个数值"),
    ),
    "PSU": (
        FieldSpec("wattage_w", "integer", True, unit="W", nullable=False),
        FieldSpec("efficiency", "string", False),
        FieldSpec("modular", "string", False),
        FieldSpec("form_factor", "string", False),
        FieldSpec("pcie_8pin_count", "integer", False),
        FieldSpec("pcie_12vhpwr_count", "integer", False),
        FieldSpec("length_mm", "integer", False, unit="mm"),
        FieldSpec("sata_connectors", "integer", False),
    ),
}

TYPE_CHECKS: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def _check_value(name: str, value: Any, spec: FieldSpec) -> list[str]:
    issues: list[str] = []
    if value is None:
        return issues
    expected = TYPE_CHECKS[spec.value_type]
    # bool 是 int 的子类，必须单独排除，避免 true 通过 integer 校验
    if spec.value_type in {"integer", "number"} and isinstance(value, bool):
        return [f"{name}: 期望 {spec.value_type}，实际为 bool"]
    if not isinstance(value, expected):
        issues.append(f"{name}: 期望 {spec.value_type}，实际为 {type(value).__name__}")
    if spec.value_type == "array" and isinstance(value, list):
        if any(not isinstance(item, str) for item in value):
            issues.append(f"{name}: 数组元素必须为字符串")
    return issues


def validate_record(record: dict[str, Any], *, strict_compat: bool = False) -> list[str]:
    """校验一条主数据记录，返回问题列表（空列表表示通过）。"""

    issues: list[str] = []
    category = record.get("category")
    if category not in CATEGORIES:
        return [f"category 非法：{category!r}"]

    specs = record.get("specifications")
    if not isinstance(specs, dict):
        return ["specifications 必须为对象"]

    known_specs = {spec.name for spec in CATEGORY_FIELDS[category]}
    for key in sorted(set(specs) - known_specs):
        issues.append(f"specifications 存在未登记键：{key}")

    for spec in COMMON_FIELDS:
        value = record.get(spec.name)
        if value is None or value == "" or value == [] or value == {}:
            if spec.required:
                issues.append(f"缺少必填字段：{spec.name}")
            continue
        if spec.name in ENUM_FIELDS and value not in ENUM_FIELDS[spec.name]:
            issues.append(f"{spec.name} 取值非法：{value!r}")
        issues.extend(_check_value(spec.name, value, spec))

    raw_specs = record.get("raw_specs")
    if isinstance(raw_specs, dict) and not raw_specs:
        issues.append("raw_specs 不得为空，必须保留原始行")

    for spec in CATEGORY_FIELDS[category]:
        value = specs.get(spec.name)
        if value is None:
            if spec.required:
                issues.append(f"缺少类别必填规格：{spec.name}")
            continue
        issues.extend(_check_value(f"specifications.{spec.name}", value, spec))

    if strict_compat:
        for name in COMPAT_CRITICAL[category]:
            if specs.get(name) in (None, "", []):
                issues.append(f"兼容性关键字段缺失：{name}")

    return issues


def category_json_schema(category: str) -> dict[str, Any]:
    """生成单个类别的 JSON Schema。"""

    properties: dict[str, Any] = {}
    required: list[str] = []

    for spec in COMMON_FIELDS:
        schema = spec.as_json_schema()
        if spec.name in ENUM_FIELDS:
            schema["enum"] = list(ENUM_FIELDS[spec.name])
        if spec.name == "category":
            schema["enum"] = [category]
        if spec.name == "specifications":
            schema = {
                "type": "object",
                "properties": {
                    field.name: field.as_json_schema() for field in CATEGORY_FIELDS[category]
                },
                "required": [
                    field.name for field in CATEGORY_FIELDS[category] if field.required
                ],
                "additionalProperties": False,
            }
        properties[spec.name] = schema
        if spec.required:
            required.append(spec.name)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://example.local/schemas/pc-config/{category.lower()}.schema.json",
        "title": f"PC Hardware Master - {category}",
        "schema_version": SCHEMA_VERSION,
        "category": category,
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def export_schemas(export_dir: Path) -> list[Path]:
    """导出公共 Schema 与八类专属 Schema，返回写入的文件路径。"""

    export_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    index: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "categories": {},
        "enums": {
            "governance_status": list(GOVERNANCE_STATUSES),
            "lifecycle_status": list(LIFECYCLE_STATUSES),
            "market_status": list(MARKET_STATUSES),
            "recommendation_status": list(RECOMMENDATION_STATUSES),
            "benchmark_type": list(BENCHMARK_TYPES),
            "match_scope": list(MATCH_SCOPES),
            "match_status": list(MATCH_STATUSES),
        },
    }
    for category in CATEGORIES:
        path = export_dir / f"{category.lower()}.schema.json"
        path.write_text(
            json.dumps(category_json_schema(category), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
        index["categories"][category] = path.name

    index_path = export_dir / "hardware-master.schema.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    written.append(index_path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 8.2 统一 Hardware Schema 导出")
    parser.add_argument("--export-dir", default="data/pc-config/schema")
    args = parser.parse_args(argv)

    written = export_schemas(Path(args.export_dir))
    print(f"[ok] Schema 版本 {SCHEMA_VERSION}，已导出 {len(written)} 个文件到 {args.export_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
