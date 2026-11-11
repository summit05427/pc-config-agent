"""限流单测：固定窗口计数、降级分支与 429 响应头。

用内存假客户端替代 Redis，避免测试依赖真实实例；`now` 可注入，跨窗口无需 sleep。
"""

from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import RateLimitSettings
from app.core.exceptions import RateLimitExceededError, RedisUnavailableError
from app.services import rate_limit as rate_limit_module
from app.services.rate_limit import RateLimitDecision, check_window, enforce_chat_rate_limit


class FakeRedis:
    """只实现 incr/expire 的最小客户端。"""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, ttl: int) -> bool:
        self.ttls[key] = ttl
        return True


async def test_check_window_allows_within_limit() -> None:
    client = FakeRedis()
    decision = await check_window(client, "chat", "user-1", limit=2, window_seconds=60, now=1000.0)

    assert decision.allowed is True
    assert decision.remaining == 1
    assert decision.retry_after_seconds == 20
    # 首次计数才设置过期，避免每次请求都刷新 TTL 让窗口永不结束
    assert list(client.ttls.values()) == [61]


async def test_check_window_rejects_over_limit() -> None:
    client = FakeRedis()
    await check_window(client, "chat", "user-1", limit=1, window_seconds=60, now=1000.0)
    decision = await check_window(client, "chat", "user-1", limit=1, window_seconds=60, now=1001.0)

    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.retry_after_seconds == 19


async def test_check_window_resets_in_next_window() -> None:
    client = FakeRedis()
    await check_window(client, "chat", "user-1", limit=1, window_seconds=60, now=1000.0)
    decision = await check_window(client, "chat", "user-1", limit=1, window_seconds=60, now=1061.0)

    assert decision.allowed is True


async def test_check_window_keys_are_isolated_by_user() -> None:
    client = FakeRedis()
    await check_window(client, "chat", "user-1", limit=1, window_seconds=60, now=1000.0)
    decision = await check_window(client, "chat", "user-2", limit=1, window_seconds=60, now=1000.0)

    assert decision.allowed is True


def _patch_settings(monkeypatch: Any, **overrides: Any) -> None:
    settings = RateLimitSettings(**overrides)
    monkeypatch.setattr(
        rate_limit_module,
        "get_settings",
        lambda: SimpleNamespace(rate_limit=settings),
    )


async def test_enforce_skips_when_disabled(monkeypatch: Any) -> None:
    _patch_settings(monkeypatch, enabled=False)
    monkeypatch.setattr(rate_limit_module, "is_redis_enabled", lambda: True)
    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: FakeRedis())

    # 关闭时不应访问 Redis；一旦访问会因缺少计数而无法断言，这里以不抛错为准
    await enforce_chat_rate_limit("user-1")


async def test_enforce_skips_without_redis(monkeypatch: Any) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setattr(rate_limit_module, "is_redis_enabled", lambda: False)

    await enforce_chat_rate_limit("user-1")


async def test_enforce_degrades_open_when_redis_unavailable(monkeypatch: Any) -> None:
    _patch_settings(monkeypatch, fail_open=True)
    monkeypatch.setattr(rate_limit_module, "is_redis_enabled", lambda: True)

    def raise_unavailable() -> Any:
        raise RedisUnavailableError("down")

    monkeypatch.setattr(rate_limit_module, "get_redis", raise_unavailable)

    await enforce_chat_rate_limit("user-1")


async def test_enforce_fails_closed_when_configured(monkeypatch: Any) -> None:
    _patch_settings(monkeypatch, fail_open=False)
    monkeypatch.setattr(rate_limit_module, "is_redis_enabled", lambda: True)

    def raise_unavailable() -> Any:
        raise RedisUnavailableError("down")

    monkeypatch.setattr(rate_limit_module, "get_redis", raise_unavailable)

    with pytest.raises(RedisUnavailableError):
        await enforce_chat_rate_limit("user-1")


async def test_enforce_raises_429_with_retry_after(monkeypatch: Any) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setattr(rate_limit_module, "is_redis_enabled", lambda: True)
    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: FakeRedis())

    async def reject(*_args: Any, **_kwargs: Any) -> RateLimitDecision:
        return RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=17)

    monkeypatch.setattr(rate_limit_module, "check_window", reject)

    with pytest.raises(RateLimitExceededError) as captured:
        await enforce_chat_rate_limit("user-1")

    assert captured.value.status_code == 429
    assert captured.value.code == "rate_limited"
    assert captured.value.headers == {"Retry-After": "17"}
