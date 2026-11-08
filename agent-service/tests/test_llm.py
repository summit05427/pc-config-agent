"""LLM 客户端测试：只验证装配逻辑，不发起真实网络请求。"""

import pytest
from langchain_core.messages import AIMessageChunk
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.services.llm import (
    BYOK_GATEWAY_MODEL,
    ReasoningChatOpenAI,
    clear_chat_model_cache,
    create_chat_model,
    get_chat_model,
    invalidate_credential,
)

GATEWAY_BASE_URL = "https://gateway.example.com"


def _settings(**llm_overrides: object) -> Settings:
    """构造不读取 .env 的配置对象，默认进入网关模式。"""
    return Settings(
        _env_file=None,
        llm={
            "gateway_api_key": "sk-gateway-123",
            "gateway_base_url": GATEWAY_BASE_URL,
            **llm_overrides,
        },
    )


def test_create_chat_model_reads_settings() -> None:
    """模型参数应与配置一致，且请求发往网关而不是 Provider。"""
    model = create_chat_model(_settings(model="gpt-4o-mini", temperature=0.2))

    assert model.model_name == "gpt-4o-mini"
    assert model.openai_api_base == GATEWAY_BASE_URL
    assert model.temperature == 0.2
    assert model.max_retries == 2


def test_reasoning_chunk_keeps_reasoning_content() -> None:
    """LangChain 默认丢弃的 reasoning_content 必须由子类补回 additional_kwargs。"""
    model = create_chat_model(_settings())
    assert isinstance(model, ReasoningChatOpenAI)

    chunk = {
        "choices": [
            {
                "index": 0,
                "delta": {"content": "", "reasoning_content": "先分析"},
                "finish_reason": None,
            }
        ],
        "model": "gpt-4o-mini",
    }
    generation = model._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)

    assert generation is not None
    assert generation.message.additional_kwargs["reasoning_content"] == "先分析"


def test_plain_chunk_does_not_add_reasoning_key() -> None:
    """普通 chunk 不能凭空多出字段，避免前端误判模型支持思考。"""
    model = create_chat_model(_settings())

    chunk = {
        "choices": [{"index": 0, "delta": {"content": "你好"}, "finish_reason": None}],
        "model": "gpt-4o-mini",
    }
    generation = model._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)

    assert generation is not None
    assert "reasoning_content" not in generation.message.additional_kwargs


def test_missing_gateway_key_raises_clear_error() -> None:
    """未配置网关密钥时应给出可读错误，而不是等到调用模型才 401。"""
    with pytest.raises(AppError) as exc_info:
        create_chat_model(_settings(gateway_api_key=None, api_key=None))

    assert exc_info.value.code == "llm_not_configured"
    assert exc_info.value.status_code == 503


def test_placeholder_gateway_key_raises_clear_error() -> None:
    """.env.example 里的占位符也应被识别为未配置。"""
    with pytest.raises(AppError) as exc_info:
        create_chat_model(_settings(gateway_api_key="sk-replace-with-real-key"))

    assert exc_info.value.code == "llm_not_configured"


def test_temperature_out_of_range_is_rejected() -> None:
    """配置层校验应在启动/构造阶段拦截非法参数。"""
    with pytest.raises(ValidationError):
        _settings(temperature=3.0)


def test_get_chat_model_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一进程内多次获取应返回同一实例。"""
    monkeypatch.setenv("LLM__GATEWAY_API_KEY", "sk-gateway-123")
    get_settings.cache_clear()
    clear_chat_model_cache()

    first = get_chat_model()
    second = get_chat_model()

    assert first is second


def test_get_chat_model_uses_byok_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """BYOK 凭证放进 user_config，网关鉴权仍用平台密钥。"""
    monkeypatch.setenv("LLM__GATEWAY_API_KEY", "sk-gateway-123")
    get_settings.cache_clear()
    clear_chat_model_cache()

    created = get_chat_model(
        "openai",
        "openai:gpt-4o-mini",
        "cred-1",
        api_key="sk-byok-1",
        base_url="https://byok.example.com/v1",
    )
    cached = get_chat_model("openai", "openai:gpt-4o-mini", "cred-1")

    assert cached is created
    assert created.model_name == BYOK_GATEWAY_MODEL
    # 发往网关的仍是平台密钥，用户密钥只出现在请求体里
    assert created.openai_api_key is not None
    assert created.openai_api_key.get_secret_value() == "sk-gateway-123"
    user_config = created.extra_body["user_config"]  # type: ignore[index]
    params = user_config["model_list"][0]["litellm_params"]
    assert params["model"] == "openai/gpt-4o-mini"
    assert params["api_key"] == "sk-byok-1"
    assert params["api_base"] == "https://byok.example.com/v1"


def test_get_chat_model_requires_credential_on_byok_cache_miss() -> None:
    """缓存未命中却没有凭证时不能静默用平台密钥，否则费用归属会错。"""
    clear_chat_model_cache()

    with pytest.raises(AppError) as exc_info:
        get_chat_model("openai", "openai:gpt-4o-mini", "cred-unknown")

    assert exc_info.value.code == "credential_unavailable"
    assert exc_info.value.status_code == 503


def test_invalidate_credential_drops_cached_instance() -> None:
    """凭证撤销后必须丢弃实例，下一次使用需要重新 lease。"""
    clear_chat_model_cache()
    get_chat_model(
        "openai",
        "openai:gpt-4o-mini",
        "cred-1",
        api_key="sk-byok-1",
        base_url="https://byok.example.com/v1",
    )

    invalidate_credential("cred-1")

    with pytest.raises(AppError):
        get_chat_model("openai", "openai:gpt-4o-mini", "cred-1")


def test_byok_omits_api_base_when_not_provided() -> None:
    """未填接入地址时不传 api_base，由网关使用该 Provider 的官方地址。"""
    model = create_chat_model(
        _settings(),
        provider="openai",
        model_key="openai:gpt-4o-mini",
        api_key="sk-byok",
        base_url=None,
    )

    user_config = model.extra_body["user_config"]  # type: ignore[index]
    params = user_config["model_list"][0]["litellm_params"]
    assert "api_base" not in params


def test_byok_rejects_unsupported_provider() -> None:
    with pytest.raises(AppError) as exc_info:
        create_chat_model(
            _settings(),
            provider="azure_openai",
            model_key="azure_openai:gpt-4o-mini",
            api_key="sk-byok",
            base_url="https://byok.example.com/v1",
        )

    assert exc_info.value.code == "llm_provider_unsupported"


def test_byok_requires_gateway_mode() -> None:
    """没有网关时不能使用自带密钥，否则凭证会绕过统一出口。"""
    with pytest.raises(AppError) as exc_info:
        create_chat_model(
            _settings(gateway_api_key=None, api_key="sk-test-123"),
            provider="openai",
            model_key="openai:gpt-4o-mini",
            api_key="sk-byok",
            base_url="https://byok.example.com/v1",
        )

    assert exc_info.value.code == "llm_not_configured"


def test_get_chat_model_switches_instance_on_model_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型切换必须真正换实例，不能复用旧模型（缓存键含模型标识）。"""
    monkeypatch.setenv("LLM__GATEWAY_API_KEY", "sk-gateway-123")
    get_settings.cache_clear()
    clear_chat_model_cache()

    first = get_chat_model("deepseek", "deepseek:deepseek-v4-pro")
    same_key = get_chat_model("deepseek", "deepseek:deepseek-v4-pro", None)
    other_model = get_chat_model("deepseek", "deepseek:deepseek-flash")

    assert same_key is first
    assert other_model is not first
    assert other_model.model_name == "deepseek:deepseek-flash"
    assert first.model_name == "deepseek:deepseek-v4-pro"


def test_get_chat_model_switches_instance_on_agent_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一模型下不同 Profile 不能复用实例：温度与输出上限不同。"""
    monkeypatch.setenv("LLM__GATEWAY_API_KEY", "sk-gateway-123")
    get_settings.cache_clear()
    clear_chat_model_cache()

    default_agent = get_chat_model("deepseek", "deepseek:deepseek-v4-pro", agent_id="default")
    writer_agent = get_chat_model(
        "deepseek",
        "deepseek:deepseek-v4-pro",
        agent_id="writer",
        temperature=0.8,
        max_tokens=3000,
    )

    assert writer_agent is not default_agent
    assert writer_agent.temperature == 0.8
    assert writer_agent.max_tokens == 3000


def test_managed_traffic_always_uses_gateway() -> None:
    """托管流量只认网关地址，Provider 差异不再由 Agent 判断。"""
    model = create_chat_model(
        _settings(),
        provider="openai",
        model_key="openai:gpt-4o-mini",
    )

    assert model.model_name == "openai:gpt-4o-mini"
    assert model.openai_api_base == GATEWAY_BASE_URL


def test_direct_mode_keeps_solo_deployment_working() -> None:
    """未配置网关密钥时退化为直连，供 Solo 部署使用。"""
    model = create_chat_model(
        _settings(
            gateway_api_key=None,
            api_key="sk-test-123",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com/v1",
        )
    )

    assert model.model_name == "deepseek-v4-pro"
    assert model.openai_api_base == "https://api.deepseek.com/v1"
