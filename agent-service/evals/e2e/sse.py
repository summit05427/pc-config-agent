"""SSE 帧解析：把服务端字节流还原成 `(event, data)` 序列。

与测试里的整段文本解析不同，这里按行增量消费：
真实 HTTP 响应不能先落地成完整字符串；心跳注释（以 `:` 开头）必须被识别并忽略，
否则会被当成残缺的业务事件。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

# SSE 字段前缀；按规范字段名后可以带一个空格
FIELD_SEPARATOR = ":"
COMMENT_PREFIX = ":"
DEFAULT_EVENT = "message"


class SseParseError(RuntimeError):
    """帧结构或 JSON 负载非法；属于服务端契约缺陷，直接判用例失败。"""


@dataclass(frozen=True)
class SseFrame:
    """一个原始 SSE 块；心跳只有注释，没有事件名与数据。"""

    event_id: str | None
    event: str | None
    data: str | None
    comment: str | None = None

    @property
    def is_comment(self) -> bool:
        return self.comment is not None

    def to_event(self) -> SseEvent:
        """转成可断言的业务事件；心跳与缺字段的块不允许被当成业务事件。"""
        if self.event is None or self.data is None:
            raise SseParseError("业务帧缺少 event 或 data 字段")
        try:
            payload = json.loads(self.data)
        except json.JSONDecodeError as exc:
            raise SseParseError(f"事件 {self.event} 的 data 不是合法 JSON：{exc.msg}") from exc
        if not isinstance(payload, dict):
            raise SseParseError(f"事件 {self.event} 的 data 必须是 JSON 对象")
        return SseEvent(
            event_id=self.event_id,
            event=self.event or DEFAULT_EVENT,
            data=payload,
        )


@dataclass(frozen=True)
class SseEvent:
    """一个业务事件；`event_id` 保持原始字符串，契约检查负责校验自增。"""

    event_id: str | None
    event: str
    data: dict[str, Any]


def parse_frames(lines: Iterable[str]) -> Iterator[SseFrame]:
    """按行解析 SSE；空行结束一个块，流末尾没有空行时也要补发最后一个块。"""
    event_id: str | None = None
    event: str | None = None
    data_lines: list[str] = []
    comment: str | None = None
    started = False

    for raw_line in lines:
        # 兼容 CRLF；这里按 LF 发送，但代理或测试客户端可能改写行尾
        line = raw_line.rstrip("\r\n")
        if not line:
            if started:
                yield _build_frame(event_id, event, data_lines, comment)
            event_id, event, comment = None, None, None
            data_lines = []
            started = False
            continue

        started = True
        if line.startswith(COMMENT_PREFIX):
            # 心跳形如 `: ping - 2026-...`；只记录，不产生业务事件
            comment = line[len(COMMENT_PREFIX) :].strip()
            continue

        field, separator, value = line.partition(FIELD_SEPARATOR)
        if not separator:
            # 未知的裸行按规范应忽略，不能因此中断解析
            continue
        value = value[1:] if value.startswith(" ") else value
        if field == "id":
            event_id = value
        elif field == "event":
            event = value
        elif field == "data":
            data_lines.append(value)

    if started:
        yield _build_frame(event_id, event, data_lines, comment)


def _build_frame(
    event_id: str | None,
    event: str | None,
    data_lines: list[str],
    comment: str | None,
) -> SseFrame:
    return SseFrame(
        event_id=event_id,
        event=event,
        data="\n".join(data_lines) if data_lines else None,
        comment=comment,
    )


def parse_events(frames: Iterable[SseFrame]) -> tuple[list[SseEvent], list[str]]:
    """把非注释帧转成业务事件；返回 (事件列表, 解析错误列表)，不抛异常。"""
    events: list[SseEvent] = []
    errors: list[str] = []
    for frame in frames:
        if frame.is_comment:
            continue
        try:
            events.append(frame.to_event())
        except SseParseError as exc:
            errors.append(str(exc))
    return events, errors
