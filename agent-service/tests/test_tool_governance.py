"""工具输出治理测试：截断、脱敏、单轮调用上限与开关。"""

import pytest
from langchain_core.tools import tool

from app.agent import registry as registry_module
from app.agent.context import count_tokens, truncate_to_token_budget
from app.agent.registry import ToolSpec, govern_tool, redact_sensitive_text
from app.agent.tool_context import ToolTurn
from app.core.config import Settings


@tool
async def echo(value: str) -> str:
    """原样返回输入。"""
    return value


@tool
async def huge_output() -> str:
    """返回超长文本，用于验证截断。"""
    return "长" * 100_000


@tool
async def contacts() -> str:
    """返回含手机号、邮箱、身份证与 Token 的文本。"""
    return (
        "手机 13812345678，邮箱 alice@example.com，"
        "身份证 110101199001011234，密钥 sk-abcdefgh12345678，"
        "请求头 Bearer abcdefghijklmnop"
    )


def _settings(**agent_overrides: object) -> Settings:
    """构造不读取 .env 的配置对象；auth 由 conftest 注入。"""
    return Settings(_env_file=None, agent=agent_overrides)


async def test_huge_output_is_truncated_with_notice() -> None:
    """10 万字符的返回必须被截到 2000 token 以内，并告知模型原长度。"""
    wrapped = govern_tool(ToolSpec(tool=huge_output, timeout_seconds=5, max_retries=0))

    result = await wrapped.ainvoke({})

    assert isinstance(result, str)
    assert len(result) < 100_000
    assert "[结果已截断，原长度 100000 字符]" in result
    assert count_tokens(result) <= 2000


async def test_sensitive_fields_are_masked_by_default() -> None:
    """手机号、邮箱、身份证、API Key 与 Bearer 凭据一律打码后才进入模型。"""
    wrapped = govern_tool(ToolSpec(tool=contacts, timeout_seconds=5, max_retries=0))

    result = await wrapped.ainvoke({})

    assert "13812345678" not in result
    assert "138****5678" in result
    assert "alice@example.com" not in result
    assert "a***@example.com" in result
    assert "110101199001011234" not in result
    assert "110101********1234" in result
    assert "sk-abcdefgh12345678" not in result
    assert "sk-****" in result
    assert "Bearer abcdefghijklmnop" not in result
    assert "Bearer ****" in result


async def test_redaction_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """关闭开关后保留原文，便于本地排查；生产默认必须开启。"""
    settings = _settings(tool_redact_output=False)
    monkeypatch.setattr(registry_module, "get_settings", lambda: settings)
    wrapped = govern_tool(ToolSpec(tool=contacts, timeout_seconds=5, max_retries=0))

    result = await wrapped.ainvoke({})

    assert "13812345678" in result
    assert "alice@example.com" in result


async def test_fourth_call_returns_limit_notice_instead_of_raising() -> None:
    """超过单轮上限时返回提示文本，让模型基于已有信息收敛回答。"""
    wrapped = govern_tool(
        ToolSpec(tool=echo, timeout_seconds=1, max_retries=0, max_calls_per_turn=3)
    )

    with ToolTurn(()):
        for _ in range(3):
            assert await wrapped.ainvoke({"value": "ok"}) == "ok"

        limited = await wrapped.ainvoke({"value": "ok"})

    assert "本轮调用次数已达上限（3 次）" in limited


async def test_call_counter_resets_between_turns() -> None:
    """计数按请求重置：同一工具在新一轮对话中可以继续调用。"""
    wrapped = govern_tool(
        ToolSpec(tool=echo, timeout_seconds=1, max_retries=0, max_calls_per_turn=1)
    )

    with ToolTurn(()):
        assert await wrapped.ainvoke({"value": "first"}) == "first"
        assert "上限" in await wrapped.ainvoke({"value": "second"})

    with ToolTurn(()):
        assert await wrapped.ainvoke({"value": "third"}) == "third"


def test_redact_sensitive_text_keeps_normal_text() -> None:
    """脱敏只针对敏感形态，普通文本不得被误改。"""
    text = "订单号 20261104，数量 12，备注正常"

    assert redact_sensitive_text(text) == text


def test_truncate_to_token_budget_edge_cases() -> None:
    """小文本原样返回；非法预算在入口拒绝。"""
    text, truncated = truncate_to_token_budget("短文本", 100)
    assert text == "短文本"
    assert truncated is False

    with pytest.raises(ValueError):
        truncate_to_token_budget("短文本", 0)
