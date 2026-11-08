"""Postgres 适配器：墓碑落在 `session_deletion_tasks`，跨进程与重启可恢复。"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from app.services.session_deletion import constants
from app.services.session_deletion.interface import ClaimedDeletion, next_backoff

logger = structlog.get_logger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS session_deletion_tasks (
    user_id              TEXT        NOT NULL,
    thread_id            TEXT        NOT NULL,
    checkpoint_thread_id TEXT        NOT NULL,
    status               TEXT        NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'completed', 'failed', 'cancelled')),
    attempts             INTEGER     NOT NULL DEFAULT 0,
    next_retry_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error           TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, thread_id)
)
"""

CREATE_PENDING_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_session_deletion_pending
    ON session_deletion_tasks (next_retry_at) WHERE status = 'pending'
"""

# 重复删除同一会话时重置墓碑：上一轮的 completed/failed 不能阻止新一轮清理
ENQUEUE_SQL = """
INSERT INTO session_deletion_tasks (user_id, thread_id, checkpoint_thread_id)
VALUES (%s, %s, %s)
ON CONFLICT (user_id, thread_id) DO UPDATE
SET checkpoint_thread_id = EXCLUDED.checkpoint_thread_id,
    status = 'pending',
    attempts = 0,
    next_retry_at = now(),
    last_error = NULL,
    updated_at = now()
"""

CANCEL_SQL = """
UPDATE session_deletion_tasks SET status = 'cancelled', updated_at = now()
WHERE user_id = %s AND thread_id = %s AND status = 'pending'
"""

CLAIM_SQL = """
UPDATE session_deletion_tasks
SET next_retry_at = now() + make_interval(secs => %s), updated_at = now()
WHERE (user_id, thread_id) IN (
    SELECT user_id, thread_id FROM session_deletion_tasks
    WHERE status = 'pending' AND next_retry_at <= now()
    ORDER BY next_retry_at
    LIMIT %s
    FOR UPDATE SKIP LOCKED
)
RETURNING user_id, thread_id, checkpoint_thread_id, attempts
"""

SELECT_STATUS_SQL = """
SELECT status FROM session_deletion_tasks WHERE user_id = %s AND thread_id = %s
"""

SELECT_ATTEMPTS_SQL = """
SELECT attempts FROM session_deletion_tasks WHERE user_id = %s AND thread_id = %s
"""

MARK_TERMINAL_SQL = """
UPDATE session_deletion_tasks
SET status = %s, next_retry_at = now(), last_error = %s, updated_at = now()
WHERE user_id = %s AND thread_id = %s AND status = 'pending'
"""

MARK_ATTEMPT_SQL = """
UPDATE session_deletion_tasks
SET status = %s, attempts = %s, last_error = %s,
    next_retry_at = now() + make_interval(secs => %s), updated_at = now()
WHERE user_id = %s AND thread_id = %s AND status = 'pending'
"""

RESCHEDULE_SQL = """
UPDATE session_deletion_tasks
SET next_retry_at = now() + make_interval(secs => %s), updated_at = now()
WHERE user_id = %s AND thread_id = %s AND status = 'pending'
"""

PURGE_SQL = """
DELETE FROM session_deletion_tasks
WHERE (status IN ('completed', 'cancelled')
       AND updated_at < now() - make_interval(secs => %s))
   OR (status = 'failed'
       AND updated_at < now() - make_interval(secs => %s))
"""

COUNT_BY_STATUS_SQL = """
SELECT status, COUNT(*) FROM session_deletion_tasks GROUP BY status
"""


class PostgresDeletionQueue:
    """连接池为 autocommit，领取时靠 `next_retry_at` 推进形成租约。"""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def setup(self) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(CREATE_TABLE_SQL)
            await connection.execute(CREATE_PENDING_INDEX_SQL)

    async def enqueue(
        self,
        user_id: str,
        thread_id: str,
        checkpoint_thread_id: str,
    ) -> bool:
        try:
            async with self._pool.connection() as connection:
                await connection.execute(
                    ENQUEUE_SQL, (user_id, thread_id, checkpoint_thread_id)
                )
        except Exception as exc:
            # 调用方会退化为「立即尽力删除」，这里只记录可恢复失败
            logger.warning(
                "session_deletion.enqueue_failed", error_type=type(exc).__name__
            )
            return False
        return True

    async def cancel(self, user_id: str, thread_id: str) -> None:
        try:
            async with self._pool.connection() as connection:
                await connection.execute(CANCEL_SQL, (user_id, thread_id))
        except Exception as exc:
            logger.warning(
                "session_deletion.cancel_failed", error_type=type(exc).__name__
            )

    async def claim(self, limit: int = constants.BATCH_SIZE) -> list[ClaimedDeletion]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                CLAIM_SQL, (constants.CLAIM_LEASE_SECONDS, limit)
            )
            rows = await cursor.fetchall()
        return [ClaimedDeletion(row[0], row[1], row[2], row[3]) for row in rows]

    async def status_of(self, user_id: str, thread_id: str) -> str | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                SELECT_STATUS_SQL, (user_id, thread_id)
            )
            row = await cursor.fetchone()
        return row[0] if row else None

    async def attempts_of(self, user_id: str, thread_id: str) -> int | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                SELECT_ATTEMPTS_SQL, (user_id, thread_id)
            )
            row = await cursor.fetchone()
        return int(row[0]) if row else None

    async def complete(
        self,
        user_id: str,
        thread_id: str,
        note: str | None = None,
    ) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                MARK_TERMINAL_SQL,
                (constants.STATUS_COMPLETED, note, user_id, thread_id),
            )

    async def fail(
        self,
        user_id: str,
        thread_id: str,
        attempts: int,
        error: str,
    ) -> str:
        status = (
            constants.STATUS_FAILED
            if attempts >= constants.MAX_ATTEMPTS
            else constants.STATUS_PENDING
        )
        backoff = 0.0 if status == constants.STATUS_FAILED else next_backoff(attempts)
        async with self._pool.connection() as connection:
            await connection.execute(
                MARK_ATTEMPT_SQL,
                (status, attempts, error, backoff, user_id, thread_id),
            )
        return status

    async def reschedule(self, user_id: str, thread_id: str) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                RESCHEDULE_SQL,
                (constants.CLAIM_LEASE_SECONDS, user_id, thread_id),
            )

    async def purge(
        self,
        completed_retention_seconds: float,
        failed_retention_seconds: float,
    ) -> int:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                PURGE_SQL, (completed_retention_seconds, failed_retention_seconds)
            )
            return cursor.rowcount

    async def counts(self) -> dict[str, int]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(COUNT_BY_STATUS_SQL)
            rows = await cursor.fetchall()
        result = dict.fromkeys(constants.STATUS_VALUES, 0)
        for status, count in rows:
            result[status] = count
        return result
