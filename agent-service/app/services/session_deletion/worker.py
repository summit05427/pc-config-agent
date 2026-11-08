"""后台删除 worker：只负责调度，不关心墓碑存在内存还是 Postgres。

每轮流程：领取一批 → 会话锁内再确认状态 → 删除检查点 → 推进完成/退避。
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

import structlog

from app.core.exceptions import LockAcquisitionError
from app.core.metrics import SESSION_DELETION_TASKS
from app.services.session_deletion import constants
from app.services.session_deletion.interface import DeleteCheckpoint, DeletionQueue

logger = structlog.get_logger(__name__)


def _truncate(error: str) -> str:
    return error[: constants.MAX_ERROR_LENGTH]


class DeletionWorker:
    """墓碑消费者；`delete_checkpoint` 为空时只告警，不消耗队列。"""

    def __init__(
        self,
        queue: DeletionQueue,
        delete_checkpoint: DeleteCheckpoint | None,
    ) -> None:
        self._queue = queue
        self._delete_checkpoint = delete_checkpoint
        self._task: asyncio.Task[None] | None = None
        self._stopped = False

    async def run_once(self, limit: int = constants.BATCH_SIZE) -> int:
        """处理一批墓碑；返回实际处理的条数（含失败与取消）。"""
        delete_checkpoint = self._delete_checkpoint
        if delete_checkpoint is None:
            logger.warning("session_deletion.no_deleter")
            return 0

        # 延迟导入：取消/重试都要与对话共用同一把会话锁，但锁模块不属于 core；
        # 测试通过 monkeypatch `app.services.lock.acquire_thread_lock` 控制锁行为
        from app.services.lock import acquire_thread_lock

        claimed = await self._queue.claim(limit)
        processed = 0
        for item in claimed:
            processed += 1
            # 领取后可能已被新一轮对话取消，先看状态再动手
            if (
                await self._queue.status_of(item.user_id, item.thread_id)
                != constants.STATUS_PENDING
            ):
                continue

            lock_handle = None
            lock_degraded = False
            try:
                lock_handle = await acquire_thread_lock(item.checkpoint_thread_id)
            except LockAcquisitionError as exc:
                # 抢不到锁说明会话正在生成，等下一轮再删
                logger.info(
                    "session_deletion.lock_busy", error_type=type(exc).__name__
                )
                await self._queue.reschedule(item.user_id, item.thread_id)
                continue
            except Exception as exc:
                # 锁基础设施故障（如 Redis 掉线）：降级为无锁执行，
                # 否则墓碑会一直卡在 pending，检查点永远删不掉
                lock_degraded = True
                logger.warning(
                    "session_deletion.lock_unavailable",
                    error_type=type(exc).__name__,
                )
            if lock_handle is None and not lock_degraded:
                # Redis 未启用：单副本部署可接受，多副本下删除与生成可能并发
                logger.info("session_deletion.lock_unavailable")

            try:
                # 拿到锁后再确认一次，避免「领取 → 取消 → 误删」
                if (
                    await self._queue.status_of(item.user_id, item.thread_id)
                    != constants.STATUS_PENDING
                ):
                    continue
                deleted = await delete_checkpoint(item.checkpoint_thread_id)
                if not deleted:
                    await self._queue.complete(
                        item.user_id,
                        item.thread_id,
                        "checkpointer unsupported",
                    )
                    continue
                await self._queue.complete(item.user_id, item.thread_id)
            except Exception as exc:
                error = _truncate(f"{type(exc).__name__}: {exc}")
                status = await self._queue.fail(
                    item.user_id, item.thread_id, item.attempts + 1, error
                )
                logger.warning(
                    "session_deletion.delete_failed",
                    attempts=item.attempts + 1,
                    status=status,
                    error_type=type(exc).__name__,
                )
            finally:
                if lock_handle is not None:
                    await lock_handle.release()
        return processed

    async def update_metrics(self) -> None:
        """刷新墓碑状态指标；查询失败只告警。"""
        try:
            snapshot = await self._queue.counts()
        except Exception as exc:
            logger.warning(
                "session_deletion.metrics_failed", error_type=type(exc).__name__
            )
            return
        for status, count in snapshot.items():
            SESSION_DELETION_TASKS.labels(status=status).set(count)

    async def purge_finished(self) -> int:
        """清理过期的终态墓碑，避免表无限增长。"""
        return await self._queue.purge(
            constants.COMPLETED_RETENTION_SECONDS,
            constants.FAILED_RETENTION_SECONDS,
        )

    async def start(self) -> None:
        """启动后台重试循环；重复调用是幂等的。"""
        if self._task is not None and not self._task.done():
            return
        self._stopped = False
        self._task = asyncio.create_task(
            self._loop(), name="session-deletion-worker"
        )
        logger.info("session_deletion.worker_started")

    async def stop(self) -> None:
        """停止后台循环；未启动时是空操作。"""
        self._stopped = True
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        logger.info("session_deletion.worker_stopped")

    async def _loop(self) -> None:
        next_metrics_at = 0.0
        next_purge_at = (
            asyncio.get_running_loop().time() + constants.PURGE_INTERVAL_SECONDS
        )
        while not self._stopped:
            try:
                await self.run_once()
                now = asyncio.get_running_loop().time()
                if now >= next_metrics_at:
                    await self.update_metrics()
                    next_metrics_at = now + constants.METRICS_REFRESH_SECONDS
                if now >= next_purge_at:
                    await self.purge_finished()
                    next_purge_at = now + constants.PURGE_INTERVAL_SECONDS
            except Exception as exc:
                # 后台任务必须自愈，不能因单次异常永久退出
                logger.warning(
                    "session_deletion.worker_error", error_type=type(exc).__name__
                )
            await asyncio.sleep(constants.POLL_INTERVAL_SECONDS)
