"""可选 MCP 接入：作为客户端连接 LiteLLM 的聚合端点，把工具注册进受治理的工具链。

拓扑约束（ADR 0008）：
1. 模板只支持一种 MCP 拓扑——Server 清单由 LiteLLM 网关托管，Agent 只连
   `{LLM__GATEWAY_BASE_URL}/mcp`（可用 `MCP__GATEWAY_URL` 覆盖）；
2. Solo 模式没有网关，因此不提供 MCP；开启但缺少网关密钥时只告警跳过，不阻断启动；
3. 网关鉴权复用平台密钥 `LLM__GATEWAY_API_KEY`，不引入第二份凭证；
4. 超时/重试/输出脱敏/单轮调用上限等治理留在 Agent，网关只负责 Server 注册与上游鉴权。

日志只记录工具数量与异常类型，不打印 URL、令牌或工具参数。
"""

import asyncio
import json
import re
from collections.abc import Mapping
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any

import structlog
from langchain_core.tools import BaseTool, StructuredTool

from app.agent.registry import (
    ToolExecutionError,
    ToolSpec,
    ensure_tools_loaded,
    list_tool_specs,
)
from app.core.config import LLMSettings, MCPSettings, get_settings

logger = structlog.get_logger(__name__)

_MCP_TOOL_NAME_PREFIX = "mcp"
# OpenAI 兼容端点要求函数名匹配 ^[a-zA-Z0-9_-]+$；注册表进一步收紧为
# ^[a-z][a-z0-9_]{0,63}$，因此 MCP 工具名必须转成小写下划线格式
_INVALID_TOOL_NAME_CHARS = re.compile(r"[^a-z0-9_]+")
MAX_TOOL_NAME_LENGTH = 64


def _sanitize_tool_segment(value: str, fallback: str) -> str:
    """把任意名称压缩为小写字母 / 数字 / 下划线，空值用占位符兜底。"""
    cleaned = _INVALID_TOOL_NAME_CHARS.sub("_", value.lower()).strip("_")
    return cleaned or fallback


def mcp_tool_name(tool_name: str) -> str:
    """工具命名为 mcp__<tool>，避免与内置/扩展工具重名。

    网关返回的工具名已带 Server 前缀（如 deepwiki-read_wiki_structure），
    因此这里不再拼接 server 段；超长名称截断后若发生冲突，由注册冲突检测跳过。
    """
    tool = _sanitize_tool_segment(tool_name, "tool")
    return f"{_MCP_TOOL_NAME_PREFIX}__{tool}"[:MAX_TOOL_NAME_LENGTH]


def resolve_gateway_endpoint(settings: MCPSettings, llm: LLMSettings) -> tuple[str, str] | None:
    """返回 (聚合端点, 网关令牌)；不可用时告警并返回 None。

    令牌复用 `LLM__GATEWAY_API_KEY`：Solo 模式没有该密钥，MCP 自然不生效，
    不需要额外的“Solo 禁用 MCP”开关。
    """
    url = settings.gateway_url or f"{llm.gateway_base_url.rstrip('/')}/mcp"
    if not url.startswith(("http://", "https://")):
        logger.warning("mcp.gateway_url_invalid")
        return None
    token = llm.gateway_api_key.get_secret_value() if llm.gateway_api_key else ""
    if not token:
        logger.warning("mcp.gateway_credentials_missing")
        return None
    return url, token


async def _connect_gateway(
    url: str,
    token: str,
    settings: MCPSettings,
) -> tuple[Any, AsyncExitStack, Any]:
    """建立 Streamable HTTP 连接并完成 initialize / tools/list。

    返回的 AsyncExitStack 由调用方持有：连接必须活到进程退出，
    因此不能在这里 `async with` 结束后立即关闭。
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    stack = AsyncExitStack()
    try:
        read_stream, write_stream, _ = await stack.enter_async_context(
            streamablehttp_client(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=settings.connect_timeout_seconds,
            )
        )
        session = await stack.enter_async_context(
            ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=settings.request_timeout_seconds),
            )
        )
        await session.initialize()
        tools_result = await session.list_tools()
        return session, stack, tools_result
    except BaseException:
        await stack.aclose()
        raise


def _render_content(item: Any) -> str:
    """把 MCP 内容块转成模型可读文本；不支持的类型退化为 JSON。"""
    text = getattr(item, "text", None)
    if isinstance(text, str):
        return text
    if isinstance(item, str):
        return item
    if isinstance(item, Mapping):
        return json.dumps(item, ensure_ascii=False)
    model_dump_json = getattr(item, "model_dump_json", None)
    if callable(model_dump_json):
        return str(model_dump_json())
    return str(item)


def _render_result(result: Any) -> str:
    """错误结果转为可安全返回的异常，正常结果拼接为文本。"""
    if getattr(result, "isError", False):
        raise ToolExecutionError("MCP 工具执行失败，请稍后重试")
    parts = [_render_content(item) for item in getattr(result, "content", None) or ()]
    structured = getattr(result, "structuredContent", None)
    if not parts and isinstance(structured, Mapping):
        parts.append(json.dumps(structured, ensure_ascii=False))
    return "\n".join(parts)


def _build_tool(tool: Any, session: Any) -> BaseTool:
    """把 MCP 工具包装成 LangChain 工具，参数 schema 直接复用服务端 JSON Schema。"""
    tool_name = str(getattr(tool, "name", ""))

    async def invoke(**arguments: Any) -> str:
        return _render_result(await session.call_tool(tool_name, arguments))

    return StructuredTool.from_function(
        coroutine=invoke,
        name=mcp_tool_name(tool_name),
        description=getattr(tool, "description", None) or tool_name,
        args_schema=getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}},
    )


def _tool_specs(
    tools_result: Any,
    session: Any,
    settings: MCPSettings,
    reserved_names: set[str],
) -> list[ToolSpec]:
    """按 allowlist 与命名冲突规则筛选工具，并生成受治理的 ToolSpec。"""
    allowlist = set(settings.allowed_tools)
    specs: list[ToolSpec] = []
    for tool in getattr(tools_result, "tools", None) or ():
        raw_name = getattr(tool, "name", None)
        if not isinstance(raw_name, str) or not raw_name:
            logger.warning("mcp.tool_invalid")
            continue
        if allowlist and raw_name not in allowlist:
            continue
        tool_name = mcp_tool_name(raw_name)
        if tool_name in reserved_names:
            # MCP 冲突按降级处理：跳过并告警，不能让启动失败
            logger.warning("mcp.tool_conflict", tool=tool_name)
            continue
        reserved_names.add(tool_name)
        specs.append(
            ToolSpec(
                tool=_build_tool(tool, session),
                timeout_seconds=settings.request_timeout_seconds,
                source="mcp",
            )
        )
    return specs


class McpToolManager:
    """持有网关连接与工具列表；生命周期绑定 FastAPI lifespan。"""

    def __init__(self) -> None:
        self._specs: list[ToolSpec] = []
        self._stacks: list[AsyncExitStack] = []
        self._is_started = False

    @property
    def tool_specs(self) -> list[ToolSpec]:
        return list(self._specs)

    async def start(
        self,
        settings: MCPSettings | None = None,
        llm_settings: LLMSettings | None = None,
        reserved_names: set[str] | None = None,
    ) -> list[ToolSpec]:
        """建立连接并返回工具 spec；关闭或不可用时都不抛异常。"""
        if self._is_started:
            return self.tool_specs
        mcp_settings = settings or get_settings().mcp
        if not mcp_settings.enabled:
            return []

        self._is_started = True
        endpoint = resolve_gateway_endpoint(mcp_settings, llm_settings or get_settings().llm)
        if endpoint is None:
            return []

        occupied = set(reserved_names or ())
        if not occupied:
            # 冲突检测要覆盖全部已注册工具，不能只看内置模块：
            # 扩展工具（tools_ext / 配置模块）同样可能与 MCP 工具重名
            ensure_tools_loaded()
            occupied = {spec.tool.name for spec in list_tool_specs()}

        url, token = endpoint
        try:
            async with asyncio.timeout(mcp_settings.connect_timeout_seconds):
                session, stack, tools_result = await _connect_gateway(url, token, mcp_settings)
        except Exception as exc:
            logger.warning("mcp.gateway_unavailable", error_type=type(exc).__name__)
            return []

        self._stacks.append(stack)
        specs = _tool_specs(tools_result, session, mcp_settings, occupied)
        self._specs.extend(specs)
        logger.info("mcp.gateway_ready", tool_count=len(specs))
        return self.tool_specs

    async def stop(self) -> None:
        """关闭连接；关闭失败只告警，不影响应用退出。"""
        self._is_started = False
        stacks, self._stacks = self._stacks, []
        self._specs = []
        for stack in reversed(stacks):
            try:
                await stack.aclose()
            except Exception as exc:
                logger.warning("mcp.close_failed", error_type=type(exc).__name__)


_manager = McpToolManager()


async def start_mcp_tools(settings: MCPSettings | None = None) -> None:
    """应用启动时调用；关闭状态下是一条立即返回的空操作。"""
    await _manager.start(settings)


async def stop_mcp_tools() -> None:
    await _manager.stop()


def get_mcp_tool_specs() -> list[ToolSpec]:
    """构图时读取当前已接入的 MCP 工具；未启动或关闭时为空列表。"""
    return _manager.tool_specs
