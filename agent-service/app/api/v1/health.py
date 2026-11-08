"""系统级接口：存活检查与就绪检查。

为什么拆成两个：
- 存活（live）只回答「进程还在不在」，失败时编排系统应重启容器；
- 就绪（ready）回答「现在能不能接流量」，依赖未就绪时只摘除流量，不重启。

依赖状态单独暴露而不是让整个探活只返回 true/false，
便于定位是数据库、Redis 还是配置问题。
"""

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Header, Response

from app.agent.checkpointer import (
    CHECKPOINTER_STATUS_MEMORY,
    CHECKPOINTER_STATUS_UP,
    probe_checkpointer,
)
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.metrics import render_metrics
from app.core.redis import (
    REDIS_STATUS_DISABLED,
    REDIS_STATUS_UP,
    is_redis_enabled,
    probe_redis,
)

# tags 决定该组接口在 /docs 文档里的分组名称
router = APIRouter(tags=["system"])


@router.get("/health", summary="健康检查（兼容旧路径）")
@router.get("/health/live", summary="存活检查")
async def live_check() -> dict[str, str]:
    """返回服务存活状态、运行环境与 Redis 依赖状态。"""
    settings = get_settings()
    return {
        "status": "ok",
        "env": settings.app_env,
        "service": settings.app_name,
        "redis": await probe_redis(),
    }


def _is_ready(checkpointer_status: str, redis_status: str, is_redis_configured: bool) -> bool:
    """判断依赖组合是否满足接流量的条件。"""
    # memory 只在开发/测试可用；生产配置守卫已禁止，这里再兜底一次
    if checkpointer_status not in {CHECKPOINTER_STATUS_UP, CHECKPOINTER_STATUS_MEMORY}:
        return False
    if get_settings().app_env == "prod" and checkpointer_status == CHECKPOINTER_STATUS_MEMORY:
        return False
    # 配置了 Redis 就必须真正可用；未配置时服务按设计降级运行
    if is_redis_configured:
        return redis_status == REDIS_STATUS_UP
    return redis_status == REDIS_STATUS_DISABLED


@router.get("/health/ready", summary="就绪检查")
async def readiness_check(response: Response) -> dict[str, Any]:
    """依赖全部可用才返回 200，否则 503 并说明原因。"""
    settings = get_settings()
    checkpointer_status = await probe_checkpointer()
    redis_status = await probe_redis()
    is_ready = _is_ready(checkpointer_status, redis_status, is_redis_enabled())

    if not is_ready:
        response.status_code = 503

    return {
        "status": "ready" if is_ready else "not_ready",
        "env": settings.app_env,
        "service": settings.app_name,
        "dependencies": {
            "checkpointer": checkpointer_status,
            "redis": redis_status,
        },
    }


@router.get("/metrics", summary="Prometheus 指标", include_in_schema=False)
async def metrics_endpoint(
    x_metrics_token: Annotated[str | None, Header(alias="X-Metrics-Token")] = None,
) -> Response:
    """暴露指标文本。

    网关白名单是主防线；配置了 `METRICS__TOKEN` 时再校验请求头作为兜底，
    避免网关规则缺失时指标被公网直接读取。
    """
    settings = get_settings()
    if not settings.metrics.enabled:
        raise AppError("指标端点未启用", code="metrics_disabled", status_code=404)

    expected = settings.metrics.token
    if expected is not None and not secrets.compare_digest(
        x_metrics_token or "", expected.get_secret_value()
    ):
        raise AppError("指标访问被拒绝", code="metrics_forbidden", status_code=403)
    return render_metrics()
