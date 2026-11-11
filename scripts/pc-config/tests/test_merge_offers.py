"""合并阶段的异常价守卫测试：离谱的低置信观测不能进入求解。

实测出现过 RX 7800 XT 被观测成 ¥1000（多型号混卖页取 SKU 最低价），
这类价格一旦进入候选池，求解器会优先推荐它。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import merge_offers  # noqa: E402


def _gpu(hardware_id: str, model: str, vram: int = 16) -> dict:
    return {
        "hardware_id": hardware_id,
        "category": "GPU",
        "model_name": model,
        "specifications": {"vram_gb": vram, "chipset": ""},
    }


def _offer(hardware_id: str, price_fen: int, low_confidence: bool = False) -> dict:
    return {
        "hardware_id": hardware_id,
        "category": "GPU",
        "price_fen": price_fen,
        "price_basis": "SEARCH_LIST",
        "low_confidence": low_confidence,
    }


class DropImplausibleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hardware = {
            "gpu-a": _gpu("gpu-a", "Radeon RX 7600 XT 16GB"),
            "gpu-b": _gpu("gpu-b", "GeForce RTX 4060 Ti 16GB"),
            "gpu-c": _gpu("gpu-c", "GeForce RTX 4070 16GB"),
            "gpu-suspect": _gpu("gpu-suspect", "Radeon RX 7700 XT 16GB"),
        }
        self.reference = [
            _offer("gpu-a", 300_000),
            _offer("gpu-b", 320_000),
            _offer("gpu-c", 340_000),
            _offer("gpu-suspect", 100_000, low_confidence=True),
        ]

    def test_drops_price_far_below_tier_median(self) -> None:
        merged = [_offer("gpu-a", 300_000), _offer("gpu-suspect", 100_000, low_confidence=True)]

        kept, dropped = merge_offers.drop_implausible(merged, self.reference, self.hardware)

        self.assertEqual(dropped, 1)
        self.assertEqual([offer["hardware_id"] for offer in kept], ["gpu-a"])

    def test_keeps_low_confidence_offer_close_to_median(self) -> None:
        merged = [_offer("gpu-suspect", 290_000, low_confidence=True)]

        kept, dropped = merge_offers.drop_implausible(merged, self.reference, self.hardware)

        self.assertEqual(dropped, 0)
        self.assertEqual(len(kept), 1)

    def test_keeps_high_confidence_cheap_offer(self) -> None:
        """高置信观测即使便宜也保留：确实存在的促销价不能当异常剔除。"""

        merged = [_offer("gpu-suspect", 100_000, low_confidence=False)]

        kept, dropped = merge_offers.drop_implausible(merged, self.reference, self.hardware)

        self.assertEqual(dropped, 0)
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()
