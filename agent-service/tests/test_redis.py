"""Redis 基础设施测试：配置校验、key 约定、生命周期与健康探测。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from app.core import redis as redis_module
from app.core.config import RedisSettings, get_settings
from app.core.exceptions import RedisUnavailableError
from app.core.keys import build_key, jittered_ttl
from app.core.redis import (
    REDIS_STATUS_DISABLED,
    REDIS_STATUS_UNAVAILABLE,
    REDIS_STATUS_UP,
    get_redis,
    probe_redis,
    redis_lifespan,
)

# 一个必连不上的地址：端口 1 不会监听，且超时设置很短
UNREACHABLE_URL = "redis://127.0.0.1:1/0"


def _use_config(monkeypatch: pytest.MonkeyPatch, config: RedisSettings) -> None:
    """让 redis 模块读到指定配置，避免依赖本地 .env。"""
    monkeypatch.setattr(redis_module, "get_settings", lambda: SimpleNamespace(redis=config))


def test_redis_settings_allow_missing_url_when_optional() -> None:
    config = RedisSettings()

    assert config.url is None
    assert config.required is False


def test_redis_settings_require_url_when_required() -> None:
    with pytest.raises(ValidationError):
        RedisSettings(required=True)


def test_redis_settings_treat_blank_url_as_unset() -> None:
    """空串等同于未配置：Solo 用空值显式关闭 Redis，而不是启动失败。"""
    config = RedisSettings(url=SecretStr("   "))

    assert config.url is None


def test_redis_settings_reject_blank_url_when_required() -> None:
    """声明 Redis 必需时空串仍属配置错误，必须启动期失败。"""
    with pytest.raises(ValidationError):
        RedisSettings(url=SecretStr("   "), required=True)


def test_redis_settings_reject_invalid_key_prefix() -> None:
    with pytest.raises(ValidationError):
        RedisSettings(key_prefix="bad:prefix")


def test_build_key_includes_prefix_env_and_domain() -> None:
    settings = get_settings()

    key = build_key("cache", "user", "123")

    assert key == f"{settings.redis.key_prefix}:{settings.app_env}:cache:user:123"


def test_build_key_rejects_invalid_segments() -> None:
    for bad_value in ("", " user", "user:1"):
        with pytest.raises(ValueError):
            build_key("cache", bad_value)


def test_jittered_ttl_stays_in_expected_range() -> None:
    for _ in range(20):
        ttl = jittered_ttl(100)
        assert 100 <= ttl <= 110


def test_jittered_ttl_rejects_non_positive_base() -> None:
    with pytest.raises(ValueError):
        jittered_ttl(0)


def test_get_redis_raises_unavailable_error_when_not_initialized() -> None:
    redis_module._set_client(None)

    with pytest.raises(RedisUnavailableError) as exc_info:
        get_redis()

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "redis_unavailable"


async def test_lifespan_disables_redis_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_config(monkeypatch, RedisSettings())

    async with redis_lifespan(None):
        assert await probe_redis() == REDIS_STATUS_DISABLED
        with pytest.raises(RedisUnavailableError):
            get_redis()


async def test_lifespan_degrades_when_redis_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RedisSettings(
        url=SecretStr(UNREACHABLE_URL),
        socket_timeout_seconds=0.2,
        connect_timeout_seconds=0.2,
    )
    _use_config(monkeypatch, config)

    async with redis_lifespan(None):
        # 降级启动后仍能提供服务，只是 Redis 状态标记为不可用
        assert await probe_redis() == REDIS_STATUS_UNAVAILABLE


async def test_lifespan_fails_when_required_redis_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RedisSettings(
        url=SecretStr(UNREACHABLE_URL),
        required=True,
        socket_timeout_seconds=0.2,
        connect_timeout_seconds=0.2,
    )
    _use_config(monkeypatch, config)

    with pytest.raises(RuntimeError):
        async with redis_lifespan(None):
            pass


async def test_redis_roundtrip_when_service_is_available() -> None:
    """配置了真实 Redis 时验证读写与健康状态；未配置则跳过。"""
    settings = get_settings()
    if settings.redis.url is None:
        pytest.skip("未配置 REDIS__URL，跳过真实 Redis 用例")

    async with redis_lifespan(None):
        client = get_redis()
        key = build_key("test", uuid4().hex)
        try:
            await client.set(key, "ok", ex=5)
            assert await client.get(key) == "ok"
            assert await probe_redis() == REDIS_STATUS_UP
        finally:
            await client.delete(key)

    # 生命周期结束后单例必须被清空，避免外部误用已关闭的连接
    with pytest.raises(RedisUnavailableError):
        get_redis()
