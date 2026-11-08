"""对话接口：以 SSE（Server-Sent Events）流式返回 Agent 输出。

为什么用 SSE 而不是一次性 JSON：
模型生成需要几秒到几十秒，一次性返回会让前端长时间空白；
SSE 基于普通 HTTP，服务端持续推送文本块，前端可做"打字机"效果。
WebSocket 适合双向高频通信，这里只需要服务端单向推送，SSE 更简单、也更容易穿透代理。

本路由只做传输：参数校验、鉴权依赖、幂等/锁的生命周期、SSE 编码与错误映射。
回合内的编排（偏好、RAG、工具事件、落库）在 `app/services/turn.py`；
流前的运行时解析、BYOK 凭证兑换与图装配统一在 `app/services/model_runtime.py`。

稳定性约束：
1. 同一 thread 串行执行（Redis 锁），避免两条消息并发写乱上下文；
2. 模型长时间无输出时下发心跳注释，防止代理或网关判定连接空闲；
3. 客户端断开时取消图执行，避免无效的模型调用与计费；
4. 整轮对话有总超时，超时下发 error 事件而不是无限挂起。
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field, SecretStr
from redis.exceptions import RedisError
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.agent.preferences import ChatPreferences
from app.agent.profiles import ProfileNotFoundError, resolve_profile
from app.api.v1.sse import SSE_SEPARATOR, StreamEncoder
from app.core.config import get_settings
from app.core.exceptions import AppError, RedisUnavailableError
from app.core.redis import is_redis_enabled
from app.core.security import (
    CurrentUser,
    get_access_token,
    get_current_user,
    namespaced_thread_id,
)
from app.services.idempotency import (
    STATUS_DONE,
    idempotency_abort,
    idempotency_begin,
    idempotency_finish,
    idempotency_key,
    idempotency_read,
)
from app.services.lock import LockHandle, acquire_thread_lock
from app.services.model_resolver import ResolvedRuntime
from app.services.model_runtime import prepare_agent
from app.services.session_deletion import cancel_pending_deletion
from app.services.turn import TurnOutcome, TurnRequest, run_turn

router = APIRouter(prefix="/chat", tags=["chat"])
logger = structlog.get_logger(__name__)


class ChatRequest(BaseModel):
    """一次对话请求。

    thread_id 由前端维护（如 用户ID + 会话UUID），同一 ID 会接着历史上下文。
    preferences 是客户端声明的用户偏好，只影响本轮提示词与历史注入，
    不参与鉴权；缺省时保持现有行为。
    """

    message: str = Field(min_length=1, max_length=4000, description="用户输入")
    thread_id: str = Field(min_length=1, max_length=64, description="会话标识")
    # 单次覆盖模型；省略或 null 表示沿用会话默认（Auto）
    model: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9:_.-]*$",
        description="单次生效的模型完整引用，如 openai:gpt-4o-mini",
    )
    preferences: ChatPreferences | None = Field(
        default=None,
        description="客户端声明的用户偏好：指令、语言、风格、是否使用历史",
    )
    # 请求级人格选择；省略 = 使用服务端默认 Profile，未知 id 返回 404
    agent_id: str | None = Field(
        default=None,
        max_length=32,
        pattern=r"^[a-z][a-z0-9_-]{0,31}$",
        description="目标 Agent Profile 的 id，如 pc-config；省略时使用默认 Profile",
    )
    # 重新生成：替换最后一条回答，而不是追加一轮新对话
    regenerate: bool = Field(
        default=False,
        description="为 true 时重跑最后一条提问并替换上一条 AI 回答",
    )
    # 是否要求模型开启思考；缺省(null)沿用模型默认行为，true 时按目录能力位门控
    reasoning: bool | None = Field(
        default=None,
        description="是否要求模型开启思考；模型不支持时返回 422 capability_unsupported",
    )


def _chat_idempotency_key(user: CurrentUser, request_key: str | None) -> str | None:
    """把调用方提供的 Idempotency-Key 加上用户命名空间。

    幂等记录按用户隔离，避免不同用户使用相同 key 互相覆盖。
    Redis 未启用时不做幂等（流式响应本身无法重放，降级可接受）。
    """
    if request_key is None or not is_redis_enabled():
        return None
    return idempotency_key("chat", user.user_id, request_key)


async def _claim_idempotency(idempotency_record_key: str | None) -> None:
    """抢占幂等记录；重复请求直接 409，避免重复调用模型。

    Redis 故障时放弃幂等：此刻既写不进记录，也无法判断是否重复，
    直接返回 503 会让整条对话不可用；降级为「可能重复执行」更可接受。
    """
    if idempotency_record_key is None:
        return
    try:
        if await idempotency_begin(idempotency_record_key):
            return
        record = await idempotency_read(idempotency_record_key)
    except (RedisUnavailableError, RedisError) as exc:
        logger.warning("chat.idempotency_degraded", error_type=type(exc).__name__)
        return

    if record is not None and record.status == STATUS_DONE:
        raise AppError("该请求已处理完成，请勿重复提交", code="duplicate_request", status_code=409)
    raise AppError("相同请求正在处理中，请稍后重试", code="request_in_progress", status_code=409)


async def _finalize_idempotency(
    idempotency_record_key: str | None,
    payload: ChatRequest,
    is_completed: bool,
) -> None:
    """成功标记 done，失败或断开清理记录；收尾失败不能让响应报错。"""
    if idempotency_record_key is None:
        return
    try:
        if is_completed:
            await idempotency_finish(
                idempotency_record_key,
                {"thread_id": payload.thread_id},
            )
        else:
            await idempotency_abort(idempotency_record_key)
    except Exception as exc:
        logger.warning("chat.idempotency_finalize_failed", error_type=type(exc).__name__)


def _build_turn_request(
    payload: ChatRequest,
    user: CurrentUser,
    checkpoint_thread_id: str,
    graph: Any,
    runtime: ResolvedRuntime | None,
    user_token: str | None = None,
) -> TurnRequest:
    """把 HTTP 请求翻译成回合输入；两套 thread_id 各归其位。"""
    return TurnRequest(
        user_id=user.user_id,
        user_roles=tuple(user.roles),
        client_thread_id=payload.thread_id,
        checkpoint_thread_id=checkpoint_thread_id,
        message=payload.message,
        agent_id=payload.agent_id,
        preferences=payload.preferences,
        graph=graph,
        runtime=runtime,
        user_token=user_token,
        regenerate=payload.regenerate,
    )


async def _event_stream(
    payload: ChatRequest,
    user: CurrentUser,
    lock_handle: LockHandle | None,
    idempotency_record_key: str | None,
    graph: Any,
    runtime: ResolvedRuntime | None,
    user_token: str | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """传输层：迭代回合事件、编码成 SSE，并兜住超时/断开/异常。

    心跳由 `EventSourceResponse(ping=...)` 负责，本生成器只产出业务事件。
    回合内的钩子、工具上下文与落库由 `run_turn` 负责，这里只保留传输生命周期。
    """
    thread_id = namespaced_thread_id(user, payload.thread_id)
    encoder = StreamEncoder()
    outcome = TurnOutcome()
    encoder.enter()

    try:
        async for event in run_turn(
            _build_turn_request(
                payload, user, thread_id, graph, runtime, user_token
            ),
            outcome,
        ):
            yield encoder.encode(event.type, event.data)
    except TimeoutError:
        yield encoder.encode_timeout(thread_id)
    except asyncio.CancelledError:
        encoder.record_disconnect(thread_id)
        raise
    except Exception:
        yield encoder.encode_failure(thread_id)
    finally:
        encoder.exit()
        await _finalize_idempotency(idempotency_record_key, payload, outcome.completed)
        if lock_handle is not None:
            await lock_handle.release()


@router.post("/stream")
async def stream_chat(
    payload: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    access_token: SecretStr | None = Depends(get_access_token),
    request_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ] = None,
) -> EventSourceResponse:
    """流式对话接口（需登录）。

    可选 `Idempotency-Key` 请求头：重复提交时返回 409，避免重复调用模型。
    模型运行时开启时，先创建任务（额度在此扣减），失败在流建立前返回对应状态码。
    """
    thread_id = namespaced_thread_id(current_user, payload.thread_id)
    idempotency_record_key = _chat_idempotency_key(current_user, request_key)

    # 未知 agent_id 在建立流之前返回 404，避免占用幂等记录与线程锁
    try:
        profile = resolve_profile(payload.agent_id)
    except ProfileNotFoundError:
        raise AppError(
            "未找到指定的 Agent",
            code="agent_not_found",
            status_code=404,
        ) from None

    # 先做幂等抢占，再做耗时的锁等待，重复请求可以快速失败
    await _claim_idempotency(idempotency_record_key)

    lock_handle: LockHandle | None = None
    graph: Any = None
    runtime: ResolvedRuntime | None = None
    try:
        # 先抢锁再返回响应：抢不到时还能返回 409，而不是流里才报错
        lock_handle = await acquire_thread_lock(thread_id)
        # 同一 thread_id 被删除后又重新使用：取消未执行的检查点删除，避免误删新一轮状态
        await cancel_pending_deletion(current_user.user_id, payload.thread_id)
        # 解析运行时、兑换凭证与构图统一在门面内完成；
        # 额度超限、BYOK 缺少接入地址等问题都必须在流建立前以裸 JSON 返回
        prepared = await prepare_agent(
            profile,
            user_id=current_user.user_id,
            thread_id=payload.thread_id,
            access_token=access_token,
            requested_model=payload.model,
            client_idempotency_key=request_key,
            reasoning=payload.reasoning,
        )
        graph, runtime = prepared.graph, prepared.runtime
        user_token = (
            prepared.user_token.get_secret_value()
            if prepared.user_token is not None
            else None
        )
    except Exception:
        # 响应尚未开始，必须回滚已占用的资源，否则请求会白等一个锁周期
        if lock_handle is not None:
            await lock_handle.release()
        await _finalize_idempotency(idempotency_record_key, payload, is_completed=False)
        raise

    return EventSourceResponse(
        _event_stream(
            payload,
            current_user,
            lock_handle,
            idempotency_record_key,
            graph,
            runtime,
            user_token,
        ),
        # 心跳交给 sse-starlette：无业务事件时按此间隔下发注释行
        ping=get_settings().agent.sse_heartbeat_seconds,
        # 全项目统一 LF，与前端按 \n\n 切分事件块保持一致
        sep=SSE_SEPARATOR,
        headers={
            "Cache-Control": "no-cache",
            # 关闭 nginx 缓冲，否则文本会被攒成一整段再下发
            "X-Accel-Buffering": "no",
        },
    )
