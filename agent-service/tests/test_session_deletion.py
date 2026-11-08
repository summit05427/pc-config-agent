"""会话删除墓碑测试：入队、重试、终态、取消、租约与清理。

删除接口只负责入队，真正的 checkpoint 删除发生在后台 worker；
因此这里直接驱动 `DeletionWorker.run_once`，避免依赖后台轮询时序。
所有用例只走公开 API（队列查询/状态/次数），不再触碰内部快照或内存字典。
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings
from app.core.exceptions import LockAcquisitionError
from app.core.metrics import SESSION_DELETION_TASKS
from app.services import lock, session_deletion
from app.services.session_deletion import constants as deletion_constants


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    """每条用例都从空状态开始，避免进程内墓碑串扰。"""
    session_deletion.reset_session_deletion()
    yield
    session_deletion.reset_session_deletion()


class FakeDeleter:
    """记录被删除的会话；`fail_times` 控制前几次失败。"""

    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls: list[str] = []

    async def __call__(self, thread_id: str) -> bool:
        self.calls.append(thread_id)
        if len(self.calls) <= self.fail_times:
            raise RuntimeError("checkpoint store down")
        return True


async def _status(user_id: str, thread_id: str) -> str | None:
    return await session_deletion.get_deletion_queue().status_of(user_id, thread_id)


def _make_worker(
    deleter: session_deletion.DeleteCheckpoint | None,
) -> session_deletion.DeletionWorker:
    return session_deletion.DeletionWorker(
        session_deletion.get_deletion_queue(), deleter
    )


# ---------------------------------------------------------------------------
# 内存路径
# ---------------------------------------------------------------------------


async def test_enqueue_then_process_marks_completed() -> None:
    """入队后的 pending 记录会被处理并标记完成。"""
    deleter = FakeDeleter()
    await session_deletion.setup_session_deletion(
        None, auto_setup=True, delete_checkpoint=deleter
    )
    await session_deletion.enqueue_session_deletion("user-1", "demo", "user-1:demo")

    processed = await _make_worker(deleter).run_once()

    assert processed == 1
    assert deleter.calls == ["user-1:demo"]
    assert await _status("user-1", "demo") == session_deletion.STATUS_COMPLETED
    assert (await session_deletion.get_deletion_queue().counts())["completed"] == 1


async def test_retry_exhaustion_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """持续失败按退避重排，达到上限后进入 failed 且不再尝试。"""
    monkeypatch.setattr(
        deletion_constants, "RETRY_BACKOFF_SECONDS", (0.0,)
    )
    deleter = FakeDeleter(fail_times=deletion_constants.MAX_ATTEMPTS)
    await session_deletion.setup_session_deletion(
        None, auto_setup=True, delete_checkpoint=deleter
    )
    await session_deletion.enqueue_session_deletion("user-1", "demo", "user-1:demo")
    worker = _make_worker(deleter)

    for _ in range(deletion_constants.MAX_ATTEMPTS):
        await worker.run_once()

    assert len(deleter.calls) == deletion_constants.MAX_ATTEMPTS
    assert await _status("user-1", "demo") == session_deletion.STATUS_FAILED

    # failed 是终态，不应再被领取
    assert await worker.run_once() == 0
    assert len(deleter.calls) == deletion_constants.MAX_ATTEMPTS


async def test_unsupported_checkpointer_marks_completed() -> None:
    """memory 后端删不掉检查点，但数据本就不持久，应视为完成。"""
    async def unsupported(thread_id: str) -> bool:
        return False

    await session_deletion.setup_session_deletion(
        None, auto_setup=True, delete_checkpoint=unsupported
    )
    await session_deletion.enqueue_session_deletion("user-1", "demo", "user-1:demo")

    await _make_worker(unsupported).run_once()

    assert await _status("user-1", "demo") == session_deletion.STATUS_COMPLETED


async def test_cancel_before_processing_skips_delete() -> None:
    """会话被重新使用时取消墓碑，后台不得再删检查点。"""
    deleter = FakeDeleter()
    await session_deletion.setup_session_deletion(
        None, auto_setup=True, delete_checkpoint=deleter
    )
    await session_deletion.enqueue_session_deletion("user-1", "demo", "user-1:demo")
    await session_deletion.cancel_pending_deletion("user-1", "demo")

    assert await _make_worker(deleter).run_once() == 0
    assert deleter.calls == []
    assert await _status("user-1", "demo") == session_deletion.STATUS_CANCELLED


async def test_lock_busy_reschedules_without_counting_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """会话正在生成时只顺延，不把「抢不到锁」算成删除失败。"""
    deleter = FakeDeleter()
    await session_deletion.setup_session_deletion(
        None, auto_setup=True, delete_checkpoint=deleter
    )
    await session_deletion.enqueue_session_deletion("user-1", "demo", "user-1:demo")

    async def busy_lock(thread_id: str) -> Any:
        raise LockAcquisitionError()

    monkeypatch.setattr(lock, "acquire_thread_lock", busy_lock)
    await _make_worker(deleter).run_once()

    queue = session_deletion.get_deletion_queue()
    assert await queue.status_of("user-1", "demo") == session_deletion.STATUS_PENDING
    assert await queue.attempts_of("user-1", "demo") == 0
    assert deleter.calls == []


async def test_purge_finished_removes_only_expired_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """清理只动过期的终态记录；仍 pending 的墓碑必须保留。"""
    deleter = FakeDeleter()
    await session_deletion.setup_session_deletion(
        None, auto_setup=True, delete_checkpoint=deleter
    )
    # 先让 done 走完一轮成为 completed，再入队 pending，避免被本轮领取
    await session_deletion.enqueue_session_deletion("user-1", "done", "user-1:done")
    await _make_worker(deleter).run_once()
    await session_deletion.enqueue_session_deletion(
        "user-1", "pending", "user-1:pending"
    )

    monkeypatch.setattr(deletion_constants, "COMPLETED_RETENTION_SECONDS", 0)
    monkeypatch.setattr(deletion_constants, "FAILED_RETENTION_SECONDS", 0)
    removed = await _make_worker(None).purge_finished()

    assert removed == 1
    assert await _status("user-1", "done") is None
    assert await _status("user-1", "pending") == session_deletion.STATUS_PENDING


async def test_worker_start_and_stop_are_safe() -> None:
    """重复启动不会创建多个消费者；停止后可以再次启动。"""
    deleter = FakeDeleter()
    await session_deletion.setup_session_deletion(
        None, auto_setup=True, delete_checkpoint=deleter
    )

    await session_deletion.start_session_deletion_worker()
    await session_deletion.start_session_deletion_worker()
    await session_deletion.stop_session_deletion_worker()
    await session_deletion.stop_session_deletion_worker()


async def test_update_metrics_sets_gauge_per_status() -> None:
    """Gauge 按状态分别暴露，便于发现长期未清理的墓碑。"""
    await session_deletion.setup_session_deletion(None, auto_setup=True)
    await session_deletion.enqueue_session_deletion("user-1", "demo", "user-1:demo")
    await _make_worker(None).update_metrics()

    assert SESSION_DELETION_TASKS.labels(status="pending")._value.get() == 1
    assert SESSION_DELETION_TASKS.labels(status="failed")._value.get() == 0


# ---------------------------------------------------------------------------
# 装配门面与边界分支
# ---------------------------------------------------------------------------


def test_unbound_queue_raises() -> None:
    """未绑定队列时直接失败，避免调用方以为墓碑已登记。"""
    with pytest.raises(RuntimeError, match="会话删除队列未绑定"):
        session_deletion.get_deletion_queue()


async def test_unbound_worker_start_raises_and_stop_is_noop() -> None:
    """未绑定 worker 时启动应失败；停止是安全空操作。"""
    with pytest.raises(RuntimeError, match="会话删除 worker 未绑定"):
        await session_deletion.start_session_deletion_worker()
    await session_deletion.stop_session_deletion_worker()


async def test_worker_without_deleter_returns_zero() -> None:
    """没有检查点删除函数时只告警，不消耗队列。"""
    await session_deletion.setup_session_deletion(None, auto_setup=True)
    await session_deletion.enqueue_session_deletion("user-1", "demo", "user-1:demo")

    assert await _make_worker(None).run_once() == 0
    assert await _status("user-1", "demo") == session_deletion.STATUS_PENDING


async def test_setup_failure_degrades_to_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """建表失败时降级为内存队列，服务仍可启动。"""
    async def failing_setup(self: Any) -> None:
        raise RuntimeError("ddl failed")

    monkeypatch.setattr(
        session_deletion.PostgresDeletionQueue, "setup", failing_setup
    )
    await session_deletion.setup_session_deletion(object(), auto_setup=True)
    await session_deletion.enqueue_session_deletion("user-1", "demo", "user-1:demo")

    assert await _status("user-1", "demo") == session_deletion.STATUS_PENDING


async def test_setup_without_auto_setup_keeps_postgres_and_degrades_on_error() -> None:
    """auto_setup=False 不建表；连接池不可用时入队/取消只告警不抛出。"""
    await session_deletion.setup_session_deletion(object(), auto_setup=False)

    assert await session_deletion.enqueue_session_deletion(
        "user-1", "demo", "user-1:demo"
    ) is False
    await session_deletion.cancel_pending_deletion("user-1", "demo")


async def test_setup_stops_previous_worker() -> None:
    """重复装配时先停旧 worker，避免两个循环消费同一队列。"""
    deleter = FakeDeleter()
    await session_deletion.setup_session_deletion(
        None, auto_setup=True, delete_checkpoint=deleter
    )
    await session_deletion.start_session_deletion_worker()

    await session_deletion.setup_session_deletion(
        None, auto_setup=True, delete_checkpoint=FakeDeleter()
    )
    await session_deletion.stop_session_deletion_worker()


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
        await session_deletion.setup_session_deletion(pool, auto_setup=True)
        yield pool
    finally:
        await pool.close()


async def _db_status(pool: AsyncConnectionPool, user_id: str, thread_id: str) -> str | None:
    async with pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT status FROM session_deletion_tasks"
            " WHERE user_id = %s AND thread_id = %s",
            (user_id, thread_id),
        )
        row = await cursor.fetchone()
    return None if not row else str(row[0])


async def _delete_rows(pool: AsyncConnectionPool, user_id: str, thread_id: str) -> None:
    async with pool.connection() as connection:
        await connection.execute(
            "DELETE FROM session_deletion_tasks WHERE user_id = %s AND thread_id = %s",
            (user_id, thread_id),
        )


async def _claim_by_id(user_id: str) -> list[session_deletion.ClaimedDeletion]:
    claimed = await session_deletion.get_deletion_queue().claim(1000)
    return [item for item in claimed if item.user_id == user_id]


async def test_postgres_row_survives_reconnect() -> None:
    """入队后关闭连接池，重新连接仍能读到并完成删除。"""
    user_id = f"pytest-{uuid4()}"
    thread_id = "demo"

    async with _open_pool() as pool:
        await session_deletion.enqueue_session_deletion(user_id, thread_id, f"{user_id}:demo")
        assert await _db_status(pool, user_id, thread_id) == session_deletion.STATUS_PENDING

    session_deletion.detach_session_deletion()

    async with _open_pool() as pool:
        deleter = FakeDeleter()
        try:
            await _make_worker(deleter).run_once()
            assert deleter.calls == [f"{user_id}:demo"]
            assert await _db_status(pool, user_id, thread_id) == session_deletion.STATUS_COMPLETED
        finally:
            await _delete_rows(pool, user_id, thread_id)


async def test_postgres_claim_is_leased() -> None:
    """租约内第二次领取不应返回同一行，避免多副本重复删除。"""
    user_id = f"pytest-{uuid4()}"

    async with _open_pool() as pool:
        try:
            await session_deletion.enqueue_session_deletion(user_id, "demo", f"{user_id}:demo")
            counts = await session_deletion.get_deletion_queue().counts()
            assert counts["pending"] >= 1
            assert len(await _claim_by_id(user_id)) == 1
            assert await _claim_by_id(user_id) == []
        finally:
            await _delete_rows(pool, user_id, "demo")


async def test_postgres_failure_counts_until_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """失败次数按行累计，达到上限后状态为 failed。"""
    monkeypatch.setattr(
        deletion_constants, "RETRY_BACKOFF_SECONDS", (0.0,)
    )
    user_id = f"pytest-{uuid4()}"
    deleter = FakeDeleter(fail_times=deletion_constants.MAX_ATTEMPTS)

    async with _open_pool() as pool:
        try:
            await session_deletion.enqueue_session_deletion(user_id, "demo", f"{user_id}:demo")
            worker = _make_worker(deleter)
            for _ in range(deletion_constants.MAX_ATTEMPTS):
                await worker.run_once()

            assert await _db_status(pool, user_id, "demo") == session_deletion.STATUS_FAILED
            assert len(deleter.calls) == deletion_constants.MAX_ATTEMPTS
        finally:
            await _delete_rows(pool, user_id, "demo")


async def test_postgres_lock_busy_reschedules_without_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Postgres 路径同样只顺延租约，不累计失败次数。"""
    user_id = f"pytest-{uuid4()}"
    deleter = FakeDeleter()

    async def busy_lock(thread_id: str) -> Any:
        raise LockAcquisitionError()

    async with _open_pool() as pool:
        try:
            await session_deletion.enqueue_session_deletion(user_id, "demo", f"{user_id}:demo")
            monkeypatch.setattr(lock, "acquire_thread_lock", busy_lock)
            await _make_worker(deleter).run_once()

            assert deleter.calls == []
            assert await _db_status(pool, user_id, "demo") == session_deletion.STATUS_PENDING
            assert await session_deletion.get_deletion_queue().attempts_of(
                user_id, "demo"
            ) == 0
        finally:
            await _delete_rows(pool, user_id, "demo")


async def test_postgres_cancel_prevents_delete() -> None:
    """取消后即使记录曾被领取，也不会真正删除检查点。"""
    user_id = f"pytest-{uuid4()}"
    deleter = FakeDeleter()

    async with _open_pool() as pool:
        try:
            await session_deletion.enqueue_session_deletion(user_id, "demo", f"{user_id}:demo")
            await session_deletion.cancel_pending_deletion(user_id, "demo")

            await _make_worker(deleter).run_once()
            assert deleter.calls == []
            assert await _db_status(pool, user_id, "demo") == session_deletion.STATUS_CANCELLED
        finally:
            await _delete_rows(pool, user_id, "demo")


async def test_postgres_purge_removes_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保留期为 0 时，completed 记录被清理，pending 记录保留。"""
    monkeypatch.setattr(deletion_constants, "COMPLETED_RETENTION_SECONDS", 0)
    monkeypatch.setattr(deletion_constants, "FAILED_RETENTION_SECONDS", 0)
    user_id = f"pytest-{uuid4()}"
    done_thread = "done"
    pending_thread = "pending"

    async with _open_pool() as pool:
        try:
            await session_deletion.enqueue_session_deletion(
                user_id, done_thread, f"{user_id}:{done_thread}"
            )
            await _make_worker(FakeDeleter()).run_once()
            assert await _db_status(pool, user_id, done_thread) == (
                session_deletion.STATUS_COMPLETED
            )

            # 处理完成后再入队，确保 pending 行没有被本轮领取
            await session_deletion.enqueue_session_deletion(
                user_id, pending_thread, f"{user_id}:{pending_thread}"
            )

            removed = await _make_worker(None).purge_finished()
            assert removed >= 1
            assert await _db_status(pool, user_id, done_thread) is None
            assert await _db_status(pool, user_id, pending_thread) == (
                session_deletion.STATUS_PENDING
            )
        finally:
            await _delete_rows(pool, user_id, done_thread)
            await _delete_rows(pool, user_id, pending_thread)
