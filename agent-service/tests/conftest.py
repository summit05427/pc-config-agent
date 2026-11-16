"""测试环境全局配置。

JWT 已改为 RS256：测试用 RSA 密钥对在运行时生成，
仓库里不提交任何密钥文件，也不依赖本地 .env 中的真实密钥。
"""

import asyncio
import os
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)
from fastapi.testclient import TestClient

# 与 Java 签发方的默认值保持一致，覆盖测试才能反映真实契约
TEST_JWT_KID = "rsa-test"
TEST_DEV_KID = "rsa-dev"
TEST_ISSUER = "agent-application-service"
TEST_AUDIENCE = "agent-clients"

# psycopg 的异步驱动不支持 Windows 默认的 ProactorEventLoop，
# 必须在事件循环创建前切换为 SelectorEventLoop。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
    """pytest-asyncio 1.x 的官方入口：Windows 强制 Selector，避免 psycopg 异步驱动失败。"""
    del config, item
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}


def _generate_key_pair() -> tuple[str, str]:
    """运行时生成 RSA 密钥对，返回 (PKCS#8 私钥 PEM, PKIX 公钥 PEM)。"""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        Encoding.PEM,
        PrivateFormat.PKCS8,
        NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        Encoding.PEM,
        PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


TEST_PRIVATE_KEY_PEM, TEST_PUBLIC_KEY_PEM = _generate_key_pair()
# 与主密钥无关的第二把私钥，用来构造「签名不匹配」的令牌
WRONG_PRIVATE_KEY_PEM, _ = _generate_key_pair()
# dev-token 专用密钥：与主密钥分离，模拟方案中被 Java 私钥之外的独立 dev 密钥
TEST_DEV_PRIVATE_KEY_PEM, _ = _generate_key_pair()


def _single_line_pem(pem: str) -> str:
    """模拟容器里常见的单行 PEM 写法（换行写成字面量 \\n）。"""
    return pem.strip().replace("\n", "\\n")


# 必须在导入 app 之前注入：Settings 在模块导入期就会被构建。
# 这里显式覆盖 APP_ENV / DEBUG / AUTH__*，避免本地 .env 中的旧配置干扰测试。
os.environ["APP_ENV"] = "dev"
os.environ["DEBUG"] = "true"
os.environ["AUTH__JWT_PUBLIC_KEY"] = _single_line_pem(TEST_PUBLIC_KEY_PEM)
os.environ["AUTH__JWT_ALGORITHM"] = "RS256"
os.environ["AUTH__JWT_KID"] = TEST_JWT_KID
os.environ["AUTH__ISSUER"] = TEST_ISSUER
os.environ["AUTH__AUDIENCE"] = TEST_AUDIENCE
os.environ["AUTH__DEV_PRIVATE_KEY"] = _single_line_pem(TEST_DEV_PRIVATE_KEY_PEM)
os.environ["AUTH__DEV_KID"] = TEST_DEV_KID
# 模型运行时默认关闭：本地 .env 若设 MODEL_RUNTIME__ENABLED=true，
# /chat/stream 会改走控制面调用并要求 X-User-Token，测试结果随开发者环境漂移。
# 需要覆盖运行时路径的用例应自行 monkeypatch.setenv 后重建 Settings。
os.environ["MODEL_RUNTIME__ENABLED"] = "false"
# CORS 白名单固定为默认前端端口：本地 .env 若改了端口，CORS 用例会随环境漂移
os.environ["CORS_ORIGINS"] = '["http://localhost:5173"]'
# MCP 默认关闭：避免本地 .env 开启后测试触发真实网络连接
os.environ["MCP__ENABLED"] = "false"
# 生成式 UI 默认关闭：本地 .env 若设 OPENUI__ENABLED=true，正文会从 Markdown 表格
# 切换成 OpenUI 清单，渲染类断言随开发者环境漂移。
os.environ["OPENUI__ENABLED"] = "false"
# HITL 默认关闭：本地 .env 若设 HITL__ENABLED=true，澄清路径会变成 interrupt，
# 「未开启 HITL 保持原流程」用例随环境漂移；需要 HITL 的用例用 hitl_on fixture 显式开启。
os.environ["HITL__ENABLED"] = "false"
# 限流按用户计数，而集成测试共用一个 Redis 与同一批测试用户：
# 沿用默认 20 次/分钟会让后跑的用例被前面的请求挤成 429，形成顺序相关的假失败。
# 这里放大配额，只保留中间件调用路径；限流语义由 tests/test_rate_limit.py
# 与 tests/test_chat_input_guard.py 的专用用例覆盖。
os.environ["RATE_LIMIT__CHAT_PER_MINUTE"] = "600"


def _sign_access_token(
    user_id: str = "user-1",
    *,
    private_key_pem: str = TEST_PRIVATE_KEY_PEM,
    kid: str | None = TEST_JWT_KID,
    issuer: str = TEST_ISSUER,
    audience: str | None = TEST_AUDIENCE,
    expires_in_seconds: int = 3600,
    token_use: str = "access",
    roles: object = ["USER"],
) -> str:
    """按 Java 签发契约构造令牌，方便覆盖合法与各类非法场景。"""
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": user_id,
        "iss": issuer,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in_seconds),
        "jti": str(uuid4()),
        "token_use": token_use,
        "roles": roles,
    }
    if audience is not None:
        claims["aud"] = audience
    private_key = load_pem_private_key(private_key_pem.encode(), password=None)
    # kid=None 时不写 header，用于验证「缺 kid 必须被拒」
    headers = {"kid": kid} if kid is not None else None
    return jwt.encode(claims, private_key, algorithm="RS256", headers=headers)


@pytest.fixture(scope="session")
def token_factory() -> Callable[..., str]:
    """返回构造 RS256 令牌的函数，参数默认值与真实签发契约一致。"""
    return _sign_access_token


@pytest.fixture(scope="session")
def wrong_private_key_pem() -> str:
    """与可信公钥不匹配的私钥 PEM，用于构造错误签名的令牌。"""
    return WRONG_PRIVATE_KEY_PEM


@pytest.fixture(scope="session")
def public_key_pem() -> str:
    """当前进程配置的公钥 PEM，配置类测试用它构造合法 AuthSettings。"""
    return TEST_PUBLIC_KEY_PEM


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    """以上下文方式创建客户端，让 FastAPI lifespan 真正执行。

    Redis 客户端与会话检查点都在 lifespan 中初始化；若像裸的
    `TestClient(app)` 那样只发请求，这些依赖永远为未就绪状态，
    接口会直接返回 503，测试结果将与运行环境无关地失真。
    """
    # 延迟导入：应用在导入期就会读取环境变量，必须等上面的 AUTH__* 注入完成
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
