"""Stage 8.1：硬件数据基线核查。

只读扫描 `PC_DATA_DIR`，输出文件清单、行数、八类别分布、字段缺失率、重复情况、
PassMark 关联粗测与已知异常，并生成 Markdown 报告与 JSON 清单。

本脚本不修改、不复制原始数据；所有统计都能由同一份输入重复复现。

用法：
    python scripts/pc-config/inspect_dataset.py --data-dir "F:/LLM_PC_Agent/Hardware data"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pc_config_data import CATEGORY_ORDER, CATEGORY_TABLES, read_csv_rows

PASSMARK_TABLES: dict[str, str] = {
    "CPU": "passmark_cpu",
    "GPU": "passmark_gpu",
    "DISK": "passmark_disk",
}

# 兼容性关键字段：缺失会让对应兼容规则只能返回 UNKNOWN，必须在基线里单独量化
KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "CPU": ("socket", "core_count", "tdp"),
    "GPU": ("chipset", "memory", "tdp", "length", "case_expansion_slot_width"),
    "MOTHERBOARD": ("socket_cpu", "chipset", "form_factor", "memory_type", "m_2_slots"),
    "MEMORY": ("speed", "modules"),
    "STORAGE": ("capacity", "spec_type", "interface"),
    "PSU": ("wattage", "length"),
    "CASE": ("motherboard_form_factor", "maximum_video_card_length", "dimensions"),
    "COOLER": ("cpu_socket", "height"),
}

DEFAULT_MD = Path("docs/quality/hardware-data-baseline.md")
DEFAULT_JSON = Path("data/pc-config/manifest/baseline.json")


def sha256_file(path: Path) -> str:
    """计算文件摘要，用于证明原始数据未被改写。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_missing(value: str | None) -> bool:
    return value is None or not value.strip()


def profile_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    """统计列名、行数、空值率与多行取值数量。"""

    if not rows:
        return {"row_count": 0, "columns": [], "missing": {}, "multiline_fields": {}}

    columns = list(rows[0].keys())
    missing: dict[str, int] = {}
    multiline: dict[str, int] = {}
    for column in columns:
        empty = 0
        multi = 0
        for row in rows:
            value = row.get(column)
            if is_missing(value):
                empty += 1
            elif "\n" in (value or ""):
                multi += 1
        missing[column] = empty
        if multi:
            multiline[column] = multi

    return {
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": columns,
        "missing": missing,
        "multiline_fields": multiline,
    }


def duplicate_profile(rows: list[dict[str, str]]) -> dict[str, int]:
    """统计来源 ID、Part Number 与品牌+名称的重复。"""

    def duplicated(key: str) -> int:
        values = [(row.get(key) or "").strip() for row in rows]
        counts = Counter(value for value in values if value)
        return sum(count - 1 for count in counts.values() if count > 1)

    brand_model = Counter(
        ((row.get("brand") or "").strip().lower(), (row.get("name") or "").strip().lower())
        for row in rows
        if (row.get("name") or "").strip()
    )
    return {
        "pcpp_id": duplicated("pcpp_id"),
        "part_number": duplicated("part_number"),
        "brand_model": sum(count - 1 for count in brand_model.values() if count > 1),
    }


def normalize_tokens(value: str) -> str:
    """跨源粗匹配用的归一化：小写、去标点、压缩空白。"""

    lowered = (value or "").lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", lowered)).strip()


def passmark_keys(pm_rows: list[dict[str, str]]) -> set[str]:
    """从 PassMark 行生成候选匹配键，去掉时钟频率后缀。"""

    keys: set[str] = set()
    for row in pm_rows:
        for source in ((row.get("model_key") or ""), (row.get("name") or "")):
            key = normalize_tokens(source)
            key = re.sub(r"\s*\d+\s+\d+\s*ghz.*$", "", key)
            key = re.sub(r"\s+@.*$", "", key)
            key = re.sub(r"\b(intel|amd|core|processor|desktop|cpu)\b", " ", key)
            key = re.sub(r"\s+", " ", key).strip()
            if len(key) >= 5:
                keys.add(key)
    return keys


def coarse_match_rate(
    hardware_rows: list[dict[str, str]],
    keys: set[str],
    name_field: str = "name",
) -> dict[str, Any]:
    """粗测匹配率：仅用于判断规模，正式口径由 8.5 的映射脚本给出。"""

    hits = 0
    misses: list[str] = []
    for row in hardware_rows:
        name = normalize_tokens(row.get(name_field) or "")
        if any(key in name for key in keys):
            hits += 1
        else:
            misses.append((row.get(name_field) or "").strip())
    total = len(hardware_rows)
    return {
        "matched": hits,
        "total": total,
        "ratio": round(hits / total, 4) if total else 0.0,
        "miss_samples": misses[:10],
    }


def scan(data_dir: Path) -> dict[str, Any]:
    """执行全量扫描并返回结构化结果。"""

    csv_dir = data_dir / "csv"
    if not csv_dir.is_dir():
        raise SystemExit(f"数据目录缺少 csv/ 子目录：{data_dir}")

    scanned_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inputs: list[dict[str, Any]] = []
    categories: dict[str, Any] = {}

    for category in CATEGORY_ORDER:
        table = CATEGORY_TABLES[category]
        rows = read_csv_rows(data_dir, table)
        path = csv_dir / f"{table}.csv"
        inputs.append(
            {
                "table": table,
                "path": f"csv/{table}.csv",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
        profile = profile_rows(rows)
        profile["duplicates"] = duplicate_profile(rows)
        profile["key_field_missing"] = {
            field: profile["missing"].get(field, 0) for field in KEY_FIELDS[category]
        }
        categories[category] = profile

    benchmarks: dict[str, Any] = {}
    for label, table in PASSMARK_TABLES.items():
        rows = read_csv_rows(data_dir, table)
        path = csv_dir / f"{table}.csv"
        inputs.append(
            {
                "table": table,
                "path": f"csv/{table}.csv",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
        benchmarks[label] = profile_rows(rows)

    cpu_rows = read_csv_rows(data_dir, "pcpp_cpu")
    gpu_rows = read_csv_rows(data_dir, "pcpp_gpu")
    storage_rows = read_csv_rows(data_dir, "pcpp_storage")
    pm_cpu = read_csv_rows(data_dir, "passmark_cpu")
    pm_gpu = read_csv_rows(data_dir, "passmark_gpu")
    pm_disk = read_csv_rows(data_dir, "passmark_disk")

    linkage = {
        "cpu": coarse_match_rate(cpu_rows, passmark_keys(pm_cpu)),
        "gpu_chipset": coarse_match_rate(gpu_rows, passmark_keys(pm_gpu), name_field="chipset"),
        "disk": coarse_match_rate(storage_rows, passmark_keys(pm_disk), name_field="name"),
        "gpu_chipset_cardinality": {
            "boards": len(gpu_rows),
            "distinct_chipsets": len({(row.get("chipset") or "").strip() for row in gpu_rows}),
            "passmark_keys": len({(row.get("model_key") or "").strip() for row in pm_gpu}),
        },
    }

    raw_files = sorted(
        (
            {
                "path": str(path.relative_to(data_dir)).replace("\\", "/"),
                "bytes": path.stat().st_size,
            }
            for path in (data_dir / "raw").rglob("*")
            if path.is_file()
        ),
        key=lambda item: item["path"],
    )

    return {
        "scanned_at": scanned_at,
        "data_dir": str(data_dir),
        "inputs": inputs,
        "categories": categories,
        "benchmarks": benchmarks,
        "linkage": linkage,
        "raw_archive": {
            "file_count": len(raw_files),
            "total_bytes": sum(item["bytes"] for item in raw_files),
            "files": [item["path"] for item in raw_files],
        },
        "anomalies": collect_anomalies(categories, benchmarks, linkage),
    }


def collect_anomalies(
    categories: dict[str, Any],
    benchmarks: dict[str, Any],
    linkage: dict[str, Any],
) -> list[str]:
    """把扫描结论整理成可核对的异常清单。"""

    anomalies: list[str] = []

    missing_release_date = [
        category
        for category in CATEGORY_ORDER
        if "release_date" not in categories[category]["columns"]
    ]
    if missing_release_date:
        anomalies.append(
            "PCPartPicker 八张分类表均无 release_date 字段，生命周期无法直接由发布日期判定："
            + "、".join(missing_release_date)
        )

    if "memory_type" not in categories["MEMORY"]["columns"]:
        anomalies.append("内存表无独立 DDR 类型字段，只能从 speed 派生（DDR5/DDR4/DDR3/DDR2）")

    cooler_missing = categories["COOLER"]["key_field_missing"].get("height", 0)
    cooler_total = categories["COOLER"]["row_count"]
    if cooler_missing:
        anomalies.append(
            f"散热器 height 缺失 {cooler_missing}/{cooler_total}，机箱限高规则会返回 UNKNOWN"
        )

    case_missing = categories["CASE"]["key_field_missing"].get("maximum_video_card_length", 0)
    if case_missing:
        anomalies.append(f"机箱 maximum_video_card_length 缺失 {case_missing} 条")

    slots = linkage["gpu_chipset_cardinality"]
    anomalies.append(
        f"显卡为板卡级共 {slots['boards']} 条、{slots['distinct_chipsets']} 个芯片型号，"
        f"PassMark 显卡为芯片级 {slots['passmark_keys']} 个键，映射天然多对一"
    )

    for label, profile in benchmarks.items():
        mono = profile["missing"].get(
            {"CPU": "cpu_mark", "GPU": "g3d_mark", "DISK": "disk_mark"}[label], 0
        )
        if mono:
            anomalies.append(f"PassMark {label} 主指标缺失 {mono} 条")
        else:
            anomalies.append(f"PassMark {label} 主指标完整，无缺失")

    anomalies.append("PCPartPicker 价格为美元参考价（2026-10 快照），不得作为人民币报价写入主数据")
    anomalies.append("PassMark 存储型号名含 2.5\"、反斜杠等脏字符，需要在映射阶段额外容错")
    anomalies.append("raw/pcpp/images.json 仅 1,600 条映射，图片应以 CSV 的 image_url 为准")

    return anomalies


def ratio(missing: int, total: int) -> str:
    return f"{missing} ({missing / total * 100:.1f}%)" if total else str(missing)


def render_markdown(result: dict[str, Any]) -> str:
    """把扫描结果渲染为基线报告。"""

    lines: list[str] = []
    add = lines.append

    add("# 硬件数据基线核查")
    add("")
    add("| 项 | 内容 |")
    add("| --- | --- |")
    add("| 生成方式 | `scripts/pc-config/inspect_dataset.py` 自动生成，不得手改 |")
    add(f"| 扫描时间 | {result['scanned_at']} |")
    add(f"| 数据目录 | `{result['data_dir']}`（只读） |")
    add("| 权威性 | Stage 8.1 事实基线；后续治理报告以此为准 |")
    add("")

    total_hardware = sum(profile["row_count"] for profile in result["categories"].values())
    total_bench = sum(profile["row_count"] for profile in result["benchmarks"].values())
    add("## 1. 规模总览")
    add("")
    add("| 指标 | 数量 |")
    add("| --- | --- |")
    add(f"| PCPartPicker 硬件 | {total_hardware} |")
    add(f"| PassMark 跑分 | {total_bench} |")
    add(f"| 输入文件 | {len(result['inputs'])} |")
    add(f"| 原始归档文件 | {result['raw_archive']['file_count']} |")
    add(f"| 原始归档体积 | {result['raw_archive']['total_bytes'] / 1024 / 1024:.1f} MB |")
    add("")

    add("## 2. 数据文件清单")
    add("")
    add("| 文件 | 行数 | 列数 | 体积 | sha256 |")
    add("| --- | --- | --- | --- | --- |")
    # 按表名索引，避免类别标签与跑分标签（两处都有 CPU/GPU）互相覆盖
    profile_by_table: dict[str, Any] = {
        CATEGORY_TABLES[category]: result["categories"][category] for category in CATEGORY_ORDER
    }
    profile_by_table.update(
        {table: result["benchmarks"][label] for label, table in PASSMARK_TABLES.items()}
    )
    for item in result["inputs"]:
        profile = profile_by_table[item["table"]]
        add(
            f"| `{item['path']}` | {profile['row_count']} | {profile.get('column_count', 0)} | "
            f"{item['bytes'] / 1024:.0f} KB | `{item['sha256'][:16]}…` |"
        )
    add("")
    add("> 原始归档只登记文件与体积，不纳入版本库；哈希仅覆盖 `csv/` 输入。")
    add("")

    add("## 3. 八类别分布与兼容性关键字段")
    add("")
    add("| 类别 | 行数 | 列数 | 关键字段缺失 |")
    add("| --- | --- | --- | --- |")
    for category in CATEGORY_ORDER:
        profile = result["categories"][category]
        missing_text = "；".join(
            f"{field} {ratio(count, profile['row_count'])}"
            for field, count in profile["key_field_missing"].items()
        )
        add(f"| {category} | {profile['row_count']} | {profile['column_count']} | {missing_text} |")
    add("")

    add("## 4. 字段缺失率（缺失数大于 0 的列）")
    add("")
    for category in CATEGORY_ORDER:
        profile = result["categories"][category]
        empties = [
            (column, count)
            for column, count in sorted(profile["missing"].items(), key=lambda item: -item[1])
            if count
        ]
        add(f"**{category}**（{profile['row_count']} 行，{profile['column_count']} 列）")
        add("")
        if not empties:
            add("无缺失列。")
        else:
            add("| 列 | 缺失 | 多行取值 |")
            add("| --- | --- | --- |")
            for column, count in empties[:12]:
                add(
                    f"| `{column}` | {ratio(count, profile['row_count'])} | "
                    f"{profile['multiline_fields'].get(column, 0)} |"
                )
            if len(empties) > 12:
                add(f"| …其余 {len(empties) - 12} 列 | | |")
        add("")

    add("## 5. 重复情况")
    add("")
    add("| 类别 | pcpp_id 重复 | part_number 重复 | 品牌+名称重复 |")
    add("| --- | --- | --- | --- |")
    for category in CATEGORY_ORDER:
        dup = result["categories"][category]["duplicates"]
        add(f"| {category} | {dup['pcpp_id']} | {dup['part_number']} | {dup['brand_model']} |")
    add("")
    add("> 重复数只表示「多出来的行数」，不等于冲突；是否合并由 Stage 8.4 判定。")
    add("")

    add("## 6. PassMark 关联情况（粗测）")
    add("")
    add("> 本节只用于判断规模，正式匹配方法与置信度由 Stage 8.5 输出。粗测采用归一化令牌子串匹配。")
    add("")
    add("| 对象 | 命中 | 总数 | 粗测命中率 |")
    add("| --- | --- | --- | --- |")
    for label, key in (("CPU", "cpu"), ("GPU（芯片级）", "gpu_chipset"), ("存储", "disk")):
        item = result["linkage"][key]
        add(f"| {label} | {item['matched']} | {item['total']} | {item['ratio'] * 100:.1f}% |")
    add("")
    cardinality = result["linkage"]["gpu_chipset_cardinality"]
    add(
        f"显卡板卡 {cardinality['boards']} 条对应 {cardinality['distinct_chipsets']} 个芯片型号，"
        f"PassMark 侧有 {cardinality['passmark_keys']} 个型号键，因此显卡跑分只能是芯片级多对一。"
    )
    add("")

    add("## 7. 已知异常")
    add("")
    for index, anomaly in enumerate(result["anomalies"], start=1):
        add(f"{index}. {anomaly}")
    add("")

    add("## 8. 对后续阶段的输入")
    add("")
    add("- 原始数据保持只读，治理产物写入 `data/pc-config/`，不在本阶段生成。")
    add("- 关键字段缺失集中在散热器高度与机箱尺寸，需在 Stage 8.3 明确 `missing_reason`。")
    add("- 生命周期缺少发布日期基础，按 ADR 0015 分类别推进。")
    add("- 显卡跑分按芯片级映射，按 ADR 0015 与 `glossary.md` 的「匹配范围」口径表述。")
    add("")

    return "\n".join(lines)


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def resolve_data_dir(cli_value: str | None) -> Path:
    raw = cli_value or os.environ.get("PC_DATA_DIR")
    if not raw:
        raise SystemExit("请通过 --data-dir 或环境变量 PC_DATA_DIR 指定硬件数据目录")
    data_dir = Path(raw)
    if not (data_dir / "csv").is_dir():
        raise SystemExit(f"数据目录缺少 csv/ 子目录：{data_dir}")
    return data_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 8.1 硬件数据基线核查")
    parser.add_argument("--data-dir", help="Hardware data 根目录，也可用 PC_DATA_DIR")
    parser.add_argument("--output-md", default=str(DEFAULT_MD))
    parser.add_argument("--output-json", default=str(DEFAULT_JSON))
    args = parser.parse_args(argv)

    result = scan(resolve_data_dir(args.data_dir))

    md_path = Path(args.output_md)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(result), encoding="utf-8")

    json_path = Path(args.output_json)
    write_json(result, json_path)

    total = sum(profile["row_count"] for profile in result["categories"].values())
    bench = sum(profile["row_count"] for profile in result["benchmarks"].values())
    print(f"[ok] 硬件 {total} 条 / 跑分 {bench} 条 / 输入 {len(result['inputs'])} 份")
    print(f"[ok] 基线报告：{md_path}")
    print(f"[ok] 基线清单：{json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
