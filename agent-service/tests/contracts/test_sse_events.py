"""SSE 事件契约测试。

`chat.py` 只产出 7 种事件；字段集合是前端解析器的输入契约。
这里用 `encode_event` 验证编码层没有丢事件名或改变负载结构。
"""

import json
from pathlib import Path
from typing import Any

from app.api.v1.sse import SCHEMA_VERSION_FIELD, SSE_SCHEMA_VERSION, encode_event

CONTRACT_PATH = Path(__file__).with_name("sse_events.json")
CONTRACT: dict[str, Any] = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

EXPECTED_EVENT_TYPES = {
    "token",
    "reasoning",
    "tool_call",
    "tool_result",
    "citations",
    "done",
    "error",
}


def test_contract_covers_every_event_type() -> None:
    """事件类型清单必须与 chat.py 实际产出保持一致。"""
    samples: dict[str, Any] = CONTRACT["samples"]
    assert set(samples) == EXPECTED_EVENT_TYPES
    assert set(CONTRACT["event_types"]) == EXPECTED_EVENT_TYPES


def test_contract_version_matches_encoder() -> None:
    """契约文件与编码层版本号必须一致，避免只改一处。"""
    assert CONTRACT["schema_version"] == SSE_SCHEMA_VERSION


def test_encode_event_keeps_name_and_payload_fields() -> None:
    """编码后事件名与字段集合不得变化；新增字段应作为契约更新显式提交。"""
    for event, sample in CONTRACT["samples"].items():
        encoded = encode_event(event, sample, 1)
        assert encoded.event == event
        payload = json.loads(encoded.data)
        # 编码层统一注入 schema_version，其余字段必须与契约逐一对齐
        assert set(payload) == set(sample) | {SCHEMA_VERSION_FIELD}
        assert payload[SCHEMA_VERSION_FIELD] == SSE_SCHEMA_VERSION
