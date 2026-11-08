"""鉴权相关接口。

正式令牌由业务后端用 RS256 私钥签发；这里仅提供开发环境用的便捷签发接口，
用 dev 专用私钥自签，避免本地联调时还要先启动 Spring Boot。
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import ACCESS_TOKEN_USE, is_dev_token_enabled

router = APIRouter(prefix="/auth", tags=["auth"])


class DevTokenRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64, description="开发用用户标识")
    expires_minutes: int = Field(default=60, ge=1, le=1440, description="有效期（分钟）")


def _unavailable_error() -> AppError:
    """对调用方只说「不可用」，不暴露期望的环境变量名与密钥细节。"""
    return AppError("开发令牌签发不可用", code="dev_token_unavailable", status_code=503)


@router.post("/dev-token")
async def issue_dev_token(payload: DevTokenRequest) -> dict[str, object]:
    """仅在开发/测试环境签发令牌，生产环境直接拒绝。"""
    settings = get_settings()
    # 白名单写法：只允许 dev 且开启 debug，staging / prod 一律拒绝
    if not is_dev_token_enabled(settings):
        raise AppError("该接口仅限开发环境使用", code="forbidden", status_code=403)

    dev_private_key = settings.auth.dev_private_key
    if dev_private_key is None:
        raise _unavailable_error()

    try:
        private_key = load_pem_private_key(dev_private_key.get_secret_value().encode(), None)
    except (ValueError, TypeError) as exc:
        raise _unavailable_error() from exc

    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": payload.user_id,
        "iss": settings.auth.issuer,
        "aud": settings.auth.audience,
        "roles": ["user"],
        "iat": now,
        "exp": now + timedelta(minutes=payload.expires_minutes),
        # jti 供日志与后续撤销扩展使用；token_use 与 Java 签发方保持同一契约
        "jti": str(uuid4()),
        "token_use": ACCESS_TOKEN_USE,
    }
    token = jwt.encode(
        claims,
        private_key,  # type: ignore[arg-type]  # PyJWT 接受 cryptography 的私钥对象
        algorithm=settings.auth.jwt_algorithm,
        # header 带 kid，验签端才能按 kid 选中 dev 公钥
        headers={"kid": settings.auth.dev_kid},
    )
    return {
        "access_token": token,
        # 与 Java 签发方保持一致，统一使用 Bearer 大小写
        "token_type": "Bearer",
        "expires_in": payload.expires_minutes * 60,
    }
