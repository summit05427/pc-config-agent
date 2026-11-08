"""结构化日志配置。

设计目标：
1. 开发环境输出带颜色的可读文本，生产环境输出单行 JSON（便于 ELK/Loki 采集与检索）。
2. 与标准库 logging 打通，uvicorn 等第三方库的日志也能统一渲染，避免两种格式混杂。
3. 每个请求的日志自动携带 request_id，便于把一次调用的所有日志串起来。
"""

import logging
import sys

import structlog
from structlog.typing import Processor

from app.core.config import Settings


def _shared_processors() -> list[Processor]:
    """structlog 与标准库日志共用的处理链。"""
    return [
        # 注入通过 bind_contextvars 绑定的 request_id 等上下文
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]


def configure_logging(settings: Settings) -> None:
    """按运行环境初始化日志，进程启动时调用一次。"""
    log_level = logging.DEBUG if settings.debug else logging.INFO

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if settings.app_env == "prod"
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    shared_processors = _shared_processors()
    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        # 交给标准库输出，使 structlog 与 logging 走同一套 handler
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        # 非 structlog 的日志（如 uvicorn）走这里补齐字段
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # 访问日志由 RequestIDMiddleware 统一输出，关闭 uvicorn 自带的重复记录
    logging.getLogger("uvicorn.access").disabled = True

    # 降低三方库噪音，避免 DEBUG 级别下刷屏
    # sse_starlette 在 DEBUG 下会逐块打印原始 chunk（含完整回复文本），必须压到 WARNING
    for noisy_logger in ("httpx", "httpcore", "watchfiles", "sse_starlette.sse"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
