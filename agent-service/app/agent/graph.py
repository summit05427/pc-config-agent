"""图装配入口：只生产 PC 配置推荐的单一确定性流水线。

通用 ReAct 图已删除，避免同一服务存在两套并行工作流。
`get_agent` / `get_agent_for_runtime` 的缓存语义保持不变：模型切换真正更换图实例。
"""

from collections import OrderedDict
from functools import lru_cache

import structlog
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from app.agent.checkpointer import get_checkpointer
from app.agent.pc.graph import build_pc_graph
from app.agent.profiles import AgentProfile, resolve_profile
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.services.llm import clear_chat_model_cache, get_chat_model
from app.services.llm import invalidate_credential as invalidate_chat_credential
from app.services.model_resolver import ResolvedRuntime

logger = structlog.get_logger(__name__)


def build_agent(
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    profile: AgentProfile | None = None,
) -> CompiledStateGraph:
    """按 Profile 组装 PC 图。

    `model=None` 时尝试使用进程默认模型；模型配置缺失或不可用时降级为
    确定性流水线（解析走规则兜底、正文走 Markdown 渲染），仍要返回基础配置。
    """
    active_profile = profile if profile is not None else resolve_profile(None)
    chat_model = model
    if chat_model is None:
        try:
            chat_model = get_chat_model(
                agent_id=active_profile.id,
                temperature=active_profile.model.temperature,
                max_tokens=active_profile.model.max_tokens,
            )
        except AppError as exc:
            # 启动期缺密钥不应让整个配置推荐不可用
            logger.warning(
                "pc.model_unavailable",
                agent_id=active_profile.id,
                error_code=exc.code,
            )
            chat_model = None
    return build_pc_graph(
        model=chat_model,
        profile=active_profile,
        checkpointer=checkpointer or get_checkpointer(),
    )


@lru_cache
def get_agent() -> CompiledStateGraph:
    """默认 Profile 的编译图；checkpointer 切换时由 checkpointer 模块清除缓存。"""
    return build_agent(profile=resolve_profile(None))


# (agent_id, provider, 裸模型名, credential_id) -> 编译后的图
MAX_RUNTIME_AGENT_CACHE_ENTRIES = 64
_RUNTIME_AGENT_CACHE: OrderedDict[
    tuple[str, str, str, str | None], CompiledStateGraph
] = OrderedDict()


def get_agent_for_runtime(
    runtime: ResolvedRuntime | None,
    *,
    agent_id: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> CompiledStateGraph:
    """按「Profile + 运行时模型」返回图；`None` 等价于进程默认模型。"""
    profile = resolve_profile(agent_id)
    cache_key: tuple[str, str, str, str | None]
    if runtime is None:
        if profile.id == get_settings().agent.default_profile:
            return get_agent()
        cache_key = (profile.id, "", "", None)
    else:
        cache_key = (
            profile.id,
            runtime.provider,
            runtime.model_key,
            runtime.credential_id,
        )

    cached = _RUNTIME_AGENT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    model = (
        None
        if runtime is None
        else get_chat_model(
            runtime.provider,
            runtime.model_key,
            runtime.credential_id,
            agent_id=profile.id,
            temperature=profile.model.temperature,
            max_tokens=profile.model.max_tokens,
            api_key=api_key,
            base_url=base_url or runtime.base_url,
        )
    )
    agent = build_agent(model=model, profile=profile)
    if len(_RUNTIME_AGENT_CACHE) >= MAX_RUNTIME_AGENT_CACHE_ENTRIES:
        _RUNTIME_AGENT_CACHE.popitem(last=False)
    _RUNTIME_AGENT_CACHE[cache_key] = agent
    return agent


def invalidate_credential(credential_id: str) -> None:
    """凭证撤销后丢弃对应图与模型实例，避免残留明文密钥被继续使用。"""
    for cache_key in [key for key in _RUNTIME_AGENT_CACHE if key[3] == credential_id]:
        _RUNTIME_AGENT_CACHE.pop(cache_key, None)
    invalidate_chat_credential(credential_id)


def clear_agent_cache() -> None:
    """配置、凭证或 checkpointer 变化后重建所有图与模型实例。"""
    _RUNTIME_AGENT_CACHE.clear()
    get_agent.cache_clear()
    clear_chat_model_cache()


__all__: list[str] = [
    "build_agent",
    "clear_agent_cache",
    "get_agent",
    "get_agent_for_runtime",
    "invalidate_credential",
]
