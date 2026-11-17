"""消息与存储记录之间的纯转换：两个适配器共用，避免序列化规则分叉。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage


def message_role(message: AnyMessage) -> str:
    """把 LangChain 消息类型映射为前端契约里的 role。"""
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, ToolMessage):
        return "tool"
    if isinstance(message, SystemMessage):
        return "system"
    return "unknown"


def to_record(message: Any) -> dict[str, Any]:
    """只保留前端需要的字段；工具调用参数与结果都允许展示。"""
    content = message.content
    record: dict[str, Any] = {
        "role": message_role(message),
        "content": (
            content
            if isinstance(content, str)
            else json.dumps(content, ensure_ascii=False, default=str)
        ),
        "tool_calls": None,
        "name": None,
    }
    if isinstance(message, AIMessage) and message.tool_calls:
        record["tool_calls"] = [
            {"name": call["name"], "args": call["args"]} for call in message.tool_calls
        ]
    if isinstance(message, ToolMessage) and message.name:
        record["name"] = message.name
    return record


def to_payload(record: dict[str, Any]) -> dict[str, Any]:
    """去掉存储内部字段，组装成接口响应项。"""
    payload: dict[str, Any] = {"role": record["role"], "content": record["content"]}
    # 稳定消息标识：反馈按它绑定，刷新/翻页后必须命中同一条评价
    message_id = record.get("message_id")
    if message_id:
        payload["message_id"] = message_id
    if record.get("tool_calls"):
        payload["tool_calls"] = record["tool_calls"]
    if record.get("name"):
        payload["name"] = record["name"]
    if record.get("build_result"):
        payload["build_result"] = record["build_result"]
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        # 引用随历史返回，刷新后仍可展示来源；思考正文不落库，只回传可见性标记
        citations = metadata.get("citations")
        if isinstance(citations, list) and citations:
            payload["citations"] = citations
        if metadata.get("had_reasoning") is True:
            payload["had_reasoning"] = True
    created_at = record.get("created_at")
    if created_at is not None:
        # Postgres 返回 datetime，内存适配器也存 datetime；统一输出 ISO 8601
        payload["created_at"] = (
            created_at.isoformat() if hasattr(created_at, "isoformat") else created_at
        )
    return payload
