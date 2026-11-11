"""节点级追踪：统一记录每个图节点的耗时、终态与结构化事件。

为什么包一层而不是在每个节点里埋点：节点函数只负责业务，重复的计时与日志逻辑集中
在这里，新增节点或调整顺序时不会漏打点。包装器是纯观察者：原样返回节点的部分状态，
异常原样抛出，不改变任何业务语义。
"""

from collections.abc import Callable
from inspect import iscoroutinefunction, signature
from time import perf_counter
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt

from app.core.metrics import NODE_DURATION

logger = structlog.get_logger(__name__)

NODE_STATUS_SUCCESS = "success"
NODE_STATUS_ERROR = "error"
# interrupt 是正常暂停而不是失败：单独记状态，避免告警按 error 统计
NODE_STATUS_INTERRUPTED = "interrupted"

# 节点可能是同步函数，也可能是 async 函数（如 requirement_parser），包装后签名必须兼容
NodeCallable = Callable[..., Any]


def _thread_id(config: RunnableConfig | None) -> str | None:
    """只取已按用户命名空间化的 checkpoint thread id，用于把日志串成一次执行。"""
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    thread_id = configurable.get("thread_id")
    return thread_id if isinstance(thread_id, str) else None


def _record(
    *,
    name: str,
    agent_id: str,
    started_at: float,
    status: str,
    workflow_status: str | None,
    config: RunnableConfig | None,
) -> None:
    duration_seconds = perf_counter() - started_at
    NODE_DURATION.labels(node=name, status=status).observe(duration_seconds)
    logger.info(
        "agent.node.completed",
        agent_id=agent_id,
        node=name,
        status=status,
        # 节点内部的中间态（如 retry）对定位「卡在哪个分支」比最终态更有用
        workflow_status=workflow_status,
        duration_ms=round(duration_seconds * 1000),
        thread_id=_thread_id(config),
    )


def _accepts_config(node: NodeCallable) -> bool:
    """部分节点（如 requirement_parser）显式接收 config，其余节点不接收。

    只按签名转发，避免把 config 硬塞给不接收它的节点而触发 TypeError。
    """
    try:
        return "config" in signature(node).parameters
    except (TypeError, ValueError):
        return False


def trace_node(name: str, node: NodeCallable, *, agent_id: str) -> NodeCallable:
    """返回带耗时与结构化日志的节点包装器；异步节点返回异步包装器。"""
    forwards_config = _accepts_config(node)

    def call(state: dict[str, Any], config: RunnableConfig | None) -> Any:
        if forwards_config and config is not None:
            return node(state, config=config)
        return node(state)

    def finish(
        started_at: float, config: RunnableConfig | None, update: Any
    ) -> Any:
        workflow_status = update.get("workflow_status") if isinstance(update, dict) else None
        _record(
            name=name,
            agent_id=agent_id,
            started_at=started_at,
            status=NODE_STATUS_SUCCESS,
            workflow_status=workflow_status if isinstance(workflow_status, str) else None,
            config=config,
        )
        return update

    def fail(started_at: float, config: RunnableConfig | None, exc: Exception) -> None:
        # interrupt 通过抛异常暂停图执行，属于正常控制流，不能按 error 记
        status = (
            NODE_STATUS_INTERRUPTED if isinstance(exc, GraphInterrupt) else NODE_STATUS_ERROR
        )
        _record(
            name=name,
            agent_id=agent_id,
            started_at=started_at,
            status=status,
            workflow_status=None,
            config=config,
        )

    if iscoroutinefunction(node):
        async def awrapped(
            state: dict[str, Any], config: RunnableConfig | None = None
        ) -> Any:
            started_at = perf_counter()
            try:
                update = await call(state, config)
            except Exception as exc:
                fail(started_at, config, exc)
                raise
            return finish(started_at, config, update)

        return awrapped

    def wrapped(
        state: dict[str, Any], config: RunnableConfig | None = None
    ) -> Any:
        started_at = perf_counter()
        try:
            update = call(state, config)
        except Exception as exc:
            fail(started_at, config, exc)
            raise
        return finish(started_at, config, update)

    return wrapped
