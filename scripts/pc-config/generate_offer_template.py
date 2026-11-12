"""Stage 1.4 辅助：按候选目录生成报价填写模板。

模板面向人工填写：金额用人民币元、日期用 YYYY-MM-DD；
入库时由 ingest_offers.py 统一转换为分并做校验。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pc_config_data import CATEGORY_ORDER, DEFAULT_OUTPUT_DIR, REPO_ROOT

DEFAULT_TEMPLATE_PATH = REPO_ROOT / "docs" / "pc-config" / "offers.template.json"

INSTRUCTIONS = [
    "只填写能核验的报价；不采购或不确定的条目保持 match_status=PENDING，入库时会被跳过。",
    "price_cny 填人民币元，最多两位小数；入库脚本会转换为整数分。",
    "purchase_url 可填可空；填写时只要求是 http(s) 地址，不校验店铺、可达性或是否为具体商品页。",
    "verified_at 与 valid_until 使用 YYYY-MM-DD，valid_until 不得早于 verified_at。",
    "同一硬件有多个商家时，复制条目并修改 offer_id 后缀（-01、-02），保留 hardware_id 不变。",
    "不要删除字段，未知值填 null；match_status 只允许 PENDING 或 VERIFIED。",
]


def build_entry(hardware: dict[str, Any]) -> dict[str, Any]:
    reference_price = hardware.get("source", {}).get("reference_price")
    return {
        "offer_id": f"offer-{hardware['hardware_id']}-01",
        "hardware_id": hardware["hardware_id"],
        "category": hardware["category"],
        "brand": hardware["brand"],
        "hardware_model": hardware["model_name"],
        "reference_price": reference_price,
        "reference_price_note": "PCPartPicker 快照，币种存疑，仅作填写参考，不会进入推荐",
        "platform": None,
        "seller": None,
        "shop_name": None,
        "title": None,
        "platform_sku": None,
        "price_cny": None,
        "price_type": "NORMAL",
        "purchase_url": None,
        "verified_at": None,
        "valid_until": None,
        "match_status": "PENDING",
        "notes": None,
    }


def build_template(catalog: dict[str, Any], generated_at: str) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        for hardware in catalog["hardware"]:
            if hardware["category"] == category:
                entries.append(build_entry(hardware))
    return {
        "schema_version": "1.0.0",
        "data_status": "DRAFT",
        "currency": "CNY",
        "price_unit": "CNY_YUAN",
        "catalog_version": catalog["catalog_version"],
        "generated_at": generated_at,
        "instructions": INSTRUCTIONS,
        "offers": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成中国区报价填写模板")
    parser.add_argument("--catalog", default=str(DEFAULT_OUTPUT_DIR / "catalog.json"))
    parser.add_argument("--output", default=str(DEFAULT_TEMPLATE_PATH))
    args = parser.parse_args(argv)

    catalog_path = Path(args.catalog)
    if not catalog_path.is_file():
        raise SystemExit(f"缺少 {catalog_path}，请先运行 build_fixtures.py")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    template = build_template(catalog, catalog["generated_at"])

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[ok] 报价模板已写入 {output_path.relative_to(REPO_ROOT)}，共 {len(template['offers'])} 条待填")
    return 0


if __name__ == "__main__":
    sys.exit(main())
