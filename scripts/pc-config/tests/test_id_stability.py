"""ID 稳定性：运行时 catalog 的 hardware_id 必须唯一且可按主库命名复现。

主库对同型号重复记录会追加纯数字去重码（如 `-641085`），这类 ID 同样视为可复现。
"""

from __future__ import annotations

import json
import re

from conftest import REPO_ROOT
from pc_config_data import build_hardware_id

CATALOG_PATH = REPO_ROOT / "application-service" / "src" / "main" / "resources" / "pc-config" / "catalog.json"


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_catalog_fixture_has_unique_ids() -> None:
    hardware = load_catalog()["hardware"]
    ids = [item["hardware_id"] for item in hardware]

    assert ids
    assert len(ids) == len(set(ids))


def test_every_existing_hardware_id_is_reproducible() -> None:
    mismatched = [
        hardware["hardware_id"]
        for hardware in load_catalog()["hardware"]
        if not _is_reproducible(hardware)
    ]
    assert mismatched == []


def _is_reproducible(hardware: dict) -> bool:
    expected = build_hardware_id(hardware["category"], hardware["model_name"])
    if hardware["hardware_id"] == expected:
        return True
    return re.fullmatch(re.escape(expected) + r"-\d{4,}", hardware["hardware_id"]) is not None


def test_slugify_is_stable_for_punctuation_and_plus() -> None:
    assert build_hardware_id("CPU", "AMD Ryzen 5 9600X") == "cpu-amd-ryzen-5-9600x"
    assert build_hardware_id("PSU", "Corsair RM850x (2021)") == "psu-corsair-rm850x-2021"
    assert build_hardware_id("CPU", "Intel Core i5-12400F") == "cpu-intel-core-i5-12400f"
