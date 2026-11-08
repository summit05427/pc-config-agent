"""用量上报 outbox：Agent 侧的投递缓冲，Java 仍是唯一用量台账。

为什么需要它：
- 旧实现只有进程内有界队列，崩溃即丢、溢出即丢，事后无法发现「哪些没上报」；
- Java 的 `model_usage` 是唯一事实源（D7），Agent 不能建第二套台账；
- 因此这里只存「待投递事件」：投递成功立刻标记 `dispatched`，失败按退避重排，
  超过尝试上限或遇到 4xx 标记 `dead`，供对账与人工排查。

状态机：

```text
pending --发送成功--> dispatched（保留 7 天后清理）
   |--可重试失败--> pending（attempts+1，next_retry_at 延后）
   |--不可重试 / attempts>=8--> dead
```

并发与租约：
- 连接池是 autocommit 的，`SELECT ... FOR UPDATE` 的行锁在语句结束即释放；
- 所以领取时用「UPDATE 顺带把 `next_retry_at` 推到租约之后」代替持锁，
  同一行在租约内不会被其它副本再次领取；租约到期仍未被标记则视为投递失败重试。

降级：
- `STORAGE__BACKEND=memory`、表缺失或写库异常 → 进程内有界队列（重启即丢），
  记录 `usage.outbox_degraded` 并累加指标；DB 恢复后下一次成功领取会自动退出降级。
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

import structlog
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.core.metrics import (
    USAGE_OUTBOX_DEAD,
    USAGE_OUTBOX_DEGRADED_TOTAL,
    USAGE_OUTBOX_PENDING,
)

logger = structlog.get_logger(__name__)

# 状态机取值：与建表语句里的 CHECK 约束必须一致
STATUS_PENDING = "pending"
STATUS_DISPATCHED = "dispatched"
STATUS_DEAD = "dead"

# 记录当前存放在哪一侧：DB 版与内存降级版共用同一套上报循环
SOURCE_POSTGRES: Literal["postgres"] = "postgres"
SOURCE_MEMORY: Literal["memory"] = "memory"

# 超过该尝试次数直接进入 dead，避免无意义地无限重试
MAX_ATTEMPTS = 8
MAX_ERROR_LENGTH = 200
# dispatched 只用于短期排查与对账，到期物理删除
DISPATCHED_RETENTION_SECONDS = 7 * 24 * 3600

# 领取租约必须长于单次上报耗时（控制面超时 5s），否则同一行会被重复投递
CLAIM_LEASE_SECONDS = 60.0

# 内存降级队列上限：与旧实现保持一致，溢出时丢弃最旧记录
MAX_MEMORY_QUEUE_SIZE = 1000

# 第 n 次失败后的等待时长；超过列表长度时沿用最后一个值
RETRY_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 5.0, 30.0, 120.0, 300.0, 600.0, 1800.0)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS usage_outbox (
    invocation_id TEXT        PRIMARY KEY,
    payload       JSONB       NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'dispatched', 'dead')),
    attempts      INTEGER     NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

# 只索引待投递行：状态过滤后表很小，轮询代价与历史量无关
CREATE_PENDING_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_usage_outbox_pending
    ON usage_outbox (next_retry_at)
    WHERE status = 'pending'
"""

# 清理任务按 updated_at 扫已投递行
CREATE_DISPATCHED_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_usage_outbox_dispatched
    ON usage_outbox (updated_at)
    WHERE status = 'dispatched'
"""

INSERT_SQL = """
INSERT INTO usage_outbox (invocation_id, payload)
VALUES (%s, %s)
ON CONFLICT (invocation_id) DO NOTHING
"""

# UPDATE 顺带推进 next_retry_at 形成租约，替代无法在 autocommit 下持有的行锁
CLAIM_SQL = """
UPDATE usage_outbox
SET next_retry_at = now() + make_interval(secs => %s),
    updated_at = now()
WHERE invocation_id IN (
    SELECT invocation_id
    FROM usage_outbox
    WHERE status = 'pending' AND next_retry_at <= now()
    ORDER BY next_retry_at
    LIMIT %s
    FOR UPDATE SKIP LOCKED
)
RETURNING invocation_id, payload, attempts
"""

MARK_DISPATCHED_SQL = """
UPDATE usage_outbox
SET status = 'dispatched',
    attempts = attempts + 1,
    last_error = NULL,
    updated_at = now()
WHERE invocation_id = ANY(%s)
"""

MARK_FAILED_SQL = """
UPDATE usage_outbox
SET status = %s,
    attempts = %s,
    next_retry_at = now() + make_interval(secs => %s),
    last_error = %s,
    updated_at = now()
WHERE invocation_id = %s
"""

PURGE_SQL = """
DELETE FROM usage_outbox
WHERE status = 'dispatched'
  AND updated_at < now() - make_interval(secs => %s)
"""

COUNT_BY_STATUS_SQL = "SELECT COUNT(*) FROM usage_outbox WHERE status = %s"

TABLE_EXISTS_SQL = "SELECT to_regclass('usage_outbox')"

_pool: AsyncConnectionPool | None = None
_is_degraded = False


@dataclass(frozen=True)
class ClaimedRecord:
    """一次领取到的待投递记录；`source` 决定标记回写到哪一侧。"""

    invocation_id: str
    payload: dict[str, Any]
    attempts: int
    source: Literal["postgres", "memory"]


@dataclass
class _MemoryEntry:
    invocation_id: str
    payload: dict[str, Any]
    attempts: int = 0
    # 使用 monotonic 时钟，避免系统时间调整导致租约错乱
    next_attempt_at: float = field(default_factory=time.monotonic)


class _MemoryOutbox:
    """降级队列：语义尽量与 DB 版一致，但重启即丢，只用于尽力而为。"""

    def __init__(self) -> None:
        self._entries: deque[_MemoryEntry] = deque()
        self._overflow_count = 0
        self._dead_count = 0

    @property
    def pending_count(self) -> int:
        return len(self._entries)

    @property
    def dead_count(self) -> int:
        return self._dead_count

    @property
    def overflow_count(self) -> int:
        return self._overflow_count

    def add(self, record: dict[str, Any]) -> None:
        if len(self._entries) >= MAX_MEMORY_QUEUE_SIZE:
            self._entries.popleft()
            self._overflow_count += 1
            logger.error(
                "model_usage.queue_overflow",
                dropped=1,
                overflow_count=self._overflow_count,
                queue_size=len(self._entries),
            )
        self._entries.append(
            _MemoryEntry(invocation_id=str(record["invocation_id"]), payload=record)
        )

    def claim(self, limit: int) -> list[ClaimedRecord]:
        now = time.monotonic()
        claimed: list[ClaimedRecord] = []
        for entry in self._entries:
            if len(claimed) >= limit:
                break
            if entry.next_attempt_at > now:
                continue
            # 租约：本轮被领取后，短时间内不会被同一轮或并发循环重复领取
            entry.next_attempt_at = now + CLAIM_LEASE_SECONDS
            claimed.append(
                ClaimedRecord(
                    invocation_id=entry.invocation_id,
                    payload=dict(entry.payload),
                    attempts=entry.attempts,
                    source=SOURCE_MEMORY,
                )
            )
        return claimed

    def discard(self, invocation_ids: Iterable[str]) -> None:
        targets = set(invocation_ids)
        if not targets:
            return
        self._entries = deque(
            entry for entry in self._entries if entry.invocation_id not in targets
        )

    def mark_failed(
        self,
        invocation_id: str,
        *,
        new_attempts: int,
        is_terminal: bool,
        delay_seconds: float,
    ) -> None:
        for entry in self._entries:
            if entry.invocation_id != invocation_id:
                continue
            if is_terminal:
                self._entries.remove(entry)
                self._dead_count += 1
            else:
                entry.attempts = new_attempts
                entry.next_attempt_at = time.monotonic() + delay_seconds
            return

    def clear(self) -> None:
        self._entries.clear()
        self._overflow_count = 0
        self._dead_count = 0


_memory = _MemoryOutbox()


def _degrade(error: Exception) -> None:
    """进入降级模式；只记录一次，避免 DB 长时间不可用时刷屏。"""
    global _is_degraded
    if _is_degraded:
        return
    _is_degraded = True
    USAGE_OUTBOX_DEGRADED_TOTAL.inc()
    logger.error("usage.outbox_degraded", error_type=type(error).__name__)


def _recover() -> None:
    """DB 恢复后退出降级，让新记录重新走持久化路径。"""
    global _is_degraded
    if not _is_degraded:
        return
    _is_degraded = False
    logger.warning("usage.outbox_recovered")


def _backoff_seconds(attempts: int) -> float:
    index = min(max(attempts, 1) - 1, len(RETRY_BACKOFF_SECONDS) - 1)
    return RETRY_BACKOFF_SECONDS[index]


def _normalize_invocation_id(record: dict[str, Any]) -> str | None:
    value = record.get("invocation_id")
    return value if isinstance(value, str) and value else None


async def setup_usage_outbox(pool: AsyncConnectionPool | None, *, auto_setup: bool) -> None:
    """应用启动时绑定存储：postgres 建表，memory 走进程内降级队列。"""
    global _pool, _is_degraded
    _pool = pool
    _is_degraded = False
    _memory.clear()

    if pool is None:
        logger.info("usage_outbox.memory_mode")
        return

    try:
        async with pool.connection() as connection:
            if auto_setup:
                await connection.execute(CREATE_TABLE_SQL)
                await connection.execute(CREATE_PENDING_INDEX_SQL)
                await connection.execute(CREATE_DISPATCHED_INDEX_SQL)
            else:
                # 托管库由运维手工建表；表缺失时必须显式降级，而不是每次写入都失败
                cursor = await connection.execute(TABLE_EXISTS_SQL)
                row = await cursor.fetchone()
                if not row or row[0] is None:
                    raise RuntimeError("usage_outbox 表不存在且 STORAGE__AUTO_SETUP=false")
    except Exception as error:
        _pool = None
        _degrade(error)
        logger.error("usage_outbox.setup_failed", auto_setup=auto_setup)
        return

    logger.info("usage_outbox.ready", backend="postgres", auto_setup=auto_setup)


async def add(record: dict[str, Any]) -> None:
    """把一条待投递记录落库；任何异常都降级到内存，绝不向调用方抛出。"""
    invocation_id = _normalize_invocation_id(record)
    if invocation_id is None:
        logger.error("usage_outbox.invalid_record", reason="missing invocation_id")
        return

    if _pool is None or _is_degraded:
        _memory.add(record)
        return

    try:
        async with _pool.connection() as connection:
            await connection.execute(INSERT_SQL, (invocation_id, Jsonb(record)))
    except Exception as error:
        # 边界层：写库失败不能影响对话主链路，退回内存队列并标记降级
        _degrade(error)
        _memory.add(record)


async def _pg_claim(limit: int) -> list[ClaimedRecord]:
    assert _pool is not None
    async with _pool.connection() as connection:
        cursor = await connection.execute(CLAIM_SQL, (CLAIM_LEASE_SECONDS, limit))
        rows = await cursor.fetchall()

    claimed: list[ClaimedRecord] = []
    for invocation_id, payload, attempts in rows:
        if not isinstance(invocation_id, str) or not isinstance(payload, dict):
            logger.warning("usage_outbox.invalid_row", row_type=type(payload).__name__)
            continue
        claimed.append(
            ClaimedRecord(
                invocation_id=invocation_id,
                payload=payload,
                attempts=int(attempts) if isinstance(attempts, (int, Decimal)) else 0,
                source=SOURCE_POSTGRES,
            )
        )
    return claimed


async def claim(limit: int) -> list[ClaimedRecord]:
    """领取一批到期记录：优先 DB，剩余额度再补内存降级队列。"""
    if limit <= 0:
        return []

    claimed: list[ClaimedRecord] = []
    if _pool is not None:
        try:
            claimed.extend(await _pg_claim(limit))
        except Exception as error:
            _degrade(error)
        else:
            _recover()

    remaining = limit - len(claimed)
    if remaining > 0:
        claimed.extend(_memory.claim(remaining))
    return claimed


async def mark_dispatched(records: list[ClaimedRecord]) -> None:
    """投递成功后标记 dispatched；标记失败只会导致重复投递，由 Java 侧幂等兜底。"""
    pg_ids = [record.invocation_id for record in records if record.source == SOURCE_POSTGRES]
    memory_ids = [
        record.invocation_id for record in records if record.source == SOURCE_MEMORY
    ]

    if pg_ids and _pool is not None:
        try:
            async with _pool.connection() as connection:
                await connection.execute(MARK_DISPATCHED_SQL, (pg_ids,))
        except Exception as error:
            logger.warning(
                "usage_outbox.mark_dispatched_failed", error_type=type(error).__name__
            )
    if memory_ids:
        _memory.discard(memory_ids)


async def _pg_mark_failed(
    invocation_id: str, *, status: str, new_attempts: int, delay_seconds: float, error: str
) -> None:
    assert _pool is not None
    try:
        async with _pool.connection() as connection:
            await connection.execute(
                MARK_FAILED_SQL,
                (status, new_attempts, delay_seconds, error, invocation_id),
            )
    except Exception as update_error:
        # 记录仍保持 pending 且带租约，租约到期后会再试一次，不会永久卡死
        logger.warning(
            "usage_outbox.mark_failed_error", error_type=type(update_error).__name__
        )


async def mark_failed(
    records: list[ClaimedRecord], *, is_retryable: bool, error: str
) -> None:
    """按失败原因更新状态：可重试则延后重排，否则或超过上限标记 dead。"""
    error_text = error[:MAX_ERROR_LENGTH]

    for record in records:
        new_attempts = record.attempts + 1
        is_terminal = not is_retryable or new_attempts >= MAX_ATTEMPTS
        delay_seconds = 0.0 if is_terminal else _backoff_seconds(new_attempts)
        status = STATUS_DEAD if is_terminal else STATUS_PENDING

        if record.source == SOURCE_MEMORY:
            _memory.mark_failed(
                record.invocation_id,
                new_attempts=new_attempts,
                is_terminal=is_terminal,
                delay_seconds=delay_seconds,
            )
            continue
        await _pg_mark_failed(
            record.invocation_id,
            status=status,
            new_attempts=new_attempts,
            delay_seconds=delay_seconds,
            error=error_text,
        )


async def purge_dispatched() -> int:
    """清理超过保留期的 dispatched 行；返回删除条数。"""
    if _pool is None:
        return 0
    try:
        async with _pool.connection() as connection:
            cursor = await connection.execute(PURGE_SQL, (DISPATCHED_RETENTION_SECONDS,))
            return max(cursor.rowcount, 0)
    except Exception as error:
        _degrade(error)
        return 0


async def _pg_count(status: str) -> int:
    assert _pool is not None
    async with _pool.connection() as connection:
        cursor = await connection.execute(COUNT_BY_STATUS_SQL, (status,))
        row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0


async def counts() -> tuple[int, int]:
    """返回 (pending, dead) 数量，用于指标；只做小表上的计数查询。"""
    pending = _memory.pending_count
    dead = _memory.dead_count
    if _pool is None:
        return pending, dead

    try:
        pending += await _pg_count(STATUS_PENDING)
        dead += await _pg_count(STATUS_DEAD)
    except Exception as error:
        _degrade(error)
    return pending, dead


# 已告警过的 dead 数量：dead 只能靠人工对账补录，因此按「新增」触发一次 error 日志，
# 避免每轮上报都重复刷屏；回落到 0 时重置，便于下一次故障再次触发。
_dead_alerted_count: int = 0


async def update_metrics() -> None:
    """把当前积压量写进 Prometheus Gauge，并在 dead 新增时输出可告警的 error 日志。"""
    global _dead_alerted_count
    pending, dead = await counts()
    USAGE_OUTBOX_PENDING.set(pending)
    USAGE_OUTBOX_DEAD.set(dead)
    if dead == 0:
        _dead_alerted_count = 0
        return
    if dead <= _dead_alerted_count:
        return
    logger.error(
        "usage_outbox_dead_detected",
        dead_count=dead,
        pending_count=pending,
    )
    _dead_alerted_count = dead


def memory_overflow_count() -> int:
    """内存降级队列的溢出次数，供日志与测试断言。"""
    return _memory.overflow_count


def detach_usage_outbox() -> None:
    """应用关闭时解除对连接池的引用；记录本身仍保留在数据库中。"""
    global _pool
    _pool = None


def reset_usage_outbox() -> None:
    """清空进程内状态并解除连接池引用，仅供测试使用。"""
    global _pool, _is_degraded, _dead_alerted_count
    _pool = None
    _is_degraded = False
    _dead_alerted_count = 0
    _memory.clear()
