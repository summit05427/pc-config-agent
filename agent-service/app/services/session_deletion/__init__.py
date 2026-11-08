"""会话删除墓碑的服务入口：装配「删除队列 + 后台 worker」。

为什么拆包：
旧单文件同时承担建表、内存假实现、状态机、租约、退避、清理、指标与后台循环；
现在状态机（`memory` / `postgres` 两个适配器）与调度（`worker`）分离，
调用方仍通过本模块的旧函数名使用，无需感知后端差异。

状态机：
- `pending`：等待后台删除检查点；
- `completed`：检查点已删除（或当前 checkpointer 不支持删除，数据本就不持久）；
- `failed`：达到重试上限仍失败，保留记录供人工排查；
- `cancelled`：删除后同一会话被重新使用（新一轮对话），取消删除，避免误删新检查点。
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from app.services.session_deletion import constants
from app.services.session_deletion.interface import (
    ClaimedDeletion,
    DeleteCheckpoint,
    DeletionQueue,
)
from app.services.session_deletion.memory import InMemoryDeletionQueue
from app.services.session_deletion.postgres import PostgresDeletionQueue
from app.services.session_deletion.worker import DeletionWorker

logger = structlog.get_logger(__name__)

# 只读别名：调用方与测试读取状态/上限时不必再进子模块
STATUS_PENDING = constants.STATUS_PENDING
STATUS_COMPLETED = constants.STATUS_COMPLETED
STATUS_FAILED = constants.STATUS_FAILED
STATUS_CANCELLED = constants.STATUS_CANCELLED
MAX_ATTEMPTS = constants.MAX_ATTEMPTS

_queue: DeletionQueue | None = None
_worker: DeletionWorker | None = None

__all__ = [
    "ClaimedDeletion",
    "DeleteCheckpoint",
    "DeletionQueue",
    "DeletionWorker",
    "MAX_ATTEMPTS",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "cancel_pending_deletion",
    "detach_session_deletion",
    "enqueue_session_deletion",
    "get_deletion_queue",
    "reset_session_deletion",
    "setup_session_deletion",
    "start_session_deletion_worker",
    "stop_session_deletion_worker",
]


async def setup_session_deletion(
    pool: AsyncConnectionPool | None,
    *,
    auto_setup: bool,
    delete_checkpoint: DeleteCheckpoint | None = None,
) -> None:
    """绑定删除队列与检查点删除函数；建表失败只告警，不阻止启动。"""
    global _queue, _worker

    queue: DeletionQueue
    if pool is None:
        queue = InMemoryDeletionQueue()
        logger.info("session_deletion.memory_mode")
    elif not auto_setup:
        queue = PostgresDeletionQueue(pool)
        logger.info("session_deletion.ready", backend="postgres", auto_setup=False)
    else:
        postgres_queue = PostgresDeletionQueue(pool)
        try:
            await postgres_queue.setup()
        except Exception as exc:
            # 删除墓碑是可靠性增强，不能因为建表失败让整个服务起不来
            logger.error(
                "session_deletion.setup_failed", error_type=type(exc).__name__
            )
            queue = InMemoryDeletionQueue()
        else:
            queue = postgres_queue
            logger.info("session_deletion.ready", backend="postgres", auto_setup=True)

    old_worker = _worker
    if old_worker is not None:
        await old_worker.stop()
    _queue = queue
    _worker = DeletionWorker(queue, delete_checkpoint)


def get_deletion_queue() -> DeletionQueue:
    """返回当前队列；未绑定时说明调用方漏了启动装配，直接失败而不是静默降级。"""
    if _queue is None:
        raise RuntimeError("会话删除队列未绑定")
    return _queue


async def enqueue_session_deletion(
    user_id: str,
    thread_id: str,
    checkpoint_thread_id: str,
) -> bool:
    """登记一条待删除墓碑；返回是否成功入队，失败不抛出。"""
    return await get_deletion_queue().enqueue(
        user_id, thread_id, checkpoint_thread_id
    )


async def cancel_pending_deletion(user_id: str, thread_id: str) -> None:
    """会话被重新使用时取消未执行的删除，避免误删新一轮的检查点。

    失败只记 warning：取消是保护性动作，不能反过来阻断对话。
    """
    await get_deletion_queue().cancel(user_id, thread_id)


async def start_session_deletion_worker() -> None:
    """启动后台重试循环；重复调用是幂等的。"""
    if _worker is None:
        raise RuntimeError("会话删除 worker 未绑定")
    await _worker.start()


async def stop_session_deletion_worker() -> None:
    """停止后台循环；未启动时是空操作。"""
    if _worker is None:
        return
    await _worker.stop()


def detach_session_deletion() -> None:
    """应用关闭时解除队列与 worker 引用。"""
    global _queue, _worker
    _queue = None
    _worker = None


def reset_session_deletion() -> None:
    """清空进程内引用并丢弃内存墓碑，仅供测试使用。"""
    global _queue, _worker
    _queue = None
    _worker = None
