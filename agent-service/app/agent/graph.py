"""Agent 图：START → model ⇄ tools → END 的 ReAct 循环。

ReAct = Reason（模型思考）+ Act（调用工具）：
1. 模型看到工具描述，决定是否调用；
2. 有 tool_calls → 进入 tools 节点执行，结果作为 ToolMessage 追加回状态；
3. 回到模型，模型基于工具结果继续推理；
4. 没有 tool_calls → 结束。
"""

from collections import OrderedDict
from datetime import UTC, datetime
from functools import lru_cache
from time import perf_counter
from uuid import uuid4

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.checkpointer import get_checkpointer
from app.agent.context import (
    count_tokens,
    estimate_messages_tokens,
    select_current_turn,
    trim_to_token_budget,
)
from app.agent.hooks import HookContext, HookPoint, run_hooks
from app.agent.mcp import get_mcp_tool_specs
from app.agent.memory import (
    SUMMARY_MAX_TOKENS,
    LlmSummarizer,
    Summarizer,
    summarize_history,
)
from app.agent.profiles import (
    AgentProfile,
    resolve_profile,
    resolve_profile_tools,
)
from app.agent.prompts import compose_openui_system_prompt, load_system_prompt
from app.agent.state import AgentState
from app.core.config import get_settings
from app.core.metrics import LLM_TOKENS_TOTAL
from app.services.llm import clear_chat_model_cache, get_chat_model
from app.services.llm import invalidate_credential as invalidate_chat_credential
from app.services.model_resolver import ResolvedRuntime
from app.services.model_usage import STATUS_FAILURE, STATUS_SUCCESS, UsageRecord, record_usage

logger = structlog.get_logger(__name__)


def _extract_token_usage(message: BaseMessage) -> tuple[int | None, int | None]:
    """从响应里取 token 用量；Provider 未返回时是 `(None, None)` 而不是 0。

    用 0 冒充缺失会让用量统计永久偏低，且无法与「真的用了 0 token」区分。
    """
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        return None, None

    prompt_tokens = usage.get("input_tokens")
    completion_tokens = usage.get("output_tokens")
    return (
        int(prompt_tokens) if isinstance(prompt_tokens, int) else None,
        int(completion_tokens) if isinstance(completion_tokens, int) else None,
    )


def _record_token_usage(message: BaseMessage, model_label: str) -> tuple[int | None, int | None]:
    """记录一次模型调用的 token 用量。

    只记录数量，不记录内容；Provider 未返回 usage 时静默跳过，
    不能用 0 冒充，否则会掩盖统计缺失。
    """
    input_tokens, output_tokens = _extract_token_usage(message)
    if input_tokens:
        LLM_TOKENS_TOTAL.labels(model=model_label, type="input").inc(input_tokens)
    if output_tokens:
        LLM_TOKENS_TOTAL.labels(model=model_label, type="output").inc(output_tokens)
    logger.info(
        "agent.llm_usage",
        model=model_label,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return input_tokens, output_tokens


def _runtime_from_config(config: RunnableConfig | None) -> ResolvedRuntime | None:
    """从图配置里取运行时；缺省返回 None（沿用进程默认模型）。

    运行时信息不写入 AgentState，避免 task 元数据被 checkpointer 持久化。
    """
    if not config:
        return None
    runtime = (config.get("configurable") or {}).get("model_runtime")
    return runtime if isinstance(runtime, ResolvedRuntime) else None


def _utc_now_iso() -> str:
    """ISO-8601 UTC，与其他服务的接口格式保持一致。"""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _build_usage_record(
    runtime: ResolvedRuntime,
    invocation_id: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: int,
    error_type: str | None,
) -> UsageRecord:
    """组装一条上报记录；拿不到的字段保持 None，禁止填 0 或估算值。"""
    return UsageRecord(
        invocation_id=invocation_id,
        task_id=runtime.task_id,
        model_role=runtime.model_role,
        provider=runtime.provider,
        model_key=runtime.model_key,
        credential_source=runtime.credential_source,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        status=STATUS_FAILURE if error_type else STATUS_SUCCESS,
        error_type=error_type,
        occurred_at=_utc_now_iso(),
    )



async def _prepare_model_input(
    state: AgentState,
    base_prompt: str,
    raw_budget: int,
    summarizer: Summarizer | None = None,
) -> list[BaseMessage]:
    """按「基础提示词 + 本轮偏好」计算预算，必要时摘要早期历史，再裁剪。

    偏好每轮都可能变化，所以预算不能像基础提示词那样在编译期固定；
    系统提示词必须先扣掉，否则历史会挤占它自己的位置。
    摘要只在显式启用且历史超过阈值时发生，摘要结果不写回 AgentState。
    """
    prompt = base_prompt
    preference_prompt = state.get("preference_prompt")
    if preference_prompt:
        prompt = f"{base_prompt}\n\n{preference_prompt}"

    budget = max(1, raw_budget - count_tokens(prompt))

    history = state["messages"]
    # use_history=False 时只看本轮；状态本身不裁剪，本轮消息照常落库
    scoped = history if state.get("use_history", True) else select_current_turn(history)

    messages = scoped
    trigger_tokens = get_settings().agent.summary_trigger_tokens
    if summarizer is not None and estimate_messages_tokens(scoped) > trigger_tokens:
        messages = await summarize_history(
            scoped,
            keep_tokens=max(1, budget // 2),
            summarizer=summarizer,
            max_summary_tokens=max(1, min(SUMMARY_MAX_TOKENS, budget // 4)),
        )

    trimmed = trim_to_token_budget(messages, budget)
    if len(trimmed) < len(messages):
        # 只记录数量与估算值，不打印对话内容
        logger.info(
            "agent.context_trimmed",
            dropped_messages=len(messages) - len(trimmed),
            kept_tokens=estimate_messages_tokens(trimmed),
            budget=budget,
        )
    return [SystemMessage(content=prompt), *trimmed]


async def _report_model_usage(
    runtime: ResolvedRuntime | None,
    invocation_id: str,
    response: BaseMessage | None,
    latency_ms: int,
    error_type: str | None,
) -> None:
    """记录本次模型调用的 token 用量并写入 outbox；缺少运行时则跳过上报。

    写入 outbox 是单次 INSERT；发送由后台任务完成，失败不影响本轮 SSE。
    """
    model_label = runtime.model_key if runtime is not None else get_settings().llm.model
    if response is not None:
        prompt_tokens, completion_tokens = _record_token_usage(response, model_label)
    else:
        prompt_tokens, completion_tokens = None, None
    if runtime is not None:
        await record_usage(
            _build_usage_record(
                runtime,
                invocation_id,
                prompt_tokens,
                completion_tokens,
                latency_ms,
                error_type,
            )
        )


def _thread_id_from_config(config: RunnableConfig) -> str | None:
    """从图配置里取会话键；钩子只用于关联日志，不参与业务判断。"""
    configurable = config.get("configurable") or {}
    thread_id = configurable.get("thread_id")
    return thread_id if isinstance(thread_id, str) else None


def _message_text(message: BaseMessage) -> str | None:
    """模型输出文本；多模态内容不在此断言，避免把结构体塞进钩子。"""
    return message.content if isinstance(message.content, str) and message.content else None


def build_agent(
    model: BaseChatModel | None = None,
    tools: list[BaseTool] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    context_max_tokens: int | None = None,
    system_prompt: str | None = None,
    openui_enabled: bool | None = None,
    profile: AgentProfile | None = None,
) -> CompiledStateGraph:
    """组装并编译 ReAct Agent。

    model / tools / checkpointer / 上下文预算 / 系统提示词均可注入，
    便于测试时替换为假实现或按场景切换人格。
    显式参数优先；未提供时从 `profile`（缺省为默认 Profile）读取人格、
    工具集与上下文预算，Profile 未声明的项再回落到全局配置。
    `openui_enabled` 为 None 时读取配置；显式传入可避免测试依赖环境变量。
    """
    active_profile = profile if profile is not None else resolve_profile(None)
    # 工具集由 Profile 决定：省略 = 全部工具，[] = 不绑定任何工具；
    # MCP 工具作为运行时 ToolSpec 并入，未启用时为空，行为与接入前一致
    tool_list = (
        tools
        if tools is not None
        else resolve_profile_tools(active_profile, extra_specs=get_mcp_tool_specs())
    )
    settings = get_settings()
    raw_model = model or get_chat_model(
        agent_id=active_profile.id,
        temperature=active_profile.model.temperature,
        max_tokens=active_profile.model.max_tokens,
    )
    chat_model = raw_model.bind_tools(tool_list)
    # 摘要复用同一 Profile 的模型；关闭时不构造、不产生额外调用
    summarizer: Summarizer | None = None
    if settings.agent.summary_enabled:
        summarizer = LlmSummarizer(raw_model)
    base_prompt = (
        system_prompt
        if system_prompt is not None
        else load_system_prompt(active_profile.system_prompt)
    )
    # 关闭时完全不追加，保证提示词与接入前逐字节一致；
    # OpenUI 契约会先占用上下文预算，由 _prepare_model_input 统一扣减
    is_openui_enabled = (
        settings.openui.enabled if openui_enabled is None else openui_enabled
    )
    if is_openui_enabled:
        base_prompt = compose_openui_system_prompt(base_prompt)

    raw_budget = (
        context_max_tokens
        if context_max_tokens is not None
        else active_profile.context.max_tokens or get_settings().agent.context_max_tokens
    )

    async def call_model(state: AgentState, config: RunnableConfig) -> dict:
        """模型节点：基于裁剪后的历史决定"调用工具"还是"直接回答"。

        偏好片段随请求变化，所以不能像基础提示词那样在编译期固定：
        每轮按「基础提示词 + 偏好」重新计算预算。

        每次真实模型调用（含工具循环中的每一次）都生成独立 `invocation_id`，
        用同一个 ID 重试上报才算「同一次调用」，否则会重复计费。
        """
        model_input = await _prepare_model_input(
            state, base_prompt, raw_budget, summarizer
        )
        thread_id = _thread_id_from_config(config)
        # 阻断钩子在这里停下本轮，不会产生模型调用费用
        await run_hooks(
            HookContext(
                point=HookPoint.BEFORE_MODEL,
                thread_id=thread_id,
                agent_id=active_profile.id,
            )
        )

        runtime = _runtime_from_config(config)
        invocation_id = str(uuid4())
        started_at = perf_counter()
        response: BaseMessage | None = None
        error_type: str | None = None
        try:
            response = await chat_model.ainvoke(model_input)
        except Exception as exc:
            # 只记录类型：异常文本可能包含上游 URL、密钥片段或对话内容
            error_type = type(exc).__name__
            raise
        finally:
            latency_ms = int((perf_counter() - started_at) * 1000)
            await _report_model_usage(runtime, invocation_id, response, latency_ms, error_type)

        if response is not None:
            # 输出审核等阻断钩子在这里失败，本轮以 error 事件结束
            await run_hooks(
                HookContext(
                    point=HookPoint.AFTER_MODEL,
                    thread_id=thread_id,
                    agent_id=active_profile.id,
                    text=_message_text(response),
                )
            )

        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("model", call_model)
    graph.add_node("tools", ToolNode(tool_list))

    graph.add_edge(START, "model")
    # 条件边：最后一条消息含 tool_calls → tools，否则 → END
    graph.add_conditional_edges("model", tools_condition)
    graph.add_edge("tools", "model")

    # 默认使用当前生效的 checkpointer（postgres 或 memory）
    return graph.compile(checkpointer=checkpointer or get_checkpointer())


@lru_cache
def get_agent() -> CompiledStateGraph:
    """默认 Profile 的编译图；checkpointer 切换时由 checkpointer 模块清除缓存。"""
    # 不能调用 get_agent_for_runtime(None)：默认 Profile 分支会回指 get_agent，
    # 直接构图避免无限递归
    return build_agent(profile=resolve_profile(None))


# (agent_id, provider, 裸模型名, credential_id) -> 编译后的图
# 有界 LRU：BYOK 实例按凭证增长且内部持有明文密钥，无上限会随用户数线性泄漏内存
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
    """按「Profile + 运行时模型」返回图；`None` 等价于进程默认模型。

    模型切换必须真正更换实例：缓存键包含 agent_id、provider、模型名与凭证标识，
    不同 Profile 的人格/温度不同，不参与缓存键会互相串扰。
    `api_key` 只在 BYOK 首次装配时使用，命中缓存后无需再次兑换。
    """
    profile = resolve_profile(agent_id)
    cache_key: tuple[str, str, str, str | None]
    if runtime is None:
        # 默认 Profile + 进程默认模型：沿用 lru_cache 的默认图，保持旧调用路径
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
        # 淘汰最早使用的图；其模型实例仍在 llm 缓存里，下次使用会重新装配
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

