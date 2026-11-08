"""可观测测试：9 个指标族的埋点行为与基数约束。"""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.tools import tool
from prometheus_client import REGISTRY
from pydantic import SecretStr

from app.agent.graph import build_agent
from app.agent.registry import ToolExecutionError, ToolSpec, govern_tool
from app.agent.tool_context import ToolTurn
from app.api.v1 import chat as chat_module
from app.api.v1 import health as health_module
from app.core.config import get_settings
from app.core.security import CurrentUser
from app.main import app
from app.services import model_runtime as model_runtime_module

client = TestClient(app)


def _metric(name: str, **labels: str) -> float:
    """读取当前指标值；不存在时按 0 处理，便于断言增量。"""
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


def test_http_metrics_use_route_template() -> None:
    """HTTP 指标按路由模板聚合，不把真实路径写进标签。"""
    before = _metric(
        "agent_http_requests_total",
        method="GET",
        route="/api/v1/health",
        status="200",
    )
    duration_before = _metric(
        "agent_http_request_duration_seconds_count",
        method="GET",
        route="/api/v1/health",
    )

    assert client.get("/api/v1/health").status_code == 200

    assert _metric(
        "agent_http_requests_total",
        method="GET",
        route="/api/v1/health",
        status="200",
    ) == before + 1
    assert _metric(
        "agent_http_request_duration_seconds_count",
        method="GET",
        route="/api/v1/health",
    ) == duration_before + 1


def test_http_metrics_collapse_unmatched_routes() -> None:
    """404 等未匹配路由归入固定标签，避免标签基数随随机路径增长。"""
    before = _metric(
        "agent_http_requests_total",
        method="GET",
        route="unmatched",
        status="404",
    )

    response = client.get("/api/v1/not-a-real-endpoint")

    assert response.status_code == 404
    assert _metric(
        "agent_http_requests_total",
        method="GET",
        route="unmatched",
        status="404",
    ) == before + 1


def test_http_metrics_keep_path_params_as_template() -> None:
    """路径参数以占位符形式入标签，真实 ID 不会进入指标。"""
    route = "/api/v1/sessions/{thread_id}/messages"
    before = _metric(
        "agent_http_requests_total",
        method="GET",
        route=route,
        status="401",
    )

    response = client.get("/api/v1/sessions/super-secret-id/messages")

    assert response.status_code == 401
    assert _metric(
        "agent_http_requests_total",
        method="GET",
        route=route,
        status="401",
    ) == before + 1


def test_metrics_endpoint_returns_prometheus_text() -> None:
    """指标端点返回 Prometheus 文本格式，且包含核心指标名。"""
    response = client.get("/api/v1/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "agent_sse_streams_active" in response.text
    assert "agent_llm_tokens_total" in response.text


def test_metrics_endpoint_disabled_returns_404(monkeypatch: Any) -> None:
    """关闭指标时端点返回 404，而不是继续暴露数据。"""
    monkeypatch.setattr(
        health_module,
        "get_settings",
        lambda: SimpleNamespace(metrics=SimpleNamespace(enabled=False)),
    )

    response = client.get("/api/v1/metrics")

    assert response.status_code == 404
    assert response.json()["code"] == "metrics_disabled"


def test_metrics_endpoint_requires_token_when_configured(monkeypatch: Any) -> None:
    """配置兜底令牌后，缺失或错误的 X-Metrics-Token 都必须被拒绝。"""
    settings = get_settings()
    monkeypatch.setattr(settings.metrics, "token", SecretStr("metrics-token-0123456789"))

    assert client.get("/api/v1/metrics").status_code == 403
    assert client.get("/api/v1/metrics").json()["code"] == "metrics_forbidden"

    wrong = client.get("/api/v1/metrics", headers={"X-Metrics-Token": "not-the-token"})
    assert wrong.status_code == 403

    ok = client.get(
        "/api/v1/metrics",
        headers={"X-Metrics-Token": "metrics-token-0123456789"},
    )
    assert ok.status_code == 200


class TokenGraph:
    """只产出一个 token，用于验证 TTFT 与活跃流数。"""

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        yield "messages", (AIMessageChunk(content="你好"), {})


class SlowGraph:
    """长时间无输出，用于触发超时或模拟客户端断开。"""

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        await asyncio.sleep(0.3)
        yield "messages", (AIMessageChunk(content="慢"), {})


def _payload() -> chat_module.ChatRequest:
    return chat_module.ChatRequest(message="你好", thread_id="t-metrics")


async def test_sse_metrics_track_active_stream_and_ttft(monkeypatch: Any) -> None:
    """流开始后活跃数增加，结束后归零，并记录首 token 延迟。"""
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: TokenGraph())
    before_active = _metric("agent_sse_streams_active")
    before_ttft = _metric("agent_sse_time_to_first_token_seconds_count")

    chunks = [
        chunk
        async for chunk in chat_module._event_stream(
            _payload(), CurrentUser(user_id="u1"), None, None, TokenGraph(), None
        )
    ]

    assert any("你好" in chunk.data for chunk in chunks)
    assert _metric("agent_sse_streams_active") == before_active
    assert _metric("agent_sse_time_to_first_token_seconds_count") == before_ttft + 1


async def test_sse_metrics_count_timeout(monkeypatch: Any) -> None:
    """整轮超时只下发 error 事件，同时累加超时指标。"""
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: SlowGraph())
    # 运行期取配置，避免 test_llm 里 cache_clear 后拿到旧实例
    monkeypatch.setattr(get_settings().agent, "request_timeout_seconds", 0.05)
    before = _metric("agent_sse_timeouts_total")

    chunks = [
        chunk
        async for chunk in chat_module._event_stream(
            _payload(), CurrentUser(user_id="u1"), None, None, SlowGraph(), None
        )
    ]

    assert any("request_timeout" in chunk.data for chunk in chunks), chunks
    assert _metric("agent_sse_timeouts_total") == before + 1


async def test_sse_metrics_count_disconnect(monkeypatch: Any) -> None:
    """客户端取消生成器时累加断开指标，并继续抛出取消异常。"""
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: SlowGraph())
    before = _metric("agent_sse_disconnects_total")

    async def consume() -> None:
        async for _ in chat_module._event_stream(
            _payload(), CurrentUser(user_id="u1"), None, None, SlowGraph(), None
        ):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert _metric("agent_sse_disconnects_total") == before + 1


@tool
async def metrics_ok(value: str) -> str:
    """成功工具。"""
    return value


@tool
async def metrics_slow(value: str) -> str:
    """超时工具。"""
    await asyncio.sleep(0.05)
    return value


async def test_tool_metrics_record_result_status() -> None:
    """工具成功、超时、权限拒绝分别记入不同状态，重试单独计数。"""
    tool_name = "metrics_ok"
    before_success = _metric(
        "agent_tool_calls_total", tool=tool_name, status="success"
    )
    governed = govern_tool(ToolSpec(tool=metrics_ok, timeout_seconds=1, max_retries=0))
    await governed.ainvoke({"value": "ok"})
    assert _metric(
        "agent_tool_calls_total", tool=tool_name, status="success"
    ) == before_success + 1

    tool_name = "metrics_slow"
    before_timeout = _metric(
        "agent_tool_calls_total", tool=tool_name, status="timeout"
    )
    governed = govern_tool(ToolSpec(tool=metrics_slow, timeout_seconds=0.01, max_retries=0))
    with pytest.raises(ToolExecutionError):
        await governed.ainvoke({"value": "ok"})
    assert _metric(
        "agent_tool_calls_total", tool=tool_name, status="timeout"
    ) == before_timeout + 1

    tool_name = "metrics_ok"
    before_forbidden = _metric(
        "agent_tool_calls_total", tool=tool_name, status="forbidden"
    )
    governed = govern_tool(ToolSpec(tool=metrics_ok, required_roles=("admin",)))
    with ToolTurn(("user",)):
        with pytest.raises(ToolExecutionError):
            await governed.ainvoke({"value": "ok"})
    assert _metric(
        "agent_tool_calls_total", tool=tool_name, status="forbidden"
    ) == before_forbidden + 1


async def test_tool_metrics_count_retries() -> None:
    """重试次数按实际重跑累加，成功只记一次最终结果。"""
    attempts = {"count": 0}

    @tool
    async def metrics_flaky(value: str) -> str:
        """前两次失败，第三次成功。"""
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("临时故障")
        return value

    before_retries = _metric("agent_tool_retries_total", tool="metrics_flaky")
    before_success = _metric(
        "agent_tool_calls_total", tool="metrics_flaky", status="success"
    )
    governed = govern_tool(ToolSpec(tool=metrics_flaky, timeout_seconds=1, max_retries=2))

    assert await governed.ainvoke({"value": "ok"}) == "ok"
    assert _metric("agent_tool_retries_total", tool="metrics_flaky") == before_retries + 2
    assert _metric(
        "agent_tool_calls_total", tool="metrics_flaky", status="success"
    ) == before_success + 1


class UsageModel(GenericFakeChatModel):
    """带 usage_metadata 的假模型，用于验证 token 埋点。"""

    def bind_tools(self, tools: Any) -> "UsageModel":
        return self


async def test_token_usage_is_recorded() -> None:
    """模型返回 usage 时按模型名与方向累加 token。"""
    model_name = get_settings().llm.model
    before_input = _metric(
        "agent_llm_tokens_total", model=model_name, type="input"
    )
    before_output = _metric(
        "agent_llm_tokens_total", model=model_name, type="output"
    )
    model = UsageModel(
        messages=iter(
            [
                AIMessage(
                    content="完成",
                    usage_metadata={
                        "input_tokens": 11,
                        "output_tokens": 7,
                        "total_tokens": 18,
                    },
                )
            ]
        )
    )
    agent = build_agent(model)

    await agent.ainvoke(
        {"messages": [HumanMessage(content="你好")]},
        {"configurable": {"thread_id": "t-metrics-usage"}},
    )

    assert _metric(
        "agent_llm_tokens_total", model=model_name, type="input"
    ) == before_input + 11
    assert _metric(
        "agent_llm_tokens_total", model=model_name, type="output"
    ) == before_output + 7
