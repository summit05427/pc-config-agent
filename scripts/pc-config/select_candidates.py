"""Stage 1.1：从原始 CSV 中选定候选硬件，并生成可评审清单。

候选清单是人工维护的白名单（candidate_selection.json），脚本只负责：
校验型号存在、去重、校验品牌约束、检查平台覆盖，并输出评审用 Markdown。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pc_config_data import (
    CATEGORY_ORDER,
    CATEGORY_TABLES,
    DEFAULT_SHORTLIST_DOC,
    REPO_ROOT,
    SelectedItem,
    dedupe_by_name,
    parse_capacity_gb,
    parse_millimetres,
    parse_module_layout,
    parse_number,
    parse_supported_sockets,
    parse_watts,
    read_csv_rows,
)

DEFAULT_SELECTION = Path(__file__).resolve().parent / "candidate_selection.json"
MIN_CANDIDATES = 19
MAX_CANDIDATES = 30


def load_selection(selection_path: Path, data_dir: Path) -> tuple[dict, list[SelectedItem]]:
    """按白名单读取候选行；任何型号缺失都直接失败，避免静默换型。"""

    config = json.loads(selection_path.read_text(encoding="utf-8"))
    table_cache: dict[str, list[dict[str, str]]] = {}
    selected: list[SelectedItem] = []

    for entry in config["items"]:
        category = entry["category"]
        if category not in CATEGORY_TABLES:
            raise ValueError(f"未知类别：{category}")
        table = CATEGORY_TABLES[category]
        if table not in table_cache:
            table_cache[table] = read_csv_rows(data_dir, table)
        matches = [row for row in table_cache[table] if row["name"].strip() == entry["name"]]
        if not matches:
            raise ValueError(f"候选型号不存在：{entry['name']}")
        chosen_rows, duplicates = dedupe_by_name(matches)
        if duplicates:
            print(f"[dedupe] {entry['name']} 命中 {len(matches)} 行，保留参考价最低的一条")
        selected.append(SelectedItem(category=category, row=chosen_rows[0], reason=entry["reason"]))

    _validate_brands(config, selected)
    _validate_counts(selected)
    _validate_platforms(config, selected)
    return config, selected


def _gpu_vendor(row: dict[str, str]) -> str:
    """显卡 brand 是板卡厂商（Asus/MSI），芯片厂商需从 chipset 推断。"""

    chipset = row.get("chipset", "").upper()
    if "RADEON" in chipset or chipset.startswith("RX "):
        return "AMD"
    return "NVIDIA"


def _validate_brands(config: dict, selected: list[SelectedItem]) -> None:
    allowed = config.get("brand_constraints", {})
    for item in selected:
        brands = allowed.get(item.category)
        if not brands:
            continue
        brand = _gpu_vendor(item.row) if item.category == "GPU" else item.row["brand"].strip()
        if brand not in brands:
            raise ValueError(
                f"{item.category} 品牌不在允许范围：{brand}（允许 {brands}）"
            )


def _validate_counts(selected: list[SelectedItem]) -> None:
    total = len(selected)
    if not MIN_CANDIDATES <= total <= MAX_CANDIDATES:
        raise ValueError(f"候选数量必须在 {MIN_CANDIDATES}-{MAX_CANDIDATES} 之间，当前 {total}")
    counts = {category: 0 for category in CATEGORY_ORDER}
    for item in selected:
        counts[item.category] += 1
    missing = [category for category, count in counts.items() if count == 0]
    if missing:
        raise ValueError(f"以下类别没有候选：{missing}")


def _validate_platforms(config: dict, selected: list[SelectedItem]) -> None:
    for pair in config.get("platform_pairs", []):
        socket = pair["cpu_socket"]
        cpu_count = sum(
            1 for item in selected if item.category == "CPU" and item.row["socket"] == socket
        )
        board_count = sum(
            1
            for item in selected
            if item.category == "MOTHERBOARD" and item.row["socket_cpu"] == socket
        )
        if cpu_count == 0 or board_count == 0:
            raise ValueError(f"平台 {pair['platform']} 缺少 CPU 或主板候选")


def key_spec_summary(category: str, row: dict[str, str]) -> str:
    """评审清单里只展示与该类别兼容性判断最相关的几个字段。"""

    if category == "CPU":
        return f"{row['socket']} / {row['core_count']}C{row['thread_count']}T / {parse_watts(row['tdp'])}W"
    if category == "GPU":
        vram = parse_capacity_gb(row.get("memory"))
        return f"{row['chipset']} / {vram}GB / {parse_watts(row['tdp'])}W / {parse_millimetres(row['length'])}mm"
    if category == "MOTHERBOARD":
        return f"{row['socket_cpu']} / {row['form_factor']} / {row['memory_type']} / M.2×{row['m_2_slots'].lower().count('m-key')}"
    if category == "MEMORY":
        modules, size = parse_module_layout(row.get("modules"))
        return f"{row['speed']} / {modules}×{size}GB / {row['form_factor'].split(' (')[0]}"
    if category == "STORAGE":
        return f"{parse_capacity_gb(row.get('capacity'))}GB / {row['interface']} / {row['form_factor']}"
    if category == "COOLER":
        sockets = parse_supported_sockets(row.get("cpu_socket"))
        height = parse_millimetres(row.get("height"))
        return f"{len(sockets)} sockets / {'水冷' if not height else f'{height}mm'}"
    if category == "CASE":
        return f"{row['maximum_video_card_length'].splitlines()[0].strip()} 显卡 / ATX Mid Tower"
    if category == "PSU":
        return f"{parse_watts(row['wattage'])}W / {row['efficiency_rating']} / 6+2×{row['pcie_6_2_pin_connectors']}"
    return ""


def write_shortlist_markdown(
    config: dict, selected: list[SelectedItem], output_path: Path
) -> None:
    """输出人工评审用清单，明确标注参考价不等于报价。"""

    lines = [
        "# PC 配置候选硬件清单",
        "",
        f"- 数据集版本：`{config['catalog_version']}`",
        f"- 候选数量：{len(selected)}",
        f"- 说明：{config.get('selection_notes', '')}",
        "- 参考价来自 PCPartPicker 快照，**不是中国区可购买报价**，不参与预算判断。",
        "",
        "| 类别 | 品牌 | 标准型号 | 关键规格 | 参考价 | 选择理由 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for category in CATEGORY_ORDER:
        items = [item for item in selected if item.category == category]
        for item in items:
            row = item.row
            price = parse_number(row.get("price"))
            price_text = f"{price:.2f}" if price is not None else "—"
            lines.append(
                f"| {category} | {row['brand']} | {row['name']} | "
                f"{key_spec_summary(category, row)} | {price_text} | {item.reason} |"
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_data_dir(cli_value: str | None) -> Path:
    raw = cli_value or os.environ.get("PC_DATA_DIR")
    if not raw:
        raise SystemExit("请通过 --data-dir 或环境变量 PC_DATA_DIR 指定硬件数据目录")
    data_dir = Path(raw)
    if not (data_dir / "csv").is_dir():
        raise SystemExit(f"数据目录缺少 csv/ 子目录：{data_dir}")
    return data_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 PC 配置候选硬件清单")
    parser.add_argument("--data-dir", help="Hardware data 根目录，也可用 PC_DATA_DIR")
    parser.add_argument("--selection", default=str(DEFAULT_SELECTION))
    parser.add_argument("--shortlist-doc", default=str(DEFAULT_SHORTLIST_DOC))
    parser.add_argument("--check-only", action="store_true", help="只校验，不写 Markdown")
    args = parser.parse_args(argv)

    data_dir = resolve_data_dir(args.data_dir)
    config, selected = load_selection(Path(args.selection), data_dir)
    if not args.check_only:
        write_shortlist_markdown(config, selected, Path(args.shortlist_doc))
        print(f"[ok] 候选清单已写入 {Path(args.shortlist_doc).relative_to(REPO_ROOT)}")
    print(f"[ok] 候选校验通过，共 {len(selected)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
