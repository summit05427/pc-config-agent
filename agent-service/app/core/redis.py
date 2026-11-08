"""Redis 客户端生命周期与健康探测。

模板定位：
1. 只提供连接、探测与错误约定，不内置缓存、锁、限流等具体用法；
2. 客户端随 FastAPI lifespan 创建与关闭，业务代码禁止自行建连接；
3. Redis 是否必需由 REDIS__REQUIRED 决定，启动行为必须明确可预期。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from redis.asyncio import Redis

from app.core.config import RedisSettings, get_settings
from app.core.exceptions import RedisUnavailableError

logger = structlog.get_logger(__name__)

# 进程内单例：连接池由 redis-py 管理，重复创建会浪费连接
_client: Redis | None = None

# 健康探测的三种结果，供 /health 原样暴露给编排系统
REDIS_STATUS_DISABLED = "disabled"
REDIS_STATUS_UNAVAILABLE = "unavailable"
REDIS_STATUS_DOWN = "down"
REDIS_STATUS_UP = "up"


def _set_client(client: Redis | None) -> None:
    """切换单例，测试与生命周期结束后都需要重置。"""
    global _client
    _client = client


def get_redis() -> Redis:
    """返回已就绪的客户端。

    未初始化说明配置缺失或启动时已降级，这里抛 503 而不是让调用方拿到 None。
    """
    if _client is None:
        raise RedisUnavailableError()
    return _client


def is_redis_enabled() -> bool:
    """是否配置了 Redis，用于区分「未启用」与「已启用但故障」。"""
    return get_settings().redis.url is not None


async def probe_redis() -> str:
    """执行一次 PING，返回可观测的状态字符串。

    健康检查只做一次轻量 PING，不读取业务 key，避免探活本身产生额外压力。
    """
    if not is_redis_enabled():
        return REDIS_STATUS_DISABLED

    client = _client
    if client is None:
        # 已配置但客户端未建立：启动时连接失败并走了降级分支
        return REDIS_STATUS_UNAVAILABLE

    try:
        await client.ping()
    except Exception as exc:
        # 同一故障会被周期性探活触发，只记录类型，不重复打印堆栈
        logger.warning("redis.health_check_failed", error_type=type(exc).__name__)
        return REDIS_STATUS_DOWN
    return REDIS_STATUS_UP


def _create_client(config: RedisSettings) -> Redis:
    """按配置创建异步客户端，连接池参数全部显式传入。"""
    # model_validator 已保证 required=true 时 url 非空
    assert config.url is not None
    return Redis.from_url(
        config.url.get_secret_value(),
        max_connections=config.max_connections,
        socket_timeout=config.socket_timeout_seconds,
        socket_connect_timeout=config.connect_timeout_seconds,
        health_check_interval=config.health_check_interval_seconds,
        # 缓存值统一按字符串处理，避免调用方再关心字节解码
        decode_responses=True,
    )


@asynccontextmanager
async def redis_lifespan(app: object) -> AsyncIterator[None]:
    """建立并释放 Redis 连接池。

    required=true 时连接失败直接拒绝启动；
    required=false 时降级启动，仅记录 warning，由调用方决定是否使用。
    """
    config = get_settings().redis

    if config.url is None:
        if config.required:
            raise RuntimeError("REDIS__REQUIRED=true 时必须提供 REDIS__URL")
        logger.warning("redis.disabled", reason="未配置 REDIS__URL")
        yield
        return

    client = _create_client(config)
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        if config.required:
            logger.error(
                "redis.unavailable",
                required=True,
                error_type=type(exc).__name__,
            )
            raise RuntimeError("Redis 不可用且 REDIS__REQUIRED=true，拒绝启动") from exc

        logger.warning(
            "redis.unavailable",
            required=False,
            error_type=type(exc).__name__,
        )
        yield
        return

    _set_client(client)
    logger.info(
        "redis.ready",
        max_connections=config.max_connections,
        key_prefix=config.key_prefix,
    )
    try:
        yield
    finally:
        await client.aclose()
        # 连接已关闭，避免后续误用失效连接
        _set_client(None)
