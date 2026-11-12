"""WebSearch 区间锚点的校验与展开测试。

锚点是「参考价」而非成交价，因此重点验证三件事：
1. 没有来源链接或价格不在区间内的锚点必须拒绝；
2. 档位锚点只能命中对应粗档，不能污染其他类别；
3. 单型号锚点优先于档位锚点。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import web_price_anchors as anchors  # noqa: E402


def _source(price: int) -> dict:
    return {"title": "示例报价页", "url": "https://example.com/price", "price_cny": price}


def _tier_anchor(key: list, low: int, high: int, **scope) -> dict:
    return {
        "anchor_id": "a1",
        "scope": {"type": "tier", "category": "MEMORY", "key": key, "where": scope.get("where") or {}},
        "price_low_cny": low,
        "price_high_cny": high,
        "query": "DDR5 32GB 价格",
        "observed_at": "2026-11-11",
        "sources": [_source(low)],
    }


def _memory(hardware_id: str, capacity: int, memory_type: str = "DDR5") -> dict:
    return {
        "hardware_id": hardware_id,
        "category": "MEMORY",
        "model_name": f"{memory_type} {capacity}GB",
        "specifications": {"memory_type": memory_type, "capacity_gb": capacity},
    }


class AnchorValidationTest(unittest.TestCase):
    def test_rejects_missing_sources(self) -> None:
        payload = {**_tier_anchor(["mem", 32, "ddr5"], 1499, 2293), "sources": []}
        with self.assertRaises(anchors.AnchorValidationError):
            anchors.validate_anchor(payload, 1)

    def test_rejects_source_price_outside_range(self) -> None:
        payload = {**_tier_anchor(["mem", 32, "ddr5"], 1499, 2293), "sources": [_source(3999)]}
        with self.assertRaises(anchors.AnchorValidationError):
            anchors.validate_anchor(payload, 1)

    def test_uses_range_midpoint(self) -> None:
        result = anchors.validate_anchor(_tier_anchor(["mem", 32, "ddr5"], 1500, 2300), 1)
        self.assertEqual(result["price_fen"], 190000)


class AnchorExpansionTest(unittest.TestCase):
    def test_tier_anchor_only_hits_matching_capacity(self) -> None:
        catalog = [_memory("mem-32", 32), _memory("mem-16", 16)]
        expanded = anchors.expand([anchors.validate_anchor(_tier_anchor(["mem", 32, "ddr5"], 1499, 2293), 1)], catalog)
        self.assertEqual([item["hardware"]["hardware_id"] for item in expanded], ["mem-32"])

    def test_hardware_anchor_wins_over_tier(self) -> None:
        catalog = [_memory("mem-32", 32)]
        tier = anchors.validate_anchor(_tier_anchor(["mem", 32, "ddr5"], 1499, 2293), 1)
        direct = anchors.validate_anchor({
            "anchor_id": "a2",
            "scope": {"type": "hardware", "hardware_id": "mem-32"},
            "price_low_cny": 1999,
            "price_high_cny": 1999,
            "query": "指定型号",
            "observed_at": "2026-11-11",
            "sources": [_source(1999)],
        }, 2)
        expanded = anchors.expand([tier, direct], catalog)
        self.assertEqual(expanded[0]["anchor"]["anchor_id"], "a2")


if __name__ == "__main__":
    unittest.main()
