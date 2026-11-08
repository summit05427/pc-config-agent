"""模型运行时解析：把一次请求映射成具体模型与任务。

解析顺序（docs/model-runtime-architecture.md §10.1）：
请求级 `model`（单次覆盖） > 会话 `session_meta.model_key` > Auto（交给 Java 选默认）。

失败策略（§10.3）：
- 控制面不可达时，仅 Auto（未指定模型）降级到进程默认模型并记 warning；
- 用户显式指定了模型（请求级或会话级）时，控制面不可达直接报 503，禁止偷换模型；
- 额度超限、模型不可用、能力不支持等确定性错误直接抛出，流开始前返回对应状态码；
- BYOK 任务必须先兑换一次性凭证（`resolve_credential`），兑换失败同样在流开始前返回 401/409，
  绝不退回平台托管模型。
"""

from dataclasses import dataclass, field
from hashlib import sha256
from uuid import uuid4

import structlog

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.services import control_plane
from app.services.control_plane import ControlPlaneError
from app.services.session_store import get_session_store

logger = structlog.get_logger(__name__)

# 平台托管凭证使用服务端的统一网关与密钥；BYOK 用用户自己的凭证与接入地址
CREDENTIAL_SOURCE_MANAGED = "MANAGED"
CREDENTIAL_SOURCE_BYOK = "BYOK"
DEFAULT_MODEL_ROLE = "conversation"

# Java 侧幂等键长度上限 64；SHA-256 截断到 32 位十六进制足够避免碰撞且留出余量
TASK_IDEMPOTENCY_KEY_LENGTH = 32
# 确定性错误码：必须原样抛给调用方，不允许降级
_PROPAGATED_CODES = frozenset(
    {
        control_plane.QUOTA_EXCEEDED,
        control_plane.MODEL_NOT_AVAILABLE,
        control_plane.CAPABILITY_UNSUPPORTED,
        control_plane.UPSTREAM_ERROR,
        control_plane.IDEMPOTENCY_CONFLICT,
    }
)


@dataclass(frozen=True)
class ResolvedRuntime:
    """一次请求实际使用的模型与任务信息，不含任何凭证。"""

    task_id: str
    provider: str
    model_key: str
    credential_source: str
    credential_id: str | None = None
    # BYOK 接入地址快照；MANAGED 时为空，使用平台网关
    base_url: str | None = None
    model_role: str = DEFAULT_MODEL_ROLE
    # 目录能力位：请求侧能力门控（如 reasoning）只依据这里，不猜 Provider
    capabilities: tuple[str, ...] = ()

    @property
    def is_byok(self) -> bool:
        return self.credential_source == CREDENTIAL_SOURCE_BYOK


@dataclass(frozen=True)
class ResolvedCredential:
    """BYOK 任务的明文凭证；只在单次请求内存中存在。

    `api_key` 用 `repr=False` 排除，避免对象被日志或异常打印时泄露密钥。
    """

    api_key: str = field(repr=False)
    base_url: str | None = None


def _to_app_error(error: ControlPlaneError) -> AppError:
    """把控制面错误转成统一业务异常（含额度超限负载）。"""
    return control_plane.to_app_error(error)


def derive_task_idempotency_key(
    user_id: str, thread_id: str, client_key: str | None
) -> str:
    """派生模型任务幂等键。

    有客户端键时按「用户 + 会话 + 客户端键」做 SHA-256 截断：同一轮对话的重复
    提交（网络重试、前端重发）得到相同键，由 Java 复用既有任务，额度只扣一次。
    无客户端键时退化为一次性随机键，仅保证单次调用内部不重复建任务。
    """
    if client_key is None:
        return uuid4().hex
    material = f"{user_id}|{thread_id}|{client_key}"
    return sha256(material.encode("utf-8")).hexdigest()[:TASK_IDEMPOTENCY_KEY_LENGTH]


async def resolve_runtime(
    *,
    user_id: str,
    thread_id: str,
    user_token: str,
    requested_model: str | None,
    default_model: str | None = None,
    client_idempotency_key: str | None = None,
    settings: Settings | None = None,
    client: control_plane.ControlPlaneClient | None = None,
) -> ResolvedRuntime | None:
    """解析本次请求的运行时。

    模型优先级：请求 > 会话 > Profile 默认 > Auto。
    Profile 默认模型按「显式模型」处理：控制面不可达时不降级。

    :param default_model: Profile 声明的默认模型；仅在请求与会话都未指定时生效。
    :param client_idempotency_key: 客户端（前端）传入的 `Idempotency-Key`；
        用于派生模型任务幂等键，缺省时每次调用生成一次性键。
    :return: `ResolvedRuntime`；返回 `None` 表示沿用进程默认模型
             （模型运行时关闭，或控制面不可达时显式降级）。
    :raises AppError: 额度超限 429、模型不可用 403、能力不支持 422、
                      幂等键冲突 409、控制面异常 503、BYOK 未支持 503。
    """
    active_settings = settings or get_settings()
    if not active_settings.model_runtime.enabled:
        # 关闭时保持原有单模型逻辑，不发起任何出站请求
        return None

    model_key = (
        requested_model
        or await get_session_store().get_model_key(user_id, thread_id)
    )
    model_key = model_key or default_model

    active_client = client or control_plane.get_control_plane_client()
    try:
        task = await active_client.create_task(
            user_token=user_token,
            thread_id=thread_id,
            requested_model=model_key,
            idempotency_key=derive_task_idempotency_key(
                user_id, thread_id, client_idempotency_key
            ),
        )
    except ControlPlaneError as error:
        if error.code in _PROPAGATED_CODES:
            raise _to_app_error(error) from None
        if model_key is not None:
            # 显式指定模型时不能降级：控制面不可达意味着无法确认该模型可用，
            # 换成进程默认等于偷换用户选择，而前端仍会显示「已切换」。
            raise _to_app_error(error) from None
        logger.warning(
            "model_runtime.degraded",
            code=error.code,
            thread_id=thread_id,
            reason="control_plane_unavailable",
        )
        return None

    if task.credential_source == CREDENTIAL_SOURCE_BYOK and not task.credential_id:
        # Java 应保证 BYOK 任务必带 credential_id；缺失说明契约被破坏。
        # 此时若继续执行只能退回平台凭证，会让用户误以为自己用的是 BYOK 密钥。
        raise AppError(
            "BYOK 任务缺少凭证标识，请重新选择模型",
            code=control_plane.CREDENTIAL_REVOKED,
            status_code=401,
        )

    return ResolvedRuntime(
        task_id=task.task_id,
        provider=task.provider,
        model_key=task.model_key,
        credential_source=task.credential_source,
        credential_id=task.credential_id,
        base_url=task.base_url,
        capabilities=task.capabilities,
    )


async def resolve_credential(
    runtime: ResolvedRuntime,
    *,
    client: control_plane.ControlPlaneClient | None = None,
) -> ResolvedCredential | None:
    """BYOK 任务兑换一次性明文凭证；MANAGED 返回 `None`。

    兑换失败必须抛给调用方（流建立前 401/409）：凭证撤销、已兑换或任务不是 BYOK
    都意味着本次请求不能继续，降级成平台模型会造成费用归属错误。
    """
    if not runtime.is_byok:
        return None

    active_client = client or control_plane.get_control_plane_client()
    try:
        lease = await active_client.lease_credential(task_id=runtime.task_id)
    except ControlPlaneError as error:
        raise _to_app_error(error) from None

    # 日志只记录任务与凭证类型，绝不打印 secret
    logger.info(
        "model_runtime.credential_leased",
        task_id=runtime.task_id,
        credential_type=lease.credential_type,
        expires_in=lease.expires_in,
    )
    return ResolvedCredential(api_key=lease.secret, base_url=runtime.base_url)
