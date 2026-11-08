"""用户偏好模型与提示词渲染测试：只验证纯函数与校验，不接触模型与网络。"""

import pytest
from pydantic import ValidationError

from app.agent.preferences import (
    INSTRUCTIONS_MAX_LENGTH,
    ChatPreferences,
    build_preference_prompt,
)


def test_no_preferences_keep_current_behavior() -> None:
    """不传偏好、或传全默认值时，不得向系统提示词追加任何内容。"""
    assert build_preference_prompt(None) is None
    assert build_preference_prompt(ChatPreferences()) is None


def test_prompt_contains_instructions_language_and_style() -> None:
    """指令、语言、风格都应转成可读的提示词条目。"""
    prompt = build_preference_prompt(
        ChatPreferences(
            instructions="回答尽量简短",
            reply_language="zh-CN",
            response_style="concise",
        )
    )

    assert prompt is not None
    assert prompt.startswith("## 用户偏好")
    assert "回答尽量简短" in prompt
    assert "简体中文" in prompt
    assert "尽量简短" in prompt


def test_auto_language_adds_no_hint() -> None:
    """auto 表示不额外约束，不应生成多余提示。"""
    assert build_preference_prompt(ChatPreferences(reply_language="auto")) is None


def test_blank_instructions_are_ignored() -> None:
    """空白指令按未设置处理，其余偏好仍照常渲染。"""
    prompt = build_preference_prompt(
        ChatPreferences(instructions="   ", reply_language="en-US")
    )

    assert prompt is not None
    assert "用户自定义指令" not in prompt
    assert "English" in prompt


def test_instructions_longer_than_limit_are_rejected() -> None:
    """超长指令直接拒绝，避免把用户输入无限制塞进提示词。"""
    with pytest.raises(ValidationError):
        ChatPreferences(instructions="x" * (INSTRUCTIONS_MAX_LENGTH + 1))


def test_unknown_reply_language_is_rejected() -> None:
    """语言只接受白名单取值。"""
    with pytest.raises(ValidationError):
        ChatPreferences(reply_language="fr-FR")  # type: ignore[call-arg]


def test_unknown_response_style_is_rejected() -> None:
    """风格只接受白名单取值。"""
    with pytest.raises(ValidationError):
        ChatPreferences(response_style="verbose")  # type: ignore[call-arg]


def test_use_history_defaults_to_true() -> None:
    """缺省时保持现有行为：继续注入历史。"""
    assert ChatPreferences().use_history is True
