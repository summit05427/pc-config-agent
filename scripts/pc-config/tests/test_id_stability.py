"""Stage 8.4 ID 稳定性：现有 28 条 catalog.json 的 hardware_id 必须可复现。"""

from __future__ import annotations

import json

from conftest import REPO_ROOT
from pc_config_data import build_hardware_id

CATALOG_PATH = REPO_ROOT / "application-service" / "src" / "main" / "resources" / "pc-config" / "catalog.json"


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_catalog_fixture_is_unchanged_in_size() -> None:
    assert len(load_catalog()["hardware"]) == 28


def test_every_existing_hardware_id_is_reproducible() -> None:
    mismatched = [
        hardware["hardware_id"]
        for hardware in load_catalog()["hardware"]
        if build_hardware_id(hardware["category"], hardware["model_name"]) != hardware["hardware_id"]
    ]
    assert mismatched == []


def test_slugify_is_stable_for_punctuation_and_plus() -> None:
    assert build_hardware_id("CPU", "AMD Ryzen 5 9600X") == "cpu-amd-ryzen-5-9600x"
    assert build_hardware_id("PSU", "Corsair RM850x (2021)") == "psu-corsair-rm850x-2021"
    assert build_hardware_id("CPU", "Intel Core i5-12400F") == "cpu-intel-core-i5-12400f"
