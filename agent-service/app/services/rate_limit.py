"""按用户限流的固定窗口实现。

为什么用固定窗口而不是令牌桶：
- 对话接口的限流目标是「挡住脚本刷接口」，不是平滑流量整形；
- 固定窗口只需要 INCR + EXPIRE，没有 Lua 脚本与时钟同步成本，故障面更小。

已知取舍：窗口边界会出现最多 2 倍突刺。若后续要精确平滑，再引入令牌桶。

Redis 不可用时默认放行（fail-open），与幂等降级策略一致；生产需要严格限流时
把 `RATE_LIMIT__FAIL_OPEN` 置为 false，此时返回 503 而不是静默放行。
"""

import time
from dataclasses import dataclass
from typing import Any

import structlog

from app.core.config import RateLimitSettings, get_settings
from app.core.exceptions import RateLimitExceededError, RedisUnavailableError
from app.core.keys import build_key
from app.core.metrics import RATE_LIMIT_REJECTIONS
from app.core.redis import get_redis, is_redis_enabled

logger = structlog.get_logger(__name__)

SCOPE_CHAT = "chat"
LIMIT_DOMAIN = "ratelimit"


@dataclass(frozen=True)
class RateLimitDecision:
    """一次窗口检查的结果。"""

    allowed: bool
    remaining: int
    retry_after_seconds: int


async def check_window(
    client: Any,
    scope: str,
    subject: str,
    limit: int,
    window_seconds: int,
    *,
    now: float | None = None,
) -> RateLimitDecision:
    """在固定窗口内累加计数并判断是否超限。

    `client` 只要求实现 `incr` / `expire`，单测可用内存假对象替换。
    `now` 可注入，便于测试跨窗口行为而不 sleep。
    """
    current = time.time() if now is None else now
    window_index = int(current // window_seconds)
    key = build_key(LIMIT_DOMAIN, scope, subject, str(window_index))

    count = int(await client.incr(key))
    if count == 1:
        # 首次计数时设置过期：窗口结束后 key 自动回收，避免 key 无限增长
        await client.expire(key, window_seconds + 1)

    retry_after = window_seconds - int(current % window_seconds)
    return RateLimitDecision(
        allowed=count <= limit,
        remaining=max(limit - count, 0),
        retry_after_seconds=retry_after,
    )


async def enforce_chat_rate_limit(user_id: str) -> None:
    """对话入口限流；超限抛 429 并带 `Retry-After`。"""
    settings = get_settings().rate_limit
    if not settings.enabled or settings.chat_per_minute <= 0:
        return
    if not is_redis_enabled():
        return

    try:
        decision = await check_window(
            get_redis(),
            SCOPE_CHAT,
            user_id,
            settings.chat_per_minute,
            settings.window_seconds,
        )
    except RedisUnavailableError:
        _degrade(settings, "client_unavailable")
        return
    except Exception as exc:  # noqa: BLE001 - 限流不得把 Redis 故障升级成业务故障
        logger.warning("rate_limit.redis_error", error_type=type(exc).__name__)
        _degrade(settings, "redis_error")
        return

    if decision.allowed:
        return

    RATE_LIMIT_REJECTIONS.labels(scope=SCOPE_CHAT).inc()
    logger.warning(
        "rate_limit.rejected",
        scope=SCOPE_CHAT,
        retry_after_seconds=decision.retry_after_seconds,
    )
    raise RateLimitExceededError(decision.retry_after_seconds)


def _degrade(settings: RateLimitSettings, reason: str) -> None:
    """Redis 故障时的分支：fail-open 放行并记录，fail-closed 返回 503。"""
    if settings.fail_open:
        logger.warning("rate_limit.degraded", reason=reason, fail_open=True)
        return
    raise RedisUnavailableError("限流服务不可用，请稍后重试")
