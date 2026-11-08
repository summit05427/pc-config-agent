"""Java 控制面（/internal/v1）客户端。

为什么单独一层：
1. 服务令牌换取、缓存与单飞刷新属于基础设施细节，路由与图都不该关心；
2. Java 数字码 + 顶层 errorType 必须在一处收敛成 Agent 字符串码，避免映射散落；
3. 令牌只允许出现在 HTTP 头里，禁止进入日志、异常文本、state 与 SSE。

调用方通过模块级单例 `get_control_plane_client()` 复用连接池与令牌；
`ControlPlaneClient` 也可直接构造（测试注入 MockTransport）。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError

logger = structlog.get_logger(__name__)

# Agent 对外字符串码（docs/api-contract.md §6）
QUOTA_EXCEEDED = "quota_exceeded"
MODEL_NOT_AVAILABLE = "model_not_available"
CAPABILITY_UNSUPPORTED = "capability_unsupported"
CONTROL_PLANE_UNAVAILABLE = "control_plane_unavailable"
UPSTREAM_ERROR = "upstream_error"
# BYOK 凭证类错误：流建立前必须原样返回，不允许降级成平台模型
CREDENTIAL_REVOKED = "credential_revoked"
CREDENTIAL_LEASE_CONSUMED = "credential_lease_consumed"
LEASE_NOT_BYOK = "lease_not_byok"
CREDENTIAL_REJECTED = "credential_rejected"
# 幂等键被同一用户用于不同请求：属于调用方错误，不能重试，也不允许降级
IDEMPOTENCY_CONFLICT = "idempotency_conflict"

# Java ModelErrorCode 数字码（application-service/.../ModelErrorCode.java）
JAVA_QUOTA_EXCEEDED = 40201
JAVA_MODEL_NOT_AVAILABLE = 40202
JAVA_CAPABILITY_UNSUPPORTED = 40203
JAVA_LEASE_CONSUMED = 40215
JAVA_CREDENTIAL_REVOKED = 40216
JAVA_CREDENTIAL_VERIFY_FAILED = 40217
JAVA_LEASE_NOT_BYOK = 40218
JAVA_CREDENTIAL_REJECTED = 40219
JAVA_IDEMPOTENCY_CONFLICT = 40220
JAVA_DEPENDENCY_UNAVAILABLE = 50001

SERVICE_TOKEN_PATH = "/internal/v1/auth/service-token"
MODEL_TASKS_PATH = "/internal/v1/model-tasks"
MODEL_ACCESS_PATH = "/internal/v1/model-access/check"
MODEL_USAGE_PATH = "/internal/v1/model-usage"

# 用户身份由独立请求头携带：服务令牌证明「是谁在调用」，它证明「代表哪个用户」
USER_TOKEN_HEADER = "X-User-Token"

# 幂等键请求头：同键重复创建任务由 Java 复用既有任务，避免超时重试重复扣额度
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"

# 同一个服务令牌会被并发请求复用，刷新必须单飞，避免高峰期反复换取
SERVICE_TOKEN_REFRESH_RATIO = 0.1
SERVICE_TOKEN_MIN_MARGIN_SECONDS = 5.0
SERVICE_TOKEN_MAX_MARGIN_SECONDS = 30.0

MESSAGE_CONTROL_PLANE_UNAVAILABLE = "模型控制面暂不可用，请稍后重试"
MESSAGE_UPSTREAM_ERROR = "模型服务暂时不可用，请稍后重试"


class ControlPlaneError(Exception):
    """控制面调用失败，携带对外的字符串码与可选的额度详情。

    异常文本只用于日志与本地排查，禁止包含请求头、令牌或上游密钥。
    """

    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        *,
        quota: dict[str, Any] | None = None,
        is_retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message
        self.quota = quota
        self.is_retryable = is_retryable


def to_app_error(error: ControlPlaneError) -> AppError:
    """把控制面错误统一转成业务异常；额度超限时附带 `quota` 负载。"""
    extra = {"quota": error.quota} if error.quota else None
    return AppError(
        error.message,
        code=error.code,
        status_code=error.status_code,
        extra=extra,
    )


@dataclass(frozen=True)
class ModelTask:
    """`POST /internal/v1/model-tasks` 的解析结果，不含凭证。"""

    task_id: str
    provider: str
    model_key: str
    credential_source: str
    expires_at: str | None
    credential_id: str | None = None
    # BYOK 接入地址快照；MANAGED 时为空，使用平台网关
    base_url: str | None = None
    # 目录能力位：Agent 据此在请求侧做能力门控，缺失时按空元组处理
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class CredentialLease:
    """一次性兑换得到的明文凭证。

    `secret` 用 `repr=False` 排除：dataclass 默认 `__str__` 复用 `__repr__`，
    异常文本、structlog 事件一旦打印对象就会把密钥写进日志。
    """

    credential_type: str
    secret: str = field(repr=False)
    expires_in: int = 0


@dataclass(frozen=True)
class ModelAvailability:
    """`POST /internal/v1/model-access/check` 的可用性结果。"""

    provider: str
    model_key: str
    display_name: str | None
    capabilities: tuple[str, ...]
    context_window: int | None


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _quota_payload(data: Any) -> dict[str, Any] | None:
    """把 Java 的 camelCase 额度详情转成 Agent 对外 snake_case 字段。"""
    raw = _as_mapping(data)
    mapped = {
        "quota_type": raw.get("quotaType"),
        "limit": raw.get("limit"),
        "used": raw.get("used"),
        "reset_at": raw.get("resetAt"),
    }
    present = {key: value for key, value in mapped.items() if value is not None}
    return present or None


def _retryable_status(status_code: int) -> bool:
    """只有网络错误、5xx 与 429 值得重试；4xx 重试只会放大错误。"""
    return status_code == 429 or status_code >= 500


def _map_error(status_code: int, payload: dict[str, Any]) -> ControlPlaneError:
    """Java 数字码（优先）/ 顶层 errorType → Agent 字符串码。"""
    java_code = payload.get("code")
    error_type = payload.get("errorType")
    data = payload.get("data")
    retryable = _retryable_status(status_code)

    if java_code == JAVA_QUOTA_EXCEEDED or error_type == QUOTA_EXCEEDED or status_code == 429:
        return ControlPlaneError(
            QUOTA_EXCEEDED,
            429,
            "今日请求额度已用尽，请明日再试",
            quota=_quota_payload(data),
            is_retryable=retryable,
        )
    if java_code == JAVA_MODEL_NOT_AVAILABLE or error_type == MODEL_NOT_AVAILABLE:
        return ControlPlaneError(
            MODEL_NOT_AVAILABLE, 403, "模型不存在或当前账号不可用", is_retryable=retryable
        )
    if java_code == JAVA_CAPABILITY_UNSUPPORTED or error_type == CAPABILITY_UNSUPPORTED:
        return ControlPlaneError(
            CAPABILITY_UNSUPPORTED, 422, "当前模型不支持所需能力", is_retryable=retryable
        )
    # 凭证类错误必须是终态：重试只会拿到同样的结果，且降级会掩盖用户凭证问题
    if java_code == JAVA_CREDENTIAL_REVOKED or error_type == CREDENTIAL_REVOKED:
        return ControlPlaneError(
            CREDENTIAL_REVOKED, 401, "BYOK 凭证已撤销或不可用，请重新绑定", is_retryable=retryable
        )
    if java_code == JAVA_LEASE_CONSUMED or error_type == CREDENTIAL_LEASE_CONSUMED:
        return ControlPlaneError(
            CREDENTIAL_LEASE_CONSUMED,
            409,
            "BYOK 凭证已被兑换，请重新发起请求",
            is_retryable=retryable,
        )
    if java_code == JAVA_LEASE_NOT_BYOK or error_type == LEASE_NOT_BYOK:
        return ControlPlaneError(
            LEASE_NOT_BYOK, 409, "该任务不使用 BYOK 凭证", is_retryable=retryable
        )
    if java_code == JAVA_CREDENTIAL_REJECTED or error_type == CREDENTIAL_REJECTED:
        return ControlPlaneError(
            CREDENTIAL_REJECTED, 422, "Provider 拒绝了该 BYOK 凭证", is_retryable=retryable
        )
    if java_code == JAVA_IDEMPOTENCY_CONFLICT or error_type == IDEMPOTENCY_CONFLICT:
        # 同一幂等键被换成了不同模型/会话：重试也无法成功，必须让调用方换键重发
        return ControlPlaneError(
            IDEMPOTENCY_CONFLICT, 409, "幂等键已用于其他请求，请重新发起", is_retryable=False
        )
    if java_code == JAVA_CREDENTIAL_VERIFY_FAILED:
        # 远程验证失败属上游不可用；用户可稍后重试验证
        return ControlPlaneError(
            UPSTREAM_ERROR, 503, MESSAGE_UPSTREAM_ERROR, is_retryable=True
        )
    if java_code == JAVA_DEPENDENCY_UNAVAILABLE or status_code >= 500:
        return ControlPlaneError(
            CONTROL_PLANE_UNAVAILABLE,
            503,
            MESSAGE_CONTROL_PLANE_UNAVAILABLE,
            is_retryable=retryable,
        )
    # 未知数字码（如 40204–40208）统一收敛，不把内部错误语义透给前端
    return ControlPlaneError(UPSTREAM_ERROR, 503, MESSAGE_UPSTREAM_ERROR, is_retryable=retryable)


def _network_error() -> ControlPlaneError:
    """网络错误与超时统一为可重试的控制面不可用。"""
    return ControlPlaneError(
        CONTROL_PLANE_UNAVAILABLE, 503, MESSAGE_CONTROL_PLANE_UNAVAILABLE, is_retryable=True
    )


def _read_data(response: httpx.Response) -> dict[str, Any]:
    """解析 Java 统一信封，成功返回 data，失败抛出映射后的错误。"""
    try:
        payload = response.json()
    except ValueError:
        raise ControlPlaneError(
            UPSTREAM_ERROR, 503, MESSAGE_UPSTREAM_ERROR
        ) from None
    if not isinstance(payload, dict):
        raise ControlPlaneError(UPSTREAM_ERROR, 503, MESSAGE_UPSTREAM_ERROR) from None

    if response.is_success and payload.get("code") == 0:
        return _as_mapping(payload.get("data"))
    raise _map_error(response.status_code, payload)


def _text_field(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ControlPlaneError(UPSTREAM_ERROR, 503, MESSAGE_UPSTREAM_ERROR) from None
    return value


def _optional_text_field(data: dict[str, Any], key: str) -> str | None:
    """可空字段：缺失、null 或空串都归一为 None，避免空串被当成有效标识。"""
    value = data.get(key)
    return value if isinstance(value, str) and value else None


def _capabilities_field(data: dict[str, Any]) -> tuple[str, ...]:
    """解析目录能力位；缺失或类型不符时返回空元组。

    能力位只用于门控，解析失败不应让整次请求失败：真正的可用性由 Java 判定。
    """
    raw = data.get("capabilities")
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw)


def _usage_record_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Agent 内部 snake_case → Java 内部 DTO 的 camelCase。

    字段映射只在这里做一次：上层（图、队列）保持 snake_case，
    避免两套命名混进同一层（§9.3 命名说明）。
    """
    return {
        "invocationId": record.get("invocation_id"),
        "taskId": record.get("task_id"),
        "modelRole": record.get("model_role"),
        "provider": record.get("provider"),
        "modelKey": record.get("model_key"),
        "credentialSource": record.get("credential_source"),
        "promptTokens": record.get("prompt_tokens"),
        "completionTokens": record.get("completion_tokens"),
        "latencyMs": record.get("latency_ms"),
        "status": record.get("status"),
        "errorType": record.get("error_type"),
        "occurredAt": record.get("occurred_at"),
    }


class ControlPlaneClient:
    """控制面客户端：令牌缓存 + 单飞刷新 + 数字码映射。"""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._base_url = settings.control_plane.base_url.rstrip("/")
        self._timeout = settings.control_plane.timeout_seconds
        # 注入的客户端由调用方负责关闭；自建客户端在 aclose 中释放
        self._client = client
        self._owns_client = client is None
        self._service_token: str | None = None
        self._token_refresh_at = 0.0
        self._token_lock = asyncio.Lock()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def get_service_token(self) -> str:
        """返回缓存的服务令牌；过期前按比例提前刷新，并发刷新保持单飞。"""
        if self._service_token is not None and time.monotonic() < self._token_refresh_at:
            return self._service_token

        async with self._token_lock:
            # 双检：等锁期间可能已被其他协程刷新
            if self._service_token is not None and time.monotonic() < self._token_refresh_at:
                return self._service_token

            secret = (
                self._settings.control_plane.client_secret.get_secret_value()
                if self._settings.control_plane.client_secret is not None
                else ""
            )
            if not secret:
                raise ControlPlaneError(
                    CONTROL_PLANE_UNAVAILABLE, 503, MESSAGE_CONTROL_PLANE_UNAVAILABLE
                )

            try:
                response = await self._http().post(
                    f"{self._base_url}{SERVICE_TOKEN_PATH}",
                    data={
                        "client_id": self._settings.control_plane.client_id,
                        "client_secret": secret,
                    },
                )
            except httpx.HTTPError:
                # 不保留原始异常文本，避免把请求细节带进日志
                raise _network_error() from None

            data = _read_data(response)
            token = _text_field(data, "accessToken")
            expires_in = data.get("expiresIn")
            if not isinstance(expires_in, int) or expires_in <= 0:
                raise ControlPlaneError(UPSTREAM_ERROR, 503, MESSAGE_UPSTREAM_ERROR)

            margin = min(
                SERVICE_TOKEN_MAX_MARGIN_SECONDS,
                max(SERVICE_TOKEN_MIN_MARGIN_SECONDS, expires_in * SERVICE_TOKEN_REFRESH_RATIO),
            )
            self._service_token = token
            self._token_refresh_at = time.monotonic() + expires_in - margin
            return token

    def _authorized_headers(self, service_token: str, user_token: str | None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {service_token}"}
        if user_token is not None:
            headers[USER_TOKEN_HEADER] = user_token
        return headers

    async def create_task(
        self,
        *,
        user_token: str,
        thread_id: str,
        requested_model: str | None,
        idempotency_key: str | None = None,
    ) -> ModelTask:
        """创建运行时任务；额度在 Java 侧原子扣减，Agent 不自行计数。

        `idempotency_key` 由调用方按「用户 + 会话 + 客户端键」派生：
        同一键重试时 Java 复用既有任务，额度不会重复扣减。
        """
        service_token = await self.get_service_token()
        body = {"threadId": thread_id, "model": requested_model}
        headers = self._authorized_headers(service_token, user_token)
        if idempotency_key is not None:
            headers[IDEMPOTENCY_KEY_HEADER] = idempotency_key
        try:
            response = await self._http().post(
                f"{self._base_url}{MODEL_TASKS_PATH}",
                json=body,
                headers=headers,
            )
        except httpx.HTTPError:
            raise _network_error() from None

        data = _read_data(response)
        return ModelTask(
            task_id=_text_field(data, "taskId"),
            provider=_text_field(data, "provider"),
            model_key=_text_field(data, "modelKey"),
            credential_source=_text_field(data, "credentialSource"),
            expires_at=data.get("expiresAt") if isinstance(data.get("expiresAt"), str) else None,
            credential_id=_optional_text_field(data, "credentialId"),
            base_url=_optional_text_field(data, "baseUrl"),
            capabilities=_capabilities_field(data),
        )

    async def lease_credential(self, *, task_id: str) -> CredentialLease:
        """一次性兑换 BYOK 明文凭证。

        只带服务令牌：任务已由用户令牌创建，兑换阶段不再重复校验用户身份，
        这样 Java 侧可以用条件 UPDATE 把「只能兑换一次」做成原子操作。
        明文只在本进程内存中短暂存在，禁止写入日志、异常或状态。
        """
        service_token = await self.get_service_token()
        path = f"{MODEL_TASKS_PATH}/{task_id}/credential-lease"
        try:
            response = await self._http().post(
                f"{self._base_url}{path}",
                headers=self._authorized_headers(service_token, None),
            )
        except httpx.HTTPError:
            raise _network_error() from None

        data = _read_data(response)
        expires_in = data.get("expiresIn")
        if not isinstance(expires_in, int) or expires_in <= 0:
            raise ControlPlaneError(UPSTREAM_ERROR, 503, MESSAGE_UPSTREAM_ERROR)
        return CredentialLease(
            credential_type=_text_field(data, "credentialType"),
            secret=_text_field(data, "secret"),
            expires_in=expires_in,
        )

    async def check_model_access(self, *, user_token: str, model_key: str) -> ModelAvailability:
        """校验模型是否在目录中且当前用户可用。"""
        service_token = await self.get_service_token()
        try:
            response = await self._http().post(
                f"{self._base_url}{MODEL_ACCESS_PATH}",
                json={"modelKey": model_key},
                headers=self._authorized_headers(service_token, user_token),
            )
        except httpx.HTTPError:
            raise _network_error() from None

        data = _read_data(response)
        display_name = data.get("displayName")
        return ModelAvailability(
            provider=_text_field(data, "provider"),
            model_key=_text_field(data, "modelKey"),
            display_name=display_name if isinstance(display_name, str) else None,
            capabilities=_capabilities_field(data),
            context_window=data.get("contextWindow")
            if isinstance(data.get("contextWindow"), int)
            else None,
        )

    async def report_usage(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """批量上报使用明细；调用方负责拆批与重试。"""
        if not records:
            return {}
        service_token = await self.get_service_token()
        try:
            response = await self._http().post(
                f"{self._base_url}{MODEL_USAGE_PATH}",
                json={"records": [_usage_record_payload(record) for record in records]},
                headers=self._authorized_headers(service_token, None),
            )
        except httpx.HTTPError:
            raise _network_error() from None
        return _read_data(response)

    async def aclose(self) -> None:
        """只关闭自己创建的客户端，注入的客户端生命周期由调用方管理。"""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
        self._client = None


_client_singleton: ControlPlaneClient | None = None


def get_control_plane_client() -> ControlPlaneClient:
    """进程内复用客户端与令牌缓存。"""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = ControlPlaneClient(get_settings())
    return _client_singleton


async def close_control_plane_client() -> None:
    """应用关闭时释放连接池。"""
    global _client_singleton
    if _client_singleton is not None:
        await _client_singleton.aclose()
        _client_singleton = None


def reset_control_plane_client() -> None:
    """丢弃单例（测试或配置热切换后使用）。"""
    global _client_singleton
    _client_singleton = None
