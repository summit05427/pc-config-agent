"""LLM 客户端封装。

为什么需要一层封装，而不是在路由里直接 new ChatOpenAI：
1. 模型对象内部持有 HTTP 连接池，每个请求新建会造成额外开销与连接泄漏；
2. 超时、重试、参数只在这里配置一次，避免各接口配置漂移；
3. 模型运行时可在同一进程内切换多个模型，缓存键必须能区分它们；
4. 方便测试时替换成假模型，不发真实请求。

所有模型请求只有一个出口：LiteLLM 网关（ADR 0008）。
- 托管流量：平台密钥只用于通过网关鉴权，模型名直接使用业务标识 `provider:model`；
- BYOK 流量：用户密钥与接入地址通过请求体的 `user_config` 传给网关，
  网关仅在本次请求内使用，不落库，也不进入任何日志。

本模块不再包含任何 Provider 协议分支；协议差异由网关负责。

缓存键为 `(agent_id, provider, model_key, credential_id)`：
- 切换模型或切换 Profile 必须真正换实例，不能复用旧模型；
- 禁止把 API Key 放进缓存键，避免密钥出现在日志、内存 dump 或异常文本里。
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError

# .env 中的占位符，视为"尚未配置"
PLACEHOLDER_API_KEY_PREFIX = "sk-replace"

# 缓存按凭证增长，必须有上限；超出后淘汰最早插入的实例
MAX_CHAT_MODEL_CACHE_ENTRIES = 64

# SDK 内置重试：仅对连接失败、429、5xx 生效，且只在首字节返回前重试
# 跨 Provider 的故障切换由网关负责，这里只做单次请求内的传输层重试
DEFAULT_MAX_RETRIES = 2

# BYOK 请求在网关侧的临时模型名；真实模型、密钥与地址放在 user_config 中
BYOK_GATEWAY_MODEL = "byok-model"

# 业务 provider 标识 → LiteLLM provider 前缀
# 只做命名翻译（qwen 在 LiteLLM 中叫 dashscope），不涉及任何协议实现
LITELLM_PROVIDER_PREFIX: dict[str, str] = {
    "openai": "openai",
    "deepseek": "deepseek",
    "qwen": "dashscope",
    "volcengine": "volcengine",
    "gemini": "gemini",
    "anthropic": "anthropic",
}

# (agent_id, provider, model_key, credential_id) -> 客户端实例
# agent_id 必须参与缓存键：不同 Profile 的人格/温度不同，复用会串扰
_CHAT_MODEL_CACHE: dict[tuple[str, str, str, str | None], BaseChatModel] = {}


class ReasoningChatOpenAI(ChatOpenAI):
    """保留网关归一化的思考内容，避免 LangChain 在流式转换时丢弃。

    langchain-openai 1.7.x 的 `_convert_delta_to_message_chunk` 只保留
    content / function_call / tool_calls，`reasoning_content` 会被忽略。
    这里在父类结果上补回该字段，不做任何 Provider 判断——协议差异仍由网关负责。
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation_chunk is None:
            return None
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or [{}]
        reasoning = (choices[0].get("delta") or {}).get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            generation_chunk.message.additional_kwargs["reasoning_content"] = reasoning
        return generation_chunk


def _secret_value(secret: SecretStr | None, name: str) -> str:
    """取密钥明文；缺失或仍是占位符时直接失败，避免运行期才暴露。"""
    if secret is None or not secret.get_secret_value().strip():
        raise AppError(
            f"未配置 {name}，请检查模型网关配置",
            code="llm_not_configured",
            status_code=503,
        )
    value = secret.get_secret_value().strip()
    if value.startswith(PLACEHOLDER_API_KEY_PREFIX):
        raise AppError(
            f"{name} 仍是占位符，请替换为真实密钥",
            code="llm_not_configured",
            status_code=503,
        )
    return value


def _is_gateway_mode(settings: Settings) -> bool:
    return bool(
        settings.llm.gateway_api_key
        and settings.llm.gateway_api_key.get_secret_value().strip()
    )


def _bare_model_name(model_key: str) -> str:
    """去掉 `<provider>:` 前缀，得到 Provider 需要的裸模型名。"""
    _, separator, bare_name = model_key.partition(":")
    return bare_name if separator and bare_name else model_key


def _managed_credentials(settings: Settings) -> tuple[str, str]:
    """返回托管流量的 `(api_key, base_url)`。

    配置了网关密钥就走网关；否则退化为直连（Solo 部署），只支持 OpenAI 兼容端点。
    """
    if _is_gateway_mode(settings):
        return (
            _secret_value(settings.llm.gateway_api_key, "LLM__GATEWAY_API_KEY"),
            settings.llm.gateway_base_url,
        )
    return (
        _secret_value(settings.llm.api_key, "LLM__API_KEY"),
        settings.llm.base_url or "https://api.deepseek.com/v1",
    )


def _byok_request_body(
    settings: Settings,
    *,
    provider: str,
    model_key: str,
    api_key: str,
    base_url: str | None,
) -> dict[str, object]:
    """构造 BYOK 的 `user_config`。

    网关据此在本次请求内使用用户凭证；平台密钥只用于通过网关鉴权。
    `api_base` 为空时不传，由网关使用该 Provider 的官方默认地址。
    """
    prefix = LITELLM_PROVIDER_PREFIX.get(provider.strip().lower())
    if prefix is None:
        raise AppError(
            f"暂不支持 provider={provider} 的自带密钥接入",
            code="llm_provider_unsupported",
            status_code=422,
        )
    litellm_params: dict[str, object] = {
        "model": f"{prefix}/{_bare_model_name(model_key)}",
        "api_key": api_key,
        "timeout": settings.llm.timeout_seconds,
    }
    if base_url:
        litellm_params["api_base"] = base_url
    return {
        "user_config": {
            "model_list": [
                {
                    "model_name": BYOK_GATEWAY_MODEL,
                    "litellm_params": litellm_params,
                }
            ]
        }
    }


def _validate_byok_settings(api_key: str) -> str:
    """校验 BYOK 凭证；接入地址可空，空值由网关回落到 Provider 官方地址。"""
    if not api_key:
        raise AppError(
            "BYOK 凭证为空，请重新绑定后再试",
            code="credential_unavailable",
            status_code=503,
        )
    return api_key


def create_chat_model(
    settings: Settings,
    *,
    provider: str | None = None,
    model_key: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """按配置构造 ChatModel。

    只负责"装配"，不发起任何网络请求；构造失败说明配置有问题。
    - 不传 `api_key`：托管流量，使用平台密钥与网关地址；
    - 传 `api_key`：BYOK，凭证与接入地址随请求体传给网关，绝不落库。
    """
    model_ref = model_key or settings.llm.model
    if api_key is None:
        key_value, resolved_base_url = _managed_credentials(settings)
        gateway_model = model_ref
        extra_body = None
    else:
        if not _is_gateway_mode(settings):
            raise AppError(
                "未配置模型网关，无法使用自带密钥",
                code="llm_not_configured",
                status_code=503,
            )
        key_value = _secret_value(settings.llm.gateway_api_key, "LLM__GATEWAY_API_KEY")
        resolved_base_url = settings.llm.gateway_base_url
        gateway_model = BYOK_GATEWAY_MODEL
        user_key = _validate_byok_settings(api_key)
        extra_body = _byok_request_body(
            settings,
            provider=provider or "",
            model_key=model_ref,
            api_key=user_key,
            base_url=base_url,
        )

    return ReasoningChatOpenAI(
        model=gateway_model,
        api_key=SecretStr(key_value),
        base_url=resolved_base_url,
        temperature=settings.llm.temperature if temperature is None else temperature,
        # max_tokens 是 ChatOpenAI 的 pydantic 字段，
        # 但其 __init__ 重载未暴露该参数，故 mypy 会误报
        max_tokens=settings.llm.max_tokens if max_tokens is None else max_tokens,  # type: ignore[call-arg]
        timeout=settings.llm.timeout_seconds,
        max_retries=DEFAULT_MAX_RETRIES,
        extra_body=extra_body,
    )


def get_chat_model(
    provider: str | None = None,
    model_key: str | None = None,
    credential_id: str | None = None,
    *,
    agent_id: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> BaseChatModel:
    """按 `(agent_id, provider, model_key, credential_id)` 复用模型实例。

    无参调用等价于旧行为：返回进程默认模型，并在进程内缓存。
    `agent_id` 参与缓存键：不同 Profile 即使模型相同，温度/输出上限不同也不能复用。
    BYOK 首次装配必须提供 `api_key`；命中缓存时不再需要凭证，
    因为实例内部已经持有同一个密钥。
    """
    settings = get_settings()
    model_ref = model_key or settings.llm.model
    provider_code = provider or ""
    cache_key = (
        agent_id or settings.agent.default_profile,
        provider_code,
        model_ref,
        credential_id,
    )

    cached = _CHAT_MODEL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if credential_id is not None and api_key is None:
        # 缓存未命中却没有凭证：只能退回平台密钥装配，那会把 BYOK 调成平台调用
        raise AppError(
            "BYOK 凭证未就绪，请重新发起请求",
            code="credential_unavailable",
            status_code=503,
        )

    created = create_chat_model(
        settings,
        provider=provider_code,
        model_key=model_ref,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if len(_CHAT_MODEL_CACHE) >= MAX_CHAT_MODEL_CACHE_ENTRIES:
        # dict 保持插入顺序，淘汰最早插入的实例即可
        _CHAT_MODEL_CACHE.pop(next(iter(_CHAT_MODEL_CACHE)))
    _CHAT_MODEL_CACHE[cache_key] = created
    return created


def invalidate_credential(credential_id: str) -> None:
    """丢弃某凭证对应的模型实例：凭证撤销或轮换后不得继续复用。"""
    for cache_key in [key for key in _CHAT_MODEL_CACHE if key[3] == credential_id]:
        _CHAT_MODEL_CACHE.pop(cache_key, None)


def clear_chat_model_cache() -> None:
    """清空模型缓存；配置或凭证变化后由调用方触发。"""
    _CHAT_MODEL_CACHE.clear()
