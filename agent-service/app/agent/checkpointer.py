"""Checkpointer 生命周期管理。

为什么需要这一层：
1. 图的记忆能力由 checkpointer 决定，但业务代码不该关心用的是哪种实现；
2. 连接池、建表、关闭都需要在应用启动/退出时统一处理；
3. 测试与本地开发可用 memory，生产切 postgres，仅改环境变量。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

# 就绪探测结果，供 /health/ready 原样暴露
CHECKPOINTER_STATUS_MEMORY = "memory"
CHECKPOINTER_STATUS_UP = "up"
CHECKPOINTER_STATUS_DOWN = "down"
CHECKPOINTER_STATUS_UNAVAILABLE = "unavailable"

# 探测超时要短：探活本身不能拖垮编排系统
PROBE_TIMEOUT_SECONDS = 2.0

# 未走 lifespan（例如单元测试直接建图）时的安全默认值
_checkpointer: BaseCheckpointSaver = MemorySaver()
# postgres 后端下保存连接池，供就绪探测与关闭复用
_pool: AsyncConnectionPool | None = None


def get_checkpointer() -> BaseCheckpointSaver:
    """返回当前生效的 checkpointer，供图编译时注入。"""
    return _checkpointer


def get_connection_pool() -> AsyncConnectionPool | None:
    """返回 postgres 后端的连接池；memory 后端为 None。

    消息表与会话检查点共用同一个池，避免为旁路存储再建一套连接。
    """
    return _pool


async def probe_checkpointer() -> str:
    """真实查询一次数据库，确认会话存储可用。

    只做 `SELECT 1`，不读取业务 key，避免探活产生额外压力。
    """
    if _pool is None:
        # backend=postgres 但连接池未建立，说明启动未完成或已降级
        if get_settings().storage.backend == "memory":
            return CHECKPOINTER_STATUS_MEMORY
        return CHECKPOINTER_STATUS_UNAVAILABLE

    try:
        async with _pool.connection(timeout=PROBE_TIMEOUT_SECONDS) as connection:
            await connection.execute("SELECT 1")
    except Exception as exc:
        # 周期性探活会反复触发，只记录类型，不重复打印堆栈
        logger.warning("checkpointer.health_check_failed", error_type=type(exc).__name__)
        return CHECKPOINTER_STATUS_DOWN
    return CHECKPOINTER_STATUS_UP


async def delete_thread_checkpoint(thread_id: str) -> bool:
    """删除指定会话的全部检查点；返回 False 表示当前实现不支持删除。

    `memory` 后端本来就不持久化，删不掉也等于没有残留；`postgres` 后端
    由 `AsyncPostgresSaver.adelete_thread` 清理 checkpoint 相关表。
    """
    deleter = getattr(get_checkpointer(), "adelete_thread", None)
    if deleter is None:
        logger.warning("checkpointer.delete_unsupported")
        return False
    try:
        await deleter(thread_id)
    except NotImplementedError:
        logger.warning("checkpointer.delete_unsupported")
        return False
    return True


def _set_checkpointer(saver: BaseCheckpointSaver) -> None:
    """切换实现后必须重建已缓存的图，否则仍在用旧存储。"""
    global _checkpointer
    _checkpointer = saver

    # 延迟导入避免模块循环依赖
    from app.agent.graph import get_agent

    get_agent.cache_clear()


def _set_pool(pool: AsyncConnectionPool | None) -> None:
    """记录/清空连接池，供就绪探测使用。"""
    global _pool
    _pool = pool


@asynccontextmanager
async def checkpointer_lifespan(app: object) -> AsyncIterator[None]:
    """FastAPI lifespan：启动时建立存储，退出时释放连接池。

    第一个参数由 FastAPI 传入应用实例，本模块用不到。
    """
    settings = get_settings()

    if settings.storage.backend == "memory":
        _set_checkpointer(MemorySaver())
        logger.warning("checkpointer.memory_mode", reason="会话不会持久化，仅适用于测试")
        yield
        _set_checkpointer(MemorySaver())
        return

    # postgres 分支：连接池由 psycopg 管理，saver 只负责读写检查点
    # autocommit 必开：setup() 里包含 CREATE INDEX CONCURRENTLY，不能在事务块中执行
    postgres_url = settings.storage.postgres_url
    # model_validator 已保证 backend=postgres 时 url 非空，这里只为类型收窄
    assert postgres_url is not None
    pool = AsyncConnectionPool(
        conninfo=postgres_url.get_secret_value(),
        max_size=settings.storage.pool_size,
        kwargs={"autocommit": True},
        open=False,
    )
    await pool.open()
    try:
        # psycopg-pool 的泛型参数与 AsyncPostgresSaver 期望的不一致，属于上游类型标注问题
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        if settings.storage.auto_setup:
            # 幂等 DDL：创建 checkpoints / checkpoint_blobs / checkpoint_writes 等表
            await saver.setup()
        _set_pool(pool)
        _set_checkpointer(saver)
        logger.info(
            "checkpointer.ready",
            backend="postgres",
            pool_size=settings.storage.pool_size,
        )
        yield
    finally:
        await pool.close()
        # 进程退出后连接已失效，避免后续误用
        _set_pool(None)
        _set_checkpointer(MemorySaver())
