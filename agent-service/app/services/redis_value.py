"""Redis 值编解码的公共规则。

cache 与 idempotency 需要同一套约束：
1. TTL 必须为正，显式值优先于配置默认值；
2. 值只走 JSON，禁止 pickle，避免反序列化执行任意代码；
3. 读到损坏数据统一「告警 + 删除 + 当作不存在」，避免脏值反复失败。

规则分散在各原语里时，改一处会留下静默不一致。锁保存的是随机 token，
释放要用 Lua 比对，语义不同，因此不并入本模块。
"""

import json
from typing import Any

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


def resolve_ttl(ttl_seconds: int | None, *, default_seconds: int, label: str) -> int:
    """解析显式 TTL 或配置默认值，并保证为正数。

    :raises ValueError: TTL 小于等于 0，`label` 用于让错误信息指明确切原语。
    """
    ttl = ttl_seconds if ttl_seconds is not None else default_seconds
    if ttl <= 0:
        raise ValueError(f"{label} TTL 必须大于 0")
    return ttl


def encode(value: Any, *, label: str) -> str:
    """把值转为 JSON 文本；不可序列化时带上业务语义明确报错。

    :raises TypeError: 值包含 JSON 不支持的类型。
    """
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label}必须可被 JSON 序列化") from exc


def decode(raw: str | bytes) -> tuple[bool, Any]:
    """返回 (是否合法, 值)；字节解码失败与非法 JSON 都视为损坏。"""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return False, None
    try:
        return True, json.loads(raw)
    except json.JSONDecodeError:
        return False, None


async def read_json(
    client: Redis,
    key: str,
    *,
    invalid_event: str,
) -> tuple[bool, Any]:
    """读取并解析 JSON 值；缺失与损坏都返回 (False, None)。

    `invalid_event` 保留各原语的日志事件名，便于按用途检索告警。
    损坏值删除后，下一次读取会重新生成。
    """
    raw = await client.get(key)
    if raw is None:
        return False, None

    is_valid, value = decode(raw)
    if is_valid:
        return True, value

    logger.warning(invalid_event, key=key)
    await client.delete(key)
    return False, None
