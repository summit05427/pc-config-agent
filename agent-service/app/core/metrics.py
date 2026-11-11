"""Prometheus 指标定义与 HTTP 采集中间件。

只覆盖「延迟、错误、成本」三条主线，共 15 个指标族：

1. HTTP 请求数、HTTP 耗时
2. SSE 活跃流、首 token 延迟、超时、客户端断开
3. 工具调用结果、工具重试
4. 图节点耗时（按节点与成败）
5. LLM token 用量
6. 用量 outbox 待投递、死信、降级计数
7. 会话删除墓碑按状态的数量
8. 输出事实校验命中（按规则）

两条硬约束：
- 禁止把 user_id / thread_id 作为标签，否则时间序列基数会失控；
- 路由标签必须使用路由模板（如 /sessions/{thread_id}/messages），不能使用真实路径。

中间件采用纯 ASGI 实现，原因与 RequestIDMiddleware 相同：
BaseHTTPMiddleware 对流式响应存在兼容风险，而本服务的核心接口就是 SSE。
"""

import time

from fastapi import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.types import ASGIApp, Message, Receive, Scope, Send

UNMATCHED_ROUTE = "unmatched"

HTTP_REQUESTS_TOTAL = Counter(
    "agent_http_requests_total",
    "HTTP 请求总数",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "agent_http_request_duration_seconds",
    "HTTP 请求耗时（秒）",
    ("method", "route"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
SSE_STREAMS_ACTIVE = Gauge(
    "agent_sse_streams_active",
    "当前活跃的 SSE 流数量",
)
SSE_TIME_TO_FIRST_TOKEN = Histogram(
    "agent_sse_time_to_first_token_seconds",
    "从流开始到首个 token 事件的耗时（秒）",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60),
)
SSE_TIMEOUTS_TOTAL = Counter(
    "agent_sse_timeouts_total",
    "SSE 流达到总超时上限的次数",
)
SSE_DISCONNECTS_TOTAL = Counter(
    "agent_sse_disconnects_total",
    "客户端在流结束前断开的次数",
)
TOOL_CALLS_TOTAL = Counter(
    "agent_tool_calls_total",
    "工具调用最终结果",
    ("tool", "status"),
)
NODE_DURATION = Histogram(
    "agent_node_duration_seconds",
    "图节点执行耗时（秒）",
    ("node", "status"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
OUTPUT_GUARD_VIOLATIONS = Counter(
    "agent_output_guard_violations_total",
    "输出事实校验命中次数",
    ("rule",),
)
INPUT_GUARD_VIOLATIONS = Counter(
    "agent_input_guard_violations_total",
    "输入护栏拒绝次数",
    ("rule",),
)
RATE_LIMIT_REJECTIONS = Counter(
    "agent_rate_limit_rejections_total",
    "限流拒绝次数",
    ("scope",),
)
TOOL_RETRIES_TOTAL = Counter(
    "agent_tool_retries_total",
    "工具因超时或异常发生的重试次数",
    ("tool",),
)
TOOL_OUTPUT_TOKENS = Histogram(
    "agent_tool_output_tokens",
    "工具返回内容（治理后）的估算 token 数",
    ("tool",),
    buckets=(100, 500, 1000, 2000, 4000, 8000, 16000),
)
LLM_TOKENS_TOTAL = Counter(
    "agent_llm_tokens_total",
    "LLM token 用量",
    ("model", "type"),
)
# outbox 指标由投递循环周期刷新：待投递量与死信量代表「台账可能不完整」的风险
USAGE_OUTBOX_PENDING = Gauge(
    "agent_usage_outbox_pending",
    "用量 outbox 中待投递的记录数",
)
USAGE_OUTBOX_DEAD = Gauge(
    "agent_usage_outbox_dead",
    "用量 outbox 中投递失败且不再重试的记录数",
)
USAGE_OUTBOX_DEGRADED_TOTAL = Counter(
    "agent_usage_outbox_degraded_total",
    "用量 outbox 写库失败并降级到内存队列的次数",
)
# 墓碑长期停留在 pending/failed 说明 checkpoint 删除持续失败，需要人工介入
SESSION_DELETION_TASKS = Gauge(
    "agent_session_deletion_tasks",
    "会话删除墓碑按状态的数量",
    ("status",),
)

TOOL_STATUS_SUCCESS = "success"
TOOL_STATUS_TIMEOUT = "timeout"
TOOL_STATUS_ERROR = "error"
TOOL_STATUS_FORBIDDEN = "forbidden"
TOOL_STATUS_LIMITED = "limited"


def _route_template(scope: Scope) -> str:
    """从匹配结果还原完整路由模板。

    新版 FastAPI 使用惰性 include，`scope["route"].path` 不包含 include 前缀，
    直接使用会得到 `/health` 而不是 `/api/v1/health`。
    这里按「实际路径前缀 + 路由模板后缀」拼接，既保留前缀，
    又不会把路径参数的真实值写进标签。
    """
    route = scope.get("route")
    template = getattr(route, "path", None)
    if not isinstance(template, str):
        return UNMATCHED_ROUTE

    path = scope.get("path", "")
    if not isinstance(path, str):
        return template

    actual_segments = (path.rstrip("/") or "/").split("/")
    template_segments = template.split("/")
    if len(actual_segments) < len(template_segments):
        return template

    prefix_segments = actual_segments[: len(actual_segments) - len(template_segments) + 1]
    return "/".join([*prefix_segments, *template_segments[1:]])


def render_metrics() -> Response:
    """输出 Prometheus 文本格式。"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


class MetricsMiddleware:
    """记录 HTTP 请求数与耗时；排除指标端点自身，避免自增噪声。"""

    def __init__(self, app: ASGIApp, metrics_path: str) -> None:
        self.app = app
        self.metrics_path = metrics_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == self.metrics_path:
            await self.app(scope, receive, send)
            return

        started_at = time.perf_counter()
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            # 404 等未匹配路由的请求没有 route 对象，归入固定标签避免基数增长
            route_path = _route_template(scope)
            method = scope.get("method", "UNKNOWN")
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                route=route_path,
                status=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION.labels(method=method, route=route_path).observe(
                time.perf_counter() - started_at
            )
