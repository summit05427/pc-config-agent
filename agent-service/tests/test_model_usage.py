"""使用明细上报测试：批量投递、重试升级为 dead、失败隔离。

上报是旁路能力：任何失败都不得改变对话结果，因此这里重点验证
「不抛异常」「可重试失败会持续重排」「4xx 直接 dead」三条契约。
"""

import asyncio
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from app.services import model_usage, usage_outbox
from app.services.control_plane import (
    CONTROL_PLANE_UNAVAILABLE,
    UPSTREAM_ERROR,
    ControlPlaneError,
)
from app.services.model_usage import (
    MAX_BATCH_SIZE,
    STATUS_SUCCESS,
    UsageReporter,
    reset_usage_reporter,
)

TEST_POLL_INTERVAL = 0.01


def _record(invocation_id: str) -> dict[str, Any]:
    """构造一条完整记录；Token 缺失用 None，禁止填 0。"""
    return {
        "invocation_id": invocation_id,
        "task_id": "task-1",
        "model_role": "conversation",
        "provider": "openai",
        "model_key": "openai:gpt-4o-mini",
        "credential_source": "MANAGED",
        "prompt_tokens": None,
        "completion_tokens": None,
        "latency_ms": 120,
        "status": STATUS_SUCCESS,
        "error_type": None,
        "occurred_at": "2026-10-30T08:00:00Z",
    }


class FakeClient:
    """记录每次上报的批次内容。"""

    def __init__(self, *, result: dict[str, Any] | None = None) -> None:
        self.batches: list[list[dict[str, Any]]] = []
        self._result = result or {"accepted": 1, "rejected": 0}

    async def report_usage(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        self.batches.append(list(records))
        return self._result

    @property
    def call_count(self) -> int:
        return len(self.batches)


class FailingClient:
    """每次调用都抛指定异常，用于验证重试与吞异常。"""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.call_count = 0

    async def report_usage(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        self.call_count += 1
        raise self._error


async def _wait_until(predicate: Callable[[], bool], deadline_seconds: float = 5.0) -> None:
    """轮询等待后台消费者完成，避免依赖固定 sleep 造成偶发失败。"""
    deadline = time.monotonic() + deadline_seconds
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("后台消费者未在超时内完成任务")
        await asyncio.sleep(0.01)


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    """每条用例都从空的 outbox 开始，避免进程内状态串扰。"""
    reset_usage_reporter()
    yield
    reset_usage_reporter()


async def test_batches_are_capped_and_flushed() -> None:
    """单批最多 20 条，剩余记录在同一轮内发完。"""
    client = FakeClient()
    reporter = UsageReporter(client=client, poll_interval_seconds=TEST_POLL_INTERVAL)

    for index in range(25):
        await reporter.enqueue(_record(f"inv-{index}"))  # type: ignore[arg-type]
    await reporter.start()
    # 重复 start 是幂等的，不应再起一个消费者
    await reporter.start()

    await _wait_until(lambda: reporter.forwarded_count == 25)
    await reporter.stop()

    assert [len(batch) for batch in client.batches] == [MAX_BATCH_SIZE, 5]


async def test_retryable_failure_is_rescheduled_until_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """可重试失败按退避重排，达到上限后进入 dead 且不再上报。"""
    # 退避为 0 只为让用例快速跑到上限，不改变状态机语义
    monkeypatch.setattr(usage_outbox, "RETRY_BACKOFF_SECONDS", (0.0,))
    error = ControlPlaneError(CONTROL_PLANE_UNAVAILABLE, 503, "unavailable", is_retryable=True)
    client = FailingClient(error)
    reporter = UsageReporter(client=client, poll_interval_seconds=TEST_POLL_INTERVAL)

    await reporter.enqueue(_record("inv-retry"))  # type: ignore[arg-type]
    await reporter.start()
    await _wait_until(
        lambda: reporter.failed_attempt_count >= usage_outbox.MAX_ATTEMPTS,
        deadline_seconds=10.0,
    )
    await reporter.stop()

    assert client.call_count == usage_outbox.MAX_ATTEMPTS
    pending, dead = await usage_outbox.counts()
    assert (pending, dead) == (0, 1)


async def test_non_retryable_failure_becomes_dead_without_retry() -> None:
    """4xx 重试只会放大错误，必须一次失败即放弃。"""
    error = ControlPlaneError(UPSTREAM_ERROR, 400, "bad request", is_retryable=False)
    client = FailingClient(error)
    reporter = UsageReporter(client=client, poll_interval_seconds=TEST_POLL_INTERVAL)

    await reporter.enqueue(_record("inv-rejected"))  # type: ignore[arg-type]
    await reporter.start()
    await _wait_until(lambda: reporter.failed_attempt_count == 1)
    await reporter.stop()

    assert client.call_count == 1
    pending, dead = await usage_outbox.counts()
    assert (pending, dead) == (0, 1)


async def test_unexpected_error_does_not_propagate() -> None:
    """序列化等未预期异常同样只记日志，不影响主链路。"""
    client = FailingClient(RuntimeError("boom"))
    reporter = UsageReporter(client=client, poll_interval_seconds=TEST_POLL_INTERVAL)

    await reporter.enqueue(_record("inv-unexpected"))  # type: ignore[arg-type]
    await reporter.start()
    await _wait_until(lambda: reporter.failed_attempt_count == 1)
    await reporter.stop()

    assert client.call_count == 1


async def test_partially_rejected_batch_is_dispatched() -> None:
    """Java 返回 rejected 只说明部分记录被拒，重发不会改变结果。"""
    client = FakeClient(result={"accepted": 0, "rejected": 1})
    reporter = UsageReporter(client=client, poll_interval_seconds=TEST_POLL_INTERVAL)

    await reporter.enqueue(_record("inv-partial"))  # type: ignore[arg-type]
    await reporter.start()
    await _wait_until(lambda: reporter.forwarded_count == 1)
    await reporter.stop()

    assert client.call_count == 1
    pending, dead = await usage_outbox.counts()
    assert (pending, dead) == (0, 0)


async def test_stop_without_start_is_safe() -> None:
    """未启动就停止属于正常收尾路径，不应抛错。"""
    await UsageReporter().stop()


async def test_module_helpers_share_one_reporter(monkeypatch: pytest.MonkeyPatch) -> None:
    """模块级入队与启停必须操作同一个单例，否则记录会丢失。"""
    client = FakeClient()
    monkeypatch.setattr(model_usage, "get_control_plane_client", lambda: client)

    await model_usage.start_usage_reporter()
    await model_usage.record_usage(_record("inv-module"))  # type: ignore[arg-type]
    await _wait_until(lambda: client.call_count == 1)
    await model_usage.stop_usage_reporter()

    assert client.batches[0][0]["invocation_id"] == "inv-module"


async def test_enqueue_falls_back_to_memory_when_db_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写库失败必须降级到内存队列并继续投递，而不是丢记录。"""
    monkeypatch.setattr(usage_outbox, "_pool", _BrokenPool())
    client = FakeClient()
    reporter = UsageReporter(client=client, poll_interval_seconds=TEST_POLL_INTERVAL)

    await reporter.enqueue(_record("inv-fallback"))  # type: ignore[arg-type]
    await reporter.start()
    await _wait_until(lambda: reporter.forwarded_count == 1)
    await reporter.stop()

    assert client.call_count == 1
    pending, dead = await usage_outbox.counts()
    assert (pending, dead) == (0, 0)


class _BrokenPool:
    """连接池不可用：用于验证写库异常被降级路径吞掉。"""

    def connection(self) -> Any:
        raise RuntimeError("database is down")
