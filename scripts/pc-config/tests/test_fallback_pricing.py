"""兜底报价估算的回归测试。

根因：容量类硬件缺档时会退回类别中位价，把 128GB 套条算成 16GB 的价格
（实测出现 128GB DDR5 报 ¥228）。这里锁定「按每 GB 单位价外推」的行为。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import fallback_pricing as pricing  # noqa: E402


def _memory_row(hardware_id: str, capacity_gb: int, memory_type: str = "DDR5") -> dict:
    return {
        "hardware_id": hardware_id,
        "category": "MEMORY",
        "model_name": f"Test {capacity_gb}GB {memory_type}",
        "specifications": {
            "memory_type": memory_type,
            "capacity_gb": capacity_gb,
        },
    }


class UnitMedianTest(unittest.TestCase):
    def test_unit_median_uses_price_per_gb(self) -> None:
        rows = [_memory_row("mem-16", 16), _memory_row("mem-32", 32)]
        prices = {"mem-16": 30_000, "mem-32": 60_000}

        medians = pricing.build_unit_medians(rows, prices)

        self.assertAlmostEqual(medians[("MEMORY", "ddr5")], 1875.0)

    def test_unit_median_splits_by_memory_generation(self) -> None:
        rows = [
            _memory_row("ddr5-16", 16, "DDR5"),
            _memory_row("ddr4-16", 16, "DDR4"),
        ]
        prices = {"ddr5-16": 48_000, "ddr4-16": 16_000}

        medians = pricing.build_unit_medians(rows, prices)

        self.assertAlmostEqual(medians[("MEMORY", "ddr5")], 3000.0)
        self.assertAlmostEqual(medians[("MEMORY", "ddr4")], 1000.0)

    def test_large_capacity_is_extrapolated_not_category_median(self) -> None:
        """128GB 缺同容量样本时，必须按容量外推，而不是复用 16GB 的类别中位价。"""

        rows = [_memory_row("mem-16", 16), _memory_row("mem-32", 32)]
        prices = {"mem-16": 30_000, "mem-32": 60_000}
        medians = pricing.build_medians(rows, prices)
        unit_medians = pricing.build_unit_medians(rows, prices)

        category_median = medians[("MEMORY",)]
        unit_price = unit_medians[("MEMORY", "ddr5")]
        extrapolated = int(round(unit_price * 128))

        # 类别中位价（16GB/32GB 的中位）会把 128GB 算成 ¥450，外推价必须是容量倍数。
        self.assertEqual(category_median, 45_000)
        self.assertEqual(extrapolated, 240_000)
        self.assertGreater(extrapolated, category_median * 4)

    def test_storage_subtype_uses_interface(self) -> None:
        row = {
            "hardware_id": "ssd-1",
            "category": "STORAGE",
            "model_name": "Test 1TB",
            "specifications": {"interface": "M.2 PCIe 4.0 x4", "capacity_gb": 1024},
        }
        prices = {"ssd-1": 51_200}

        medians = pricing.build_unit_medians([row], prices)

        self.assertAlmostEqual(medians[("STORAGE", "m.2 pcie 4.0 x4")], 50.0)


class GpuClassTest(unittest.TestCase):
    """型号分档：四位型号不能按 %100 取尾数，否则 7800 会被算成入门档。"""

    def test_amd_four_digit_uses_middle_digits(self) -> None:
        self.assertEqual(pricing.gpu_class("Radeon RX 7800 XT 16GB", {}), "high")
        self.assertEqual(pricing.gpu_class("Radeon RX 7900 XTX 24GB", {}), "top")
        self.assertEqual(pricing.gpu_class("Radeon RX 7600 XT 16GB", {}), "mid")

    def test_rdna4_and_nvidia_use_last_digits(self) -> None:
        self.assertEqual(pricing.gpu_class("Radeon RX 9070 XT 16GB", {}), "high")
        self.assertEqual(pricing.gpu_class("GeForce RTX 5070 Ti 16GB", {}), "high")
        self.assertEqual(pricing.gpu_class("GeForce RTX 5060 8GB", {}), "mid")

    def test_entry_level_models(self) -> None:
        self.assertEqual(pricing.gpu_class("GeForce RTX 3050 8GB", {}), "entry")
        self.assertEqual(pricing.gpu_class("Radeon RX 7500 XT 8GB", {}), "entry")


if __name__ == "__main__":
    unittest.main()
