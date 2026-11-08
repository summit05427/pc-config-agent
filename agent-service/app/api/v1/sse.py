"""SSE 事件编码（基于 sse-starlette）。

保留这一层薄封装的原因：
1. 统一分隔符为 `\n`，与前端解析逻辑一致（sse-starlette 默认 `\r\n`）；
2. 事件负载统一走 JSON，避免各路由自行拼字符串导致格式漂移；
3. 心跳交给 `EventSourceResponse(ping=...)` 的官方实现，不再自研定时器。
"""

import json
import time
from typing import Any

import structlog
from sse_starlette.sse import ServerSentEvent

from app.core.error_codes import CODE_AGENT_ERROR, CODE_REQUEST_TIMEOUT
from app.core.metrics import (
    SSE_DISCONNECTS_TOTAL,
    SSE_STREAMS_ACTIVE,
    SSE_TIME_TO_FIRST_TOKEN,
    SSE_TIMEOUTS_TOTAL,
)

logger = structlog.get_logger(__name__)

# 全项目统一使用 LF；前端按 `\n\n` 切分事件块
SSE_SEPARATOR = "\n"

# 事件负载版本：新增字段一律可选，旧前端忽略该字段仍能正常渲染（决策 D6）
SSE_SCHEMA_VERSION = "1"
SCHEMA_VERSION_FIELD = "schema_version"


def encode_event(event: str, data: dict[str, Any], event_id: int) -> ServerSentEvent:
    """构造单个业务事件。

    :param event: 事件类型（token / tool_call / tool_result / done / error）
    :param data: 事件负载，序列化为 JSON；会被追加 `schema_version`
    :param event_id: 自增序号，仅用于排查乱序，不支持断点续传
    """
    # 版本号由编码层统一注入，避免各路由漏加或写错版本
    payload = {**data, SCHEMA_VERSION_FIELD: SSE_SCHEMA_VERSION}
    return ServerSentEvent(
        event=event,
        id=str(event_id),
        data=json.dumps(payload, ensure_ascii=False),
        sep=SSE_SEPARATOR,
    )


class StreamEncoder:
    """业务事件的编码器：统一事件编号、首 token 计时与流级指标。

    编号与 TTFT 状态若散落在生成器里，超时/错误分支会被淹没在细节中；
    收敛到这一处后，传输层只需要迭代回合事件并逐个编码。
    """

    def __init__(self) -> None:
        self._event_id = 0
        self._started_at = time.perf_counter()
        self._has_first_token = False

    def encode(self, event: str, data: dict[str, Any]) -> ServerSentEvent:
        """编号并编码下一个事件；只对首个用户可见 token 记录 TTFT。"""
        if event == "token" and not self._has_first_token:
            self._has_first_token = True
            SSE_TIME_TO_FIRST_TOKEN.observe(time.perf_counter() - self._started_at)
        self._event_id += 1
        return encode_event(event, data, self._event_id)

    def encode_timeout(self, thread_id: str) -> ServerSentEvent:
        """超时分支：计数与告警后下发 error；流内无法再改状态码。"""
        SSE_TIMEOUTS_TOTAL.inc()
        logger.warning("chat.stream_timeout", thread_id=thread_id)
        return self.encode("error", {"code": CODE_REQUEST_TIMEOUT, "message": "生成超时，请重试"})

    def encode_failure(self, thread_id: str) -> ServerSentEvent:
        """未预期异常：只打一次堆栈，再以 error 事件告知前端。"""
        logger.exception("chat.stream_failed", thread_id=thread_id)
        return self.encode("error", {"code": CODE_AGENT_ERROR, "message": "生成回复失败，请重试"})

    def record_disconnect(self, thread_id: str) -> None:
        """客户端断开：只计数与告警，取消异常由调用方继续抛出。"""
        SSE_DISCONNECTS_TOTAL.inc()
        logger.info("chat.stream_cancelled", thread_id=thread_id)

    def enter(self) -> None:
        """进入流：活跃流计数加一。"""
        SSE_STREAMS_ACTIVE.inc()

    def exit(self) -> None:
        """离开流：活跃流计数减一。"""
        SSE_STREAMS_ACTIVE.dec()
