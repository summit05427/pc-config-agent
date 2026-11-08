"""通用幂等原语。

状态机只有三个值：
- processing：已抢占，正在执行；
- done：执行完成，结果可供重放；
- 无记录：未开始，或失败后被主动清理。

模板只提供状态存取，不决定接口返回什么。业务层在收到 processing 时
可以返回“处理中”，收到 done 时直接复用结果，从而避免重复调用模型。
值的 JSON 编解码与坏值策略统一由 redis_value 提供。
"""

from dataclasses import dataclass
from typing import Any

import structlog

from app.core.config import get_settings
from app.core.keys import build_key
from app.core.redis import get_redis
from app.services.redis_value import encode, read_json, resolve_ttl

logger = structlog.get_logger(__name__)

IDEMPOTENCY_DOMAIN = "idempotency"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
_VALID_STATUSES = frozenset({STATUS_PROCESSING, STATUS_DONE})

# 事件名与错误文案保持原样，避免影响既有排障习惯与调用方断言
_INVALID_VALUE_EVENT = "idempotency.invalid_value"
_PAYLOAD_LABEL = "幂等结果"
_TTL_LABEL = "幂等"


@dataclass(frozen=True)
class IdempotencyRecord:
    """幂等记录：processing 时 result 为 None，done 时携带结果。"""

    status: str
    result: Any | None = None


def idempotency_key(*parts: str) -> str:
    """生成幂等用途的 key，例如 `前缀:环境:idempotency:chat:request-id`。"""
    return build_key(IDEMPOTENCY_DOMAIN, *parts)


def _ttl(ttl_seconds: int | None) -> int:
    return resolve_ttl(
        ttl_seconds,
        default_seconds=get_settings().redis.idempotency_ttl_seconds,
        label=_TTL_LABEL,
    )


async def idempotency_begin(key: str, ttl_seconds: int | None = None) -> bool:
    """抢占幂等记录。

    返回 True 表示本次请求是第一个执行者；False 表示已有记录，
    调用方应读取记录并决定返回“处理中”还是复用结果。
    """
    payload = encode({"status": STATUS_PROCESSING}, label=_PAYLOAD_LABEL)
    ttl = _ttl(ttl_seconds)
    acquired = await get_redis().set(key, payload, nx=True, px=ttl * 1000)
    return bool(acquired)


async def idempotency_read(key: str) -> IdempotencyRecord | None:
    """读取幂等记录；不存在或内容损坏都返回 None。"""
    client = get_redis()
    is_found, data = await read_json(client, key, invalid_event=_INVALID_VALUE_EVENT)
    if not is_found:
        return None

    if not isinstance(data, dict) or data.get("status") not in _VALID_STATUSES:
        # 旧版本格式或手工写入会留下无法识别的数据，删除后允许重新执行
        logger.warning(_INVALID_VALUE_EVENT, key=key)
        await client.delete(key)
        return None

    return IdempotencyRecord(status=data["status"], result=data.get("result"))


async def idempotency_finish(
    key: str,
    result: Any,
    ttl_seconds: int | None = None,
) -> None:
    """标记执行完成并保存结果，供后续重复请求直接复用。"""
    payload = encode({"status": STATUS_DONE, "result": result}, label=_PAYLOAD_LABEL)
    ttl = _ttl(ttl_seconds)
    await get_redis().set(key, payload, px=ttl * 1000)


async def idempotency_abort(key: str) -> None:
    """清理未完成的记录，让失败请求可以立即重试。"""
    await get_redis().delete(key)
