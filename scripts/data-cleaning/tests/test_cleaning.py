"""Stage 1/2 清洗规则的单元测试。

重点验证：
1. 单位解析不会把 "288 mm" 当成无单位数字；
2. 只有 MPN 精确一致才自动合并，不同品牌/不同显存必须保留；
3. 清洗链路不读取任何跑分文件。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cleaning_common import parse_capacity_gb, parse_modules  # noqa: E402
from spec_normalizer import (  # noqa: E402
    chipset_short,
    normalize_gpu,
)
from stage2_clean import group_records  # noqa: E402


def _record(pcpp_id: str, *, brand: str, model: str, mpn: list[str],
            vram: float = 16.0, chipset: str = "GeForce RTX 5070") -> dict:
    return {
        "pcpp_id": pcpp_id,
        "category": "GPU",
        "brand": brand,
        "model_name": model,
        "mpn_values": mpn,
        "image_url": None,
        "source_url": f"https://example.com/{pcpp_id}",
        "reference_price_usd": None,
        "raw_specs": {},
        "specifications": {
            "chipset": chipset,
            "vram_gb": vram,
            "memory_type": "GDDR7",
            "length_mm": 300,
            "anomalies": [],
        },
        "quality_status": "GOOD",
        "quality_reasons": [],
    }


class ParseTest(unittest.TestCase):
    def test_capacity_units(self) -> None:
        self.assertEqual(parse_capacity_gb("1 TB"), 1024)
        self.assertEqual(parse_capacity_gb("512 GB"), 512)
        self.assertEqual(parse_modules("2 x 16GB"), (2, 32))

    def test_gpu_length_with_mm_suffix(self) -> None:
        specs = normalize_gpu({"Memory": "16 GB", "Length": "288 mm", "TDP": "250 W"})
        self.assertEqual(specs["length_mm"], 288)
        self.assertEqual(specs["vram_gb"], 16)

    def test_chipset_short(self) -> None:
        self.assertEqual(chipset_short("AMD B850"), "B850")
        self.assertEqual(chipset_short("Intel Z890"), "Z890")


class DedupeTest(unittest.TestCase):
    def test_same_mpn_merges(self) -> None:
        groups = group_records([
            _record("1", brand="ASUS", model="TUF 5070", mpn=["TUF-5070"]),
            _record("2", brand="ASUS", model="TUF 5070", mpn=["TUF-5070"]),
        ])
        self.assertEqual(len(groups), 1)

    def test_different_brand_not_merged(self) -> None:
        groups = group_records([
            _record("1", brand="ASUS", model="Dual 5070", mpn=["A"]),
            _record("2", brand="MSI", model="Dual 5070", mpn=["B"]),
        ])
        self.assertEqual(len(groups), 2)

    def test_different_vram_not_merged(self) -> None:
        groups = group_records([
            _record("1", brand="ASUS", model="TUF 5060 Ti", mpn=["A"], vram=8.0),
            _record("2", brand="ASUS", model="TUF 5060 Ti", mpn=["B"], vram=16.0),
        ])
        self.assertEqual(len(groups), 2)

    def test_multi_mpn_record_not_duplicated(self) -> None:
        groups = group_records([
            _record("1", brand="ASUS", model="TUF 5070", mpn=["A", "A2"]),
            _record("2", brand="ASUS", model="TUF 5070", mpn=["A2"]),
        ])
        flattened = [item["pcpp_id"] for group in groups for item in group]
        self.assertEqual(sorted(flattened), ["1", "2"])


class NoBenchmarkDependencyTest(unittest.TestCase):
    def test_cleaning_scripts_do_not_reference_benchmarks(self) -> None:
        for name in ("cleaning_common.py", "spec_normalizer.py", "stage1_audit.py", "stage2_clean.py"):
            text = (SCRIPT_DIR / name).read_text(encoding="utf-8").lower()
            self.assertNotIn("passmark", text, name)
            self.assertNotIn("hardware-benchmarks", text, name)


if __name__ == "__main__":
    unittest.main()
