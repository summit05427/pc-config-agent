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
    assert payload.resume is None
    # 字段集合变化属于契约变更，必须显式更新基线
    assert set(payload.model_dump()) == {
        "message",
        "thread_id",
        "model",
        "preferences",
        "agent_id",
        "regenerate",
        "reasoning",
        "resume",
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
    assert settings.system_prompt == "pc-config-system"
    assert settings.default_profile == "pc-config"
    assert settings.tool_timeout_seconds == 10.0
    assert settings.tool_max_retries == 1
    assert settings.max_solve_retries == 1


def test_default_tool_specs_are_stable() -> None:
    """默认工具集合与治理参数基线。"""
    get_default_tools()  # 触发启动期发现，确保内置工具已注册

    assert [spec.tool.name for spec in list_tool_specs()] == [
        "search_hardware_candidates",
        "get_benchmark_data",
        "get_verified_offers",
        "solve_pc_build",
        "compose_pc_build",
        "validate_pc_build",
    ]

    compose_spec = get_tool_spec("compose_pc_build")
    assert compose_spec is not None
    assert compose_spec.timeout_seconds == 30.0
    assert compose_spec.is_read_only is False

    search_spec = get_tool_spec("search_hardware_candidates")
    assert search_spec is not None
    assert search_spec.timeout_seconds == 10.0
    assert search_spec.max_retries is None
    assert search_spec.required_roles == ()

    solve_spec = get_tool_spec("solve_pc_build")
    assert solve_spec is not None
    assert solve_spec.timeout_seconds == 60.0
    assert solve_spec.is_read_only is False
