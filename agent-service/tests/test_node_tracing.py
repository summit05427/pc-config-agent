"""节点级追踪包装器：只观察不改变业务语义。"""

from typing import Any

import pytest
from structlog.testing import capture_logs

from app.agent.pc.node_tracing import (
    NODE_STATUS_ERROR,
    NODE_STATUS_SUCCESS,
    trace_node,
)
from app.core.metrics import NODE_DURATION


def _duration_count(node: str, status: str) -> float:
    for metric in NODE_DURATION.collect():
        for sample in metric.samples:
            if (
                sample.name == "agent_node_duration_seconds_count"
                and sample.labels == {"node": node, "status": status}
            ):
                return float(sample.value)
    return 0.0


def test_trace_node_returns_same_update_and_records_success() -> None:
    before = _duration_count("unit_node", NODE_STATUS_SUCCESS)
    wrapped = trace_node(
        "unit_node", lambda state: {"workflow_status": "success"}, agent_id="pc-config"
    )

    assert wrapped({"messages": []}) == {"workflow_status": "success"}
    assert _duration_count("unit_node", NODE_STATUS_SUCCESS) == before + 1


def test_trace_node_records_error_and_reraises() -> None:
    before = _duration_count("broken_node", NODE_STATUS_ERROR)

    def explode(state: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("node failed")

    wrapped = trace_node("broken_node", explode, agent_id="pc-config")

    with pytest.raises(RuntimeError, match="node failed"):
        wrapped({})
    assert _duration_count("broken_node", NODE_STATUS_ERROR) == before + 1


def test_trace_node_logs_thread_id_and_intermediate_status() -> None:
    wrapped = trace_node(
        "retry_node", lambda state: {"workflow_status": "retry"}, agent_id="pc-config"
    )
    config = {"configurable": {"thread_id": "user-1:thread-1"}}

    with capture_logs() as logs:
        wrapped({}, config)

    assert len(logs) == 1
    entry = logs[0]
    assert entry["event"] == "agent.node.completed"
    assert entry["node"] == "retry_node"
    assert entry["status"] == NODE_STATUS_SUCCESS
    assert entry["workflow_status"] == "retry"
    assert entry["thread_id"] == "user-1:thread-1"
    assert entry["agent_id"] == "pc-config"


def test_trace_node_tolerates_missing_config_and_non_string_status() -> None:
    wrapped = trace_node("plain_node", lambda state: {"workflow_status": 200}, agent_id="pc-config")

    with capture_logs() as logs:
        wrapped({})

    assert logs[0]["thread_id"] is None
    assert logs[0]["workflow_status"] is None


async def test_trace_node_supports_async_nodes_and_forwards_config() -> None:
    """requirement_parser / response_generator 是 async 节点，包装器必须按其签名转发 config。"""
    received: dict[str, Any] = {}

    async def async_node(state: dict[str, Any], *, config: Any) -> dict[str, Any]:
        received["thread_id"] = config["configurable"]["thread_id"]
        return {"workflow_status": "success"}

    wrapped = trace_node("async_node", async_node, agent_id="pc-config")

    update = await wrapped({}, {"configurable": {"thread_id": "user-1:thread-2"}})

    assert update == {"workflow_status": "success"}
    assert received["thread_id"] == "user-1:thread-2"
