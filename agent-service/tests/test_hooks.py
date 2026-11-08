"""生命周期钩子的注册、排序、失败策略与工具链集成测试。"""

import pytest
from langchain_core.tools import StructuredTool

from app.agent import hooks
from app.agent.hooks import (
    HookBlockedError,
    HookContext,
    HookModuleImportError,
    HookPoint,
    discover_hooks,
    ensure_hooks_loaded,
    register_hook,
    reset_hooks,
    run_hooks,
)
from app.agent.registry import ToolExecutionError, ToolSpec, govern_tool
from app.core.config import AgentSettings


@pytest.fixture(autouse=True)
def _clean_hooks() -> None:
    """每个用例独立注册表，避免钩子跨用例泄漏。"""
    reset_hooks()
    yield
    reset_hooks()


async def test_run_hooks_without_registration_is_noop() -> None:
    await run_hooks(HookContext(point=HookPoint.BEFORE_MODEL))


def test_has_blocking_hook_detects_registration() -> None:
    """只有阻断型钩子才需要触发流式缓冲，非阻断钩子不应影响实时输出。"""

    @register_hook(HookPoint.AFTER_MODEL)
    async def observer(context: HookContext) -> None:
        return None

    assert hooks.has_blocking_hook(HookPoint.AFTER_MODEL) is False
    assert hooks.should_buffer_model_output() is False

    @register_hook(HookPoint.AFTER_MODEL, blocking=True)
    async def guard(context: HookContext) -> None:
        return None

    assert hooks.has_blocking_hook(HookPoint.AFTER_MODEL) is True
    assert hooks.has_blocking_hook(HookPoint.BEFORE_MODEL) is False
    # 流式层只问「要不要缓冲」，不直接依赖具体钩子点
    assert hooks.should_buffer_model_output() is True


async def test_hooks_run_in_priority_order() -> None:
    calls: list[str] = []

    @register_hook(HookPoint.BEFORE_MODEL, priority=10)
    async def late(context: HookContext) -> None:
        calls.append("late")

    @register_hook(HookPoint.BEFORE_MODEL, priority=-5)
    async def early(context: HookContext) -> None:
        calls.append("early")

    await run_hooks(HookContext(point=HookPoint.BEFORE_MODEL))

    assert calls == ["early", "late"]


async def test_hook_receives_context() -> None:
    seen: list[HookContext] = []

    @register_hook(HookPoint.AFTER_TOOL)
    async def capture(context: HookContext) -> None:
        seen.append(context)

    context = HookContext(
        point=HookPoint.AFTER_TOOL,
        tool_name="get_current_time",
        text="2026-11-05 12:00:00",
    )
    await run_hooks(context)

    assert seen == [context]


async def test_non_blocking_failure_continues_with_later_hooks() -> None:
    calls: list[str] = []

    @register_hook(HookPoint.BEFORE_REQUEST, name="broken")
    async def broken(context: HookContext) -> None:
        raise RuntimeError("未预期的钩子错误")

    @register_hook(HookPoint.BEFORE_REQUEST)
    async def after(context: HookContext) -> None:
        calls.append("after")

    await run_hooks(HookContext(point=HookPoint.BEFORE_REQUEST))

    assert calls == ["after"]


async def test_non_blocking_block_signal_is_ignored() -> None:
    calls: list[str] = []

    @register_hook(HookPoint.BEFORE_REQUEST)
    async def guard(context: HookContext) -> None:
        raise HookBlockedError("不应阻断")

    @register_hook(HookPoint.BEFORE_REQUEST)
    async def after(context: HookContext) -> None:
        calls.append("after")

    await run_hooks(HookContext(point=HookPoint.BEFORE_REQUEST))

    assert calls == ["after"]


async def test_blocking_failure_masks_detail_and_stops_flow() -> None:
    calls: list[str] = []

    @register_hook(HookPoint.AFTER_MODEL, blocking=True, name="guard")
    async def guard(context: HookContext) -> None:
        raise RuntimeError("内部细节不应外泄")

    @register_hook(HookPoint.AFTER_MODEL)
    async def after(context: HookContext) -> None:
        calls.append("after")

    with pytest.raises(HookBlockedError) as info:
        await run_hooks(HookContext(point=HookPoint.AFTER_MODEL))

    assert "guard" in str(info.value)
    assert "内部细节不应外泄" not in str(info.value)
    assert calls == []


async def test_blocking_hook_can_block_with_reason() -> None:
    @register_hook(HookPoint.AFTER_MODEL, blocking=True)
    async def guard(context: HookContext) -> None:
        raise HookBlockedError("输出命中审核规则")

    with pytest.raises(HookBlockedError, match="输出命中审核规则"):
        await run_hooks(HookContext(point=HookPoint.AFTER_MODEL))


def test_discover_hooks_deduplicates_module_names(monkeypatch: pytest.MonkeyPatch) -> None:
    imported: list[str] = []

    def fake_import(module_name: str) -> None:
        imported.append(module_name)

    monkeypatch.setattr(hooks.importlib, "import_module", fake_import)

    discover_hooks(["custom.hooks", "custom.hooks"])

    assert imported == ["custom.hooks"]


def test_ensure_hooks_loaded_runs_discovery_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(hooks, "discover_hooks", lambda: calls.append(1))

    ensure_hooks_loaded()
    ensure_hooks_loaded()

    assert calls == [1]


def test_discover_hooks_wraps_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import(module_name: str) -> None:
        raise ModuleNotFoundError("找不到模块")

    monkeypatch.setattr(hooks.importlib, "import_module", fake_import)

    with pytest.raises(HookModuleImportError, match="missing.hooks"):
        discover_hooks(["missing.hooks"])


def test_hooks_modules_are_parsed_from_comma_separated_string() -> None:
    settings = AgentSettings.model_validate({"hooks_modules": "a.b, c.d"})

    assert settings.hooks_modules == ["a.b", "c.d"]


async def test_registry_runs_tool_hooks_around_invocation() -> None:
    events: list[tuple[str, str | None]] = []

    @register_hook(HookPoint.BEFORE_TOOL)
    async def before(context: HookContext) -> None:
        events.append(("before", context.tool_name))

    @register_hook(HookPoint.AFTER_TOOL)
    async def after(context: HookContext) -> None:
        events.append(("after", context.text))

    tool = StructuredTool.from_function(
        func=lambda: "ok",
        name="demo_tool",
        description="演示工具",
    )
    governed = govern_tool(ToolSpec(tool=tool))

    assert await governed.ainvoke({}) == "ok"
    assert events == [("before", "demo_tool"), ("after", "ok")]


async def test_blocking_before_tool_hook_returns_safe_error() -> None:
    @register_hook(HookPoint.BEFORE_TOOL, blocking=True)
    async def guard(context: HookContext) -> None:
        raise HookBlockedError("禁止调用")

    tool = StructuredTool.from_function(
        func=lambda: "ok",
        name="blocked_tool",
        description="被拦截的工具",
    )
    governed = govern_tool(ToolSpec(tool=tool))

    with pytest.raises(ToolExecutionError, match="安全策略"):
        await governed.ainvoke({})


async def test_blocking_after_tool_hook_returns_safe_error() -> None:
    @register_hook(HookPoint.AFTER_TOOL, blocking=True)
    async def guard(context: HookContext) -> None:
        raise HookBlockedError("结果不可用")

    tool = StructuredTool.from_function(
        func=lambda: "ok",
        name="after_blocked_tool",
        description="结果被拦截的工具",
    )
    governed = govern_tool(ToolSpec(tool=tool))

    with pytest.raises(ToolExecutionError, match="安全策略"):
        await governed.ainvoke({})
