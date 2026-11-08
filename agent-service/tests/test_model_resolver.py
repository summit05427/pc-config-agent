"""模型运行时解析测试：顺序、降级与错误透传，不发起真实网络请求。"""

from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.services import control_plane, model_resolver
from app.services.control_plane import ControlPlaneError, ModelTask
from app.services.model_resolver import (
    ResolvedRuntime,
    derive_task_idempotency_key,
    resolve_credential,
    resolve_runtime,
)


def _settings(enabled: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        model_runtime={"enabled": enabled},
        control_plane={"client_secret": "test-internal-secret"},
    )


def _task(
    credential_source: str = "MANAGED",
    credential_id: str | None = None,
    base_url: str | None = None,
) -> ModelTask:
    return ModelTask(
        task_id="task-1",
        provider="openai",
        model_key="openai:gpt-4o-mini",
        credential_source=credential_source,
        expires_at="2026-10-30T09:00:00Z",
        credential_id=credential_id,
        base_url=base_url,
    )


class FakeClient:
    """按预设返回结果，并记录调用参数。"""

    def __init__(self, *, task: ModelTask | None = None, error: Exception | None = None) -> None:
        self._task = task
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def create_task(
        self,
        *,
        user_token: str,
        thread_id: str,
        requested_model: str | None,
        idempotency_key: str | None = None,
    ) -> ModelTask:
        self.calls.append(
            {
                "user_token": user_token,
                "thread_id": thread_id,
                "requested_model": requested_model,
                "idempotency_key": idempotency_key,
            }
        )
        if self._error is not None:
            raise self._error
        assert self._task is not None
        return self._task


def test_derive_task_idempotency_key_is_scoped_and_stable() -> None:
    """同一用户同一会话同一客户端键必须得到同一个键，换任一维度都要变化。"""
    base = derive_task_idempotency_key("u-1", "t-1", "client-key-1")

    assert base == derive_task_idempotency_key("u-1", "t-1", "client-key-1")
    assert len(base) == model_resolver.TASK_IDEMPOTENCY_KEY_LENGTH
    assert base != derive_task_idempotency_key("u-2", "t-1", "client-key-1")
    assert base != derive_task_idempotency_key("u-1", "t-2", "client-key-1")
    assert base != derive_task_idempotency_key("u-1", "t-1", "client-key-2")


def test_derive_task_idempotency_key_without_client_key_is_unique() -> None:
    """缺少客户端键时退化为一次性随机键，至少满足 Java 的 64 位上限。"""
    first = derive_task_idempotency_key("u-1", "t-1", None)
    second = derive_task_idempotency_key("u-1", "t-1", None)

    assert first != second
    assert len(first) <= 64


async def test_resolve_runtime_passes_derived_idempotency_key() -> None:
    """派生出的幂等键必须透传给控制面，Java 才能做任务级去重。"""
    client = FakeClient(task=_task())

    await resolve_runtime(
        user_id="u-1",
        thread_id="t-1",
        user_token="user-token",
        requested_model=None,
        client_idempotency_key="client-key-1",
        settings=_settings(),
        client=client,
    )

    assert client.calls[0]["idempotency_key"] == derive_task_idempotency_key(
        "u-1", "t-1", "client-key-1"
    )


async def test_disabled_runtime_makes_no_outbound_call() -> None:
    """关闭模型运行时时直接返回 None，行为与旧版一致。"""
    client = FakeClient(task=_task())

    result = await resolve_runtime(
        user_id="u-1",
        thread_id="t-1",
        user_token="user-token",
        requested_model="openai:gpt-4o-mini",
        settings=_settings(enabled=False),
        client=client,
    )

    assert result is None
    assert client.calls == []


async def test_request_model_takes_precedence_over_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """请求级 model 优先，命中时不再读会话配置。"""
    calls: list[tuple[str, str]] = []

    async def fake_session_key(user_id: str, thread_id: str) -> str | None:
        calls.append((user_id, thread_id))
        return "openai:gpt-4o"

    monkeypatch.setattr(
        model_resolver,
        "get_session_store",
        lambda: SimpleNamespace(get_model_key=fake_session_key),
    )
    client = FakeClient(task=_task())

    await resolve_runtime(
        user_id="u-1",
        thread_id="t-1",
        user_token="user-token",
        requested_model="openai:gpt-4o-mini",
        settings=_settings(),
        client=client,
    )

    assert calls == []
    assert client.calls[0]["requested_model"] == "openai:gpt-4o-mini"


async def test_profile_default_model_is_used_when_request_and_session_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """请求与会话都没指定时，使用 Profile 默认模型，并按显式模型处理。"""

    async def fake_session_key(user_id: str, thread_id: str) -> str | None:
        return None

    monkeypatch.setattr(
        model_resolver,
        "get_session_store",
        lambda: SimpleNamespace(get_model_key=fake_session_key),
    )
    client = FakeClient(task=_task())

    await resolve_runtime(
        user_id="u-1",
        thread_id="t-1",
        user_token="user-token",
        requested_model=None,
        default_model="openai:gpt-4o-mini",
        settings=_settings(),
        client=client,
    )

    assert client.calls[0]["requested_model"] == "openai:gpt-4o-mini"


async def test_session_model_takes_precedence_over_profile_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """会话级选择应覆盖 Profile 默认值，只有前两者都缺失才落到 Profile。"""

    async def fake_session_key(user_id: str, thread_id: str) -> str | None:
        return "openai:gpt-4o"

    monkeypatch.setattr(
        model_resolver,
        "get_session_store",
        lambda: SimpleNamespace(get_model_key=fake_session_key),
    )
    client = FakeClient(task=_task())

    await resolve_runtime(
        user_id="u-1",
        thread_id="t-1",
        user_token="user-token",
        requested_model=None,
        default_model="deepseek:deepseek-v4-pro",
        settings=_settings(),
        client=client,
    )

    assert client.calls[0]["requested_model"] == "openai:gpt-4o"


async def test_session_model_is_used_when_request_has_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_session_key(user_id: str, thread_id: str) -> str | None:
        return "openai:gpt-4o"

    monkeypatch.setattr(
        model_resolver,
        "get_session_store",
        lambda: SimpleNamespace(get_model_key=fake_session_key),
    )
    client = FakeClient(task=_task())

    await resolve_runtime(
        user_id="u-1",
        thread_id="t-1",
        user_token="user-token",
        requested_model=None,
        settings=_settings(),
        client=client,
    )

    assert client.calls[0]["requested_model"] == "openai:gpt-4o"


async def test_managed_task_returns_runtime_with_model_key() -> None:
    client = FakeClient(task=_task())

    runtime = await resolve_runtime(
        user_id="u-1",
        thread_id="t-1",
        user_token="user-token",
        requested_model=None,
        settings=_settings(),
        client=client,
    )

    assert isinstance(runtime, ResolvedRuntime)
    assert runtime.task_id == "task-1"
    assert runtime.credential_source == "MANAGED"
    assert runtime.credential_id is None
    # 模型标识原样保留，前缀由网关解析，Agent 不再截断
    assert runtime.model_key == "openai:gpt-4o-mini"


async def test_model_key_without_provider_prefix_is_returned_as_is() -> None:
    """兼容 Java 未来返回裸模型名的情况，不做字符串截断。"""
    task = ModelTask(
        task_id="task-1",
        provider="openai",
        model_key="gpt-4o-mini",
        credential_source="MANAGED",
        expires_at=None,
    )
    runtime = ResolvedRuntime(
        task_id=task.task_id,
        provider=task.provider,
        model_key=task.model_key,
        credential_source=task.credential_source,
    )

    assert runtime.model_key == "gpt-4o-mini"


async def test_control_plane_unavailable_degrades_to_default() -> None:
    """控制面不可达时 Auto/Managed 显式降级，而不是让整条对话失败。"""
    client = FakeClient(
        error=ControlPlaneError(
            control_plane.CONTROL_PLANE_UNAVAILABLE,
            503,
            "unavailable",
            is_retryable=True,
        )
    )

    result = await resolve_runtime(
        user_id="u-1",
        thread_id="t-1",
        user_token="user-token",
        requested_model=None,
        settings=_settings(),
        client=client,
    )

    assert result is None


async def test_control_plane_unavailable_does_not_degrade_explicit_model() -> None:
    """显式指定模型时控制面不可达必须报 503，不能静默换成进程默认模型。"""
    client = FakeClient(
        error=ControlPlaneError(
            control_plane.CONTROL_PLANE_UNAVAILABLE,
            503,
            "unavailable",
            is_retryable=True,
        )
    )

    with pytest.raises(AppError) as exc_info:
        await resolve_runtime(
            user_id="u-1",
            thread_id="t-1",
            user_token="user-token",
            requested_model="openai:gpt-4o-mini",
            settings=_settings(),
            client=client,
        )

    assert exc_info.value.code == control_plane.CONTROL_PLANE_UNAVAILABLE
    assert exc_info.value.status_code == 503


@pytest.mark.parametrize(
    ("code", "status_code", "quota"),
    [
        (control_plane.QUOTA_EXCEEDED, 429, {"quota_type": "daily_requests", "limit": 100}),
        (control_plane.MODEL_NOT_AVAILABLE, 403, None),
        (control_plane.CAPABILITY_UNSUPPORTED, 422, None),
        (control_plane.IDEMPOTENCY_CONFLICT, 409, None),
        (control_plane.UPSTREAM_ERROR, 503, None),
    ],
)
async def test_deterministic_errors_are_propagated(
    code: str, status_code: int, quota: dict[str, Any] | None
) -> None:
    """确定性错误必须原样抛出，不能静默降级。"""
    client = FakeClient(
        error=ControlPlaneError(code, status_code, "failed", quota=quota)
    )

    with pytest.raises(AppError) as exc_info:
        await resolve_runtime(
            user_id="u-1",
            thread_id="t-1",
            user_token="user-token",
            requested_model=None,
            settings=_settings(),
            client=client,
        )

    assert exc_info.value.code == code
    assert exc_info.value.status_code == status_code
    if quota is not None:
        assert exc_info.value.extra == {"quota": quota}
    else:
        assert exc_info.value.extra is None


async def test_byok_task_carries_credential_and_base_url() -> None:
    """BYOK 任务必须带上凭证标识与接入地址，供后续 lease 与模型装配使用。"""
    client = FakeClient(
        task=_task(
            credential_source="BYOK",
            credential_id="cred-1",
            base_url="https://byok.example.com/v1",
        )
    )

    runtime = await resolve_runtime(
        user_id="u-1",
        thread_id="t-1",
        user_token="user-token",
        requested_model=None,
        settings=_settings(),
        client=client,
    )

    assert runtime is not None
    assert runtime.is_byok is True
    assert runtime.credential_id == "cred-1"
    assert runtime.base_url == "https://byok.example.com/v1"


async def test_byok_task_without_credential_id_is_rejected() -> None:
    """契约被破坏时不能退回平台凭证，否则费用与归属都会记错。"""
    client = FakeClient(task=_task(credential_source="BYOK", credential_id=None))

    with pytest.raises(AppError) as exc_info:
        await resolve_runtime(
            user_id="u-1",
            thread_id="t-1",
            user_token="user-token",
            requested_model=None,
            settings=_settings(),
            client=client,
        )

    assert exc_info.value.code == control_plane.CREDENTIAL_REVOKED
    assert exc_info.value.status_code == 401


class FakeLeaseClient:
    """记录 lease 调用；可预设错误，用于验证错误透传。"""

    def __init__(
        self,
        *,
        lease: control_plane.CredentialLease | None = None,
        error: Exception | None = None,
    ) -> None:
        self._lease = lease
        self._error = error
        self.calls: list[str] = []

    async def lease_credential(self, *, task_id: str) -> control_plane.CredentialLease:
        self.calls.append(task_id)
        if self._error is not None:
            raise self._error
        assert self._lease is not None
        return self._lease


def _byok_runtime() -> ResolvedRuntime:
    return ResolvedRuntime(
        task_id="task-1",
        provider="openai",
        model_key="openai:gpt-4o-mini",
        credential_source="BYOK",
        credential_id="cred-1",
        base_url="https://byok.example.com/v1",
    )


async def test_resolve_credential_leases_byok_task() -> None:
    """BYOK 兑换返回明文凭证，但对象打印时必须隐藏密钥。"""
    lease = control_plane.CredentialLease(
        credential_type="api_key", secret="sk-byok-secret", expires_in=600
    )
    client = FakeLeaseClient(lease=lease)

    credential = await resolve_credential(_byok_runtime(), client=client)

    assert credential is not None
    assert credential.api_key == "sk-byok-secret"
    assert credential.base_url == "https://byok.example.com/v1"
    assert client.calls == ["task-1"]
    assert "sk-byok-secret" not in repr(credential)
    assert "sk-byok-secret" not in repr(lease)


async def test_resolve_credential_skips_managed_task() -> None:
    """MANAGED 任务不需要兑换，也不得发起任何出站请求。"""
    client = FakeLeaseClient(
        lease=control_plane.CredentialLease(credential_type="api_key", secret="unused")
    )

    credential = await resolve_credential(_runtime_managed(), client=client)

    assert credential is None
    assert client.calls == []


def _runtime_managed() -> ResolvedRuntime:
    return ResolvedRuntime(
        task_id="task-1",
        provider="openai",
        model_key="openai:gpt-4o-mini",
        credential_source="MANAGED",
    )


async def test_resolve_credential_maps_revoked_to_unauthorized() -> None:
    """凭证撤销后 lease 返回 401，调用方据此在流建立前中止请求。"""
    client = FakeLeaseClient(
        error=ControlPlaneError(control_plane.CREDENTIAL_REVOKED, 401, "revoked")
    )

    with pytest.raises(AppError) as exc_info:
        await resolve_credential(_byok_runtime(), client=client)

    assert exc_info.value.code == control_plane.CREDENTIAL_REVOKED
    assert exc_info.value.status_code == 401
