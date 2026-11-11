"""补齐机箱规格：从 raw_specs 与商品名推导板型支持与显卡限长。

主库 CASE 记录的 specifications 为空，原因是历史构建时字段未落盘；raw_specs 里其实
保留了 maximum_video_card_length，商品名里带 "ATX / MicroATX / Mini ITX" 板型线索。
本脚本只修 CASE，其它类别原样保留，并同步更新运行时目录。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from normalize_specs import parse_millimetres

REPO_ROOT = Path(__file__).resolve().parents[2]
MASTER_PATH = REPO_ROOT / "data" / "pc-config" / "master" / "hardware-master.jsonl"
CATALOG_PATH = REPO_ROOT / "application-service" / "src" / "main" / "resources" / "pc-config" / "catalog.json"

# 大机箱向下兼容小板型；顺序即校验器比对的字符串。
FORM_FACTORS = {
    "EATX": ["EATX", "ATX", "Micro ATX", "Mini ITX"],
    "ATX": ["ATX", "Micro ATX", "Mini ITX"],
    "M_ATX": ["Micro ATX", "Mini ITX"],
    "ITX": ["Mini ITX"],
}


def case_form_factors(record: dict) -> list[str]:
    text = " ".join([record.get("model_name") or ""] + (record.get("aliases") or [])).lower()
    if re.search(r"e-?atx|xl[- ]atx", text):
        return FORM_FACTORS["EATX"]
    if re.search(r"micro-?atx|micro atx|m-?atx", text):
        return FORM_FACTORS["M_ATX"]
    if re.search(r"mini-?itx|mini itx", text):
        return FORM_FACTORS["ITX"]
    if re.search(r"\batx\b", text):
        return FORM_FACTORS["ATX"]
    return []


def build_case_specifications(record: dict) -> dict:
    raw = record.get("raw_specs") or {}
    return {
        "supported_mainboard_form_factors": case_form_factors(record),
        "max_gpu_length_mm": parse_millimetres(raw.get("maximum_video_card_length")),
        # 主库没有散热器限高与电源仓板型，保持 None，不猜测。
        "max_cooler_height_mm": None,
        "psu_form_factor": None,
        "radiator_support": None,
        "expansion_slots": None,
    }


def main() -> int:
    lines = [json.loads(line) for line in MASTER_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    specs_by_id: dict[str, dict] = {}
    for record in lines:
        if record["category"] != "CASE":
            continue
        specifications = build_case_specifications(record)
        record["specifications"] = specifications
        specs_by_id[record["hardware_id"]] = specifications

    MASTER_PATH.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in lines) + "\n",
        encoding="utf-8",
    )

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    patched = 0
    for entry in catalog["hardware"]:
        if entry["hardware_id"] in specs_by_id:
            entry["specifications"] = specs_by_id[entry["hardware_id"]]
            patched += 1
    version = catalog["catalog_version"]
    match = re.search(r"-(\d+)$", version)
    catalog["catalog_version"] = f"{version[:match.start()]}-{int(match.group(1)) + 1}" if match else f"{version}-2"
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with_form = sum(1 for specs in specs_by_id.values() if specs["supported_mainboard_form_factors"])
    with_length = sum(1 for specs in specs_by_id.values() if specs["max_gpu_length_mm"])
    print(f"主库机箱 {len(specs_by_id)} 条，板型可判定 {with_form}，限长可判定 {with_length}，目录更新 {patched}，版本 {catalog['catalog_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
