"""会话存储契约测试：同一套用例同时约束内存与 Postgres 适配器。

删除两条实现分支的重复之前，先用契约锁住它们必须一致的行为；
Postgres 未配置或未启动时自动跳过，内存适配器始终参与。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings
from app.services.session_store import InMemorySessionStore, PostgresSessionStore


def _postgres_url() -> str:
    settings = get_settings()
    if settings.storage.backend != "postgres" or settings.storage.postgres_url is None:
        pytest.skip("当前未启用 postgres 后端")
    return settings.storage.postgres_url.get_secret_value()


@pytest.fixture(params=["memory", "postgres"])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[Any]:
    if request.param == "memory":
        yield InMemorySessionStore()
        return

    pool = AsyncConnectionPool(
        conninfo=_postgres_url(),
        kwargs={"autocommit": True},
        open=False,
    )
    try:
        await pool.open(timeout=10)
    except Exception as exc:  # 数据库没起来时跳过，而不是让整个测试套件失败
        pytest.skip(f"Postgres 不可用：{exc}")

    adapter = PostgresSessionStore(pool, auto_create=True)
    try:
        await adapter.setup()
        yield adapter
    finally:
        await pool.close()


def _user_id() -> str:
    """每个用例独占一个用户，避免共享库里的历史行影响断言。"""
    return f"pytest-{uuid4().hex[:8]}"


async def test_record_turn_persists_catalog_and_messages(store: Any) -> None:
    user_id = _user_id()
    messages = [HumanMessage("你好"), AIMessage("回复")]

    await store.record_turn(user_id, "t-1", messages, "你好")

    entries, total = await store.list_sessions(user_id, page=1, size=20)
    assert total == 1
    assert entries[0].thread_id == "t-1"
    assert entries[0].title == "你好"

    items, message_total = await store.read_messages(user_id, "t-1", page=1, size=20)
    assert message_total == 2
    assert [item["role"] for item in items] == ["user", "assistant"]
    # 稳定消息标识：反馈按它绑定，两个适配器必须给出同一规则
    assert [item["message_id"] for item in items] == ["t-1:0", "t-1:1"]


async def test_title_is_written_once(store: Any) -> None:
    user_id = _user_id()

    await store.record_turn(user_id, "t-1", [], "第一句")
    await store.record_turn(user_id, "t-1", [], None)
    await store.record_turn(user_id, "t-1", [], "另一个标题")

    entries, _ = await store.list_sessions(user_id, page=1, size=20)
    assert entries[0].title == "第一句"


async def test_rename_and_delete_are_scoped_by_user(store: Any) -> None:
    user_id = _user_id()
    await store.record_turn(user_id, "t-1", [HumanMessage("你好")], "标题")

    assert await store.rename_session(user_id, "t-1", "新标题") is True
    assert await store.rename_session(f"{user_id}-other", "t-1", "劫持") is False
    assert await store.delete_session(f"{user_id}-other", "t-1") is False

    assert await store.delete_session(user_id, "t-1") is True
    assert await store.read_messages(user_id, "t-1", page=1, size=20) == ([], 0)


async def test_message_window_and_desc_order(store: Any) -> None:
    user_id = _user_id()
    messages = [HumanMessage(f"m{index}") for index in range(5)]
    await store.record_turn(user_id, "t-1", messages, None)

    items, total = await store.read_messages(user_id, "t-1", page=2, size=2)
    assert total == 5
    assert [item["content"] for item in items] == ["m2", "m3"]
    # 翻到第 2 页后 ID 仍指向全局序号，不能退化成窗口内下标
    assert [item["message_id"] for item in items] == ["t-1:2", "t-1:3"]

    latest, _ = await store.read_messages(user_id, "t-1", page=1, size=2, order="desc")
    assert [item["content"] for item in latest] == ["m4", "m3"]


async def test_message_write_is_idempotent(store: Any) -> None:
    user_id = _user_id()
    messages = [HumanMessage(f"m{index}") for index in range(3)]

    await store.record_turn(user_id, "t-1", messages, None)
    await store.record_turn(user_id, "t-1", messages, None)

    _, total = await store.read_messages(user_id, "t-1", page=1, size=20)
    assert total == 3


async def test_tool_calls_roundtrip(store: Any) -> None:
    user_id = _user_id()
    messages = [
        AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "c1"}]),
        ToolMessage(content="结果", tool_call_id="c1", name="t"),
    ]
    await store.record_turn(user_id, "t-1", messages, None)

    items, _ = await store.read_messages(user_id, "t-1", page=1, size=20)
    assert items[0]["tool_calls"][0]["name"] == "t"
    assert items[1]["name"] == "t"


async def test_model_key_roundtrip(store: Any) -> None:
    user_id = _user_id()
    await store.record_turn(user_id, "t-1", [], None)

    assert await store.get_model_key(user_id, "t-1") is None
    assert await store.set_model_key(user_id, "t-1", "openai:gpt-4o") is not None
    assert await store.get_model_key(user_id, "t-1") == "openai:gpt-4o"
    assert await store.set_model_key(user_id, "t-1", None) is not None
    assert await store.get_model_key(user_id, "t-1") is None


async def test_list_orders_by_last_active(store: Any) -> None:
    user_id = _user_id()
    for thread_id in ("old", "mid", "new"):
        await store.record_turn(user_id, thread_id, [], thread_id)
        # Postgres 的 now() 以事务时间为准；留出间隔才能稳定断言先后
        await asyncio.sleep(0.02)

    entries, total = await store.list_sessions(user_id, page=1, size=2)
    assert total == 3
    assert [entry.thread_id for entry in entries] == ["new", "mid"]
