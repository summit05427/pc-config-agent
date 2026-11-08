"""System Prompt 目录化测试：加载、缓存与名称白名单。"""

import pytest

import app.main as main_module
from app.agent.prompts import (
    PromptNotFoundError,
    compose_openui_system_prompt,
    load_openui_prompt,
    load_prompt,
    load_system_prompt,
)
from app.core.config import AuthSettings, OpenUiSettings, Settings
from app.main import create_app


def test_default_system_prompt_is_loaded() -> None:
    content = load_system_prompt()

    assert "PC 装机配置助手" in content
    assert len(content) > 20


@pytest.mark.parametrize(
    "name",
    ["../secrets", "nested/default", "Default", "", "default.md"],
)
def test_invalid_prompt_name_is_rejected(name: str) -> None:
    """名称白名单天然排除路径分隔符与扩展名，防止读取目录外文件。"""
    with pytest.raises(PromptNotFoundError):
        load_prompt(name)


def test_missing_prompt_file_is_rejected() -> None:
    with pytest.raises(PromptNotFoundError):
        load_prompt("not-exists")


def test_prompt_is_cached_in_process() -> None:
    load_prompt.cache_clear()

    first = load_prompt("pc-config-system")
    second = load_prompt("pc-config-system")

    assert first is second
    assert load_prompt.cache_info().hits == 1


def test_openui_prompt_is_generated_artifact() -> None:
    """契约文件由 frontend 生成脚本产出，必须包含语法入口与组件签名。"""
    content = load_openui_prompt()

    assert "openui-lang" in content
    assert "root = Stack" in content
    assert "## Component Signatures" in content
    # 官方 prompt 默认要求整条裸 DSL；项目约定是 ```openui 围栏块，必须防止漂移
    assert "```openui" in content
    assert "## Project Output Convention" in content


def test_openui_prompt_name_uses_same_whitelist() -> None:
    with pytest.raises(PromptNotFoundError):
        load_openui_prompt("../secrets")


def test_compose_openui_system_prompt_appends_contract_and_limit() -> None:
    """顺序固定为「人格提示词 → 组件契约 → 规模限制」，人格不被替换。"""
    composed = compose_openui_system_prompt("你是助手")

    assert composed.startswith("你是助手")
    assert "openui-lang" in composed
    assert "最多输出 4 个顶层 UI 块" in composed


def test_create_app_fails_fast_when_openui_prompt_missing(
    public_key_pem: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """开启 OpenUI 但契约缺失时，应用组装阶段即失败，不等首个对话请求。"""
    settings = Settings(
        _env_file=None,
        app_env="dev",
        auth=AuthSettings(jwt_public_key=public_key_pem),
        openui=OpenUiSettings(enabled=True, prompt_name="missing"),
    )
    # prompts.load_openui_prompt 与 create_app 都从配置读取开关，
    # 必须同时替换两处，否则会读到默认的 openui 文件而绕过缺失场景
    monkeypatch.setattr("app.agent.prompts.get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="提示词加载失败"):
        create_app()
