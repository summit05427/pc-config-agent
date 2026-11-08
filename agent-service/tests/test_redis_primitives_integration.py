"""三个原语对真实 Redis 的集成验证。

CI 中始终配置 REDIS__URL，因此这些用例不会跳过；
本地未启用 Redis 时跳过，分支逻辑由单元测试覆盖。
"""

import asyncio
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.redis import redis_lifespan
from app.services.cache import (
    cache_delete,
    cache_get,
    cache_get_or_set,
    cache_key,
    cache_set,
)
from app.services.idempotency import (
    STATUS_DONE,
    idempotency_begin,
    idempotency_finish,
    idempotency_key,
    idempotency_read,
)
from app.services.lock import distributed_lock, lock_key

pytestmark = pytest.mark.skipif(
    get_settings().redis.url is None,
    reason="未配置 REDIS__URL，跳过真实 Redis 用例",
)


async def test_cache_roundtrip_with_real_redis() -> None:
    key = cache_key("integration", uuid4().hex)

    async with redis_lifespan(None):
        try:
            await cache_set(key, {"ok": True}, ttl_seconds=10)
            assert await cache_get(key) == {"ok": True}

            async def producer() -> dict[str, bool]:
                raise AssertionError("命中缓存时不应执行 producer")

            assert await cache_get_or_set(key, producer) == {"ok": True}
        finally:
            await cache_delete(key)


async def test_lock_serializes_two_workers_with_real_redis() -> None:
    key = lock_key("integration", uuid4().hex)
    order: list[str] = []

    async def first_worker() -> None:
        async with distributed_lock(key, ttl_seconds=5, wait_timeout_seconds=2):
            order.append("first-start")
            await asyncio.sleep(0.1)
            order.append("first-end")

    async def second_worker() -> None:
        await asyncio.sleep(0.02)
        async with distributed_lock(key, ttl_seconds=5, wait_timeout_seconds=2):
            order.append("second")

    async with redis_lifespan(None):
        await asyncio.gather(first_worker(), second_worker())

    assert order == ["first-start", "first-end", "second"]


async def test_idempotency_flow_with_real_redis() -> None:
    key = idempotency_key("integration", uuid4().hex)

    async with redis_lifespan(None):
        assert await idempotency_begin(key, ttl_seconds=10) is True
        assert await idempotency_begin(key, ttl_seconds=10) is False

        await idempotency_finish(key, {"answer": "ok"}, ttl_seconds=10)
        record = await idempotency_read(key)

        assert record is not None
        assert record.status == STATUS_DONE
        assert record.result == {"answer": "ok"}
