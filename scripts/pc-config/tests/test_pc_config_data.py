"""数据准备脚本的单元测试，运行方式：python -m unittest discover -s scripts/pc-config/tests"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import match_benchmarks as benchmarks  # noqa: E402
import normalize_specs as norms  # noqa: E402
import pc_config_data as data  # noqa: E402


class ParseHelpersTest(unittest.TestCase):
    def test_parse_watts_reads_number_and_unit(self) -> None:
        self.assertEqual(data.parse_watts("120 W"), 120)
        self.assertEqual(data.parse_watts("304 W"), 304)
        self.assertIsNone(data.parse_watts(""))

    def test_parse_capacity_converts_tb_to_gb(self) -> None:
        self.assertEqual(data.parse_capacity_gb("2 TB"), 2048)
        self.assertEqual(data.parse_capacity_gb("16 GB"), 16)
        self.assertIsNone(data.parse_capacity_gb("N/A"))

    def test_parse_millimetres_uses_first_line(self) -> None:
        raw = '392 mm\n                    15.433"'
        self.assertEqual(data.parse_millimetres(raw), 392)

    def test_parse_speed_reads_ddr_generation(self) -> None:
        self.assertEqual(data.parse_speed_mts("DDR5-6000"), 6000)
        self.assertIsNone(data.parse_speed_mts("unknown"))

    def test_parse_max_memory_speed_picks_highest(self) -> None:
        raw = "DDR5-4800\n          DDR5-6000\n          DDR5-8400"
        self.assertEqual(data.parse_max_memory_speed(raw), 8400)

    def test_parse_m2_slot_count_only_counts_m_key(self) -> None:
        raw = "2280/22110 M-key\n  2260/2280 M-key\n  2230 E-key"
        self.assertEqual(data.parse_m2_slot_count(raw), 2)

    def test_parse_module_layout(self) -> None:
        self.assertEqual(data.parse_module_layout("2 x 16GB"), (2, 16))
        self.assertEqual(data.parse_module_layout("invalid"), (None, None))

    def test_parse_external_power_distinguishes_connector_type(self) -> None:
        self.assertEqual(
            data.parse_external_power("3 x PCIe 8-pin"),
            {"connector_type": "PCIE_8PIN", "count": 3},
        )
        self.assertEqual(
            data.parse_external_power("1 x PCIe 16-pin 12VHPWR"),
            {"connector_type": "PCIE_12VHPWR", "count": 1},
        )

    def test_normalize_cpu_name_removes_frequency_and_core_suffix(self) -> None:
        self.assertEqual(
            data.normalize_cpu_name("AMD Ryzen 7 9800X3D 4.7 GHz 8-Core Processor"),
            "AMD Ryzen 7 9800X3D",
        )
        self.assertEqual(
            data.normalize_cpu_name("Intel Core Ultra 5 245K 4.2 GHz 14-Core Processor"),
            "Intel Core Ultra 5 245K",
        )


class SelectionHelpersTest(unittest.TestCase):
    def test_dedupe_by_name_keeps_lowest_price(self) -> None:
        rows = [
            {"name": "Same Model", "price": "120.00"},
            {"name": "Same Model", "price": "99.50"},
            {"name": "Other", "price": "10.00"},
        ]
        kept, duplicates = data.dedupe_by_name(rows)
        self.assertEqual(duplicates, 1)
        self.assertEqual(len(kept), 2)
        self.assertEqual(kept[0]["price"], "99.50")

    def test_case_form_factors_filters_indentation_fragments(self) -> None:
        raw = "ATX\n   \n   Micro ATX\n   Mini ITX"
        self.assertEqual(
            norms.parse_case_form_factors(raw), ["ATX", "Micro ATX", "Mini ITX"]
        )


class QualityStatusTest(unittest.TestCase):
    def test_missing_required_field_blocks_recommendation(self) -> None:
        status, recommendation, unverified = norms.evaluate_quality(
            "CPU", {"socket": "AM5", "core_count": 8, "thread_count": 16, "tdp_w": None}
        )
        self.assertEqual(status, "BLOCKED")
        self.assertEqual(recommendation, "BLOCKED")
        self.assertIn("tdp_w", unverified)

    def test_case_without_cooler_height_is_partial_not_blocked(self) -> None:
        status, recommendation, unverified = norms.evaluate_quality(
            "CASE",
            {"supported_mainboard_form_factors": ["ATX"], "max_gpu_length_mm": 392},
        )
        self.assertEqual(status, "PARTIAL")
        self.assertEqual(recommendation, "ELIGIBLE")
        self.assertEqual(unverified, ["max_cooler_height_mm"])


class ModelNameTest(unittest.TestCase):
    def test_cpu_model_name_drops_frequency_and_core_suffix(self) -> None:
        row = {"name": "AMD Ryzen 7 9800X3D 4.7 GHz 8-Core Processor"}
        self.assertEqual(norms.derive_model_name("CPU", row), "AMD Ryzen 7 9800X3D")

    def test_psu_model_name_stops_before_wattage(self) -> None:
        row = {
            "name": "MSI MAG A650GLS PCIE5 650 W 80+ Gold Certified Fully Modular ATX Power Supply"
        }
        self.assertEqual(norms.derive_model_name("PSU", row), "MSI MAG A650GLS PCIE5")

    def test_storage_model_name_drops_interface_suffix(self) -> None:
        row = {
            "name": "Kingston NV3 1 TB M.2-2280 PCIe 4.0 X4 NVME Solid State Drive"
        }
        self.assertEqual(norms.derive_model_name("STORAGE", row), "Kingston NV3 1 TB")


class BenchmarkMatchTest(unittest.TestCase):
    def test_cpu_matches_by_normalized_full_name(self) -> None:
        hardware = {"hardware_id": "cpu-x", "display_name": "AMD Ryzen 7 9800X3D 4.7 GHz 8-Core Processor"}
        rows = [{"name": "AMD Ryzen 7 9800X3D", "cpu_mark": "39917", "rank_no": "10", "samples": "1000"}]
        entry = benchmarks.match_cpu(hardware, rows)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry["score"], 39917.0)
        self.assertEqual(entry["match_method"], "EXACT_NAME")

    def test_gpu_prefers_same_vram_when_chipset_repeats(self) -> None:
        hardware = {
            "hardware_id": "gpu-x",
            "specifications": {"chipset": "GeForce RTX 5060 Ti", "vram_gb": 16},
        }
        rows = [
            {"name": "GeForce RTX 5060 Ti 8GB", "g3d_mark": "18000", "samples": "900"},
            {"name": "GeForce RTX 5060 Ti 16GB", "g3d_mark": "22000", "samples": "800"},
        ]
        entry = benchmarks.match_gpu(hardware, rows)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry["score"], 22000.0)
        self.assertEqual(entry["match_method"], "EXACT_CHIPSET_VRAM")


if __name__ == "__main__":
    unittest.main()
