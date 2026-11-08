"""统一错误响应与 CORS 的测试。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import AppError, register_exception_handlers
from app.main import app as main_app


def _create_error_app() -> FastAPI:
    """构造一个只用于测试异常处理的小应用，避免污染业务路由。"""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise AppError("额度不足", code="quota_exceeded", status_code=409)

    @app.get("/quota")
    async def quota() -> None:
        raise AppError(
            "今日请求额度已用尽",
            code="quota_exceeded",
            status_code=429,
            extra={"quota": {"quota_type": "daily_requests", "limit": 100, "used": 100}},
        )

    @app.get("/items")
    async def items(limit: int) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("数据库连接失败")

    return app


# 关闭 raise_server_exceptions，否则测试客户端会直接抛出服务端异常
client = TestClient(_create_error_app(), raise_server_exceptions=False)
main_client = TestClient(main_app)


def test_app_error_returns_unified_payload() -> None:
    """业务异常应返回约定的 code / message / request_id 结构。"""
    response = client.get("/boom")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "quota_exceeded"
    assert body["message"] == "额度不足"
    assert "request_id" in body


def test_app_error_extra_is_merged_at_top_level() -> None:
    """额度详情属于顶层扩展字段，不能塞进 data，也不能被 message 覆盖。"""
    response = client.get("/quota")

    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "quota_exceeded"
    assert body["quota"] == {"quota_type": "daily_requests", "limit": 100, "used": 100}
    assert "data" not in body


def test_validation_error_has_field_details() -> None:
    """参数校验失败应返回 422，并指出具体字段。"""
    response = client.get("/items", params={"limit": "abc"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["details"][0]["field"].startswith("query")


def test_unexpected_error_returns_500() -> None:
    """未捕获异常也应返回统一结构，而不是框架默认的纯文本。"""
    response = client.get("/crash")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"


def test_404_uses_unified_payload() -> None:
    """框架级 404 也要统一格式。"""
    response = main_client.get("/api/v1/not-exists")

    assert response.status_code == 404
    assert response.json()["code"] == "http_404"


def test_cors_preflight_allows_configured_origin() -> None:
    """前端跨域预检应通过，并回显允许的来源。"""
    response = main_client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_unconfigured_origin() -> None:
    """不在白名单里的来源不应拿到允许头。"""
    response = main_client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
