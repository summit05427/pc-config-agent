"""JWT 鉴权：校验访问令牌并解析当前用户。

职责边界：
- 本服务只「校验」令牌，不签发正式令牌；
- 正式令牌由业务后端（Spring Boot）用 RS256 私钥签发，本服务只持公钥验签；
- 开发环境可用 /auth/dev-token 以独立的 dev 私钥自签，生产环境禁用。
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
import structlog
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError

# auto_error=False：缺令牌时不抛框架默认错误，改为抛 AppError 统一格式
bearer_scheme = HTTPBearer(auto_error=False)

logger = structlog.get_logger(__name__)

# Java 签发方的默认 kid；未配置 AUTH__JWT_KID 时用它注册主公钥
DEFAULT_JWT_KID = "rsa-2026-10"

# 访问令牌必须携带的用途标记，用于区分未来的 refresh token
ACCESS_TOKEN_USE = "access"


@dataclass(frozen=True)
class CurrentUser:
    """鉴权后的当前用户，作为依赖注入给路由。"""

    user_id: str
    roles: tuple[str, ...] = ()


def namespaced_thread_id(user: CurrentUser, client_thread_id: str) -> str:
    """把客户端 thread_id 拼上用户命名空间。

    会话归属由服务端决定，客户端无法通过伪造 thread_id 读取他人历史。
    """
    return f"{user.user_id}:{client_thread_id}"


def is_dev_token_enabled(settings: Settings) -> bool:
    """dev-token 只在 dev + debug 下启用：staging / prod 一律不认签名私钥。"""
    return settings.app_env == "dev" and settings.debug


def _invalid_token_error() -> AppError:
    return AppError("无效的访问令牌", code="token_invalid", status_code=401)


@lru_cache(maxsize=4)
def _trusted_public_keys(
    public_key_pem: str,
    key_id: str,
    dev_kid: str,
    dev_private_key_pem: str | None,
) -> dict[str, Any]:
    """按 kid 建立可信公钥映射。

    用 lru_cache 缓存：Settings 是单例，避免每次请求都解析 PEM。
    dev 私钥只在开发环境传入，其公钥由私钥派生，生产环境不会注册。
    """
    try:
        keys: dict[str, Any] = {key_id: load_pem_public_key(public_key_pem.encode())}
        if dev_private_key_pem is not None:
            dev_private_key = load_pem_private_key(dev_private_key_pem.encode(), password=None)
            keys[dev_kid] = dev_private_key.public_key()
    except (ValueError, TypeError) as exc:
        # 配置错误不应该泄露到响应里，也不应该让请求绕过验签
        logger.error("jwt_key_config_invalid", error=str(exc))
        raise _invalid_token_error() from exc
    return keys


def _key_ring(settings: Settings) -> dict[str, Any]:
    """当前进程信任的公钥集合：主公钥 + （仅 dev）dev 公钥。"""
    auth = settings.auth
    dev_private_key_pem: str | None = None
    if is_dev_token_enabled(settings) and auth.dev_private_key is not None:
        dev_private_key_pem = auth.dev_private_key.get_secret_value()
    return _trusted_public_keys(
        auth.jwt_public_key,
        auth.jwt_kid or DEFAULT_JWT_KID,
        auth.dev_kid,
        dev_private_key_pem,
    )


def decode_access_token(token: str, settings: Settings) -> CurrentUser:
    """解析并校验 JWT，失败时抛 401。

    kid 只用于「选择本进程已有的公钥」，绝不根据令牌内容去远端拉取密钥。
    未知 kid 直接拒绝，避免攻击者用任意密钥试探。
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise _invalid_token_error() from exc

    key_id = header.get("kid")
    public_key = _key_ring(settings).get(str(key_id)) if key_id else None
    if public_key is None:
        raise _invalid_token_error()

    try:
        payload = jwt.decode(
            token,
            public_key,  # type: ignore[arg-type]  # PyJWT 接受 cryptography 的公钥对象
            algorithms=[settings.auth.jwt_algorithm],
            issuer=settings.auth.issuer,
            audience=settings.auth.audience,
            options={
                # 缺任何一个声明都视为非法令牌，避免「省略即可绕过」的玩法
                "require": ["exp", "sub", "iss", "aud", "token_use"],
                "verify_aud": True,
                "verify_iss": True,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError("登录已过期，请重新登录", code="token_expired", status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise _invalid_token_error() from exc

    # PyJWT 不认识 token_use 语义，必须自己校验，拒绝 refresh 等其它用途的令牌
    if payload.get("token_use") != ACCESS_TOKEN_USE:
        raise _invalid_token_error()

    subject = payload.get("sub")
    if not subject:
        raise AppError("令牌缺少主体信息", code="token_invalid", status_code=401)

    roles = payload.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]

    return CurrentUser(user_id=str(subject), roles=tuple(str(role) for role in roles))


async def get_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> SecretStr | None:
    """返回原始访问令牌，仅供转发给控制面使用。

    这里不做验签：验签由 `get_current_user` 完成。缺失时返回 None，
    由调用方在真正需要时拒绝（模型运行时关闭时无需该令牌）。
    令牌禁止进入日志、异常文本、AgentState 与 SSE 事件。
    """
    if credentials is None:
        return None
    return SecretStr(credentials.credentials)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """FastAPI 依赖：从 Authorization: Bearer <token> 中还原当前用户。"""
    if credentials is None:
        raise AppError("缺少访问令牌", code="unauthorized", status_code=401)

    user = decode_access_token(credentials.credentials, settings)
    # 绑定到日志上下文，后续日志自动带上 user_id（中间件会统一清理）
    structlog.contextvars.bind_contextvars(user_id=user.user_id)
    return user
