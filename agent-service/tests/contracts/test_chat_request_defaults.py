"""请求默认值与运行时默认参数基线。

阶段 1 会新增 `agent_id` 等可选字段；此处先冻结「不传可选字段时」的解析结果，
保证改造后旧请求的默认行为可以逐项对照。
"""

from app.agent.registry import get_default_tools, get_tool_spec, list_tool_specs
from app.api.v1.chat import ChatRequest
from app.core.config import AgentSettings, LLMSettings


def test_chat_request_without_optional_fields_is_valid() -> None:
    """只传 message + thread_id 时请求合法，模型/偏好/Agent 均为未指定。"""
    payload = ChatRequest(message="你好", thread_id="t-defaults")

    assert payload.model is None
    assert payload.preferences is None
    assert payload.agent_id is None
    assert payload.reasoning is None
    # 字段集合变化属于契约变更，必须显式更新基线
    assert set(payload.model_dump()) == {
        "message",
        "thread_id",
        "model",
        "preferences",
        "agent_id",
        "regenerate",
        "reasoning",
    }


def test_llm_defaults_are_stable() -> None:
    """进程默认模型参数基线；改默认值必须先改本用例与文档。"""
    settings = LLMSettings()

    assert settings.model == "deepseek:deepseek-v4-pro"
    assert settings.gateway_base_url == "http://litellm:4000"
    assert settings.temperature == 0.7
    assert settings.max_tokens == 2048


def test_agent_defaults_are_stable() -> None:
    """Agent 稳定性参数基线：上下文预算、提示词与工具治理默认值。"""
    settings = AgentSettings()

    assert settings.context_max_tokens == 6000
    assert settings.system_prompt == "default"
    assert settings.tool_timeout_seconds == 10.0
    assert settings.tool_max_retries == 1


def test_default_tool_specs_are_stable() -> None:
    """默认工具集合与治理参数基线。"""
    get_default_tools()  # 触发启动期发现，确保内置工具已注册

    assert [spec.tool.name for spec in list_tool_specs()] == ["get_current_time"]

    time_spec = get_tool_spec("get_current_time")
    assert time_spec is not None
    assert time_spec.timeout_seconds == 5.0
    assert time_spec.max_retries == 0
    assert time_spec.required_roles == ()
