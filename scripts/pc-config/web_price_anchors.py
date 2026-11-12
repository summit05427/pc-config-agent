"""把 WebSearch 记录的区间价格转换为可合并的参考价。

锚点只表示「大概的国内参考价」，不冒充商品成交价：
- 输出 `price_basis=WEB_ANCHOR`，`price_fen` 取区间中点；
- 必须记录检索词、来源链接与观测日期，便于追溯；
- 支持两种作用域：`hardware`（单型号直锚）与 `tier`（按粗档位批量锚定）。

锚点优先级低于详情页/搜索卡片观测，高于档位中位价，避免覆盖真实观测。
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fallback_pricing import coarse_key
from pc_config_data import REPO_ROOT

MKT = REPO_ROOT / "data" / "pc-config" / "export" / "marketplace"
DEFAULT_INPUT = MKT / "web_anchors.json"
DEFAULT_OUTPUT = MKT / "web_anchors_offers.json"
CATALOG = (
    REPO_ROOT / "application-service" / "src" / "main" / "resources" / "pc-config" / "catalog.json"
)
MAX_SPREAD_RATIO = 5.0


class AnchorValidationError(ValueError):
    """锚点数据不满足可追溯要求。"""


def _require_url(value: Any) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AnchorValidationError(f"来源链接必须是 http(s)：{value!r}")
    return text


def _parse_date(value: Any) -> str:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise AnchorValidationError(f"observed_at 必须是 YYYY-MM-DD：{value!r}") from error


def _match_value(actual: Any, expected: Any) -> bool:
    if actual is None:
        return False
    if isinstance(actual, list):
        return any(_match_value(item, expected) for item in actual)
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return float(actual) == float(expected)
    return str(actual).strip().lower() == str(expected).strip().lower()


def validate_anchor(anchor: dict[str, Any], index: int) -> dict[str, Any]:
    scope = anchor.get("scope") or {}
    scope_type = str(scope.get("type") or "")
    if scope_type not in {"hardware", "tier"}:
        raise AnchorValidationError(f"第 {index} 条：scope.type 只能是 hardware 或 tier")

    low = anchor.get("price_low_cny")
    high = anchor.get("price_high_cny")
    if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
        raise AnchorValidationError(f"第 {index} 条：价格区间必须是数字")
    if low <= 0 or high < low:
        raise AnchorValidationError(f"第 {index} 条：价格区间非法（{low}-{high}）")
    if high / low > MAX_SPREAD_RATIO:
        raise AnchorValidationError(f"第 {index} 条：区间跨度过大（{low}-{high}）")

    sources = anchor.get("sources") or []
    if not sources:
        raise AnchorValidationError(f"第 {index} 条：至少需要一条来源")
    for source in sources:
        _require_url(source.get("url"))
        price = source.get("price_cny")
        if price is not None:
            if not isinstance(price, (int, float)) or not low * 0.99 <= price <= high * 1.01:
                raise AnchorValidationError(f"第 {index} 条：来源价格 {price} 不在区间内")

    if scope_type == "hardware" and not scope.get("hardware_id"):
        raise AnchorValidationError(f"第 {index} 条：hardware 作用域缺少 hardware_id")
    if scope_type == "tier" and not scope.get("category"):
        raise AnchorValidationError(f"第 {index} 条：tier 作用域缺少 category")

    return {
        **anchor,
        "anchor_id": str(anchor.get("anchor_id") or f"anchor-{index:03d}"),
        "query": str(anchor.get("query") or "").strip(),
        "observed_at": _parse_date(anchor.get("observed_at")),
        "price_fen": int(round((low + high) * 100 / 2)),
        "source_count": len(sources),
    }


def tier_matches(anchor: dict[str, Any], hardware: dict[str, Any]) -> bool:
    scope = anchor["scope"]
    if hardware.get("category") != scope.get("category"):
        return False
    key = coarse_key(
        hardware["category"],
        hardware.get("specifications") or {},
        hardware.get("model_name") or "",
    )
    expected = tuple(scope.get("key") or ())
    if not key or not expected or key[: len(expected)] != expected:
        return False
    specs = hardware.get("specifications") or {}
    return all(_match_value(specs.get(field), value) for field, value in (scope.get("where") or {}).items())


def expand(anchors: list[dict[str, Any]], catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按作用域展开到硬件；同一硬件取「档位更具体、观测更近」的锚点。"""

    chosen: dict[str, tuple[tuple, dict[str, Any]]] = {}
    by_id = {row["hardware_id"]: row for row in catalog}
    for anchor in anchors:
        scope = anchor["scope"]
        if scope["type"] == "hardware":
            row = by_id.get(str(scope["hardware_id"]))
            if row is None:
                raise AnchorValidationError(f"hardware_id 不在目录中：{scope['hardware_id']}")
            targets = [row]
        else:
            targets = [row for row in catalog if tier_matches(anchor, row)]
        for row in targets:
            # 单型号锚点优先于档位锚点；同为档位时取更具体、观测更近的一条。
            rank = (scope["type"] == "hardware", len(scope.get("key") or ()), anchor["observed_at"])
            current = chosen.get(row["hardware_id"])
            if current is None or rank > current[0]:
                chosen[row["hardware_id"]] = (rank, anchor)
    return [
        {"hardware": by_id[hardware_id], "anchor": anchor}
        for hardware_id, (_, anchor) in chosen.items()
    ]


def build_offers(expanded: list[dict[str, Any]]) -> list[dict[str, Any]]:
    offers = []
    for item in expanded:
        hardware, anchor = item["hardware"], item["anchor"]
        low = anchor["price_low_cny"]
        high = anchor["price_high_cny"]
        offers.append({
            "hardware_id": hardware["hardware_id"],
            "category": hardware["category"],
            "title": hardware.get("model_name") or "",
            "price_fen": anchor["price_fen"],
            "sample_count": anchor["source_count"],
            "spread": round(high / low - 1, 4),
            "low_confidence": True,
            "price_basis": "WEB_ANCHOR",
            "url": anchor["sources"][0]["url"],
            "item_id": None,
            "shop": None,
            "notes": (
                f"WebSearch 区间 {low:.0f}-{high:.0f} 元，{anchor['source_count']} 个来源，"
                f"检索词「{anchor['query']}」"
            ),
            "observed_at": anchor["observed_at"],
        })
    return offers


def main() -> int:
    parser = argparse.ArgumentParser(description="把 WebSearch 区间锚点展开为参考价")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--catalog", default=str(CATALOG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    anchors_payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    anchors = [
        validate_anchor(anchor, index)
        for index, anchor in enumerate(anchors_payload.get("anchors") or [], start=1)
    ]
    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))["hardware"]
    offers = build_offers(expand(anchors, catalog))

    payload = {
        "provider": "web-search",
        "price_basis": "WEB_ANCHOR",
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "offers": offers,
    }
    print(f"锚点 {len(anchors)} 条，覆盖硬件 {len(offers)} 条")
    if not args.dry_run:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
