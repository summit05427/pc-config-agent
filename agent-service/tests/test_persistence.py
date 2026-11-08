"""会话持久化测试：默认连接真实 Postgres，未配置时自动跳过。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from pydantic import ValidationError

from app.agent import checkpointer as checkpointer_module
from app.agent.checkpointer import (
    CHECKPOINTER_STATUS_DOWN,
    CHECKPOINTER_STATUS_MEMORY,
    CHECKPOINTER_STATUS_UNAVAILABLE,
    CHECKPOINTER_STATUS_UP,
    probe_checkpointer,
)
from app.agent.graph import build_agent
from app.core.config import StorageSettings, get_settings
from app.main import app


def _postgres_url() -> str:
    settings = get_settings()
    if settings.storage.backend != "postgres" or settings.storage.postgres_url is None:
        pytest.skip("当前未启用 postgres 后端")
    return settings.storage.postgres_url.get_secret_value()


@asynccontextmanager
async def _open_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    """每次调用都新建连接池，用来模拟进程重启。"""
    pool = AsyncConnectionPool(
        conninfo=_postgres_url(),
        kwargs={"autocommit": True},
        open=False,
    )
    try:
        await pool.open(timeout=10)
    except Exception as exc:  # 数据库没起来时跳过，而不是让整个测试套件失败
        pytest.skip(f"Postgres 不可用：{exc}")

    saver = AsyncPostgresSaver(pool)
    try:
        await saver.setup()
        yield saver
    finally:
        await pool.close()


class ScriptedModel:
    """按顺序返回预设消息的假模型，不发起真实请求。"""

    def __init__(self, *replies: str) -> None:
        self._responses = iter([AIMessage(content=reply) for reply in replies])

    def bind_tools(self, tools: Any) -> "ScriptedModel":
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        return next(self._responses)


async def test_conversation_survives_reconnect() -> None:
    """写完关闭连接池，再从新连接读回来，验证真持久化。"""
    thread = {"configurable": {"thread_id": f"pytest-{uuid4()}"}}

    async with _open_checkpointer() as saver:
        graph = build_agent(model=ScriptedModel("第一轮回复"), tools=[], checkpointer=saver)
        await graph.ainvoke({"messages": [HumanMessage("你好")]}, thread)

    async with _open_checkpointer() as saver:
        graph = build_agent(model=ScriptedModel("第二轮回复"), tools=[], checkpointer=saver)
        restored = await graph.aget_state(thread)
        assert len(restored.values["messages"]) == 2

        await graph.ainvoke({"messages": [HumanMessage("还记得我吗")]}, thread)
        updated = await graph.aget_state(thread)
        assert len(updated.values["messages"]) == 4
        assert updated.values["messages"][-1].content == "第二轮回复"


async def test_threads_are_isolated() -> None:
    """不同会话之间不串记忆。"""
    config_a = {"configurable": {"thread_id": f"pytest-a-{uuid4()}"}}
    config_b = {"configurable": {"thread_id": f"pytest-b-{uuid4()}"}}

    async with _open_checkpointer() as saver:
        graph = build_agent(model=ScriptedModel("只给 A 的回复"), tools=[], checkpointer=saver)
        await graph.ainvoke({"messages": [HumanMessage("我是 A")]}, config_a)

        state_b = await graph.aget_state(config_b)
        assert state_b.values.get("messages", []) == []


def test_postgres_backend_requires_url() -> None:
    with pytest.raises(ValidationError):
        StorageSettings(backend="postgres")


def test_app_startup_uses_configured_checkpointer() -> None:
    """TestClient 作为上下文管理器时才会执行 lifespan。"""
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200


def _use_backend(monkeypatch: pytest.MonkeyPatch, backend: str) -> None:
    """让探测读到指定后端配置，不触碰真实数据库。"""
    monkeypatch.setattr(
        checkpointer_module,
        "get_settings",
        lambda: SimpleNamespace(storage=SimpleNamespace(backend=backend)),
    )


async def test_probe_checkpointer_reports_memory_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_backend(monkeypatch, "memory")
    checkpointer_module._set_pool(None)

    assert await probe_checkpointer() == CHECKPOINTER_STATUS_MEMORY


async def test_probe_checkpointer_reports_unavailable_before_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_backend(monkeypatch, "postgres")
    checkpointer_module._set_pool(None)

    assert await probe_checkpointer() == CHECKPOINTER_STATUS_UNAVAILABLE


class _FakeConnection:
    async def execute(self, query: str) -> None:
        if query != "SELECT 1":
            raise RuntimeError("unexpected query")


class _FakePool:
    def __init__(self, *, is_healthy: bool) -> None:
        self.is_healthy = is_healthy

    @asynccontextmanager
    async def connection(self, **_: Any) -> AsyncIterator[_FakeConnection]:
        if not self.is_healthy:
            raise RuntimeError("pool exhausted")
        yield _FakeConnection()


async def test_probe_checkpointer_reports_up_when_query_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_backend(monkeypatch, "postgres")
    checkpointer_module._set_pool(_FakePool(is_healthy=True))  # type: ignore[arg-type]

    try:
        assert await probe_checkpointer() == CHECKPOINTER_STATUS_UP
    finally:
        checkpointer_module._set_pool(None)


async def test_probe_checkpointer_reports_down_when_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_backend(monkeypatch, "postgres")
    checkpointer_module._set_pool(_FakePool(is_healthy=False))  # type: ignore[arg-type]

    try:
        assert await probe_checkpointer() == CHECKPOINTER_STATUS_DOWN
    finally:
        checkpointer_module._set_pool(None)
