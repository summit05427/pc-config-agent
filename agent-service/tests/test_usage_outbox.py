"""用量 outbox 测试：内存降级语义、DB 持久化、租约与清理。

内存侧是降级路径（重启即丢），DB 侧是生产路径；两侧共用同一套状态机，
因此两处都要覆盖「成功、可重试、不可重试、超上限」四类分支。
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings
from app.core.metrics import USAGE_OUTBOX_DEAD, USAGE_OUTBOX_PENDING
from app.services import usage_outbox


def _record(invocation_id: str) -> dict[str, Any]:
    return {
        "invocation_id": invocation_id,
        "task_id": "task-1",
        "model_role": "conversation",
        "provider": "openai",
        "model_key": "openai:gpt-4o-mini",
        "credential_source": "MANAGED",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "latency_ms": 120,
        "status": "success",
        "error_type": None,
        "occurred_at": "2026-10-30T08:00:00Z",
    }


@pytest.fixture(autouse=True)
def _reset_outbox() -> Iterator[None]:
    usage_outbox.reset_usage_outbox()
    yield
    usage_outbox.reset_usage_outbox()


class _BrokenPool:
    """连接池不可用：用于验证写库异常被降级路径吞掉。"""

    def connection(self) -> Any:
        raise RuntimeError("database is down")


# ---------------------------------------------------------------------------
# 内存降级路径
# ---------------------------------------------------------------------------


async def test_memory_add_claim_and_dispatch() -> None:
    """无连接池时记录进入内存队列，投递成功后即被移除。"""
    await usage_outbox.add(_record("inv-1"))
    await usage_outbox.add(_record("inv-2"))

    claimed = await usage_outbox.claim(10)
    assert [item.invocation_id for item in claimed] == ["inv-1", "inv-2"]
    assert all(item.source == usage_outbox.SOURCE_MEMORY for item in claimed)

    await usage_outbox.mark_dispatched(claimed)
    assert await usage_outbox.counts() == (0, 0)


async def test_memory_claim_is_leased() -> None:
    """领取会推进租约，同一行不会被同一轮重复领取。"""
    await usage_outbox.add(_record("inv-lease"))

    first = await usage_outbox.claim(10)
    second = await usage_outbox.claim(10)
    assert len(first) == 1
    assert second == []


async def test_memory_retry_then_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    """可重试失败重新排队，不可重试失败直接进入 dead。"""
    monkeypatch.setattr(usage_outbox, "RETRY_BACKOFF_SECONDS", (0.0,))
    await usage_outbox.add(_record("inv-retry"))

    first = await usage_outbox.claim(10)
    await usage_outbox.mark_failed(first, is_retryable=True, error="503")

    retried = await usage_outbox.claim(10)
    assert retried[0].attempts == 1

    await usage_outbox.mark_failed(retried, is_retryable=False, error="400")
    assert await usage_outbox.counts() == (0, 1)


async def test_memory_overflow_drops_oldest() -> None:
    """内存队列写满后丢弃最旧记录并累加溢出计数。"""
    for index in range(usage_outbox.MAX_MEMORY_QUEUE_SIZE + 1):
        await usage_outbox.add(_record(f"inv-{index}"))

    assert usage_outbox.memory_overflow_count() == 1
    claimed = await usage_outbox.claim(1)
    # 最旧的 inv-0 已被丢弃，队首是 inv-1
    assert claimed[0].invocation_id == "inv-1"


async def test_record_without_invocation_id_is_ignored() -> None:
    """缺少幂等键的记录无法去重，直接拒绝入队。"""
    await usage_outbox.add({"task_id": "task-1"})
    assert await usage_outbox.counts() == (0, 0)


async def test_write_failure_degrades_to_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """写库异常必须被吞掉并降级，不能影响模型调用主链路。"""
    monkeypatch.setattr(usage_outbox, "_pool", _BrokenPool())
    await usage_outbox.add(_record("inv-degraded"))

    claimed = await usage_outbox.claim(10)
    assert claimed[0].source == usage_outbox.SOURCE_MEMORY


async def test_update_metrics_logs_dead_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dead 新增时输出一次 error 日志；重复轮询不刷屏，dead 归零后可再次触发。"""
    errors: list[dict[str, Any]] = []
    monkeypatch.setattr(
        usage_outbox.logger,
        "error",
        lambda event, **fields: errors.append({"event": event, **fields}),
    )
    await usage_outbox.add(_record("inv-dead-alert"))

    claimed = await usage_outbox.claim(10)
    await usage_outbox.mark_failed(claimed, is_retryable=False, error="400")

    # 首轮：dead 从 0 增至 1，应告警一次
    await usage_outbox.update_metrics()
    assert len(errors) == 1
    assert errors[0]["event"] == "usage_outbox_dead_detected"
    assert errors[0]["dead_count"] == 1

    # 第二轮：dead 未变化，不得重复告警
    await usage_outbox.update_metrics()
    assert len(errors) == 1


async def test_update_metrics_reflects_pending_and_dead() -> None:
    """Gauge 应等于当前待投递量与死信量。"""
    await usage_outbox.add(_record("inv-pending"))
    await usage_outbox.add(_record("inv-dead"))

    claimed = await usage_outbox.claim(10)
    await usage_outbox.mark_failed(claimed[1:], is_retryable=False, error="400")
    await usage_outbox.update_metrics()

    assert USAGE_OUTBOX_PENDING._value.get() == 1
    assert USAGE_OUTBOX_DEAD._value.get() == 1


# ---------------------------------------------------------------------------
# Postgres 持久化路径（未启用 postgres 后端时跳过）
# ---------------------------------------------------------------------------


def _postgres_url() -> str:
    settings = get_settings()
    if settings.storage.backend != "postgres" or settings.storage.postgres_url is None:
        pytest.skip("当前未启用 postgres 后端")
    return settings.storage.postgres_url.get_secret_value()


@asynccontextmanager
async def _open_pool() -> AsyncIterator[AsyncConnectionPool]:
    """每次调用都新建连接池，用来模拟进程重启。"""
    pool = AsyncConnectionPool(
        conninfo=_postgres_url(),
        kwargs={"autocommit": True},
        open=False,
    )
    try:
        await pool.open(timeout=10)
    except Exception as exc:  # 数据库没起来时跳过，而不是让整个测试套件失败
        pytest.skip(f"Postgres 不可用：{exc}")

    try:
        await usage_outbox.setup_usage_outbox(pool, auto_setup=True)
        yield pool
    finally:
        await pool.close()


async def _fetch_status(pool: AsyncConnectionPool, invocation_id: str) -> str | None:
    async with pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT status FROM usage_outbox WHERE invocation_id = %s", (invocation_id,)
        )
        row = await cursor.fetchone()
    return None if not row else str(row[0])


async def _count_rows(pool: AsyncConnectionPool, invocation_id: str) -> int:
    async with pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT COUNT(*) FROM usage_outbox WHERE invocation_id = %s", (invocation_id,)
        )
        row = await cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


async def _delete_rows(pool: AsyncConnectionPool, invocation_id: str) -> None:
    async with pool.connection() as connection:
        await connection.execute(
            "DELETE FROM usage_outbox WHERE invocation_id = %s", (invocation_id,)
        )


async def _claim_by_id(invocation_id: str) -> list[usage_outbox.ClaimedRecord]:
    """领取一批后只保留目标记录，避免受残留数据影响。"""
    claimed = await usage_outbox.claim(1000)
    return [item for item in claimed if item.invocation_id == invocation_id]


async def test_postgres_record_survives_reconnect() -> None:
    """写入后关闭连接池，重新连接仍能读到，验证真持久化。"""
    invocation_id = f"pytest-{uuid4()}"

    async with _open_pool() as pool:
        await usage_outbox.add(_record(invocation_id))
        assert await _fetch_status(pool, invocation_id) == usage_outbox.STATUS_PENDING

    usage_outbox.detach_usage_outbox()

    async with _open_pool() as pool:
        try:
            claimed = await _claim_by_id(invocation_id)
            assert len(claimed) == 1
            await usage_outbox.mark_dispatched(claimed)
            assert await _fetch_status(pool, invocation_id) == usage_outbox.STATUS_DISPATCHED
        finally:
            await _delete_rows(pool, invocation_id)


async def test_postgres_duplicate_invocation_is_ignored() -> None:
    """同一 invocation_id 重复写入只保留一条，保证 Java 台账不被重复计费。"""
    invocation_id = f"pytest-{uuid4()}"

    async with _open_pool() as pool:
        try:
            await usage_outbox.add(_record(invocation_id))
            await usage_outbox.add(_record(invocation_id))
            assert await _count_rows(pool, invocation_id) == 1
        finally:
            await _delete_rows(pool, invocation_id)


async def test_postgres_claim_lease_is_exclusive() -> None:
    """领取后租约内第二次领取不应再返回同一行。"""
    invocation_id = f"pytest-{uuid4()}"

    async with _open_pool() as pool:
        try:
            await usage_outbox.add(_record(invocation_id))
            assert len(await _claim_by_id(invocation_id)) == 1
            assert await _claim_by_id(invocation_id) == []
        finally:
            await _delete_rows(pool, invocation_id)


async def test_postgres_retry_and_dead_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """可重试失败回到 pending 且 attempts 递增，不可重试失败直接 dead。"""
    monkeypatch.setattr(usage_outbox, "RETRY_BACKOFF_SECONDS", (0.0,))
    invocation_id = f"pytest-{uuid4()}"

    async with _open_pool() as pool:
        try:
            await usage_outbox.add(_record(invocation_id))

            claimed = await _claim_by_id(invocation_id)
            await usage_outbox.mark_failed(claimed, is_retryable=True, error="503")
            assert await _fetch_status(pool, invocation_id) == usage_outbox.STATUS_PENDING

            retried = await _claim_by_id(invocation_id)
            assert retried[0].attempts == 1
            await usage_outbox.mark_failed(retried, is_retryable=False, error="400")
            assert await _fetch_status(pool, invocation_id) == usage_outbox.STATUS_DEAD
        finally:
            await _delete_rows(pool, invocation_id)


async def test_postgres_purge_removes_old_dispatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保留期归零时，已投递记录应被清理；pending 记录不受影响。"""
    monkeypatch.setattr(usage_outbox, "DISPATCHED_RETENTION_SECONDS", 0)
    dispatched_id = f"pytest-{uuid4()}"
    pending_id = f"pytest-{uuid4()}"

    async with _open_pool() as pool:
        try:
            await usage_outbox.add(_record(dispatched_id))
            await usage_outbox.add(_record(pending_id))

            claimed = await _claim_by_id(dispatched_id)
            await usage_outbox.mark_dispatched(claimed)
            assert await _fetch_status(pool, dispatched_id) == usage_outbox.STATUS_DISPATCHED

            await usage_outbox.purge_dispatched()
            assert await _fetch_status(pool, dispatched_id) is None
            assert await _fetch_status(pool, pending_id) == usage_outbox.STATUS_PENDING
        finally:
            await _delete_rows(pool, dispatched_id)
            await _delete_rows(pool, pending_id)
