"""通用缓存原语。

模板只提供机制，不规定缓存什么：
1. key 统一通过 cache_key 生成，自带前缀、环境与用途；
2. 值统一 JSON 序列化（规则见 redis_value），禁止 pickle，避免反序列化执行任意代码；
3. 所有写入都带 TTL，并用抖动降低同批 key 集中失效的风险；
4. 读不到、值损坏都返回 None，不把缓存故障升级成业务故障。
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import get_settings
from app.core.keys import build_key, jittered_ttl
from app.core.redis import get_redis
from app.services.redis_value import encode, read_json, resolve_ttl

CACHE_DOMAIN = "cache"

# 缓存读取的坏值事件名与错误文案保持原样，避免影响既有排障习惯与调用方断言
_INVALID_VALUE_EVENT = "cache.invalid_value"
_VALUE_LABEL = "缓存值"
_TTL_LABEL = "缓存"


def cache_key(*parts: str) -> str:
    """生成缓存用途的 key，例如 `前缀:环境:cache:user:1`。"""
    return build_key(CACHE_DOMAIN, *parts)


async def cache_get(key: str) -> Any | None:
    """读取缓存；key 不存在或内容损坏都返回 None。"""
    _, value = await read_json(get_redis(), key, invalid_event=_INVALID_VALUE_EVENT)
    return value


async def cache_set(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    """写入缓存，TTL 会在配置值基础上增加随机抖动。"""
    payload = encode(value, label=_VALUE_LABEL)
    ttl = jittered_ttl(
        resolve_ttl(
            ttl_seconds,
            default_seconds=get_settings().redis.default_ttl_seconds,
            label=_TTL_LABEL,
        )
    )
    await get_redis().set(key, payload, px=ttl * 1000)


async def cache_delete(key: str) -> None:
    """删除缓存，用于数据变更后主动失效。"""
    await get_redis().delete(key)


async def cache_get_or_set[T](
    key: str,
    producer: Callable[[], Awaitable[T]],
    ttl_seconds: int | None = None,
) -> T:
    """读缓存，未命中时执行 producer 并回填。

    注意：这里没有做并发合并（single-flight）。多个请求同时未命中时，
    producer 可能被调用多次。需要严格只执行一次的场景应配合分布式锁。
    """
    is_found, cached = await read_json(
        get_redis(),
        key,
        invalid_event=_INVALID_VALUE_EVENT,
    )
    if is_found:
        return cached

    value = await producer()
    await cache_set(key, value, ttl_seconds)
    return value
