"""内存适配器：测试与 Solo 模式的默认后端，进程退出即丢失。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services.session_store.interface import SessionEntry
from app.services.session_store.mapping import to_payload, to_record


@dataclass
class _SessionRecord:
    """一个会话的全部内存状态；消息与目录同生同灭，删除天然原子。"""

    title: str | None = None
    model_key: str | None = None
    is_pinned: bool = False
    is_archived: bool = False
    last_active_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    messages: dict[int, dict[str, Any]] = field(default_factory=dict)


class InMemorySessionStore:
    """进程内实现；时间通过构造函数注入，测试无需 monkeypatch 模块全局。"""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._records: dict[tuple[str, str], _SessionRecord] = {}

    async def setup(self) -> None:
        return None

    async def record_turn(
        self,
        user_id: str,
        thread_id: str,
        messages: list[Any],
        title: str | None,
        replace_existing: bool = False,
    ) -> None:
        now = self._clock()
        record = self._records.get((user_id, thread_id))
        if record is None:
            record = _SessionRecord()
            self._records[(user_id, thread_id)] = record

        record.last_active_at = now
        record.updated_at = now
        if record.title is None and title is not None:
            record.title = title
        for seq, message in enumerate(messages):
            payload = to_record(message)
            payload["created_at"] = now
            if replace_existing:
                record.messages[seq] = payload
            else:
                record.messages.setdefault(seq, payload)
        if replace_existing:
            # 重新生成后消息条数可能减少，清理多余的尾部序号
            for seq in [key for key in record.messages if key >= len(messages)]:
                del record.messages[seq]

    async def list_sessions(
        self,
        user_id: str,
        page: int,
        size: int,
        archived: bool = False,
    ) -> tuple[list[SessionEntry], int]:
        rows = [
            item
            for item in self._records.items()
            if item[0][0] == user_id and item[1].is_archived == archived
        ]
        # 与 Postgres 的 ORDER BY is_pinned DESC, last_active_at DESC, thread_id ASC 保持一致
        rows.sort(
            key=lambda item: (
                not item[1].is_pinned,
                -item[1].last_active_at.timestamp(),
                item[0][1],
            )
        )
        window = rows[(page - 1) * size : (page - 1) * size + size]
        return [self._to_entry(thread_id, record) for (_, thread_id), record in window], len(rows)

    def _to_entry(self, thread_id: str, record: _SessionRecord) -> SessionEntry:
        return SessionEntry(
            thread_id=thread_id,
            title=record.title,
            last_active_at=record.last_active_at,
            model_key=record.model_key,
            updated_at=record.updated_at,
            is_pinned=record.is_pinned,
            is_archived=record.is_archived,
        )

    async def get_session(self, user_id: str, thread_id: str) -> SessionEntry | None:
        record = self._records.get((user_id, thread_id))
        if record is None:
            return None
        return self._to_entry(thread_id, record)

    async def set_pinned(self, user_id: str, thread_id: str, pinned: bool) -> SessionEntry | None:
        record = self._records.get((user_id, thread_id))
        if record is None:
            return None
        record.is_pinned = pinned
        record.updated_at = self._clock()
        return self._to_entry(thread_id, record)

    async def set_archived(
        self, user_id: str, thread_id: str, archived: bool
    ) -> SessionEntry | None:
        record = self._records.get((user_id, thread_id))
        if record is None:
            return None
        record.is_archived = archived
        record.updated_at = self._clock()
        return self._to_entry(thread_id, record)

    async def rename_session(self, user_id: str, thread_id: str, title: str) -> bool:
        record = self._records.get((user_id, thread_id))
        if record is None:
            return False
        record.title = title
        record.updated_at = self._clock()
        return True

    async def delete_session(self, user_id: str, thread_id: str) -> bool:
        return self._records.pop((user_id, thread_id), None) is not None

    async def read_messages(
        self,
        user_id: str,
        thread_id: str,
        page: int,
        size: int,
        order: str = "asc",
    ) -> tuple[list[dict[str, Any]], int]:
        record = self._records.get((user_id, thread_id))
        if record is None:
            return [], 0

        ordered = sorted(record.messages.items(), reverse=order == "desc")
        window = [item for _, item in ordered[(page - 1) * size : (page - 1) * size + size]]
        return [to_payload(item) for item in window], len(ordered)

    async def get_model_key(self, user_id: str, thread_id: str) -> str | None:
        record = self._records.get((user_id, thread_id))
        return record.model_key if record is not None else None

    async def set_model_key(
        self,
        user_id: str,
        thread_id: str,
        model_key: str | None,
    ) -> datetime | None:
        record = self._records.get((user_id, thread_id))
        if record is None:
            return None
        record.model_key = model_key
        record.updated_at = self._clock()
        return record.updated_at
