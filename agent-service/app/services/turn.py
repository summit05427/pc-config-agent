"""回合执行模块：从一条用户输入到一次完整回复的全部编排。

路由只负责 HTTP/SSE 传输，这里负责：
1. 偏好渲染、RAG 检索与引用、生命周期钩子；
2. 把 LangGraph 的运行过程翻译成回合事件（token / tool_call / tool_result / citations）；
3. 在发 `done` 之前把本轮消息落库；
4. 保证工具上下文与流结束钩子在异常、超时、取消时都能归位。

把这一段从路由里抽出来的原因：路由同时承担协议细节与业务编排时，
任何一处改动都要在几百行的生成器里反复对照超时、幂等与锁的边界。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from app.agent.hooks import (
    HookBlockedError,
    HookContext,
    HookPoint,
    run_hooks,
    should_buffer_model_output,
)
from app.agent.preferences import ChatPreferences, build_preference_prompt
from app.agent.tool_context import ToolTurn
from app.core.config import get_settings
from app.rag import Citation, RetrievalRequest, build_retrieval_prompt, get_retriever
from app.services.model_resolver import ResolvedRuntime
from app.services.session_store import get_session_store

logger = structlog.get_logger(__name__)

# 自动标题取首条用户消息的前 N 个字符；标题列上限 80，留出余量给手动重命名
AUTO_TITLE_LENGTH = 40

TurnEventType = Literal["token", "reasoning", "tool_call", "tool_result", "citations", "done"]


@dataclass(frozen=True)
class TurnEvent:
    """回合内的一个可见事件；由传输层编码成 SSE 事件。"""

    type: TurnEventType
    data: dict[str, Any]


@dataclass(frozen=True)
class TurnRequest:
    """执行一次回合所需的全部输入。

    `client_thread_id` 与 `checkpoint_thread_id` 不能混用：前者用于业务表与回传，
    后者用于 checkpointer；两者由调用方按 `namespaced_thread_id` 派生。
    """

    user_id: str
    user_roles: tuple[str, ...]
    client_thread_id: str
    checkpoint_thread_id: str
    message: str
    agent_id: str | None
    preferences: ChatPreferences | None
    graph: Any
    runtime: ResolvedRuntime | None = None
    # 重新生成：删除最后一条 AI 回答后重跑模型，而不是追加一轮新对话
    regenerate: bool = False


@dataclass
class TurnOutcome:
    """回合结果，由调用方在流结束后读取。

    `completed` 在模型生成结束时就置位，而不是等 `done` 发出：
    客户端在落库阶段断开不应把本轮判为失败。
    """

    completed: bool = False


async def run_turn(request: TurnRequest, outcome: TurnOutcome) -> AsyncIterator[TurnEvent]:
    """执行一次完整回合，按发生顺序产出可见事件。

    异常不在这里吞掉：超时、取消与未预期错误交给传输层映射成 SSE error，
    但工具上下文与结束钩子必须在这里归位，避免泄漏到后续请求。
    """
    settings = get_settings()
    stream_error: str | None = None
    # 角色与调用配额成对进入/退出：任何异常或取消都不会只复位一半
    with ToolTurn(request.user_roles):
        try:
            # 请求级钩子：阻断时由传输层转成流内 error，不改动已建立的 200 响应
            await run_hooks(_hook_context(HookPoint.BEFORE_REQUEST, request))
            async with asyncio.timeout(settings.agent.request_timeout_seconds):
                async for event in _turn_events(request, outcome):
                    yield event
        except TimeoutError as exc:
            stream_error = type(exc).__name__
            raise
        except asyncio.CancelledError as exc:
            stream_error = type(exc).__name__
            raise
        except Exception as exc:
            stream_error = type(exc).__name__
            raise
        finally:
            await _notify_stream_end(request, stream_error)


async def _turn_events(request: TurnRequest, outcome: TurnOutcome) -> AsyncIterator[TurnEvent]:
    """生成回合内的业务事件；超时已由调用方套好。"""
    preference_prompt = build_preference_prompt(request.preferences)
    # 未携带偏好时 use_history 回到默认 True，防止同一 thread 继承上一轮的 False
    use_history = request.preferences.use_history if request.preferences else True

    citations: list[Citation] = []
    # RAG 默认关闭；开启时先按权限过滤检索，再把引用与提示词片段带进本轮
    if get_settings().rag.enabled:
        citations = await _retrieve_citations(
            request.message,
            request.user_id,
            request.user_roles,
        )
        if citations:
            yield TurnEvent(
                "citations",
                {"citations": [citation.to_payload() for citation in citations]},
            )
    turn_prompt = _compose_turn_prompt(preference_prompt, build_retrieval_prompt(citations))

    async for event in _agent_events(request, turn_prompt, use_history):
        yield event

    # 生成已结束：此后即使客户端在落库阶段断开，本轮也应记为完成
    outcome.completed = True
    # 先落库再发 done：前端收到 done 后立即查询历史即可看到本轮消息
    await _persist_turn(request)
    # 回传客户端自己的 thread_id，不暴露服务端命名空间
    yield TurnEvent("done", {"thread_id": request.client_thread_id})


async def _agent_events(
    request: TurnRequest,
    turn_prompt: str | None,
    use_history: bool,
) -> AsyncIterator[TurnEvent]:
    """把图的 messages / updates 流翻译成回合事件。

    偏好字段每轮都显式传入：即使本轮不携带偏好，也要把旧值覆盖为默认，
    避免同一 thread 上一轮的偏好残留。

    运行时放在 `configurable` 而不是 AgentState：task 元数据不应被 checkpointer
    持久化，也不应出现在历史消息接口里。
    """
    # 存在阻断型 after_model 钩子时先缓冲文本：钩子未通过前不能把内容推给客户端
    buffer_output = should_buffer_model_output()
    pending_events: list[TurnEvent] = []
    turn_messages = await _turn_input_messages(request)
    async for mode, chunk in request.graph.astream(
        {
            "messages": turn_messages,
            "preference_prompt": turn_prompt,
            "use_history": use_history,
        },
        _agent_config(request),
        # 必须是 list：LangGraph 只把 list 识别为多模式，tuple 会被当成单一模式
        # mypy 无法从 list 字面量推断 Literal 序列，属于上游重载标注问题
        stream_mode=["messages", "updates"],  # type: ignore[call-overload]
    ):
        if mode == "messages":
            events = _chunk_events(chunk, buffer_output, pending_events)
        else:
            events = _update_events(chunk, pending_events)
        for event in events:
            yield event


async def _turn_input_messages(request: TurnRequest) -> list[Any]:
    """构造本轮图输入。

    重新生成时把最后一条 AI 回答从检查点状态里移除，模型会基于
    「用户提问 + 已有工具结果」重新生成；找不到可替换回答时降级为普通回合。
    """
    if not request.regenerate:
        return [HumanMessage(content=request.message)]

    try:
        snapshot = await request.graph.aget_state(_agent_config(request))
    except Exception as exc:
        logger.warning("turn.regenerate_state_failed", error_type=type(exc).__name__)
        return [HumanMessage(content=request.message)]

    messages = (snapshot.values or {}).get("messages") or []
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.id:
            return [RemoveMessage(id=str(message.id))]
    return [HumanMessage(content=request.message)]


def _chunk_events(
    chunk: Any,
    buffer_output: bool,
    pending_events: list[TurnEvent],
) -> list[TurnEvent]:
    """messages 模式：思考内容与正文分成独立事件，可缓冲时等钩子通过后再放行。"""
    message_chunk, _metadata = chunk
    events: list[TurnEvent] = []
    # LiteLLM 把各厂商的思考内容统一成 reasoning_content，由 llm.py 的
    # ReasoningChatOpenAI 保留到 additional_kwargs，这里不再区分 Provider
    reasoning = (getattr(message_chunk, "additional_kwargs", None) or {}).get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        events.append(TurnEvent("reasoning", {"text": reasoning}))
    content = message_chunk.content
    if isinstance(content, str) and content:
        events.append(TurnEvent("token", {"text": content}))
    if not events:
        return []
    if buffer_output:
        # 思考内容必须和正文一起缓冲：否则阻断型钩子可以通过 reasoning 提前泄漏内容
        pending_events.extend(events)
        return []
    return events


def _update_events(
    chunk: dict[str, Any],
    pending_events: list[TurnEvent],
) -> list[TurnEvent]:
    """updates 模式：放行已缓冲事件，并翻译工具调用与工具结果。"""
    events: list[TurnEvent] = []
    for node, update in chunk.items():
        if node == "model" and pending_events:
            # 节点已返回说明 after_model 钩子通过，此时才放行本轮缓冲
            events.extend(pending_events)
            pending_events.clear()
        events.extend(_node_message_events(node, update.get("messages", [])))
    return events


def _node_message_events(node: str, messages: list[Any]) -> list[TurnEvent]:
    """把节点产出的消息翻译成 tool_call / tool_result 事件。"""
    events: list[TurnEvent] = []
    for node_message in messages:
        tool_calls = getattr(node_message, "tool_calls", None)
        if node == "model" and tool_calls:
            events.extend(
                TurnEvent("tool_call", {"name": call["name"], "args": call["args"]})
                for call in tool_calls
            )
        elif isinstance(node_message, ToolMessage):
            events.append(
                TurnEvent(
                    "tool_result",
                    {"name": node_message.name, "preview": str(node_message.content)[:200]},
                )
            )
    return events


def _agent_config(request: TurnRequest) -> dict[str, Any]:
    """组装图配置；运行时只放 configurable，不进入可持久化的 AgentState。"""
    config: dict[str, Any] = {
        "configurable": {"thread_id": request.checkpoint_thread_id},
        # 防止模型反复调用工具；超限时 LangGraph 抛错，由外层转成 error 事件
        "recursion_limit": get_settings().agent.recursion_limit,
    }
    if request.runtime is not None:
        config["configurable"]["model_runtime"] = request.runtime
    return config


async def _persist_turn(request: TurnRequest) -> None:
    """把本轮结束后的完整消息写入会话存储，供历史接口按窗口查询。

    历史接口不读 checkpointer，所以必须在发 `done` 之前完成写入。
    写入失败只记 warning：对话本身已经成功，旁路存储不应影响用户。

    消息从本轮实际使用的图读取：默认图与 Profile 图各自持有 checkpointer，
    用默认图读 Profile 会话会拿到过期快照。
    """
    try:
        snapshot = await request.graph.aget_state(
            {"configurable": {"thread_id": request.checkpoint_thread_id}}
        )
        messages = (snapshot.values or {}).get("messages") or []
        # 消息与活跃时间由 store 在同一事务里写入：列表与标题不再依赖 Redis 索引
        await get_session_store().record_turn(
            request.user_id,
            request.client_thread_id,
            messages,
            _derive_title(messages),
            replace_existing=request.regenerate,
        )
    except Exception as exc:
        # 周期性失败会反复出现，只记录类型，不打印堆栈
        logger.warning("turn.message_persist_failed", error_type=type(exc).__name__)


def _derive_title(messages: list[Any]) -> str | None:
    """取首条用户消息前 40 个字符作为会话标题；没有用户消息时返回 None。

    标题只用于列表展示，截断即可，不参与检索；空内容不写标题，
    避免把「空白会话」显示成一段空白。
    """
    for message in messages:
        if not isinstance(message, HumanMessage):
            continue
        content = message.content if isinstance(message.content, str) else str(message.content)
        title = content.strip()
        return title[:AUTO_TITLE_LENGTH] or None
    return None


async def _retrieve_citations(
    query: str,
    user_id: str,
    roles: tuple[str, ...],
) -> list[Citation]:
    """检索失败按「无引用」降级：RAG 是增强能力，不能阻断对话。"""
    try:
        return await get_retriever().retrieve(
            RetrievalRequest(
                query=query,
                user_id=user_id,
                # roles 即权限范围；检索器必须在检索前据此过滤，禁止先查后筛
                roles=roles,
                limit=get_settings().rag.top_k,
            )
        )
    except Exception as exc:
        logger.warning("rag.retrieve_failed", error_type=type(exc).__name__)
        return []


def _compose_turn_prompt(
    preference_prompt: str | None,
    retrieval_prompt: str | None,
) -> str | None:
    """偏好与检索片段都只作用于本轮，合并不是持久化内容。"""
    parts = [part for part in (preference_prompt, retrieval_prompt) if part]
    return "\n\n".join(parts) or None


def _hook_context(
    point: HookPoint,
    request: TurnRequest,
    error_type: str | None = None,
) -> HookContext:
    """构造钩子上下文；只放调用方明确提供的字段，不夹带请求头或密钥。"""
    return HookContext(
        point=point,
        thread_id=request.client_thread_id,
        user_id=request.user_id,
        agent_id=request.agent_id,
        error_type=error_type,
    )


async def _notify_stream_end(request: TurnRequest, error_type: str | None) -> None:
    """流结束钩子只做观测：阻断也不能破坏工具上下文复位。"""
    try:
        await run_hooks(_hook_context(HookPoint.ON_STREAM_END, request, error_type))
    except HookBlockedError:
        logger.warning("turn.stream_end_hook_blocked", thread_id=request.checkpoint_thread_id)
