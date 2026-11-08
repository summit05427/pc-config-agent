"""OpenAPI 契约快照测试。

快照由 `scripts/snapshot_openapi.py` 从代码生成（生产环境关闭 OpenAPI，
拿不到线上 `/openapi.json`）。契约变化必须显式重新生成快照，
让评审看到「改了接口」，而不是悄悄漂移。
"""

import json
from pathlib import Path
from typing import Any

from app.main import app

SNAPSHOT_PATH = Path(__file__).with_name("openapi_snapshot.json")


def _canonical(schema: dict[str, Any]) -> str:
    """与快照脚本一致的序列化格式：UTF-8 不转义、键排序、单换行结尾。"""
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def test_snapshot_file_is_canonical() -> None:
    """快照必须由脚本生成，避免手改导致两次生成出现格式 diff。"""
    assert SNAPSHOT_PATH.is_file(), (
        "缺少 OpenAPI 快照，请运行 "
        "`uv --directory agent-service run python ../scripts/snapshot_openapi.py`"
    )
    text = SNAPSHOT_PATH.read_text(encoding="utf-8")
    assert text == _canonical(json.loads(text))


def test_openapi_matches_snapshot() -> None:
    """线上契约与仓库快照必须一致；变更时重新生成并同步 docs/api-contract.md。"""
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert app.openapi() == expected
