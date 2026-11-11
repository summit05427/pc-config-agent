"""会话数据接口：会话列表、重命名、删除与历史消息。

数据来源：
- 会话列表来自 `session_meta` 表（Postgres；本地/测试为进程内字典），
  因此 Redis 未配置时列表依然可用；
- 历史消息来自 `session_messages` 表（每轮对话结束前写入），按窗口查询；
- 删除同时清理元数据与消息，检查点删除登记到 `session_deletion_tasks` 由后台重试，
  不再只做一次性尽力删除。
"""

from datetime import UTC, datetime
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field, SecretStr, field_validator

from app.agent.checkpointer import delete_thread_checkpoint
from app.agent.graph import get_agent
from app.agent.pc.hitl import interrupt_payload, is_interrupt_expired
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import (
    CurrentUser,
    get_access_token,
    get_current_user,
    namespaced_thread_id,
)
from app.services import control_plane, session_model
from app.services.lock import acquire_thread_lock
from app.services.session_deletion import enqueue_session_deletion
from app.services.session_model import SessionModelState
from app.services.session_store import get_session_store

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = structlog.get_logger(__name__)

DEFAULT_PAGE = 1
DEFAULT_SIZE = 20
MAX_SIZE = 100
MAX_TITLE_LENGTH = 80
# 与 Java 目录的 modelKey 格式保持一致；合法性最终由 Java 判定，这里只挡明显非法值
MODEL_KEY_PATTERN = r"^[a-z0-9][a-z0-9:_.-]*$"


class SessionModelRequest(BaseModel):
    """会话模型设置请求；`null` 表示恢复 Auto（平台默认模型）。"""

    model_key: str | None = Field(
        default=None,
        max_length=64,
        pattern=MODEL_KEY_PATTERN,
        description="完整模型引用，如 openai:gpt-4o-mini；null 表示 Auto",
    )


class SessionPinnedRequest(BaseModel):
    """置顶状态请求；true 置顶，false 取消置顶。"""

    pinned: bool


class SessionArchivedRequest(BaseModel):
    """归档状态请求；true 归档，false 恢复。"""

    archived: bool


class SessionRenameRequest(BaseModel):
    """重命名请求；先 trim 再校验长度，保证「空白包裹」不会误判超长。"""

    title: str

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """去首尾空白；纯空白与超长都在这里拒绝，返回 422 `validation_error`。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("标题不能为空白")
        if len(normalized) > MAX_TITLE_LENGTH:
            raise ValueError(f"标题不能超过 {MAX_TITLE_LENGTH} 个字符")
        return normalized


def _validate_pagination(page: int, size: int) -> None:
    """分页越界直接返回 400。

    与 Java 的 PageQuery 保持同一语义：框架默认会把约束失败映射成 422，
    跨端契约要求分页越界统一为 400，因此这里显式校验。
    """
    if page < 1 or size < 1 or size > MAX_SIZE:
        raise AppError(
            f"分页参数不合法：page 需 ≥ 1，size 需在 1..{MAX_SIZE} 之间",
            code="invalid_pagination",
            status_code=400,
        )


def _to_iso(timestamp: datetime) -> str:
    """统一为 UTC ISO-8601，与其他服务的时间格式保持一致。"""
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _newest_assistant_index(
    items: list[dict[str, Any]], order: Literal["asc", "desc"]
) -> int | None:
    """最新一条助手消息在返回窗口中的下标；desc 时窗口首条即最新。"""
    if order == "desc":
        return next(
            (index for index, item in enumerate(items) if item.get("role") == "assistant"),
            None,
        )
    for index in range(len(items) - 1, -1, -1):
        if items[index].get("role") == "assistant":
            return index
    return None


async def _attach_pending_hitl(
    items: list[dict[str, Any]],
    total: int,
    page: int,
    size: int,
    order: Literal["asc", "desc"],
    checkpoint_thread_id: str,
) -> None:
    """把待恢复的 HITL 中断附加到最新一条助手消息。

    中断只存在于 checkpointer、不落 `session_messages`；刷新页面后前端靠这个字段
    重建表单。只附加「未过期」且窗口确实包含最新消息的中断，避免旧分页出现幽灵表单。
    历史读取不能因旁路状态失败而报错，因此异常只记录日志。
    """
    settings = get_settings()
    if not settings.hitl.enabled or not items:
        return
    if order == "desc" and page != 1:
        return
    if order == "asc" and (page - 1) * size + len(items) < total:
        return

    index = _newest_assistant_index(items, order)
    if index is None:
        return

    try:
        snapshot = await get_agent().aget_state(
            {"configurable": {"thread_id": checkpoint_thread_id}}
        )
    except Exception as exc:
        logger.warning("sessions.hitl_state_read_failed", error_type=type(exc).__name__)
        return

    interrupts = list(getattr(snapshot, "interrupts", ()) or ())
    if not interrupts:
        return
    if is_interrupt_expired(
        getattr(snapshot, "created_at", None),
        settings.hitl.interrupt_ttl_seconds,
    ):
        return
    payload = interrupt_payload(interrupts[0])
    if payload is not None:
        items[index] = {**items[index], "hitl": payload}


async def _delete_checkpoint_now(thread_id: str) -> None:
    """墓碑入队失败时的兜底：立即尝试一次删除。

    入队失败通常意味着数据库不可用，此时只能退回旧行为（尽力而为），
    宁可能删不掉也不能让删除接口失败——业务数据已经清理完成。
    """
    try:
        await delete_thread_checkpoint(thread_id)
    except Exception as exc:
        logger.warning("sessions.checkpoint_delete_failed", error_type=type(exc).__name__)


def _model_payload(
    availability: control_plane.ModelAvailability,
) -> dict[str, Any]:
    """把 Java 返回的可用性结果转成前端可直接展示的模型信息。"""
    return {
        "provider": availability.provider,
        "model_key": availability.model_key,
        "display_name": availability.display_name,
        "capabilities": list(availability.capabilities),
        "context_window": availability.context_window,
    }


def _session_model_response(state: SessionModelState) -> dict[str, Any]:
    """会话模型配置响应；`model_key` 为 null 即 Auto。"""
    return {
        "thread_id": state.thread_id,
        "model_key": state.model_key,
        "effective": "explicit" if state.model_key else "auto",
        "model": (
            _model_payload(state.availability)
            if state.availability is not None
            else None
        ),
        "updated_at": (
            _to_iso(state.updated_at) if state.updated_at is not None else None
        ),
    }


def _session_state_payload(entry: Any) -> dict[str, Any]:
    """会话状态响应：置顶/归档开关共用同一结构。"""
    return {
        "thread_id": entry.thread_id,
        "is_pinned": entry.is_pinned,
        "is_archived": entry.is_archived,
        "updated_at": _to_iso(entry.updated_at) if entry.updated_at is not None else None,
    }


@router.get("", summary="当前用户的会话列表")
async def list_user_sessions(
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(default=DEFAULT_PAGE),
    size: int = Query(default=DEFAULT_SIZE),
    archived: bool = Query(default=False),
) -> dict[str, Any]:
    """按置顶优先、最近活跃倒序返回会话；`title` 为空表示尚未生成标题。"""
    _validate_pagination(page, size)
    entries, total = await get_session_store().list_sessions(
        current_user.user_id, page, size, archived
    )
    return {
        "list": [
            {
                "thread_id": entry.thread_id,
                "title": entry.title,
                "model_key": entry.model_key,
                "last_active_at": _to_iso(entry.last_active_at),
                "is_pinned": entry.is_pinned,
                "is_archived": entry.is_archived,
            }
            for entry in entries
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@router.put("/{thread_id}/pin", summary="置顶或取消置顶会话")
async def set_session_pinned(
    payload: SessionPinnedRequest,
    thread_id: str = Path(min_length=1, max_length=64),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """只影响列表排序；归档会话的置顶状态保留，恢复后继续生效。"""
    entry = await get_session_store().set_pinned(
        current_user.user_id, thread_id, payload.pinned
    )
    if entry is None:
        raise AppError("会话不存在", code="session_not_found", status_code=404)
    return _session_state_payload(entry)


@router.put("/{thread_id}/archive", summary="归档或恢复会话")
async def set_session_archived(
    payload: SessionArchivedRequest,
    thread_id: str = Path(min_length=1, max_length=64),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """归档后会话从默认列表移除，可通过 `archived=true` 查询并恢复。"""
    entry = await get_session_store().set_archived(
        current_user.user_id, thread_id, payload.archived
    )
    if entry is None:
        raise AppError("会话不存在", code="session_not_found", status_code=404)
    return _session_state_payload(entry)


@router.patch("/{thread_id}", summary="重命名会话")
async def rename_user_session(
    payload: SessionRenameRequest,
    thread_id: str = Path(min_length=1, max_length=64),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """重命名当前用户名下的会话；不存在或不属于当前用户统一返回 404。"""
    if not await get_session_store().rename_session(
        current_user.user_id, thread_id, payload.title
    ):
        raise AppError("会话不存在", code="session_not_found", status_code=404)
    return {"thread_id": thread_id, "title": payload.title}


@router.put("/{thread_id}/model", summary="设置会话模型")
async def set_session_model(
    payload: SessionModelRequest,
    thread_id: str = Path(min_length=1, max_length=64),
    current_user: CurrentUser = Depends(get_current_user),
    access_token: SecretStr | None = Depends(get_access_token),
) -> dict[str, Any]:
    """设置会话级模型选择；校验顺序与幂等语义由 service 层保证。"""
    state = await session_model.set_session_model(
        current_user.user_id,
        thread_id,
        payload.model_key,
        access_token,
    )
    return _session_model_response(state)


@router.delete("/{thread_id}", status_code=204, summary="删除会话")
async def delete_user_session(
    thread_id: str = Path(min_length=1, max_length=64),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """删除会话元数据、消息与 checkpointer 状态。

    先抢会话锁：删除与生成并发时，避免「生成中写入、删除后残留半轮消息」。
    检查点删除登记为墓碑，由后台按退避重试，失败记录可在指标与表中追踪。
    """
    checkpoint_thread_id = namespaced_thread_id(current_user, thread_id)
    lock_handle = await acquire_thread_lock(checkpoint_thread_id)
    try:
        if not await get_session_store().delete_session(current_user.user_id, thread_id):
            raise AppError("会话不存在", code="session_not_found", status_code=404)
        queued = await enqueue_session_deletion(
            current_user.user_id, thread_id, checkpoint_thread_id
        )
        if not queued:
            await _delete_checkpoint_now(checkpoint_thread_id)
    finally:
        if lock_handle is not None:
            await lock_handle.release()


@router.get("/{thread_id}/messages", summary="会话历史消息")
async def get_session_messages(
    thread_id: str = Path(min_length=1, max_length=64),
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(default=DEFAULT_PAGE),
    size: int = Query(default=DEFAULT_SIZE),
    order: Literal["asc", "desc"] = Query(default="asc"),
) -> dict[str, Any]:
    """按窗口读取指定会话的消息。

    `order=desc` 供长会话从最新一页向前翻；返回结果仍按请求方向排列，
    由调用方决定是否反转后渲染。
    归属隔离不靠字符串前缀，而是查询条件里的 `user_id`：
    其他用户即使猜到 thread_id，也只会查到自己的空结果。
    """
    _validate_pagination(page, size)
    items, total = await get_session_store().read_messages(
        current_user.user_id, thread_id, page, size, order
    )
    if total == 0:
        raise AppError("会话不存在或尚无消息", code="session_not_found", status_code=404)

    await _attach_pending_hitl(
        items,
        total,
        page,
        size,
        order,
        namespaced_thread_id(current_user, thread_id),
    )

    return {
        "thread_id": thread_id,
        "list": items,
        "total": total,
        "page": page,
        "size": size,
        "order": order,
    }
