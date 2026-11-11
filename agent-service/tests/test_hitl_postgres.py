"""真实 Postgres 上的 HITL 重启恢复演练。

默认跳过：只有设置 `AGENT_TEST_POSTGRES_URL` 时才连库，CI 无数据库不受影响。
覆盖「进程退出 → 新连接池 → 新图」的真实持久化路径；内存版的重建测试见
`test_hitl.py::test_interrupt_survives_graph_rebuild`。

连接串里的 host 必须是 IPv4 字面量（与 `agent-service/.env.example` 一致）：
Windows 上 `localhost` 会先解析到 `::1`，而 Docker Desktop 只发布 `127.0.0.1`，
连 `::1` 既不拒绝也不响应，没有 `connect_timeout` 时会一直等到池超时。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg_pool import AsyncConnectionPool
from test_agent_graph import _install_tools

from app.agent.pc.graph import build_pc_graph
from app.agent.pc.status import STATUS_SUCCESS
from app.agent.profiles import resolve_profile
from app.core.config import get_settings

POSTGRES_URL_ENV = "AGENT_TEST_POSTGRES_URL"


@pytest.fixture
def hitl_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """开启 HITL；checkpointer 由用例显式注入，不读这里的假 URL。"""
    monkeypatch.setenv("HITL__ENABLED", "true")
    monkeypatch.setenv("STORAGE__BACKEND", "postgres")
    monkeypatch.setenv("STORAGE__POSTGRES_URL", "postgresql://u:p@localhost:5432/agent")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


@asynccontextmanager
async def _saver(url: str) -> AsyncIterator[AsyncPostgresSaver]:
    """每次进入都新建连接池与 saver，等价于一次进程启动。"""
    pool = AsyncConnectionPool(
        conninfo=url,
        min_size=1,
        max_size=2,
        kwargs={"autocommit": True},
        open=False,
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()
        yield saver
    finally:
        await pool.close()


@pytest.mark.skipif(
    not os.getenv(POSTGRES_URL_ENV),
    reason=f"未设置 {POSTGRES_URL_ENV}，跳过真实 Postgres 重启演练",
)
async def test_hitl_interrupt_resumes_after_process_restart(
    monkeypatch: pytest.MonkeyPatch, hitl_on: None
) -> None:
    url = os.environ[POSTGRES_URL_ENV]
    loop = asyncio.get_running_loop()
    assert isinstance(loop, asyncio.SelectorEventLoop), type(loop).__name__
    counters = _install_tools(monkeypatch)
    profile = resolve_profile("pc-config")
    thread_id = f"hitl-pg-{uuid4().hex}"

    async with _saver(url) as saver:
        graph = build_pc_graph(model=None, profile=profile, checkpointer=saver)
        await graph.ainvoke(
            {"messages": [HumanMessage("帮我配台电脑")], "use_history": True},
            _config(thread_id),
        )
        paused = await graph.aget_state(_config(thread_id))
        assert len(paused.interrupts) == 1

    # 连接池与图全部丢弃后重新建立：状态只能来自 Postgres checkpointer
    async with _saver(url) as saver:
        rebuilt = build_pc_graph(model=None, profile=profile, checkpointer=saver)
        await rebuilt.ainvoke(
            Command(
                resume={
                    "message": "预算 8000 元，打游戏",
                    "answer": {"budget_yuan": 8000, "scenario": "GAMING"},
                }
            ),
            _config(thread_id),
        )
        final = await rebuilt.aget_state(_config(thread_id))
        assert final.values["workflow_status"] == STATUS_SUCCESS
        assert not final.interrupts
        assert counters["solve"] == 1

        await saver.adelete_thread(thread_id)
