"""模型运行时门面测试：验证装配顺序、降级与凭证撤销，不发起网络请求。"""

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from app.agent.profiles import resolve_profile
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.services import model_runtime as model_runtime_module
from app.services.model_runtime import prepare_agent


def _set_enabled(monkeypatch: Any, enabled: bool) -> None:
    """只切换运行时开关，其余配置沿用测试进程的默认值。"""
    monkeypatch.setattr(get_settings().model_runtime, "enabled", enabled)


def _runtime(
    *,
    credential_id: str | None = "cred-1",
    credential_source: str = "BYOK",
    capabilities: tuple[str, ...] = (),
) -> SimpleNamespace:
    """按 `ResolvedRuntime` 的字段构造假运行时；门面只读取这些字段。"""
    return SimpleNamespace(
        task_id="task-1",
        provider="openai",
        model_key="openai:gpt-4o-mini",
        credential_source=credential_source,
        credential_id=credential_id,
        base_url="https://byok.example.com/v1",
        capabilities=capabilities,
    )


def _forbid_resolve_runtime(monkeypatch: Any) -> None:
    """关闭运行时或缺少令牌时，绝不应发起控制面调用。"""

    async def fail_resolve(**_kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError("不应解析运行时")

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fail_resolve)


async def test_disabled_runtime_uses_default_graph_without_control_plane(
    monkeypatch: Any,
) -> None:
    """关闭运行时且为默认 Profile 时，直接复用进程默认图，不调用控制面。"""
    _set_enabled(monkeypatch, False)
    _forbid_resolve_runtime(monkeypatch)
    graph = SimpleNamespace()
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: graph)

    prepared = await prepare_agent(
        resolve_profile(None),
        user_id="test-user",
        thread_id="t-1",
        access_token=SecretStr("user-token"),
        requested_model=None,
    )

    assert prepared.graph is graph
    assert prepared.runtime is None
    # 用户令牌只用于本回合的 Java 内部接口，不进入图状态
    assert prepared.user_token is not None
    assert prepared.user_token.get_secret_value() == "user-token"


async def test_disabled_runtime_uses_profile_scoped_default_graph(
    monkeypatch: Any,
) -> None:
    """关闭运行时但指定了非默认 Profile 时，按 agent_id 取独立缓存的默认图。"""
    _set_enabled(monkeypatch, False)
    _forbid_resolve_runtime(monkeypatch)
    captured: dict[str, Any] = {}
    graph = SimpleNamespace()

    def fake_get_agent_for_runtime(runtime: Any, **kwargs: Any) -> SimpleNamespace:
        captured.update({"runtime": runtime, **kwargs})
        return graph

    def fail_get_agent() -> None:  # pragma: no cover
        raise AssertionError("非默认 Profile 不应使用进程默认图")

    monkeypatch.setattr(
        model_runtime_module, "get_agent_for_runtime", fake_get_agent_for_runtime
    )
    monkeypatch.setattr(model_runtime_module, "get_agent", fail_get_agent)

    prepared = await prepare_agent(
        resolve_profile(None).model_copy(update={"id": "alt-profile"}),
        user_id="test-user",
        thread_id="t-2",
        access_token=SecretStr("user-token"),
        requested_model=None,
    )

    assert captured == {"runtime": None, "agent_id": "alt-profile"}
    assert prepared.graph is graph
    assert prepared.runtime is None


async def test_missing_access_token_raises_unauthorized(monkeypatch: Any) -> None:
    """开启运行时后缺少访问令牌必须在解析前返回 401。"""
    _set_enabled(monkeypatch, True)
    _forbid_resolve_runtime(monkeypatch)

    with pytest.raises(AppError) as exc_info:
        await prepare_agent(
            resolve_profile(None),
            user_id="test-user",
            thread_id="t-3",
            access_token=None,
            requested_model=None,
        )

    assert exc_info.value.code == "unauthorized"
    assert exc_info.value.status_code == 401


async def test_unresolved_runtime_degrades_to_default_graph(monkeypatch: Any) -> None:
    """控制面不可达且未显式指定模型时，降级到默认图且运行时为空。"""
    _set_enabled(monkeypatch, True)
    graph = SimpleNamespace()

    async def fake_resolve_runtime(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fake_resolve_runtime)
    monkeypatch.setattr(model_runtime_module, "get_agent", lambda: graph)

    prepared = await prepare_agent(
        resolve_profile(None),
        user_id="test-user",
        thread_id="t-4",
        access_token=SecretStr("user-token"),
        requested_model=None,
    )

    assert prepared.graph is graph
    assert prepared.runtime is None


async def test_managed_credential_builds_graph_without_api_key(monkeypatch: Any) -> None:
    """托管凭证无需兑换，构图时 api_key/base_url 均为空，运行时原样透传。"""
    _set_enabled(monkeypatch, True)
    runtime = _runtime(credential_id=None, credential_source="MANAGED")
    captured: dict[str, Any] = {}
    graph = SimpleNamespace()

    async def fake_resolve_runtime(**_kwargs: Any) -> Any:
        return runtime

    async def fake_resolve_credential(_runtime: Any) -> None:
        return None

    def fake_get_agent_for_runtime(value: Any, **kwargs: Any) -> SimpleNamespace:
        captured.update({"runtime": value, **kwargs})
        return graph

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fake_resolve_runtime)
    monkeypatch.setattr(model_runtime_module, "resolve_credential", fake_resolve_credential)
    monkeypatch.setattr(
        model_runtime_module, "get_agent_for_runtime", fake_get_agent_for_runtime
    )

    prepared = await prepare_agent(
        resolve_profile(None),
        user_id="test-user",
        thread_id="t-5",
        access_token=SecretStr("user-token"),
        requested_model=None,
    )

    assert captured == {
        "runtime": runtime,
        "agent_id": "pc-config",
        "api_key": None,
        "base_url": None,
        # 生产调用不传检查点，保持进程缓存与业务库检查点不变
        "checkpointer": None,
    }
    assert prepared.runtime is runtime
    assert prepared.graph is graph


async def test_byok_credential_is_forwarded_to_graph_builder(monkeypatch: Any) -> None:
    """BYOK 兑换到的密钥与接入地址必须交给构图函数，而不是写进图配置。"""
    _set_enabled(monkeypatch, True)
    runtime = _runtime()
    captured: dict[str, Any] = {}
    graph = SimpleNamespace()

    async def fake_resolve_runtime(**_kwargs: Any) -> Any:
        return runtime

    async def fake_resolve_credential(_runtime: Any) -> Any:
        return SimpleNamespace(api_key="sk-byok-secret", base_url=runtime.base_url)

    def fake_get_agent_for_runtime(value: Any, **kwargs: Any) -> SimpleNamespace:
        captured.update({"runtime": value, **kwargs})
        return graph

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fake_resolve_runtime)
    monkeypatch.setattr(model_runtime_module, "resolve_credential", fake_resolve_credential)
    monkeypatch.setattr(
        model_runtime_module, "get_agent_for_runtime", fake_get_agent_for_runtime
    )

    prepared = await prepare_agent(
        resolve_profile(None),
        user_id="test-user",
        thread_id="t-6",
        access_token=SecretStr("user-token"),
        requested_model="openai:gpt-4o-mini",
    )

    assert captured["api_key"] == "sk-byok-secret"
    assert captured["base_url"] == "https://byok.example.com/v1"
    assert prepared.runtime is runtime


async def test_revoked_credential_invalidates_cache_and_reraises(monkeypatch: Any) -> None:
    """凭证撤销时必须清掉该凭证的缓存，并继续抛出原始业务错误。"""
    _set_enabled(monkeypatch, True)
    runtime = _runtime(credential_id="cred-1")
    invalidated: list[str] = []

    async def fake_resolve_runtime(**_kwargs: Any) -> Any:
        return runtime

    async def raise_revoked(_runtime: Any) -> Any:
        raise AppError("BYOK 凭证已撤销", code="credential_revoked", status_code=401)

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fake_resolve_runtime)
    monkeypatch.setattr(model_runtime_module, "resolve_credential", raise_revoked)
    monkeypatch.setattr(model_runtime_module, "invalidate_credential", invalidated.append)

    with pytest.raises(AppError) as exc_info:
        await prepare_agent(
            resolve_profile(None),
            user_id="test-user",
            thread_id="t-7",
            access_token=SecretStr("user-token"),
            requested_model=None,
        )

    assert exc_info.value.code == "credential_revoked"
    assert invalidated == ["cred-1"]


async def test_revoked_credential_without_id_skips_invalidation(monkeypatch: Any) -> None:
    """没有凭证标识时无从清理缓存，错误仍应原样抛出。"""
    _set_enabled(monkeypatch, True)
    runtime = _runtime(credential_id=None)
    invalidated: list[str] = []

    async def fake_resolve_runtime(**_kwargs: Any) -> Any:
        return runtime

    async def raise_revoked(_runtime: Any) -> Any:
        raise AppError("BYOK 凭证已撤销", code="credential_revoked", status_code=401)

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fake_resolve_runtime)
    monkeypatch.setattr(model_runtime_module, "resolve_credential", raise_revoked)
    monkeypatch.setattr(model_runtime_module, "invalidate_credential", invalidated.append)

    with pytest.raises(AppError) as exc_info:
        await prepare_agent(
            resolve_profile(None),
            user_id="test-user",
            thread_id="t-8",
            access_token=SecretStr("user-token"),
            requested_model=None,
        )

    assert exc_info.value.code == "credential_revoked"
    assert invalidated == []


async def test_reasoning_request_rejected_when_capability_missing(monkeypatch: Any) -> None:
    """模型没有 reasoning 能力位时，要求开启思考必须在流前 422，且不兑换凭证。"""
    _set_enabled(monkeypatch, True)
    runtime = _runtime(capabilities=("text", "tool_calling"))

    async def fake_resolve_runtime(**_kwargs: Any) -> Any:
        return runtime

    async def fail_resolve_credential(_runtime: Any) -> Any:  # pragma: no cover
        raise AssertionError("能力门控必须在兑换凭证之前失败")

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fake_resolve_runtime)
    monkeypatch.setattr(model_runtime_module, "resolve_credential", fail_resolve_credential)

    with pytest.raises(AppError) as exc_info:
        await prepare_agent(
            resolve_profile(None),
            user_id="test-user",
            thread_id="t-9",
            access_token=SecretStr("user-token"),
            requested_model="openai:gpt-4o-mini",
            reasoning=True,
        )

    assert exc_info.value.code == "capability_unsupported"
    assert exc_info.value.status_code == 422


async def test_reasoning_request_allowed_when_capability_present(monkeypatch: Any) -> None:
    """目录声明 reasoning 时放行；请求值为 False/None 时同样不拦截。"""
    _set_enabled(monkeypatch, True)
    runtime = _runtime(
        credential_id=None,
        credential_source="MANAGED",
        capabilities=("reasoning",),
    )
    graph = SimpleNamespace()

    async def fake_resolve_runtime(**_kwargs: Any) -> Any:
        return runtime

    async def fake_resolve_credential(_runtime: Any) -> None:
        return None

    monkeypatch.setattr(model_runtime_module, "resolve_runtime", fake_resolve_runtime)
    monkeypatch.setattr(model_runtime_module, "resolve_credential", fake_resolve_credential)
    monkeypatch.setattr(
        model_runtime_module, "get_agent_for_runtime",
        lambda _runtime, **_kwargs: graph,
    )

    for reasoning in (True, False, None):
        prepared = await prepare_agent(
            resolve_profile(None),
            user_id="test-user",
            thread_id="t-10",
            access_token=SecretStr("user-token"),
            requested_model="openai:gpt-4o-mini",
            reasoning=reasoning,
        )
        assert prepared.graph is graph
