"""删除队列的最小接口：调度（worker）与存储（内存/Postgres）只通过它交互。

为什么把状态机与调度分离：
墓碑的领取、退避、租约是队列语义，内存与 Postgres 只是同一语义的两个适配器；
后台循环只负责「领一批 → 删检查点 → 推进状态」，不再关心 SQL 或进程内字典。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import NamedTuple, Protocol

from app.services.session_deletion import constants


class ClaimedDeletion(NamedTuple):
    """一次领取到的墓碑；`attempts` 是本次领取前的失败次数。"""

    user_id: str
    thread_id: str
    checkpoint_thread_id: str
    attempts: int


DeleteCheckpoint = Callable[[str], Awaitable[bool]]


def next_backoff(attempts: int) -> float:
    """按已失败次数取退避；超出列表长度时复用最后一档。"""
    index = min(max(attempts - 1, 0), len(constants.RETRY_BACKOFF_SECONDS) - 1)
    return constants.RETRY_BACKOFF_SECONDS[index]


class DeletionQueue(Protocol):
    """墓碑存储的唯一接口；调用方与测试都只跨这个 seam。"""

    async def setup(self) -> None:
        """执行一次性初始化；内存适配器为空实现。"""
        ...

    async def enqueue(
        self,
        user_id: str,
        thread_id: str,
        checkpoint_thread_id: str,
    ) -> bool:
        """登记一条待删除墓碑；返回是否成功入队，失败不抛出。"""
        ...

    async def cancel(self, user_id: str, thread_id: str) -> None:
        """取消未执行的删除；只影响 pending 记录。"""
        ...

    async def claim(self, limit: int = constants.BATCH_SIZE) -> list[ClaimedDeletion]:
        """领取到期的 pending 记录，并推进租约。"""
        ...

    async def status_of(self, user_id: str, thread_id: str) -> str | None:
        """读取墓碑状态；无记录返回 `None`。"""
        ...

    async def attempts_of(self, user_id: str, thread_id: str) -> int | None:
        """读取已失败次数；无记录返回 `None`，供测试与排查使用。"""
        ...

    async def complete(
        self,
        user_id: str,
        thread_id: str,
        note: str | None = None,
    ) -> None:
        """标记完成；只在 pending 时生效，`note` 记录原因（如 checkpointer 不支持删除）。"""
        ...

    async def fail(
        self,
        user_id: str,
        thread_id: str,
        attempts: int,
        error: str,
    ) -> str:
        """记录一次失败并按退避重排；返回推进后的状态（pending 或 failed）。"""
        ...

    async def reschedule(self, user_id: str, thread_id: str) -> None:
        """锁被占用时不动 attempts，只把本次领取顺延一个租约周期。"""
        ...

    async def purge(
        self,
        completed_retention_seconds: float,
        failed_retention_seconds: float,
    ) -> int:
        """清理过期终态墓碑；返回删除行数。"""
        ...

    async def counts(self) -> dict[str, int]:
        """按状态统计墓碑数量，供指标与排查使用。"""
        ...
