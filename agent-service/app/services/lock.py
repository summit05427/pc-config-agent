"""通用分布式锁原语。

实现要点：
1. 用 `SET key token NX PX ttl` 原子抢锁，token 保证释放时只删自己的锁；
2. 释放用 Lua 先比较 token 再删除，避免“锁过期后误删别人的锁”；
3. 只提供互斥与等待窗口，不内置业务重试策略；
4. 锁的 TTL 必须大于临界区耗时，模板不做自动续期，避免引入看门狗复杂度。
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

import structlog

from app.core.config import get_settings
from app.core.exceptions import LockAcquisitionError
from app.core.keys import build_key
from app.core.redis import get_redis, is_redis_enabled

logger = structlog.get_logger(__name__)

LOCK_DOMAIN = "lock"
THREAD_LOCK_DOMAIN = "thread"

# 只有 token 一致时才删除，防止锁已过期并被其他请求获取后误删
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def lock_key(*parts: str) -> str:
    """生成锁用途的 key，例如 `前缀:环境:lock:thread:alice:demo`。"""
    return build_key(LOCK_DOMAIN, *parts)


def thread_lock_key(thread_id: str) -> str:
    """生成会话锁 key。

    thread_id 形如 `用户ID:会话ID`，可能包含冒号等 key 非法字符，
    因此用摘要作为分段；原始值只出现在日志里，不参与 key 拼接。
    """
    digest = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()
    return lock_key(THREAD_LOCK_DOMAIN, digest)


async def acquire_thread_lock(thread_id: str) -> LockHandle | None:
    """同一会话串行化，供对话与删除共用。

    Redis 未启用时返回 None，退化为进程内并发（单副本部署可接受），
    此时删除与生成之间没有互斥，属已知限制。
    """
    if not is_redis_enabled():
        return None

    settings = get_settings()
    return await acquire_lock(
        thread_lock_key(thread_id),
        ttl_seconds=settings.agent.thread_lock_ttl_seconds,
        wait_timeout_seconds=settings.agent.thread_lock_wait_seconds,
    )


def _validate_options(
    ttl_seconds: int | None,
    wait_timeout_seconds: float,
    retry_interval_seconds: float,
) -> int:
    ttl = ttl_seconds if ttl_seconds is not None else get_settings().redis.lock_ttl_seconds
    if ttl <= 0:
        raise ValueError("锁 TTL 必须大于 0")
    if wait_timeout_seconds < 0:
        raise ValueError("等待时间不能为负数")
    if retry_interval_seconds <= 0:
        raise ValueError("重试间隔必须大于 0")
    return ttl


@dataclass
class LockHandle:
    """已获取的锁。

    释放必须由调用方在 finally 中执行；重复释放是安全的空操作。
    """

    key: str
    token: str
    _is_released: bool = False

    async def release(self) -> None:
        if self._is_released:
            return
        self._is_released = True
        try:
            await get_redis().eval(_RELEASE_SCRIPT, 1, self.key, self.token)
        except Exception as exc:
            # 释放失败不能覆盖临界区里的原始异常；锁本身会按 TTL 自动过期
            logger.warning("lock.release_failed", key=self.key, error_type=type(exc).__name__)


async def acquire_lock(
    key: str,
    ttl_seconds: int | None = None,
    wait_timeout_seconds: float = 0.0,
    retry_interval_seconds: float = 0.05,
) -> LockHandle:
    """在等待窗口内抢锁，成功后返回句柄；抢不到抛 LockAcquisitionError。

    拆成显式的 acquire / release，是为了让「流式响应」这类
    生命周期比函数调用更长的场景也能先拿锁、再逐块返回。
    """
    ttl = _validate_options(ttl_seconds, wait_timeout_seconds, retry_interval_seconds)
    client = get_redis()
    token = uuid4().hex
    deadline = time.monotonic() + wait_timeout_seconds

    while True:
        acquired = await client.set(key, token, nx=True, px=ttl * 1000)
        if acquired:
            return LockHandle(key=key, token=token)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LockAcquisitionError(
                f"等待 {wait_timeout_seconds} 秒仍未获取到锁，请稍后重试"
            )
        await asyncio.sleep(min(retry_interval_seconds, remaining))


@asynccontextmanager
async def distributed_lock(
    key: str,
    ttl_seconds: int | None = None,
    wait_timeout_seconds: float = 0.0,
    retry_interval_seconds: float = 0.05,
) -> AsyncIterator[None]:
    """获取锁后执行临界区，退出时自动释放。

    `wait_timeout_seconds=0` 表示只尝试一次，抢不到立即抛 LockAcquisitionError。
    """
    handle = await acquire_lock(key, ttl_seconds, wait_timeout_seconds, retry_interval_seconds)
    try:
        yield
    finally:
        await handle.release()
