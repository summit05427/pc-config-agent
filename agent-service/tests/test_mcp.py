"""MCP 接入测试：默认关闭、网关端点解析、命名映射、降级与治理继承。

所有连接都用 stub 客户端替代，不访问真实网络，也不依赖任何 MCP Server。
"""

import sys
from contextlib import AsyncExitStack
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.agent import mcp as mcp_module
from app.agent.mcp import McpToolManager, mcp_tool_name, resolve_gateway_endpoint
from app.agent.registry import (
    ToolExecutionError,
    ToolSpec,
    build_tools,
    ensure_tools_loaded,
    list_tool_specs,
)
from app.core.config import AuthSettings, LLMSettings, MCPSettings, Settings

WARNING_EVENTS_TYPE = list[tuple[str, dict[str, Any]]]


def _record_warnings(monkeypatch: pytest.MonkeyPatch) -> WARNING_EVENTS_TYPE:
    """替换模块日志器，断言告警事件与字段（避免依赖日志渲染配置）。"""
    events: WARNING_EVENTS_TYPE = []

    def fake_warning(event: str, **kwargs: Any) -> None:
        events.append((event, kwargs))

    monkeypatch.setattr(mcp_module.logger, "warning", fake_warning)
    return events


def _gateway_llm(
    token: str | None = "sk-test",
    base_url: str = "http://litellm:4000",
) -> LLMSettings:
    return LLMSettings(gateway_base_url=base_url, gateway_api_key=token)


def _fake_tool(name: str, description: str = "示例工具") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description=description,
        inputSchema={
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
    )


class FakeSession:
    """最小 MCP ClientSession 替身，只实现被测路径用到的方法。"""

    def __init__(
        self,
        result: Any | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or SimpleNamespace(
            content=[SimpleNamespace(text="answer")], isError=False
        )
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        self.calls.append((name, arguments or {}))
        if self.error is not None:
            raise self.error
        return self.result

    tools: list[SimpleNamespace] = []


def _install_fake_connection(
    monkeypatch: pytest.MonkeyPatch,
    session: FakeSession,
    tools: list[SimpleNamespace],
    stack: Any | None = None,
) -> None:
    """用 stub 替换真实建连，返回固定 session 与 tools/list 结果。"""
    session.tools = tools

    async def fake_connect(url: str, token: str, settings: MCPSettings) -> tuple[Any, Any, Any]:
        return session, stack or AsyncExitStack(), SimpleNamespace(tools=tools)

    monkeypatch.setattr(mcp_module, "_connect_gateway", fake_connect)


def test_mcp_defaults_to_disabled() -> None:
    """默认关闭，且超时都有安全默认值。"""
    settings = MCPSettings()

    assert settings.enabled is False
    assert settings.gateway_url is None
    assert settings.allowed_tools == []
    assert settings.connect_timeout_seconds > 0
    assert settings.request_timeout_seconds > 0


def test_mcp_env_overrides(public_key_pem: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP__* 环境变量必须被 pydantic-settings 解析并覆盖默认值。"""
    monkeypatch.setenv("MCP__ENABLED", "true")
    monkeypatch.setenv("MCP__GATEWAY_URL", "http://gateway.test/mcp")
    monkeypatch.setenv("MCP__ALLOWED_TOOLS", '["echo"]')

    settings = Settings(
        _env_file=None,
        app_env="dev",
        auth=AuthSettings(jwt_public_key=public_key_pem),
    )

    assert settings.mcp.enabled is True
    assert settings.mcp.gateway_url == "http://gateway.test/mcp"
    assert settings.mcp.allowed_tools == ["echo"]


def test_mcp_timeouts_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        MCPSettings(connect_timeout_seconds=0)
    with pytest.raises(ValidationError):
        MCPSettings(request_timeout_seconds=0)


def test_endpoint_is_derived_from_gateway_base_url() -> None:
    """未显式配置时，聚合端点由网关地址推导，避免维护第二个地址。"""
    endpoint = resolve_gateway_endpoint(MCPSettings(), _gateway_llm(base_url="http://litellm:4000/"))

    assert endpoint == ("http://litellm:4000/mcp", "sk-test")


def test_gateway_url_override() -> None:
    settings = MCPSettings(gateway_url="http://127.0.0.1:4000/custom")

    endpoint = resolve_gateway_endpoint(settings, _gateway_llm())

    assert endpoint is not None
    assert endpoint[0] == "http://127.0.0.1:4000/custom"


async def test_missing_gateway_key_skips_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Solo 模式没有网关密钥：MCP 自然不生效，且不发起任何连接。"""
    events = _record_warnings(monkeypatch)

    async def forbidden_connect(url: str, token: str, settings: MCPSettings) -> Any:
        raise AssertionError("缺少网关密钥时不应建连")

    monkeypatch.setattr(mcp_module, "_connect_gateway", forbidden_connect)
    manager = McpToolManager()

    assert await manager.start(MCPSettings(enabled=True), llm_settings=LLMSettings()) == []
    assert events[0][0] == "mcp.gateway_credentials_missing"


async def test_invalid_gateway_url_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _record_warnings(monkeypatch)
    manager = McpToolManager()

    settings = MCPSettings(enabled=True, gateway_url="litellm:4000/mcp")
    assert await manager.start(settings, llm_settings=_gateway_llm()) == []
    assert events[0][0] == "mcp.gateway_url_invalid"


def test_mcp_tool_name_mapping() -> None:
    """名称必须满足 OpenAI 函数名与注册表约束，不能含冒号、点号或大写。"""
    assert mcp_tool_name("search") == "mcp__search"
    assert mcp_tool_name("deepwiki-read_wiki_structure") == "mcp__deepwiki_read_wiki_structure"
    assert mcp_tool_name("Search.Docs") == "mcp__search_docs"
    assert mcp_tool_name("!!!") == "mcp__tool"
    assert len(mcp_tool_name("t" * 100)) == 64


async def test_disabled_mcp_does_not_import_sdk_or_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """关闭时零开销：不导入 SDK、不解析端点、不建连。"""
    for module_name in [name for name in sys.modules if name == "mcp" or name.startswith("mcp.")]:
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    def forbidden_resolve(settings: MCPSettings, llm: LLMSettings) -> Any:
        raise AssertionError("关闭时不应解析网关端点")

    monkeypatch.setattr(mcp_module, "resolve_gateway_endpoint", forbidden_resolve)

    manager = McpToolManager()
    assert await manager.start(MCPSettings(enabled=False)) == []
    assert "mcp" not in sys.modules


async def test_gateway_connection_failure_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    """连接失败只告警并返回空工具，start 不抛异常。"""
    events = _record_warnings(monkeypatch)

    async def failing_connect(url: str, token: str, settings: MCPSettings) -> Any:
        raise OSError("connection refused")

    monkeypatch.setattr(mcp_module, "_connect_gateway", failing_connect)
    manager = McpToolManager()

    assert await manager.start(MCPSettings(enabled=True), llm_settings=_gateway_llm()) == []
    assert events[0][0] == "mcp.gateway_unavailable"
    assert events[0][1]["error_type"] == "OSError"


async def test_tools_are_named_and_governed(monkeypatch: pytest.MonkeyPatch) -> None:
    """工具名带 mcp__ 前缀，source=mcp，并继承 MCP 超时。"""
    session = FakeSession()
    _install_fake_connection(monkeypatch, session, [_fake_tool("search")])
    settings = MCPSettings(enabled=True, request_timeout_seconds=12)
    manager = McpToolManager()

    specs = await manager.start(settings, llm_settings=_gateway_llm())

    assert len(specs) == 1
    assert specs[0].source == "mcp"
    assert specs[0].tool.name == "mcp__search"
    assert specs[0].timeout_seconds == 12
    governed = build_tools(specs)[0]
    assert governed.name == "mcp__search"
    assert await governed.ainvoke({"q": "hello"}) == "answer"
    assert session.calls == [("search", {"q": "hello"})]


async def test_allowlist_filters_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    _install_fake_connection(
        monkeypatch, session, [_fake_tool("allowed"), _fake_tool("hidden")]
    )
    manager = McpToolManager()

    specs = await manager.start(
        MCPSettings(enabled=True, allowed_tools=["allowed"]),
        llm_settings=_gateway_llm(),
    )

    assert [spec.tool.name for spec in specs] == ["mcp__allowed"]


async def test_name_conflict_is_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    """与内置/其他工具同名时跳过并告警，不能让启动失败。"""
    events = _record_warnings(monkeypatch)
    session = FakeSession()
    _install_fake_connection(monkeypatch, session, [_fake_tool("search")])
    manager = McpToolManager()

    specs = await manager.start(
        MCPSettings(enabled=True),
        llm_settings=_gateway_llm(),
        reserved_names={"mcp__search"},
    )

    assert specs == []
    assert events[0][0] == "mcp.tool_conflict"
    assert events[0][1]["tool"] == "mcp__search"


async def test_error_result_becomes_safe_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(result=SimpleNamespace(content=[], isError=True))
    _install_fake_connection(monkeypatch, session, [_fake_tool("search")])
    manager = McpToolManager()

    specs = await manager.start(MCPSettings(enabled=True), llm_settings=_gateway_llm())

    with pytest.raises(ToolExecutionError, match="执行失败"):
        await build_tools(specs)[0].ainvoke({"q": "hello"})


async def test_stop_closes_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    stack = AsyncMock()
    session = FakeSession()
    _install_fake_connection(monkeypatch, session, [_fake_tool("search")], stack=stack)
    manager = McpToolManager()
    await manager.start(MCPSettings(enabled=True), llm_settings=_gateway_llm())

    await manager.stop()

    stack.aclose.assert_awaited_once()
    assert manager.tool_specs == []


def test_builtin_specs_keep_default_source() -> None:
    """新增 source 字段必须向后兼容，内置工具不改变既有行为。"""
    ensure_tools_loaded()
    specs = list_tool_specs()

    assert specs, "工具注册表不应为空"
    assert all(spec.source == "builtin" for spec in specs)
    assert isinstance(ToolSpec(tool=specs[0].tool), ToolSpec)
