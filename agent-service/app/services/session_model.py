"""会话级模型选择编排：归属校验 → 目录/可用性校验 → 写库。

为什么放在 service 层：
1. 路由只做参数接收与响应组装，写库顺序和「校验失败不落库」的规则属于业务约束；
2. 未来会话级偏好（温度、系统提示词）复用同一入口，避免每加一项就在路由里再抄一遍流程；
3. 控制面调用失败到 `AppError` 的映射只在这里发生，接口层不感知上游细节。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import SecretStr

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.services import control_plane
from app.services.control_plane import ControlPlaneError
from app.services.session_store import get_session_store


@dataclass(frozen=True)
class SessionModelState:
    """一次模型设置后的稳定结果；`availability` 只在显式模型时非空。"""

    thread_id: str
    model_key: str | None
    updated_at: datetime | None
    availability: control_plane.ModelAvailability | None = None


async def _check_model_access(
    access_token: SecretStr | None,
    model_key: str,
) -> control_plane.ModelAvailability:
    """经 Java 校验模型目录与用户可用性；失败直接抛业务异常，调用方不得写库。"""
    if not get_settings().model_runtime.enabled:
        raise AppError("模型运行时未启用", code="model_runtime_disabled", status_code=503)
    if access_token is None:
        # 用户身份由访问令牌承载；缺失时无法判断可用性，必须在流/写库前拒绝
        raise AppError("缺少访问令牌", code="unauthorized", status_code=401)
    try:
        return await control_plane.get_control_plane_client().check_model_access(
            user_token=access_token.get_secret_value(),
            model_key=model_key,
        )
    except ControlPlaneError as error:
        raise control_plane.to_app_error(error) from None


async def set_session_model(
    user_id: str,
    thread_id: str,
    model_key: str | None,
    access_token: SecretStr | None,
) -> SessionModelState:
    """幂等设置会话模型；重复提交相同值不改 `updated_at`，任何校验失败都不写库。"""
    store = get_session_store()
    meta = await store.get_session(user_id, thread_id)
    if meta is None:
        raise AppError("会话不存在", code="session_not_found", status_code=404)

    if model_key is None:
        # 恢复 Auto：不需要目录校验；已是 Auto 时保持幂等
        if meta.model_key is None:
            return SessionModelState(thread_id, None, meta.updated_at)
        updated_at = await store.set_model_key(user_id, thread_id, None)
        return SessionModelState(thread_id, None, updated_at)

    availability = await _check_model_access(access_token, model_key)
    if meta.model_key == model_key:
        return SessionModelState(thread_id, model_key, meta.updated_at, availability)
    updated_at = await store.set_model_key(user_id, thread_id, model_key)
    if updated_at is None:
        # 校验期间会话被删除：按不存在处理，不凭空造一条记录
        raise AppError("会话不存在", code="session_not_found", status_code=404)
    return SessionModelState(thread_id, model_key, updated_at, availability)
