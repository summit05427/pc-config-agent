"""Stage 1.4：把人工填写的报价模板校验并转换为运行时 offers.json。

VERIFIED 条目视为人工核验报价；MOCK 条目是端到端联调用的演示价，会带 price_source=MOCK_DEMO。
PENDING 条目会被跳过并计数。金额从人民币元转换为整数分，避免浮点误差进入预算计算。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pc_config_data import DEFAULT_OUTPUT_DIR, REPO_ROOT

DEFAULT_TEMPLATE_PATH = REPO_ROOT / "docs" / "pc-config" / "offers.template.json"
ALLOWED_PRICE_TYPES = {"NORMAL", "PROMO", "MEMBER"}
BLOCKED_URL_HOSTS = {"pcpartpicker.com", "www.pcpartpicker.com"}


class OfferValidationError(ValueError):
    pass


def price_to_fen(value: Any) -> int:
    """人民币元 → 整数分；拒绝非正数与超过两位小数的输入。"""

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise OfferValidationError(f"price_cny 不是合法数字：{value!r}") from error
    if amount <= 0:
        raise OfferValidationError(f"price_cny 必须大于 0：{value!r}")
    fen = amount * 100
    if fen != fen.to_integral_value():
        raise OfferValidationError(f"price_cny 最多两位小数：{value!r}")
    return int(fen)


def parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise OfferValidationError(f"{field} 缺少或不是字符串：{value!r}")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise OfferValidationError(f"{field} 必须是 YYYY-MM-DD：{value!r}") from error


def validate_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OfferValidationError("purchase_url 不能为空")
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise OfferValidationError(f"purchase_url 必须是 https 链接：{value!r}")
    if parsed.netloc.lower() in BLOCKED_URL_HOSTS:
        raise OfferValidationError("purchase_url 不能使用 PCPartPicker 参考链接")
    return value.strip()


def _require_text(entry: dict[str, Any], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise OfferValidationError(f"{field} 不能为空")
    return value.strip()


def validate_offer(entry: dict[str, Any], known_hardware_ids: set[str]) -> dict[str, Any]:
    """校验单条已核验报价，并转换为运行时结构。"""

    hardware_id = _require_text(entry, "hardware_id")
    if hardware_id not in known_hardware_ids:
        raise OfferValidationError(f"hardware_id 不在候选目录中：{hardware_id}")

    price_type = str(entry.get("price_type") or "").strip().upper()
    if price_type not in ALLOWED_PRICE_TYPES:
        raise OfferValidationError(f"price_type 非法：{entry.get('price_type')!r}")

    verified_at = parse_date(entry.get("verified_at"), "verified_at")
    valid_until = parse_date(entry.get("valid_until"), "valid_until")
    if valid_until < verified_at:
        raise OfferValidationError("valid_until 不得早于 verified_at")

    return {
        "offer_id": _require_text(entry, "offer_id"),
        "hardware_id": hardware_id,
        "category": _require_text(entry, "category"),
        "platform": _require_text(entry, "platform"),
        "seller": _require_text(entry, "seller"),
        "shop_name": entry.get("shop_name") or None,
        "title": _require_text(entry, "title"),
        "platform_sku": entry.get("platform_sku") or None,
        "price_fen": price_to_fen(entry.get("price_cny")),
        "price_type": price_type,
        "purchase_url": validate_url(entry.get("purchase_url")),
        "verified_at": verified_at.isoformat(),
        "valid_until": valid_until.isoformat(),
        "match_status": "VERIFIED",
        "price_source": "OWNER_VERIFIED",
        "notes": entry.get("notes") or None,
    }


def validate_mock_offer(entry: dict[str, Any], known_hardware_ids: set[str]) -> dict[str, Any]:
    """校验演示占位价：不校验 URL 与日期，但必须带 MOCK 标记，禁止混入核验数据。"""

    hardware_id = _require_text(entry, "hardware_id")
    if hardware_id not in known_hardware_ids:
        raise OfferValidationError(f"hardware_id 不在候选目录中：{hardware_id}")

    return {
        "offer_id": _require_text(entry, "offer_id"),
        "hardware_id": hardware_id,
        "category": _require_text(entry, "category"),
        "platform": entry.get("platform") or "MOCK_DEMO",
        "seller": entry.get("seller") or "演示数据",
        "shop_name": entry.get("shop_name") or "演示数据（非真实在售）",
        "title": _require_text(entry, "title"),
        "platform_sku": entry.get("platform_sku") or None,
        "price_fen": price_to_fen(entry.get("price_cny")),
        "price_type": "NORMAL",
        "purchase_url": None,
        "verified_at": None,
        "valid_until": None,
        "match_status": "MOCK",
        "price_source": "MOCK_DEMO",
        "notes": entry.get("notes") or "演示占位价，非真实在售报价",
    }


def build_offers(
    template: dict[str, Any], catalog: dict[str, Any], generated_at: str
) -> tuple[dict[str, Any], list[str]]:
    known_ids = {item["hardware_id"] for item in catalog["hardware"]}
    offers: list[dict[str, Any]] = []
    issues: list[str] = []
    seen_offer_ids: set[str] = set()
    skipped_pending = 0
    mock_count = 0

    for index, entry in enumerate(template.get("offers", []), start=1):
        status = str(entry.get("match_status") or "PENDING").strip().upper()
        if status == "PENDING":
            skipped_pending += 1
            continue
        if status not in {"VERIFIED", "MOCK"}:
            issues.append(f"第 {index} 条：match_status 非法（{status}）")
            continue
        try:
            if status == "MOCK":
                offer = validate_mock_offer(entry, known_ids)
            else:
                offer = validate_offer(entry, known_ids)
        except OfferValidationError as error:
            issues.append(f"第 {index} 条（{entry.get('offer_id')}）：{error}")
            continue
        if offer["offer_id"] in seen_offer_ids:
            issues.append(f"第 {index} 条：offer_id 重复（{offer['offer_id']}）")
            continue
        seen_offer_ids.add(offer["offer_id"])
        offers.append(offer)
        if status == "MOCK":
            mock_count += 1

    mock_offer_count = mock_count
    payload = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "data_status": "OWNER_VERIFIED" if mock_offer_count == 0 else "MIXED_DEMO",
        "currency": "CNY",
        "price_unit": "CNY_FEN",
        "catalog_version": catalog["catalog_version"],
        "offers": offers,
        "verified_offer_count": len(offers) - mock_offer_count,
        "mock_offer_count": mock_offer_count,
        "skipped_pending": skipped_pending,
    }
    return payload, issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验报价模板并生成 offers.json")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE_PATH))
    parser.add_argument("--catalog", default=str(DEFAULT_OUTPUT_DIR / "catalog.json"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR / "offers.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    template_path = Path(args.template)
    catalog_path = Path(args.catalog)
    for path in (template_path, catalog_path):
        if not path.is_file():
            raise SystemExit(f"缺少文件：{path}")

    template = json.loads(template_path.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload, issues = build_offers(template, catalog, generated_at)

    if issues:
        print("[error] 报价校验未通过：")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    if not payload["offers"]:
        print("[error] 没有 VERIFIED 报价，拒绝覆盖 offers.json")
        return 1

    if args.dry_run:
        print(f"[ok] 干跑通过：{payload['verified_offer_count']} 条 VERIFIED，"
              f"{payload['mock_offer_count']} 条 MOCK，跳过 {payload['skipped_pending']} 条 PENDING")
        return 0

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[ok] offers.json 已写入 {output_path.relative_to(REPO_ROOT)}："
          f"{payload['verified_offer_count']} 条 VERIFIED，"
          f"{payload['mock_offer_count']} 条 MOCK，跳过 {payload['skipped_pending']} 条 PENDING")
    return 0


if __name__ == "__main__":
    sys.exit(main())
