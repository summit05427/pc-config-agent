"""现有 catalog.json 与治理 Schema 的兼容性：只增不改，历史键不得被删除。"""

from __future__ import annotations

import json

from conftest import REPO_ROOT
from hardware_schema import CATEGORY_FIELDS, DATA_QUALITY_STATUSES, LIFECYCLE_STATUSES

CATALOG_PATH = REPO_ROOT / "application-service" / "src" / "main" / "resources" / "pc-config" / "catalog.json"


def load_hardware() -> list[dict]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["hardware"]


def test_all_existing_specification_keys_are_registered() -> None:
    problems: list[str] = []
    for hardware in load_hardware():
        registered = {spec.name for spec in CATEGORY_FIELDS[hardware["category"]]}
        unknown = set(hardware["specifications"]) - registered
        if unknown:
            problems.append(f"{hardware['hardware_id']}: {sorted(unknown)}")
    assert problems == []


def test_existing_quality_status_stays_inside_enum() -> None:
    for hardware in load_hardware():
        assert hardware["data_quality_status"] in DATA_QUALITY_STATUSES


def test_existing_lifecycle_values_remain_valid() -> None:
    # Java 侧现有取值 DISCONTINUED/EOL 必须仍被治理 Schema 接受
    for hardware in load_hardware():
        assert hardware.get("lifecycle_status") in LIFECYCLE_STATUSES
