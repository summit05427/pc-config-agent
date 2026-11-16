"""生产配置守卫测试：带病配置必须拒绝启动，而不是运行后才暴露。"""

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import AuthSettings, OpenUiSettings, RagSettings, Settings


def _prod_settings(public_key_pem: str, **overrides: Any) -> Settings:
    """构造一份合法生产配置，测试按需覆盖单个字段。"""
    values: dict[str, Any] = {
        "_env_file": None,
        "app_env": "prod",
        "debug": False,
        "cors_origins": ["https://example.com"],
        "auth": AuthSettings(jwt_public_key=public_key_pem),
        "storage": {"backend": "postgres", "postgres_url": "postgresql://u:p@db:5432/agent"},
        "redis": {"url": "redis://redis:6379/0", "required": True},
        "llm": {"api_key": "sk-real-key"},
    }
    values.update(overrides)
    return Settings(**values)


def test_valid_production_settings_are_accepted(public_key_pem: str) -> None:
    settings = _prod_settings(public_key_pem)

    assert settings.app_env == "prod"
    assert settings.auth.jwt_algorithm == "RS256"
    assert settings.auth.audience == "agent-clients"
    assert settings.agent.recursion_limit > 0


def test_production_rejects_debug_mode(public_key_pem: str) -> None:
    with pytest.raises(ValidationError, match="DEBUG"):
        _prod_settings(public_key_pem, debug=True)


def test_production_rejects_placeholder_jwt_public_key() -> None:
    with pytest.raises(ValidationError, match="JWT_PUBLIC_KEY"):
        _prod_settings("replace-with-the-rsa-public-key-pem")


def test_production_rejects_memory_checkpointer(public_key_pem: str) -> None:
    with pytest.raises(ValidationError, match="STORAGE__BACKEND"):
        _prod_settings(public_key_pem, storage={"backend": "memory"})


def test_production_rejects_wildcard_cors(public_key_pem: str) -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        _prod_settings(public_key_pem, cors_origins=["*"])


def test_production_rejects_placeholder_llm_key(public_key_pem: str) -> None:
    with pytest.raises(ValidationError, match="LLM__API_KEY"):
        _prod_settings(public_key_pem, llm={"api_key": "sk-replace-with-your-real-key"})


def test_production_requires_redis(public_key_pem: str) -> None:
    with pytest.raises(ValidationError, match="REDIS__URL"):
        _prod_settings(public_key_pem, redis={"required": False})


@pytest.mark.parametrize(
    "overrides",
    [
        {"agent": {"hooks_modules": ["acceptance.hooks"]}},
        {"agent": {"tool_modules": ["acceptance.tools"]}},
        {"rag": {"enabled": True, "retriever_module": "acceptance.retriever"}},
    ],
)
def test_production_rejects_acceptance_fixtures(
    public_key_pem: str, overrides: dict[str, Any]
) -> None:
    """验收夹具返回固定假数据，生产误启用会静默绕过真实实现。"""
    with pytest.raises(ValidationError, match="acceptance"):
        _prod_settings(public_key_pem, **overrides)


def test_production_accepts_enabled_runtime_with_real_secret(public_key_pem: str) -> None:
    """启用模型运行时时，真实内部凭据允许启动。"""
    settings = _prod_settings(
        public_key_pem,
        model_runtime={"enabled": True},
        control_plane={"client_secret": "internal-secret-value"},
    )

    assert settings.model_runtime.enabled is True
    assert settings.control_plane.client_secret is not None


def test_production_rejects_enabled_runtime_without_secret(public_key_pem: str) -> None:
    """开启模型运行时却没有服务令牌凭据，必须拒绝启动，而不是运行中全部 503。"""
    with pytest.raises(ValidationError, match="CONTROL_PLANE__CLIENT_SECRET"):
        _prod_settings(public_key_pem, model_runtime={"enabled": True})


def test_production_rejects_placeholder_control_plane_secret(public_key_pem: str) -> None:
    with pytest.raises(ValidationError, match="CONTROL_PLANE__CLIENT_SECRET"):
        _prod_settings(
            public_key_pem,
            model_runtime={"enabled": True},
            control_plane={"client_secret": "replace-with-strong-internal-client-secret"},
        )


def test_production_runtime_disabled_does_not_require_secret(public_key_pem: str) -> None:
    """关闭模型运行时不需要控制面凭据，保持单模型部署的启动方式。"""
    settings = _prod_settings(public_key_pem)

    assert settings.model_runtime.enabled is False
    assert settings.control_plane.client_secret is None


def test_development_allows_defaults(
    public_key_pem: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """开发环境不应被生产守卫误伤。"""
    # CI 会注入 STORAGE__BACKEND 等变量供集成测试连接真实服务；
    # 本用例验证的是「无环境覆盖时的默认值」，必须先清空这些变量。
    for env_name in (
        "STORAGE__BACKEND",
        "STORAGE__POSTGRES_URL",
        "REDIS__URL",
        "REDIS__REQUIRED",
    ):
        monkeypatch.delenv(env_name, raising=False)

    settings = Settings(
        _env_file=None,
        app_env="dev",
        debug=True,
        auth=AuthSettings(jwt_public_key=public_key_pem),
    )

    assert settings.storage.backend == "memory"
    assert settings.redis.required is False


def test_solo_blank_connection_strings_are_unset(public_key_pem: str) -> None:
    """Solo 用空串显式关闭 Postgres / Redis，不能被当成非法配置。"""
    settings = Settings(
        _env_file=None,
        app_env="dev",
        debug=True,
        auth=AuthSettings(jwt_public_key=public_key_pem),
        storage={"backend": "memory", "postgres_url": "   "},
        redis={"url": "   ", "required": False},
    )

    assert settings.storage.postgres_url is None
    assert settings.redis.url is None


def test_rag_enabled_defaults_to_embedding_configuration() -> None:
    """未显式配置时按 embedding 是否齐备推导；缺少配置只表示未启用，不报错。"""
    assert RagSettings().enabled is False
    assert RagSettings(embedding_model="text-embedding-3-small").enabled is False
    assert RagSettings(embedding_model="", embedding_dimensions=1536).enabled is False
    assert RagSettings(
        embedding_model="text-embedding-3-small", embedding_dimensions=1536
    ).enabled is True
    # 显式开关始终优先于推导结果
    assert RagSettings(
        enabled=False, embedding_model="text-embedding-3-small", embedding_dimensions=1536
    ).enabled is False
    assert RagSettings(enabled=True).enabled is True


def test_public_key_is_required() -> None:
    """公钥是验签的唯一凭据，缺失时必须在构造配置时就失败。"""
    with pytest.raises(ValidationError, match="jwt_public_key"):
        AuthSettings()


def test_unparseable_public_key_is_rejected_at_startup() -> None:
    """PEM 解析失败必须在构造配置时暴露，不能等到每个请求都返回 401。"""
    with pytest.raises(ValidationError, match="AUTH__JWT_PUBLIC_KEY"):
        AuthSettings(jwt_public_key="not-a-pem")


def test_auth_algorithm_only_accepts_rs256(public_key_pem: str) -> None:
    """算法写死为 RS256，HS* 与 none 一律不允许。"""
    with pytest.raises(ValidationError):
        AuthSettings(jwt_public_key=public_key_pem, jwt_algorithm="HS256")


def test_blank_audience_is_rejected(public_key_pem: str) -> None:
    """aud 必填且强制校验，空值会让所有令牌被拒，必须在启动时暴露。"""
    with pytest.raises(ValidationError, match="audience"):
        AuthSettings(jwt_public_key=public_key_pem, audience="   ")


def test_literal_newline_escapes_are_normalized(public_key_pem: str) -> None:
    """单行 PEM 里的字面量 \\n 应还原成真实换行，否则无法解析。"""
    auth = AuthSettings(jwt_public_key=public_key_pem.replace("\n", "\\n"))

    assert "\n" in auth.jwt_public_key
    assert "\\n" not in auth.jwt_public_key


def test_blank_dev_private_key_is_treated_as_unset(public_key_pem: str) -> None:
    auth = AuthSettings(jwt_public_key=public_key_pem, dev_private_key="")

    assert auth.dev_private_key is None
    assert auth.jwt_kid is None


def test_openui_settings_default_to_disabled() -> None:
    """默认关闭，未接入前端的部署输出格式不受影响。"""
    settings = OpenUiSettings()

    assert settings.enabled is False
    assert settings.prompt_name == "openui"
    assert settings.max_blocks == 4


def test_openui_prompt_name_rejects_path_segments() -> None:
    """名称白名单在启动时生效，不等读取文件才失败。"""
    with pytest.raises(ValidationError):
        OpenUiSettings(prompt_name="../secrets")


def test_openui_max_blocks_is_bounded() -> None:
    """块数上限超出范围属于配置错误。"""
    with pytest.raises(ValidationError):
        OpenUiSettings(max_blocks=0)


def test_openui_enabled_env_is_decoded(
    public_key_pem: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compose 以字符串注入 OPENUI__ENABLED，必须解析为布尔值。"""
    monkeypatch.setenv("OPENUI__ENABLED", "true")
    settings = Settings(
        _env_file=None,
        app_env="dev",
        auth=AuthSettings(jwt_public_key=public_key_pem),
    )

    assert settings.openui.enabled is True
