"""内存适配器：测试/本地默认后端，语义与 Postgres 保持一致，进程重启即丢。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.services.session_deletion import constants
from app.services.session_deletion.interface import ClaimedDeletion, next_backoff


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _MemoryTask:
    checkpoint_thread_id: str
    status: str = constants.STATUS_PENDING
    attempts: int = 0
    # 用事件循环时钟表示租约，避免测试依赖真实时间
    retry_at: float = 0.0
    updated_at: datetime = field(default_factory=_now)
    last_error: str | None = None


class InMemoryDeletionQueue:
    """进程内实现；每个实例拥有独立状态，测试通过 setup 换新实例即可清空。"""

    def __init__(self) -> None:
        self._tasks: dict[tuple[str, str], _MemoryTask] = {}

    async def setup(self) -> None:
        return None

    async def enqueue(
        self,
        user_id: str,
        thread_id: str,
        checkpoint_thread_id: str,
    ) -> bool:
        # 重复删除同一会话时重置墓碑：上一轮的 completed/failed 不能阻止新一轮清理
        self._tasks[(user_id, thread_id)] = _MemoryTask(
            checkpoint_thread_id=checkpoint_thread_id,
            retry_at=asyncio.get_running_loop().time(),
        )
        return True

    async def cancel(self, user_id: str, thread_id: str) -> None:
        task = self._tasks.get((user_id, thread_id))
        if task is not None and task.status == constants.STATUS_PENDING:
            task.status = constants.STATUS_CANCELLED
            task.updated_at = _now()

    async def claim(self, limit: int = constants.BATCH_SIZE) -> list[ClaimedDeletion]:
        now = asyncio.get_running_loop().time()
        claimed: list[ClaimedDeletion] = []
        for (user_id, thread_id), task in list(self._tasks.items()):
            if len(claimed) >= limit:
                break
            if task.status != constants.STATUS_PENDING or task.retry_at > now:
                continue
            task.retry_at = now + constants.CLAIM_LEASE_SECONDS
            claimed.append(
                ClaimedDeletion(
                    user_id, thread_id, task.checkpoint_thread_id, task.attempts
                )
            )
        return claimed

    async def status_of(self, user_id: str, thread_id: str) -> str | None:
        task = self._tasks.get((user_id, thread_id))
        return task.status if task is not None else None

    async def attempts_of(self, user_id: str, thread_id: str) -> int | None:
        task = self._tasks.get((user_id, thread_id))
        return task.attempts if task is not None else None

    async def complete(
        self,
        user_id: str,
        thread_id: str,
        note: str | None = None,
    ) -> None:
        task = self._tasks.get((user_id, thread_id))
        if task is not None and task.status == constants.STATUS_PENDING:
            task.status = constants.STATUS_COMPLETED
            task.updated_at = _now()
            task.last_error = note

    async def fail(
        self,
        user_id: str,
        thread_id: str,
        attempts: int,
        error: str,
    ) -> str:
        status = (
            constants.STATUS_FAILED
            if attempts >= constants.MAX_ATTEMPTS
            else constants.STATUS_PENDING
        )
        task = self._tasks.get((user_id, thread_id))
        if task is not None and task.status == constants.STATUS_PENDING:
            task.attempts = attempts
            task.status = status
            task.last_error = error
            task.updated_at = _now()
            task.retry_at = asyncio.get_running_loop().time() + next_backoff(attempts)
        return status

    async def reschedule(self, user_id: str, thread_id: str) -> None:
        task = self._tasks.get((user_id, thread_id))
        if task is not None and task.status == constants.STATUS_PENDING:
            task.retry_at = (
                asyncio.get_running_loop().time() + constants.CLAIM_LEASE_SECONDS
            )

    async def purge(
        self,
        completed_retention_seconds: float,
        failed_retention_seconds: float,
    ) -> int:
        now = _now()
        removed = 0
        for key, task in list(self._tasks.items()):
            if task.status in (
                constants.STATUS_COMPLETED,
                constants.STATUS_CANCELLED,
            ):
                expired = (
                    now - task.updated_at
                ).total_seconds() >= completed_retention_seconds
            elif task.status == constants.STATUS_FAILED:
                expired = (
                    now - task.updated_at
                ).total_seconds() >= failed_retention_seconds
            else:
                expired = False
            if expired:
                self._tasks.pop(key, None)
                removed += 1
        return removed

    async def counts(self) -> dict[str, int]:
        result = dict.fromkeys(constants.STATUS_VALUES, 0)
        for task in self._tasks.values():
            result[task.status] = result.get(task.status, 0) + 1
        return result
