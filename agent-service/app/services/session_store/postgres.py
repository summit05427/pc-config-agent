"""Postgres 适配器：会话目录与消息转写共用一个连接池与一个事务边界。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.services.session_store.interface import SessionEntry
from app.services.session_store.mapping import to_payload, to_record

logger = structlog.get_logger(__name__)

CREATE_META_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS session_meta (
    user_id        TEXT        NOT NULL,
    thread_id      TEXT        NOT NULL,
    title          VARCHAR(80),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_pinned      BOOLEAN     NOT NULL DEFAULT FALSE,
    is_archived    BOOLEAN     NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, thread_id)
)
"""

CREATE_META_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_session_meta_recent
    ON session_meta (user_id, last_active_at DESC)
"""

CREATE_META_ORDER_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_session_meta_order
    ON session_meta (user_id, is_archived, is_pinned DESC, last_active_at DESC)
"""

# 会话级模型选择：NULL 表示 Auto。ADD COLUMN 保证对既有部署幂等。
ADD_MODEL_KEY_COLUMN_SQL = """
ALTER TABLE session_meta ADD COLUMN IF NOT EXISTS model_key VARCHAR(64)
"""

ADD_PINNED_COLUMN_SQL = """
ALTER TABLE session_meta ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT FALSE
"""

ADD_ARCHIVED_COLUMN_SQL = """
ALTER TABLE session_meta ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE
"""

# 结构化配置结果挂在助手消息上；历史接口返回它，详情面板才能跨刷新使用
ADD_BUILD_RESULT_COLUMN_SQL = """
ALTER TABLE session_messages ADD COLUMN IF NOT EXISTS build_result JSONB
"""

# 回合级元数据（引用、思考可见性）挂在助手消息上：刷新后引用不再丢失，
# 又不必为每个新字段单独建列
ADD_METADATA_COLUMN_SQL = """
ALTER TABLE session_messages ADD COLUMN IF NOT EXISTS metadata JSONB
"""

CREATE_MESSAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS session_messages (
    user_id    TEXT        NOT NULL,
    thread_id  TEXT        NOT NULL,
    seq        INTEGER     NOT NULL,
    role       TEXT        NOT NULL,
    content    TEXT        NOT NULL DEFAULT '',
    tool_calls JSONB,
    name       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, thread_id, seq)
)
"""

CREATE_MESSAGES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_session_messages_lookup
    ON session_messages (user_id, thread_id, seq)
"""

UPSERT_META_SQL = """
INSERT INTO session_meta (user_id, thread_id, title, last_active_at)
VALUES (%s, %s, %s, now())
ON CONFLICT (user_id, thread_id) DO UPDATE
SET last_active_at = now(),
    updated_at = now(),
    title = COALESCE(session_meta.title, EXCLUDED.title)
"""

LIST_META_SQL = """
SELECT thread_id, title, last_active_at, model_key, is_pinned, is_archived
FROM session_meta
WHERE user_id = %s AND is_archived = %s
ORDER BY is_pinned DESC, last_active_at DESC, thread_id
LIMIT %s OFFSET %s
"""

COUNT_META_SQL = """
SELECT COUNT(*) FROM session_meta WHERE user_id = %s AND is_archived = %s
"""

GET_META_SQL = """
SELECT thread_id, title, last_active_at, updated_at, model_key, is_pinned, is_archived
FROM session_meta
WHERE user_id = %s AND thread_id = %s
"""

RENAME_META_SQL = """
UPDATE session_meta SET title = %s, updated_at = now()
WHERE user_id = %s AND thread_id = %s
"""

SELECT_MODEL_KEY_SQL = """
SELECT model_key FROM session_meta WHERE user_id = %s AND thread_id = %s
"""

SET_MODEL_KEY_SQL = """
UPDATE session_meta
SET model_key = %s, updated_at = now()
WHERE user_id = %s AND thread_id = %s
RETURNING updated_at
"""

INSERT_MESSAGES_SQL = """
INSERT INTO session_messages (
    user_id, thread_id, seq, role, content, tool_calls, name, build_result, metadata
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (user_id, thread_id, seq) DO NOTHING
"""

# 重新生成：覆盖同序号消息内容；只有内容变化时才刷新 created_at
UPSERT_MESSAGES_SQL = """
INSERT INTO session_messages (
    user_id, thread_id, seq, role, content, tool_calls, name, build_result, metadata
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (user_id, thread_id, seq) DO UPDATE
SET role = EXCLUDED.role,
    content = EXCLUDED.content,
    tool_calls = EXCLUDED.tool_calls,
    name = EXCLUDED.name,
    build_result = EXCLUDED.build_result,
    metadata = EXCLUDED.metadata,
    created_at = CASE
        WHEN session_messages.content IS DISTINCT FROM EXCLUDED.content THEN now()
        ELSE session_messages.created_at
    END
"""

COUNT_MESSAGES_SQL = """
SELECT COUNT(*) FROM session_messages WHERE user_id = %s AND thread_id = %s
"""

SELECT_WINDOW_ASC_SQL = """
SELECT seq, role, content, tool_calls, name, created_at, build_result, metadata
FROM session_messages
WHERE user_id = %s AND thread_id = %s
ORDER BY seq
LIMIT %s OFFSET %s
"""

SELECT_WINDOW_DESC_SQL = """
SELECT seq, role, content, tool_calls, name, created_at, build_result, metadata
FROM session_messages
WHERE user_id = %s AND thread_id = %s
ORDER BY seq DESC
LIMIT %s OFFSET %s
"""

SET_PINNED_SQL = """
UPDATE session_meta SET is_pinned = %s, updated_at = now()
WHERE user_id = %s AND thread_id = %s
RETURNING thread_id, title, last_active_at, updated_at, model_key, is_pinned, is_archived
"""

SET_ARCHIVED_SQL = """
UPDATE session_meta SET is_archived = %s, updated_at = now()
WHERE user_id = %s AND thread_id = %s
RETURNING thread_id, title, last_active_at, updated_at, model_key, is_pinned, is_archived
"""

DELETE_MESSAGES_SQL = """
DELETE FROM session_messages WHERE user_id = %s AND thread_id = %s
"""

DELETE_META_SQL = """
DELETE FROM session_meta WHERE user_id = %s AND thread_id = %s
"""


class PostgresSessionStore:
    """连接池由 checkpointer 生命周期拥有，本适配器只借用。"""

    def __init__(self, pool: AsyncConnectionPool, *, auto_create: bool) -> None:
        self._pool = pool
        self._auto_create = auto_create

    async def setup(self) -> None:
        if not self._auto_create:
            # 无 DDL 权限的托管库由运维手工建表，这里只做绑定
            logger.info("session_store.ready", backend="postgres", auto_setup=False)
            return

        async with self._pool.connection() as connection:
            # 顺序敏感：先建表再 ALTER。ADD_BUILD_RESULT/ADD_METADATA 作用于 session_messages，
            # 排在 CREATE_MESSAGES_TABLE 之前时，全新库启动即报表不存在（存量库看不出）。
            for statement in (
                CREATE_META_TABLE_SQL,
                CREATE_META_INDEX_SQL,
                ADD_MODEL_KEY_COLUMN_SQL,
                ADD_PINNED_COLUMN_SQL,
                ADD_ARCHIVED_COLUMN_SQL,
                CREATE_MESSAGES_TABLE_SQL,
                ADD_BUILD_RESULT_COLUMN_SQL,
                ADD_METADATA_COLUMN_SQL,
                CREATE_META_ORDER_INDEX_SQL,
                CREATE_MESSAGES_INDEX_SQL,
            ):
                await connection.execute(statement)
        logger.info("session_store.ready", backend="postgres", auto_setup=True)

    async def record_turn(
        self,
        user_id: str,
        thread_id: str,
        messages: list[Any],
        title: str | None,
        replace_existing: bool = False,
        build_result: dict[str, Any] | None = None,
        citations: list[dict[str, Any]] | None = None,
        had_reasoning: bool = False,
    ) -> None:
        records = [(seq, to_record(message)) for seq, message in enumerate(messages)]
        # 结果只属于本轮最后一条助手消息，避免历史里每条助手消息都带同一份配置
        last_assistant_seq = next(
            (seq for seq, record in reversed(records) if record["role"] == "assistant"),
            None,
        )
        # 引用与思考可见性同属回合元数据：只挂最后一条助手消息
        metadata: dict[str, Any] = {}
        if citations:
            metadata["citations"] = citations
        if had_reasoning:
            metadata["had_reasoning"] = True
        params = [
            (
                user_id,
                thread_id,
                seq,
                record["role"],
                record["content"],
                Jsonb(record["tool_calls"]) if record["tool_calls"] is not None else None,
                record["name"],
                Jsonb(build_result)
                if build_result is not None and seq == last_assistant_seq
                else None,
                Jsonb(metadata) if metadata and seq == last_assistant_seq else None,
            )
            for seq, record in records
        ]

        # 消息与活跃时间在同一事务里提交，避免「列表有新时间、历史缺本轮消息」
        async with self._pool.connection() as connection, connection.transaction():
            if params:
                async with connection.cursor() as cursor:
                    await cursor.executemany(
                        UPSERT_MESSAGES_SQL if replace_existing else INSERT_MESSAGES_SQL,
                        params,
                    )
            await connection.execute(UPSERT_META_SQL, (user_id, thread_id, title))

    async def list_sessions(
        self,
        user_id: str,
        page: int,
        size: int,
        archived: bool = False,
    ) -> tuple[list[SessionEntry], int]:
        offset = (page - 1) * size
        async with self._pool.connection() as connection:
            count_cursor = await connection.execute(COUNT_META_SQL, (user_id, archived))
            total = (await count_cursor.fetchone() or (0,))[0]
            window_cursor = await connection.execute(
                LIST_META_SQL, (user_id, archived, size, offset)
            )
            rows = await window_cursor.fetchall()

        return [
            SessionEntry(
                thread_id=thread_id,
                title=title,
                last_active_at=last_active_at,
                model_key=model_key,
                is_pinned=is_pinned,
                is_archived=is_archived,
            )
            for thread_id, title, last_active_at, model_key, is_pinned, is_archived in rows
        ], total

    async def get_session(self, user_id: str, thread_id: str) -> SessionEntry | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(GET_META_SQL, (user_id, thread_id))
            row = await cursor.fetchone()
        return self._to_entry(row)

    async def set_pinned(self, user_id: str, thread_id: str, pinned: bool) -> SessionEntry | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(SET_PINNED_SQL, (pinned, user_id, thread_id))
            row = await cursor.fetchone()
        return self._to_entry(row)

    async def set_archived(
        self, user_id: str, thread_id: str, archived: bool
    ) -> SessionEntry | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(SET_ARCHIVED_SQL, (archived, user_id, thread_id))
            row = await cursor.fetchone()
        return self._to_entry(row)

    @staticmethod
    def _to_entry(row: Any) -> SessionEntry | None:
        if row is None:
            return None
        return SessionEntry(
            thread_id=row[0],
            title=row[1],
            last_active_at=row[2],
            updated_at=row[3],
            model_key=row[4],
            is_pinned=row[5],
            is_archived=row[6],
        )

    async def rename_session(self, user_id: str, thread_id: str, title: str) -> bool:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(RENAME_META_SQL, (title, user_id, thread_id))
            return cursor.rowcount > 0

    async def delete_session(self, user_id: str, thread_id: str) -> bool:
        # 两表在同一事务里删除：中途失败不会留下无主消息
        async with self._pool.connection() as connection, connection.transaction():
            messages_cursor = await connection.execute(
                DELETE_MESSAGES_SQL, (user_id, thread_id)
            )
            meta_cursor = await connection.execute(DELETE_META_SQL, (user_id, thread_id))
            deleted_messages = (messages_cursor.rowcount or 0) > 0
            deleted_meta = (meta_cursor.rowcount or 0) > 0
        return deleted_meta or deleted_messages

    async def read_messages(
        self,
        user_id: str,
        thread_id: str,
        page: int,
        size: int,
        order: str = "asc",
    ) -> tuple[list[dict[str, Any]], int]:
        offset = (page - 1) * size
        sql = SELECT_WINDOW_DESC_SQL if order == "desc" else SELECT_WINDOW_ASC_SQL

        async with self._pool.connection() as connection:
            count_cursor = await connection.execute(COUNT_MESSAGES_SQL, (user_id, thread_id))
            total = (await count_cursor.fetchone() or (0,))[0]
            window_cursor = await connection.execute(sql, (user_id, thread_id, size, offset))
            rows = await window_cursor.fetchall()

        records = [
            {
                # seq 是会话内稳定序号，与 thread_id 拼成 message_id 供反馈绑定
                "message_id": f"{thread_id}:{seq}",
                "role": role,
                "content": content,
                "tool_calls": tool_calls,
                "name": name,
                "created_at": created_at,
                "build_result": build_result,
                "metadata": metadata,
            }
            for seq, role, content, tool_calls, name, created_at, build_result, metadata in rows
        ]
        return [to_payload(record) for record in records], total

    async def get_model_key(self, user_id: str, thread_id: str) -> str | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(SELECT_MODEL_KEY_SQL, (user_id, thread_id))
            row = await cursor.fetchone()
        return row[0] if row else None

    async def set_model_key(
        self,
        user_id: str,
        thread_id: str,
        model_key: str | None,
    ) -> datetime | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                SET_MODEL_KEY_SQL, (model_key, user_id, thread_id)
            )
            row = await cursor.fetchone()
        return row[0] if row else None
