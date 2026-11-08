"""缓存、分布式锁、幂等原语的单元测试。

用内存 FakeRedis 覆盖分支逻辑；真实 Redis 的行为一致性由
test_redis_primitives_integration.py 负责验证。
"""

import asyncio

import pytest

from app.core.exceptions import LockAcquisitionError
from app.services import cache as cache_module
from app.services import idempotency as idempotency_module
from app.services import lock as lock_module
from app.services.cache import (
    cache_delete,
    cache_get,
    cache_get_or_set,
    cache_key,
    cache_set,
)
from app.services.idempotency import (
    STATUS_DONE,
    STATUS_PROCESSING,
    idempotency_abort,
    idempotency_begin,
    idempotency_finish,
    idempotency_key,
    idempotency_read,
)
from app.services.lock import acquire_lock, distributed_lock, lock_key
from app.services.redis_value import decode, encode, read_json, resolve_ttl


class FakeRedis:
    """只实现原语用到的命令，行为与 Redis 保持一致。"""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.fail_eval = False

    async def set(
        self,
        name: str,
        value: str,
        *,
        nx: bool = False,
        px: int | None = None,
    ) -> bool | None:
        if nx and name in self.values:
            return None
        self.values[name] = value
        if px is not None:
            self.expirations[name] = px
        return True

    async def get(self, name: str) -> str | None:
        return self.values.get(name)

    async def delete(self, name: str) -> int:
        return 1 if self.values.pop(name, None) is not None else 0

    async def eval(self, script: str, numkeys: int, *args: str) -> int:
        if self.fail_eval:
            raise RuntimeError("redis unavailable")
        key, token = args
        if self.values.get(key) != token:
            return 0
        self.values.pop(key, None)
        return 1


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def patched_redis(monkeypatch: pytest.MonkeyPatch, fake_redis: FakeRedis) -> FakeRedis:
    """把三个原语模块的客户端替换为同一个 FakeRedis。"""
    for module in (cache_module, lock_module, idempotency_module):
        monkeypatch.setattr(module, "get_redis", lambda: fake_redis)
    return fake_redis


async def test_cache_set_and_get_roundtrip(patched_redis: FakeRedis) -> None:
    key = cache_key("test", "roundtrip")

    await cache_set(key, {"name": "张三", "age": 18})
    value = await cache_get(key)

    assert value == {"name": "张三", "age": 18}


async def test_cache_get_returns_none_for_missing_key(patched_redis: FakeRedis) -> None:
    assert await cache_get(cache_key("test", "missing")) is None


async def test_cache_delete_removes_value(patched_redis: FakeRedis) -> None:
    key = cache_key("test", "delete")
    await cache_set(key, "value")

    await cache_delete(key)

    assert await cache_get(key) is None


async def test_cache_get_or_set_calls_producer_on_miss(patched_redis: FakeRedis) -> None:
    key = cache_key("test", "miss")
    calls = 0

    async def producer() -> str:
        nonlocal calls
        calls += 1
        return "generated"

    assert await cache_get_or_set(key, producer) == "generated"
    assert await cache_get_or_set(key, producer) == "generated"
    assert calls == 1


async def test_cache_get_or_set_returns_cached_value(patched_redis: FakeRedis) -> None:
    key = cache_key("test", "hit")
    await cache_set(key, "cached")

    async def producer() -> str:
        raise AssertionError("命中缓存时不应执行 producer")

    assert await cache_get_or_set(key, producer) == "cached"


async def test_cache_get_or_set_caches_null_result(patched_redis: FakeRedis) -> None:
    key = cache_key("test", "null")
    calls = 0

    async def producer() -> None:
        nonlocal calls
        calls += 1
        return None

    assert await cache_get_or_set(key, producer) is None
    assert await cache_get_or_set(key, producer) is None
    assert calls == 1


async def test_cache_get_removes_corrupted_value(patched_redis: FakeRedis) -> None:
    key = cache_key("test", "corrupted")
    patched_redis.values[key] = "{not-json"

    assert await cache_get(key) is None
    assert key not in patched_redis.values


async def test_cache_set_rejects_non_serializable_value(patched_redis: FakeRedis) -> None:
    with pytest.raises(TypeError):
        await cache_set(cache_key("test", "bad"), object())


async def test_cache_set_applies_ttl_jitter(patched_redis: FakeRedis) -> None:
    key = cache_key("test", "ttl")

    await cache_set(key, "value", ttl_seconds=100)

    assert 100_000 <= patched_redis.expirations[key] <= 110_000


async def test_cache_rejects_non_positive_ttl(patched_redis: FakeRedis) -> None:
    with pytest.raises(ValueError):
        await cache_set(cache_key("test", "ttl"), "value", ttl_seconds=0)


async def test_lock_acquires_and_releases(patched_redis: FakeRedis) -> None:
    key = lock_key("test", "release")

    async with distributed_lock(key, ttl_seconds=5):
        assert key in patched_redis.values

    assert key not in patched_redis.values
    assert patched_redis.expirations[key] == 5_000


async def test_lock_raises_when_already_held(patched_redis: FakeRedis) -> None:
    key = lock_key("test", "conflict")

    async with distributed_lock(key):
        with pytest.raises(LockAcquisitionError) as exc_info:
            async with distributed_lock(key):
                pass

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "lock_not_acquired"


async def test_lock_waits_until_released(patched_redis: FakeRedis) -> None:
    key = lock_key("test", "wait")
    acquired = asyncio.Event()

    async def contender() -> None:
        async with distributed_lock(key, wait_timeout_seconds=1):
            acquired.set()

    async with distributed_lock(key):
        task = asyncio.create_task(contender())
        await asyncio.sleep(0.02)
        assert not acquired.is_set()

    await task
    assert acquired.is_set()


async def test_lock_does_not_delete_foreign_token(patched_redis: FakeRedis) -> None:
    key = lock_key("test", "foreign")

    async with distributed_lock(key):
        # 模拟锁已过期并被另一个请求拿走
        patched_redis.values[key] = "other-token"

    assert patched_redis.values[key] == "other-token"


async def test_lock_releases_on_body_exception(patched_redis: FakeRedis) -> None:
    key = lock_key("test", "exception")

    with pytest.raises(RuntimeError):
        async with distributed_lock(key):
            raise RuntimeError("boom")

    assert key not in patched_redis.values


async def test_lock_release_failure_does_not_mask_body_result(
    patched_redis: FakeRedis,
) -> None:
    key = lock_key("test", "release-failure")
    patched_redis.fail_eval = True

    async with distributed_lock(key):
        pass

    assert key in patched_redis.values


async def test_lock_handle_release_is_idempotent(patched_redis: FakeRedis) -> None:
    """显式句柄供流式响应使用，重复释放不应报错或误删他人锁。"""
    key = lock_key("test", "handle")
    handle = await acquire_lock(key, ttl_seconds=5)

    await handle.release()
    second_handle = await acquire_lock(key, ttl_seconds=5)
    # 第一次的句柄已释放，再次释放应是空操作，不能删掉新持有者的锁
    await handle.release()

    assert patched_redis.values[key] == second_handle.token
    await second_handle.release()


async def test_lock_rejects_invalid_options(patched_redis: FakeRedis) -> None:
    with pytest.raises(ValueError):
        async with distributed_lock(lock_key("test", "bad"), ttl_seconds=0):
            pass

    with pytest.raises(ValueError):
        async with distributed_lock(lock_key("test", "bad"), wait_timeout_seconds=-1):
            pass


async def test_idempotency_begin_is_exclusive(patched_redis: FakeRedis) -> None:
    key = idempotency_key("test", "begin")

    assert await idempotency_begin(key) is True
    assert await idempotency_begin(key) is False


async def test_idempotency_read_processing_record(patched_redis: FakeRedis) -> None:
    key = idempotency_key("test", "processing")
    await idempotency_begin(key)

    record = await idempotency_read(key)

    assert record is not None
    assert record.status == STATUS_PROCESSING
    assert record.result is None


async def test_idempotency_finish_stores_result(patched_redis: FakeRedis) -> None:
    key = idempotency_key("test", "done")
    await idempotency_begin(key)

    await idempotency_finish(key, {"answer": "42"})
    record = await idempotency_read(key)

    assert record is not None
    assert record.status == STATUS_DONE
    assert record.result == {"answer": "42"}


async def test_idempotency_abort_allows_retry(patched_redis: FakeRedis) -> None:
    key = idempotency_key("test", "abort")
    await idempotency_begin(key)

    await idempotency_abort(key)

    assert await idempotency_read(key) is None
    assert await idempotency_begin(key) is True


async def test_idempotency_read_removes_invalid_record(patched_redis: FakeRedis) -> None:
    key = idempotency_key("test", "invalid")
    patched_redis.values[key] = '{"status":"unknown"}'

    assert await idempotency_read(key) is None
    assert key not in patched_redis.values


async def test_idempotency_finish_rejects_non_serializable_result(
    patched_redis: FakeRedis,
) -> None:
    with pytest.raises(TypeError):
        await idempotency_finish(idempotency_key("test", "bad"), object())


async def test_idempotency_rejects_non_positive_ttl(patched_redis: FakeRedis) -> None:
    with pytest.raises(ValueError):
        await idempotency_begin(idempotency_key("test", "bad"), ttl_seconds=0)


def test_primitives_use_distinct_key_domains() -> None:
    assert ":cache:" in cache_key("x")
    assert ":lock:" in lock_key("y")
    assert ":idempotency:" in idempotency_key("z")


def test_resolve_ttl_prefers_explicit_and_rejects_non_positive() -> None:
    assert resolve_ttl(None, default_seconds=60, label="缓存") == 60
    assert resolve_ttl(30, default_seconds=60, label="缓存") == 30

    with pytest.raises(ValueError, match="缓存 TTL 必须大于 0"):
        resolve_ttl(0, default_seconds=60, label="缓存")


@pytest.mark.parametrize(
    ("label", "message"),
    [
        ("缓存值", "缓存值必须可被 JSON 序列化"),
        ("幂等结果", "幂等结果必须可被 JSON 序列化"),
    ],
)
def test_encode_rejects_non_serializable_value_with_label(label: str, message: str) -> None:
    """错误文案要能指出是哪个原语，避免调用方只看到笼统的 TypeError。"""
    with pytest.raises(TypeError, match=message):
        encode(object(), label=label)


def test_decode_accepts_bytes_and_rejects_corrupted_payload() -> None:
    assert decode(b'{"ok": true}') == (True, {"ok": True})
    assert decode(b"\xff\xfe") == (False, None)
    assert decode("{not-json") == (False, None)


async def test_read_json_returns_missing_and_removes_corruption(
    patched_redis: FakeRedis,
) -> None:
    key = cache_key("test", "read-json")
    assert await read_json(patched_redis, key, invalid_event="cache.invalid_value") == (
        False,
        None,
    )

    patched_redis.values[key] = "{not-json"
    assert await read_json(patched_redis, key, invalid_event="cache.invalid_value") == (
        False,
        None,
    )
    assert key not in patched_redis.values


async def test_cache_get_or_set_removes_corrupted_value_and_refills(
    patched_redis: FakeRedis,
) -> None:
    key = cache_key("test", "corrupted-refill")
    patched_redis.values[key] = "{not-json"

    async def producer() -> str:
        return "fresh"

    assert await cache_get_or_set(key, producer) == "fresh"
    assert await cache_get(key) == "fresh"


async def test_idempotency_read_removes_valid_json_with_unknown_status(
    patched_redis: FakeRedis,
) -> None:
    """合法 JSON 但状态非法属于业务脏数据，同样要删除后允许重新执行。"""
    key = idempotency_key("test", "unknown-status")
    patched_redis.values[key] = '{"status":"unknown"}'

    assert await idempotency_read(key) is None
    assert key not in patched_redis.values
