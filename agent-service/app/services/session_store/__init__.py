"""会话存储的装配入口：调用方只通过 `get_session_store()` 拿到当前适配器。

后端选择只发生在这里：应用启动时绑定 Postgres 或内存适配器，
测试与 Solo 模式在未绑定且配置为 memory 时自动落到内存实现。
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings
from app.services.session_store.interface import SessionEntry, SessionStore
from app.services.session_store.memory import InMemorySessionStore
from app.services.session_store.postgres import PostgresSessionStore

logger = structlog.get_logger(__name__)

_store: SessionStore | None = None

__all__ = [
    "InMemorySessionStore",
    "PostgresSessionStore",
    "SessionEntry",
    "SessionStore",
    "bind_session_store",
    "get_session_store",
    "setup_session_store",
    "unbind_session_store",
]


def bind_session_store(store: SessionStore) -> None:
    """绑定当前进程使用的适配器；由装配层或测试调用。"""
    global _store
    _store = store


def unbind_session_store() -> None:
    """解除绑定但不关闭连接池：池由 checkpointer 生命周期负责关闭。"""
    global _store
    _store = None


def get_session_store() -> SessionStore:
    """返回当前适配器。

    生产环境必须由 lifespan 绑定；测试与本地脚本不跑 lifespan，
    因此非 prod 下回退到内存适配器，而不是让单元测试依赖真实数据库。
    """
    global _store
    if _store is None:
        settings = get_settings()
        if settings.storage.backend != "memory" and settings.app_env == "prod":
            raise RuntimeError("会话存储尚未初始化：生产环境必须在应用启动时绑定")
        _store = InMemorySessionStore()
    return _store


async def setup_session_store(
    pool: AsyncConnectionPool | None,
    *,
    auto_setup: bool,
) -> None:
    """按连接池是否可用选择后端，并在 Postgres 下执行建表。"""
    if pool is None:
        store: SessionStore = InMemorySessionStore()
        logger.info("session_store.memory_mode")
    else:
        store = PostgresSessionStore(pool, auto_create=auto_setup)

    await store.setup()
    bind_session_store(store)
