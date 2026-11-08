"""应用骨架冒烟测试：验证路由挂载、配置读取与存活/就绪检查。"""

from typing import Any

from fastapi.testclient import TestClient

from app.api.v1 import health as health_module
from app.main import app

client = TestClient(app)


def _stub_dependencies(
    monkeypatch: Any,
    *,
    checkpointer: str,
    redis: str,
    is_redis_configured: bool,
) -> None:
    """固定依赖探测结果，避免测试依赖真实 Postgres / Redis。"""

    async def fake_checkpointer() -> str:
        return checkpointer

    async def fake_redis() -> str:
        return redis

    monkeypatch.setattr(health_module, "probe_checkpointer", fake_checkpointer)
    monkeypatch.setattr(health_module, "probe_redis", fake_redis)
    monkeypatch.setattr(health_module, "is_redis_enabled", lambda: is_redis_configured)


def test_health_check() -> None:
    """健康检查应返回 200，且状态为 ok。"""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "agent-service"


def test_unknown_route_returns_404() -> None:
    """未注册的路径应返回 404，确认没有遗留脚手架接口。"""
    response = client.get("/api/v1/not-exists")

    assert response.status_code == 404


def test_request_id_is_generated() -> None:
    """未传 X-Request-ID 时，中间件应自动生成 32 位十六进制 ID。"""
    response = client.get("/api/v1/health")

    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    assert len(request_id) == 32


def test_request_id_is_echoed_from_client() -> None:
    """客户端传入的请求 ID 应原样回传，便于跨服务串联日志。"""
    response = client.get("/api/v1/health", headers={"X-Request-ID": "trace-demo-001"})

    assert response.headers["x-request-id"] == "trace-demo-001"


def test_live_endpoint_is_available() -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_ok_when_dependencies_ready(monkeypatch: Any) -> None:
    _stub_dependencies(
        monkeypatch,
        checkpointer="up",
        redis="disabled",
        is_redis_configured=False,
    )

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["dependencies"]["checkpointer"] == "up"


def test_readiness_fails_when_checkpointer_unavailable(monkeypatch: Any) -> None:
    _stub_dependencies(
        monkeypatch,
        checkpointer="unavailable",
        redis="disabled",
        is_redis_configured=False,
    )

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_readiness_fails_when_configured_redis_is_down(monkeypatch: Any) -> None:
    """配置了 Redis 却不做必需性降级：不可用就不接流量。"""
    _stub_dependencies(monkeypatch, checkpointer="up", redis="down", is_redis_configured=True)

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503


def test_readiness_ok_when_redis_is_up(monkeypatch: Any) -> None:
    _stub_dependencies(monkeypatch, checkpointer="up", redis="up", is_redis_configured=True)

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
