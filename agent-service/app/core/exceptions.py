"""统一异常体系与全局异常处理器。

目标：
1. 前端永远收到同一种 JSON 结构，不必为每种异常写不同的解析逻辑；
2. 生产环境不把堆栈、SQL、内部路径等细节返回给客户端；
3. 异常日志自动带 request_id（由 RequestIDMiddleware 绑定），便于定位。
"""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.error_codes import (
    CODE_APP_ERROR,
    CODE_HITL_RESUME_INVALID,
    CODE_INPUT_REJECTED,
    CODE_INTERNAL_ERROR,
    CODE_LOCK_NOT_ACQUIRED,
    CODE_RATE_LIMITED,
    CODE_REDIS_UNAVAILABLE,
    CODE_VALIDATION_ERROR,
    build_http_error_code,
)

logger = structlog.get_logger(__name__)


class AppError(Exception):
    """可预期的业务异常。

    与未捕获异常的区别：这类错误由业务规则产生（如额度不足、资源不存在），
    调用方应当自行处理，日志按 warning 记录而不是 error。
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = CODE_APP_ERROR,
        status_code: int = 400,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        # 附加的业务负载（如额度超限的 quota 字段）；只在已知业务错误上使用
        self.extra = extra
        # 需要让客户端按协议读取的响应头，例如限流的 Retry-After
        self.headers = headers


class LockAcquisitionError(AppError):
    """在等待窗口内没有拿到分布式锁。

    用 409 而不是 503：Redis 本身可用，是资源当前被其他请求占用，
    调用方可以提示“操作进行中”，也可以选择稍后重试。
    """

    def __init__(self, message: str = "操作正在处理中，请稍后重试") -> None:
        super().__init__(message, code=CODE_LOCK_NOT_ACQUIRED, status_code=409)


class RedisUnavailableError(AppError):
    """Redis 未就绪时的统一错误。

    让调用方拿到 503 而不是 500：这是依赖不可用，属于可重试错误，
    且响应中不能暴露连接串、主机名等内部信息。
    """

    def __init__(self, message: str = "缓存服务暂不可用，请稍后重试") -> None:
        super().__init__(message, code=CODE_REDIS_UNAVAILABLE, status_code=503)


class HitlResumeInvalidError(AppError):
    """中断恢复内容无法被门控节点接受。

    属于客户端输入问题（如空回答、未知选项），用 422 而不是 500；
    流已建立时由传输层转成带明确错误码的 SSE error 事件。
    """

    def __init__(self, message: str = "恢复内容无效，请补充预算或用途后重试") -> None:
        super().__init__(message, code=CODE_HITL_RESUME_INVALID, status_code=422)


class InputRejectedError(AppError):
    """输入护栏命中。

    用 422 而不是 400：请求语法合法，是被业务规则拒绝；前端据此提示用户改写输入，
    不应当自动重试。
    """

    def __init__(self, message: str = "输入包含不被支持的内容，请调整后重试") -> None:
        super().__init__(message, code=CODE_INPUT_REJECTED, status_code=422)


class RateLimitExceededError(AppError):
    """对话接口超过配额。

    429 并带 `Retry-After`：调用方据此退避，而不是盲目重试继续放大成本。
    """

    def __init__(
        self,
        retry_after_seconds: int,
        message: str = "请求过于频繁，请稍后重试",
    ) -> None:
        super().__init__(
            message,
            code=CODE_RATE_LIMITED,
            status_code=429,
            headers={"Retry-After": str(max(retry_after_seconds, 1))},
        )


def _request_id() -> str:
    """从日志上下文中取请求 ID，缺失时返回空字符串。"""
    return structlog.contextvars.get_contextvars().get("request_id", "")


def _error_payload(
    code: str,
    message: str,
    details: list[dict[str, str]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一错误响应结构：code 供程序判断，message 供人阅读。"""
    payload: dict[str, Any] = {"code": code, "message": message, "request_id": _request_id()}
    if details:
        payload["details"] = details
    if extra:
        payload.update(extra)
    return payload


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "app_error",
        code=exc.code,
        status_code=exc.status_code,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(exc.code, exc.message, extra=exc.extra),
        headers=exc.headers,
    )


async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """把 pydantic 的校验错误转成前端友好的字段级提示。"""
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "reason": error["msg"],
        }
        for error in exc.errors()
    ]
    logger.info(
        "request.validation_failed",
        path=request.url.path,
        fields=[item["field"] for item in details],
    )
    return JSONResponse(
        status_code=422,
        content=_error_payload(CODE_VALIDATION_ERROR, "请求参数校验失败", details),
    )


async def handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """统一 404 / 405 等框架级错误的响应格式（默认是 {"detail": "..."}）。"""
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(build_http_error_code(exc.status_code), str(exc.detail)),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """兜底处理器：任何未捕获异常都返回 500，且不泄露内部细节。"""
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        error_type=type(exc).__name__,
    )
    # 开发环境返回真实原因便于排查，生产环境只给通用提示
    message = f"{type(exc).__name__}: {exc}" if get_settings().debug else "服务器内部错误"
    return JSONResponse(
        status_code=500,
        content=_error_payload(CODE_INTERNAL_ERROR, message),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """集中注册处理器，避免散落在各路由文件里。"""
    # Starlette 的签名要求 handler 接收 Exception，而这里按具体异常类型声明参数；
    # 这是官方推荐写法，类型不兼容属于上游标注问题
    app.add_exception_handler(AppError, handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError, handle_validation_error  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        StarletteHTTPException, handle_http_exception  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, handle_unexpected_error)
