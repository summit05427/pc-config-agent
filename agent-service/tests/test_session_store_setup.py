"""会话存储建表顺序回归。

全新库上线时踩过：`setup()` 先执行 `ALTER TABLE session_messages`，
建表语句却排在后面，导致空库启动即报 relation does not exist。
存量库看不出问题，所以用假连接锁住语句顺序，不依赖真实数据库。
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

from psycopg_pool import AsyncConnectionPool

from app.services.session_store.postgres import PostgresSessionStore


class _RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: str) -> None:
        self.statements.append(statement)


class _ConnectionContext:
    def __init__(self, connection: _RecordingConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _RecordingConnection:
        return self._connection

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakePool:
    def __init__(self, connection: _RecordingConnection) -> None:
        self._connection = connection

    def connection(self) -> _ConnectionContext:
        return _ConnectionContext(self._connection)


def _index_of(statements: list[str], marker: str) -> int:
    for index, statement in enumerate(statements):
        if marker in statement:
            return index
    raise AssertionError(f"未执行预期语句：{marker}")


def test_setup_creates_messages_table_before_altering_it() -> None:
    connection = _RecordingConnection()
    store = PostgresSessionStore(
        cast(AsyncConnectionPool, cast(Any, _FakePool(connection))),
        auto_create=True,
    )

    asyncio.run(store.setup())

    create_index = _index_of(connection.statements, "CREATE TABLE IF NOT EXISTS session_messages")
    assert create_index < _index_of(connection.statements, "ADD COLUMN IF NOT EXISTS build_result")
    assert create_index < _index_of(connection.statements, "ADD COLUMN IF NOT EXISTS metadata")
