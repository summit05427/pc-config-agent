"""Redis key 与 TTL 约定。

为什么需要统一约定：
1. 多个服务可能共用一个 Redis 实例，key 不加前缀必然冲突；
2. TTL 分散在各处写容易漏，集中在这里便于审计与调整；
3. 模板只约束格式，不约束业务语义，domain 与 parts 由使用方定义。
"""

import random

from app.core.config import get_settings

KEY_SEPARATOR = ":"
# 过期时间抖动比例：避免同一批缓存在同一秒集中失效
TTL_JITTER_RATIO = 0.1
MIN_TTL_JITTER_SECONDS = 1


def _is_valid_segment(segment: str) -> bool:
    """分段必须是已去除首尾空白的非空字符串，且不能包含分隔符。"""
    return bool(segment) and segment == segment.strip() and KEY_SEPARATOR not in segment


def build_key(domain: str, *parts: str) -> str:
    """拼装带环境前缀的 key，例如 `agent:dev:cache:user:123`。

    domain 表示用途（cache / lock / idempotency），parts 为业务标识。
    """
    settings = get_settings()
    segments = (settings.redis.key_prefix, settings.app_env, domain, *parts)
    for segment in segments:
        if not _is_valid_segment(segment):
            raise ValueError(f"非法的 key 分段：{segment!r}")

    return KEY_SEPARATOR.join(segments)


def jittered_ttl(base_seconds: int | None = None) -> int:
    """返回带随机抖动的过期秒数；不传时使用配置的默认 TTL。"""
    base = base_seconds if base_seconds is not None else get_settings().redis.default_ttl_seconds
    if base <= 0:
        raise ValueError("TTL 必须大于 0")

    max_jitter = max(MIN_TTL_JITTER_SECONDS, int(base * TTL_JITTER_RATIO))
    return base + random.randint(0, max_jitter)
