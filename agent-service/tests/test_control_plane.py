"""控制面客户端测试：令牌缓存、错误映射与字段适配，不发起真实网络请求。"""

import asyncio
import json
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.services import control_plane
from app.services.control_plane import ControlPlaneClient, ControlPlaneError

TOKEN_PATH = "/internal/v1/auth/service-token"
TASKS_PATH = "/internal/v1/model-tasks"
LEASE_PATH = "/internal/v1/model-tasks/task-1/credential-lease"
ACCESS_PATH = "/internal/v1/model-access/check"
USAGE_PATH = "/internal/v1/model-usage"


def _settings(**overrides: Any) -> Settings:
    control_plane_settings: dict[str, Any] = {
        "base_url": "https://control-plane.example.com",
        "client_id": "agent-service",
        "client_secret": "test-internal-secret",
        "timeout_seconds": 5,
    }
    control_plane_settings.update(overrides.pop("control_plane", {}))
    return Settings(
        _env_file=None,
        control_plane=control_plane_settings,
        **overrides,
    )


def _ok(data: Any) -> httpx.Response:
    """Java 统一信封的成功响应。"""
    return httpx.Response(200, json={"code": 0, "message": "ok", "data": data})


def _error(status_code: int, code: int, error_type: str, data: Any = None) -> httpx.Response:
    payload: dict[str, Any] = {"code": code, "errorType": error_type, "message": "boom"}
    if data is not None:
        payload["data"] = data
    return httpx.Response(status_code, json=payload)


def _token_response(expires_in: int = 3600) -> httpx.Response:
    return _ok(
        {"accessToken": "service-token-value", "tokenType": "Bearer", "expiresIn": expires_in}
    )


class RecordingTransport(httpx.AsyncBaseTransport):
    """记录请求并按路径返回预设响应，便于断言请求形状。"""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._handlers: dict[str, httpx.Response] = {}

    def route(self, path: str, response: httpx.Response) -> None:
        self._handlers[path] = response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self._handlers.get(request.url.path)
        if handler is None:
            raise httpx.ConnectError("unexpected path", request=request)
        return handler


def _make_client(settings: Settings, transport: RecordingTransport) -> ControlPlaneClient:
    return ControlPlaneClient(settings, client=httpx.AsyncClient(transport=transport))


async def test_service_token_is_fetched_once_and_cached() -> None:
    """并发获取只换取一次令牌，避免高峰期反复调用 Java。"""
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response())
    client = _make_client(_settings(), transport)

    tokens = await asyncio.gather(
        client.get_service_token(), client.get_service_token(), client.get_service_token()
    )

    assert tokens == ["service-token-value"] * 3
    assert len([r for r in transport.requests if r.url.path == TOKEN_PATH]) == 1
    await client.aclose()


async def test_service_token_refreshes_before_expiry() -> None:
    """有效期很短时刷新窗口已过，第二次调用必须重新换取。"""
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response(expires_in=4))
    client = _make_client(_settings(), transport)

    await client.get_service_token()
    await client.get_service_token()

    assert len([r for r in transport.requests if r.url.path == TOKEN_PATH]) == 2
    await client.aclose()


async def test_missing_client_secret_reports_unavailable() -> None:
    """未配置凭据时不允许出站，直接返回控制面不可用。"""
    client = _make_client(_settings(control_plane={"client_secret": ""}), RecordingTransport())

    with pytest.raises(ControlPlaneError) as exc_info:
        await client.get_service_token()

    assert exc_info.value.code == control_plane.CONTROL_PLANE_UNAVAILABLE
    assert exc_info.value.status_code == 503


async def test_create_task_sends_expected_headers_and_body() -> None:
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response())
    transport.route(
        TASKS_PATH,
        _ok(
            {
                "taskId": "task-1",
                "provider": "openai",
                "modelKey": "openai:gpt-4o-mini",
                "credentialSource": "MANAGED",
                "expiresAt": "2026-10-30T09:00:00Z",
            }
        ),
    )
    client = _make_client(_settings(), transport)

    task = await client.create_task(
        user_token="user-token-value", thread_id="t-demo", requested_model="openai:gpt-4o-mini"
    )

    assert task.task_id == "task-1"
    assert task.model_key == "openai:gpt-4o-mini"
    assert task.credential_source == "MANAGED"

    task_request = next(r for r in transport.requests if r.url.path == TASKS_PATH)
    assert task_request.headers["Authorization"] == "Bearer service-token-value"
    assert task_request.headers[control_plane.USER_TOKEN_HEADER] == "user-token-value"
    assert json.loads(task_request.content) == {
        "threadId": "t-demo",
        "model": "openai:gpt-4o-mini",
    }
    await client.aclose()


async def test_create_task_sends_idempotency_key_when_provided() -> None:
    """幂等键随请求头下发，Java 据此复用既有任务；缺省时不下发该头。"""
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response())
    transport.route(
        TASKS_PATH,
        _ok(
            {
                "taskId": "task-1",
                "provider": "openai",
                "modelKey": "openai:gpt-4o-mini",
                "credentialSource": "MANAGED",
                "expiresAt": "2026-10-30T09:00:00Z",
            }
        ),
    )
    client = _make_client(_settings(), transport)

    await client.create_task(
        user_token="u", thread_id="t-demo", requested_model=None, idempotency_key="idem-1"
    )
    second = await client.create_task(user_token="u", thread_id="t-demo", requested_model=None)

    # 旧版 Java 不回传 capabilities 时按空元组处理，不能因此让整次请求失败
    assert second.capabilities == ()

    requests = [r for r in transport.requests if r.url.path == TASKS_PATH]
    assert requests[0].headers[control_plane.IDEMPOTENCY_KEY_HEADER] == "idem-1"
    assert control_plane.IDEMPOTENCY_KEY_HEADER not in requests[1].headers
    await client.aclose()


async def test_create_task_parses_byok_fields() -> None:
    """BYOK 任务必须带出 credentialId 与 baseUrl；MANAGED 时两者为空。"""
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response())
    transport.route(
        TASKS_PATH,
        _ok(
            {
                "taskId": "task-1",
                "provider": "openai",
                "modelKey": "openai:gpt-4o-mini",
                "credentialSource": "BYOK",
                "credentialId": "cred-1",
                "baseUrl": "https://byok.example.com/v1",
                "expiresAt": "2026-10-30T09:00:00Z",
            }
        ),
    )
    client = _make_client(_settings(), transport)

    task = await client.create_task(user_token="u", thread_id="t-demo", requested_model=None)

    assert task.credential_source == "BYOK"
    assert task.credential_id == "cred-1"
    assert task.base_url == "https://byok.example.com/v1"
    await client.aclose()


async def test_create_task_parses_capabilities() -> None:
    """目录能力位必须随任务解析出来，Agent 靠它做请求侧门控。"""
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response())
    transport.route(
        TASKS_PATH,
        _ok(
            {
                "taskId": "task-1",
                "provider": "deepseek",
                "modelKey": "deepseek:deepseek-v4-pro",
                "credentialSource": "MANAGED",
                "expiresAt": "2026-10-30T09:00:00Z",
                "capabilities": ["text", "reasoning", "reasoning_visible"],
            }
        ),
    )
    client = _make_client(_settings(), transport)

    task = await client.create_task(user_token="u", thread_id="t-demo", requested_model=None)

    assert task.capabilities == ("text", "reasoning", "reasoning_visible")
    await client.aclose()


async def test_lease_credential_uses_service_token_only() -> None:
    """兑换只带服务令牌：用户身份已由任务创建阶段绑定，避免重复信任请求头。"""
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response())
    transport.route(
        LEASE_PATH,
        _ok({"credentialType": "api_key", "secret": "sk-byok-secret", "expiresIn": 600}),
    )
    client = _make_client(_settings(), transport)

    lease = await client.lease_credential(task_id="task-1")

    assert lease.credential_type == "api_key"
    assert lease.secret == "sk-byok-secret"
    assert lease.expires_in == 600

    lease_request = next(r for r in transport.requests if r.url.path == LEASE_PATH)
    assert lease_request.headers["Authorization"] == "Bearer service-token-value"
    assert control_plane.USER_TOKEN_HEADER not in lease_request.headers
    # 明文密钥不得出现在对象打印结果里
    assert "sk-byok-secret" not in repr(lease)
    assert "sk-byok-secret" not in str(lease)
    await client.aclose()


async def test_lease_credential_rejects_invalid_expiry() -> None:
    """兑换响应必须自带有效期；缺失或非法说明契约被破坏，不能当作成功。"""
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response())
    transport.route(
        LEASE_PATH,
        _ok({"credentialType": "api_key", "secret": "sk-byok-secret"}),
    )
    client = _make_client(_settings(), transport)

    with pytest.raises(ControlPlaneError) as exc_info:
        await client.lease_credential(task_id="task-1")

    assert exc_info.value.code == control_plane.UPSTREAM_ERROR
    await client.aclose()


@pytest.mark.parametrize(
    ("status_code", "java_code", "error_type", "expected_code", "expected_status"),
    [
        (429, 40201, "quota_exceeded", control_plane.QUOTA_EXCEEDED, 429),
        (403, 40202, "model_not_available", control_plane.MODEL_NOT_AVAILABLE, 403),
        (422, 40203, "capability_unsupported", control_plane.CAPABILITY_UNSUPPORTED, 422),
        (503, 50001, "dependency_unavailable", control_plane.CONTROL_PLANE_UNAVAILABLE, 503),
        (409, 40215, "credential_lease_consumed", control_plane.CREDENTIAL_LEASE_CONSUMED, 409),
        (401, 40216, "credential_revoked", control_plane.CREDENTIAL_REVOKED, 401),
        (409, 40218, "lease_not_byok", control_plane.LEASE_NOT_BYOK, 409),
        (422, 40219, "credential_rejected", control_plane.CREDENTIAL_REJECTED, 422),
        (409, 40220, "idempotency_conflict", control_plane.IDEMPOTENCY_CONFLICT, 409),
        (400, 40208, "model_reference_invalid", control_plane.UPSTREAM_ERROR, 503),
    ],
)
async def test_error_codes_map_to_agent_strings(
    status_code: int,
    java_code: int,
    error_type: str,
    expected_code: str,
    expected_status: int,
) -> None:
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response())
    transport.route(TASKS_PATH, _error(status_code, java_code, error_type))
    client = _make_client(_settings(), transport)

    with pytest.raises(ControlPlaneError) as exc_info:
        await client.create_task(user_token="u", thread_id="t", requested_model=None)

    assert exc_info.value.code == expected_code
    assert exc_info.value.status_code == expected_status
    await client.aclose()


async def test_quota_error_carries_snake_case_payload() -> None:
    """额度详情从 Java camelCase 转成 Agent snake_case，字段缺失不伪造。"""
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response())
    transport.route(
        TASKS_PATH,
        _error(
            429,
            40201,
            "quota_exceeded",
            {
                "quotaType": "daily_requests",
                "limit": 100,
                "used": 100,
                "resetAt": "2026-10-31T00:00:00Z",
            },
        ),
    )
    client = _make_client(_settings(), transport)

    with pytest.raises(ControlPlaneError) as exc_info:
        await client.create_task(user_token="u", thread_id="t", requested_model=None)

    assert exc_info.value.quota == {
        "quota_type": "daily_requests",
        "limit": 100,
        "used": 100,
        "reset_at": "2026-10-31T00:00:00Z",
    }
    assert exc_info.value.is_retryable is True
    await client.aclose()


async def test_network_failure_maps_to_retryable_unavailable() -> None:
    """连接失败统一收敛，异常文本不携带上游地址。"""
    transport = RecordingTransport()
    client = _make_client(_settings(), transport)

    with pytest.raises(ControlPlaneError) as exc_info:
        await client.get_service_token()

    assert exc_info.value.code == control_plane.CONTROL_PLANE_UNAVAILABLE
    assert exc_info.value.is_retryable is True
    assert "https://" not in str(exc_info.value)
    await client.aclose()


async def test_non_json_response_maps_to_upstream_error() -> None:
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, httpx.Response(200, text="<html>gateway</html>"))
    client = _make_client(_settings(), transport)

    with pytest.raises(ControlPlaneError) as exc_info:
        await client.get_service_token()

    assert exc_info.value.code == control_plane.UPSTREAM_ERROR
    await client.aclose()


async def test_check_model_access_parses_capabilities() -> None:
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response())
    transport.route(
        ACCESS_PATH,
        _ok(
            {
                "available": True,
                "provider": "openai",
                "modelKey": "openai:gpt-4o-mini",
                "displayName": "GPT-4o mini",
                "capabilities": ["text", "tool_calling"],
                "contextWindow": 128000,
            }
        ),
    )
    client = _make_client(_settings(), transport)

    availability = await client.check_model_access(user_token="u", model_key="openai:gpt-4o-mini")

    assert availability.capabilities == ("text", "tool_calling")
    assert availability.context_window == 128000
    await client.aclose()


async def test_report_usage_maps_records_to_camel_case() -> None:
    """上报字段只在 Adapter 层转 camelCase，上层保持 snake_case。"""
    transport = RecordingTransport()
    transport.route(TOKEN_PATH, _token_response())
    transport.route(USAGE_PATH, _ok({"accepted": 1, "duplicated": 0, "rejected": 0}))
    client = _make_client(_settings(), transport)

    result = await client.report_usage(
        [
            {
                "invocation_id": "inv-1",
                "task_id": "task-1",
                "model_role": "conversation",
                "provider": "openai",
                "model_key": "openai:gpt-4o-mini",
                "credential_source": "MANAGED",
                "prompt_tokens": None,
                "completion_tokens": 12,
                "latency_ms": 850,
                "status": "success",
                "error_type": None,
                "occurred_at": "2026-10-30T08:00:00Z",
            }
        ]
    )

    assert result["accepted"] == 1
    usage_request = next(r for r in transport.requests if r.url.path == USAGE_PATH)
    payload = json.loads(usage_request.content)
    assert payload["records"][0]["invocationId"] == "inv-1"
    assert payload["records"][0]["promptTokens"] is None
    assert payload["records"][0]["completionTokens"] == 12
    assert usage_request.headers["Authorization"] == "Bearer service-token-value"
    assert control_plane.USER_TOKEN_HEADER not in usage_request.headers
    await client.aclose()


async def test_report_usage_with_empty_batch_skips_network() -> None:
    transport = RecordingTransport()
    client = _make_client(_settings(), transport)

    assert await client.report_usage([]) == {}
    assert transport.requests == []
    await client.aclose()


def test_module_singleton_helpers() -> None:
    """单例只在首次访问时按配置构造，重置后可重新创建。"""
    control_plane.reset_control_plane_client()
    first = control_plane.get_control_plane_client()
    assert control_plane.get_control_plane_client() is first
    control_plane.reset_control_plane_client()
    assert control_plane.get_control_plane_client() is not first


def test_client_secret_never_appears_in_settings_repr() -> None:
    """服务令牌凭据只允许留在配置对象内部；repr/str 若泄露就会被日志直接带出。"""
    secret = "plain-secret-for-repr-check"
    settings = _settings(control_plane={"client_secret": secret})

    assert settings.control_plane.client_secret is not None
    assert secret not in repr(settings)
    assert secret not in str(settings)
    assert secret not in repr(settings.control_plane)
    assert secret not in str(settings.control_plane)
