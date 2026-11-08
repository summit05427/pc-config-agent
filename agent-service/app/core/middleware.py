"""请求级中间件。

为什么用纯 ASGI 中间件，而不是 Starlette 的 BaseHTTPMiddleware：
BaseHTTPMiddleware 会对响应再包一层，历史上与流式响应（SSE）存在兼容问题，
而 Agent 服务的核心接口就是逐字流式输出，必须保证数据块原样透传、不被缓冲。
"""

import time
import uuid

import structlog
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "x-request-id"

logger = structlog.get_logger(__name__)


class RequestIDMiddleware:
    """为每个 HTTP 请求生成/透传请求 ID，并记录结构化访问日志。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # WebSocket / lifespan 等非 HTTP 流量直接放行
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        # 优先复用网关或前端传入的 ID，保证跨服务调用链一致
        request_id = headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=scope["method"],
            path=scope["path"],
        )

        status_code = 500
        started_at = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            """在响应头回传 request_id，方便前端/网关关联日志。"""
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                raw_headers = list(message.get("headers", []))
                raw_headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info("request.finished", status_code=status_code, duration_ms=duration_ms)
            # 必须清理，否则上下文会泄漏到复用同一协程的下一个请求
            structlog.contextvars.clear_contextvars()
