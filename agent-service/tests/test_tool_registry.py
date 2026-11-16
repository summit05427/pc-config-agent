"""工具注册与治理测试：注册、发现、冲突、超时、重试与权限。"""

import asyncio
from collections.abc import Iterator

import pytest
from langchain_core.tools import tool

from app.agent import registry as registry_module
from app.agent.registry import (
    ToolExecutionError,
    ToolModuleImportError,
    ToolRegistrationError,
    ToolSpec,
    _resolve_limits,
    _tools_in_package,
    build_tools,
    discover_tools,
    ensure_tools_loaded,
    get_default_tools,
    get_tool_spec,
    govern_tool,
    list_tool_specs,
    register_tool,
)
from app.agent.tool_context import ToolTurn
from app.core.config import AgentSettings

# 验收用的外部工具模块：不在 app/ 内，只能通过显式模块路径发现
FIXTURE_TOOL_MODULE = "tests.fixtures.tools_ext.sample_tool"
CONFLICT_TOOL_MODULE = "tests.fixtures.tools_ext.conflict_tool"


@pytest.fixture(autouse=True)
def _restore_tool_registry() -> Iterator[None]:
    """注册表是进程级单例；每个用例结束后恢复到内置工具基线。"""
    ensure_tools_loaded()
    snapshot = dict(registry_module._TOOL_SPECS)
    yield
    registry_module._TOOL_SPECS.clear()
    registry_module._TOOL_SPECS.update(snapshot)


@tool
async def echo(value: str) -> str:
    """原样返回输入。"""
    return value


@tool
async def slow(value: str) -> str:
    """故意慢的工具，用于验证超时。"""
    await asyncio.sleep(0.05)
    return value


_call_counter = {"attempts": 0}


@tool
async def flaky(value: str) -> str:
    """前两次失败、第三次成功的工具，用于验证重试。"""
    _call_counter["attempts"] += 1
    if _call_counter["attempts"] < 3:
        raise RuntimeError("临时故障")
    return value


async def test_governed_tool_keeps_schema_and_works() -> None:
    wrapped = govern_tool(ToolSpec(tool=echo, timeout_seconds=1, max_retries=0))

    assert wrapped.name == "echo"
    assert wrapped.description
    assert wrapped.args_schema is not None
    assert await wrapped.ainvoke({"value": "ok"}) == "ok"


async def test_tool_timeout_is_wrapped_as_safe_error() -> None:
    wrapped = govern_tool(ToolSpec(tool=slow, timeout_seconds=0.01, max_retries=0))

    with pytest.raises(ToolExecutionError, match="执行失败"):
        await wrapped.ainvoke({"value": "ok"})


async def test_tool_retries_before_failing() -> None:
    _call_counter["attempts"] = 0
    wrapped = govern_tool(ToolSpec(tool=flaky, timeout_seconds=1, max_retries=2))

    assert await wrapped.ainvoke({"value": "ok"}) == "ok"
    assert _call_counter["attempts"] == 3


async def test_tool_permission_is_enforced_per_call() -> None:
    wrapped = govern_tool(ToolSpec(tool=echo, required_roles=("admin",)))

    with ToolTurn(("user",)):
        with pytest.raises(ToolExecutionError, match="无权"):
            await wrapped.ainvoke({"value": "ok"})

    with ToolTurn(("admin",)):
        assert await wrapped.ainvoke({"value": "ok"}) == "ok"


def test_invalid_tool_limits_are_rejected() -> None:
    with pytest.raises(ValueError):
        _resolve_limits(ToolSpec(tool=echo, timeout_seconds=0))
    with pytest.raises(ValueError):
        _resolve_limits(ToolSpec(tool=echo, max_retries=-1))


def test_build_tools_preserves_order_and_names() -> None:
    tools = build_tools([ToolSpec(tool=echo), ToolSpec(tool=slow)])

    assert [item.name for item in tools] == ["echo", "slow"]


def test_register_tool_adds_governance_metadata() -> None:
    """装饰器注册后可按名称查询，并带上注册时声明的治理参数。"""

    @register_tool(
        name="unit_echo",
        description="原样返回输入文本；用于注册表单元测试。",
        timeout_seconds=2.0,
        max_retries=0,
        max_output_tokens=500,
        max_calls_per_turn=2,
    )
    def unit_echo(value: str) -> str:
        return value

    spec = get_tool_spec("unit_echo")
    assert spec is not None
    assert spec.tool.name == "unit_echo"
    assert spec.timeout_seconds == 2.0
    assert spec.max_retries == 0
    assert spec.max_output_tokens == 500
    assert spec.max_calls_per_turn == 2
    assert spec.is_read_only is True
    assert spec.source == "builtin"


def test_duplicate_tool_name_is_rejected() -> None:
    """同名工具必须启动期失败：静默覆盖会让模型看到与文档不符的工具。"""

    with pytest.raises(ToolRegistrationError, match="重复注册"):

        @register_tool(name="solve_pc_build", description="与内置工具重名")
        def duplicate_solve(requirement_json: str) -> str:
            return requirement_json


def test_invalid_tool_metadata_is_rejected() -> None:
    with pytest.raises(ToolRegistrationError, match="非法的工具名"):
        register_tool(name="Bad-Name", description="描述合法但名称非法")
    with pytest.raises(ToolRegistrationError, match="缺少描述"):
        register_tool(name="valid_name", description="   ")
    with pytest.raises(ToolRegistrationError, match="超时"):
        register_tool(name="valid_name", description="描述", timeout_seconds=0)
    with pytest.raises(ToolRegistrationError, match="重试次数"):
        register_tool(name="valid_name", description="描述", max_retries=-1)
    with pytest.raises(ToolRegistrationError, match="输出上限"):
        register_tool(name="valid_name", description="描述", max_output_tokens=0)
    with pytest.raises(ToolRegistrationError, match="单轮调用上限"):
        register_tool(name="valid_name", description="描述", max_calls_per_turn=0)


def test_register_tool_supports_async_functions() -> None:
    """异步工具同样走装饰器注册，治理层用 `ainvoke` 统一调用。"""

    @register_tool(name="async_echo", description="异步工具样例。")
    async def async_echo(value: str) -> str:
        return f"async: {value}"

    spec = get_tool_spec("async_echo")
    assert spec is not None
    assert asyncio.run(spec.tool.ainvoke({"value": "x"})) == "async: x"


def test_unknown_tool_query_returns_none() -> None:
    assert get_tool_spec("not_registered") is None


def test_extra_module_is_discovered_and_governed() -> None:
    """显式模块路径中的工具无需改核心代码即可被发现并绑定。"""
    discover_tools(extra_modules=[FIXTURE_TOOL_MODULE])

    spec = get_tool_spec("sample_echo")
    assert spec is not None
    assert spec.source == "ext"
    assert "sample_echo" in [tool_item.name for tool_item in get_default_tools()]


def test_conflicting_module_fails_fast() -> None:
    """扩展模块与内置工具重名时，启动期直接失败而不是覆盖内置实现。"""
    with pytest.raises(ToolRegistrationError, match="重复注册"):
        discover_tools(extra_modules=[CONFLICT_TOOL_MODULE])


def test_missing_tools_package_yields_no_modules() -> None:
    """`tools_ext` 包被移除时发现流程应退化为空列表，而不是报错。"""
    assert _tools_in_package("definitely_missing_tools_package") == []


def test_missing_tool_module_reports_module_name() -> None:
    """导入失败必须指明模块名，否则接入方无法定位配置错误。"""
    with pytest.raises(ToolModuleImportError, match="not_a_module"):
        discover_tools(extra_modules=["tests.fixtures.tools_ext.not_a_module"])


def test_tool_modules_setting_accepts_comma_separated() -> None:
    """`AGENT__TOOL_MODULES` 用逗号分隔；空项被忽略。"""
    settings = AgentSettings(tool_modules="a.b, c.d , ")  # type: ignore[arg-type]

    assert settings.tool_modules == ["a.b", "c.d"]


def test_registered_tool_names_are_stable() -> None:
    """内置工具仍在注册表首位，顺序变化会影响模型看到的工具列表。"""
    assert [spec.tool.name for spec in list_tool_specs()] == [
        "search_hardware_candidates",
        "get_benchmark_data",
        "get_verified_offers",
        "solve_pc_build",
        "compose_pc_build",
        "validate_pc_build",
        "check_partial_compatibility",
        "search_knowledge",
    ]
