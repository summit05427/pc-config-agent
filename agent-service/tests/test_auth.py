"""JWT 鉴权与会话归属测试：覆盖 RS256 验签的合法与各类非法场景。"""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from app.api.v1 import auth as auth_module
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import decode_access_token
from app.services import model_runtime as model_runtime_module

settings = get_settings()


class RecordingGraph:
    """记录实际使用的 thread_id，用于验证会话归属。"""

    def __init__(self) -> None:
        self.thread_ids: list[str] = []

    async def astream(self, inputs: Any, config: Any, stream_mode: Any = None) -> Any:
        self.thread_ids.append(config["configurable"]["thread_id"])
        yield "messages", (AIMessageChunk(content="ok"), {})


def test_decode_valid_token(token_factory: Callable[..., str]) -> None:
    """Java 用私钥签发、Agent 用公钥验签的令牌应被接受。"""
    user = decode_access_token(token_factory("alice"), settings)

    assert user.user_id == "alice"
    assert user.roles == ("USER",)


def test_expired_token_is_rejected(token_factory: Callable[..., str]) -> None:
    with pytest.raises(AppError) as exc_info:
        decode_access_token(token_factory(expires_in_seconds=-10), settings)

    assert exc_info.value.code == "token_expired"
    assert exc_info.value.status_code == 401


def test_token_with_wrong_signature_is_rejected(
    token_factory: Callable[..., str], wrong_private_key_pem: str
) -> None:
    """kid 命中但签名不匹配时必须拒绝，防止伪造令牌带上真实 kid。"""
    with pytest.raises(AppError) as exc_info:
        decode_access_token(
            token_factory(private_key_pem=wrong_private_key_pem), settings
        )

    assert exc_info.value.code == "token_invalid"
    assert exc_info.value.status_code == 401


def test_token_from_other_issuer_is_rejected(token_factory: Callable[..., str]) -> None:
    with pytest.raises(AppError) as exc_info:
        decode_access_token(token_factory(issuer="other-service"), settings)

    assert exc_info.value.code == "token_invalid"


def test_token_with_wrong_audience_is_rejected(token_factory: Callable[..., str]) -> None:
    """aud 现在必填且强制校验，受众不符说明令牌不是发给本服务的。"""
    with pytest.raises(AppError) as exc_info:
        decode_access_token(token_factory(audience="other-clients"), settings)

    assert exc_info.value.code == "token_invalid"


def test_token_without_audience_is_rejected(token_factory: Callable[..., str]) -> None:
    """aud 是必填声明，省略不能绕过校验。"""
    with pytest.raises(AppError) as exc_info:
        decode_access_token(token_factory(audience=None), settings)

    assert exc_info.value.code == "token_invalid"


def test_token_with_non_access_use_is_rejected(token_factory: Callable[..., str]) -> None:
    """token_use 非 access（例如未来的 refresh）不得访问业务接口。"""
    with pytest.raises(AppError) as exc_info:
        decode_access_token(token_factory(token_use="refresh"), settings)

    assert exc_info.value.code == "token_invalid"


def test_token_with_unknown_kid_is_rejected(token_factory: Callable[..., str]) -> None:
    """未知 kid 直接拒绝，不做任何回退或远端拉取。"""
    with pytest.raises(AppError) as exc_info:
        decode_access_token(token_factory(kid="rsa-unknown"), settings)

    assert exc_info.value.code == "token_invalid"


def test_token_without_kid_header_is_rejected(token_factory: Callable[..., str]) -> None:
    """header 缺 kid 时无法选密钥，按非法令牌处理。"""
    with pytest.raises(AppError) as exc_info:
        decode_access_token(token_factory(kid=None), settings)

    assert exc_info.value.code == "token_invalid"


def test_token_with_blank_subject_is_rejected(token_factory: Callable[..., str]) -> None:
    """sub 存在但为空等于没有身份，必须拒绝。"""
    with pytest.raises(AppError) as exc_info:
        decode_access_token(token_factory(""), settings)

    assert exc_info.value.code == "token_invalid"


def test_malformed_token_is_rejected() -> None:
    """连 header 都解析不出来的字符串按非法令牌处理，而不是抛 500。"""
    with pytest.raises(AppError) as exc_info:
        decode_access_token("not-a-jwt", settings)

    assert exc_info.value.code == "token_invalid"


def test_single_role_claim_is_normalized(token_factory: Callable[..., str]) -> None:
    """Java 侧可能把 roles 写成字符串，解析时要统一成元组。"""
    user = decode_access_token(token_factory(roles="ADMIN"), settings)

    assert user.roles == ("ADMIN",)


def test_invalid_public_key_configuration_is_rejected(
    token_factory: Callable[..., str],
) -> None:
    """公钥配置错误时按非法令牌拒绝，绝不降级为不验签。"""
    broken_settings = SimpleNamespace(
        app_env="dev",
        debug=False,
        auth=SimpleNamespace(
            jwt_public_key="not-a-pem",
            jwt_kid=None,
            dev_kid="rsa-dev",
            dev_private_key=None,
        ),
    )

    with pytest.raises(AppError) as exc_info:
        decode_access_token(token_factory(), broken_settings)

    assert exc_info.value.code == "token_invalid"
    assert exc_info.value.status_code == 401


def test_chat_requires_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "demo"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_thread_id_is_namespaced_by_user(
    client: TestClient, monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    """同一客户端 thread_id，不同用户会落到不同会话，天然防越权。"""
    graph = RecordingGraph()
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: graph)

    for user_id in ("alice", "bob"):
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "你好", "thread_id": "demo"},
            headers={"Authorization": f"Bearer {token_factory(user_id)}"},
        )
        assert response.status_code == 200

    assert graph.thread_ids == ["alice:demo", "bob:demo"]


def test_dev_token_can_be_used(client: TestClient, monkeypatch: Any) -> None:
    """dev 私钥签发的令牌应能通过同一套验签链路。"""
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: RecordingGraph())

    issued = client.post("/api/v1/auth/dev-token", json={"user_id": "dev-user"})
    assert issued.status_code == 200
    token = issued.json()["access_token"]

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "你好", "thread_id": "demo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_dev_token_uses_dev_kid_and_full_claims(client: TestClient) -> None:
    """dev 令牌必须带 kid / aud / token_use，否则与 Java 契约不一致。"""
    issued = client.post("/api/v1/auth/dev-token", json={"user_id": "dev-user"})
    token = issued.json()["access_token"]

    header = jwt.get_unverified_header(token)
    payload = jwt.decode(token, options={"verify_signature": False})

    assert header["alg"] == "RS256"
    assert header["kid"] == settings.auth.dev_kid
    assert payload["aud"] == settings.auth.audience
    assert payload["token_use"] == "access"
    assert payload["jti"]


def test_dev_token_disabled_in_production(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        auth_module, "get_settings", lambda: SimpleNamespace(debug=False, app_env="prod")
    )

    response = client.post("/api/v1/auth/dev-token", json={"user_id": "dev-user"})

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_dev_token_returns_503_without_private_key(
    client: TestClient, monkeypatch: Any
) -> None:
    """未注入 dev 私钥时只返回「不可用」，不暴露内部细节。"""
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="dev",
            debug=True,
            auth=SimpleNamespace(dev_private_key=None),
        ),
    )

    response = client.post("/api/v1/auth/dev-token", json={"user_id": "dev-user"})

    assert response.status_code == 503
    assert response.json()["code"] == "dev_token_unavailable"
