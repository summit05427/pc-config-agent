"""真实服务客户端：登录、SSE 对话与会话查询/清理。

设计约束：
1. Token 只在内存中保存，禁止写入日志或报告；
2. Java 访问令牌默认 600 秒过期，按 `expiresIn` 提前续期，401 时再重登一次；
3. 只做协议封装，不做断言：断言在 `contract.py`，便于直接单测。
"""

from __future__ import annotations

from time import monotonic
from typing import Any

import httpx
from pydantic import SecretStr

from evals.e2e.sse import SseFrame, parse_frames

JAVA_LOGIN_PATH = "/api/v1/auth/login"
AGENT_CHAT_PATH = "/api/v1/chat/stream"
AGENT_SESSIONS_PATH = "/api/v1/sessions"
# 服务端令牌默认有效期 600 秒；提前续期，避免请求正好卡在过期瞬间
TOKEN_REFRESH_MARGIN_SECONDS = 30
# 失败时回显响应片段的长度上限；错误体可能包含内部信息，只用于报告定位
ERROR_BODY_CHARS = 300
MAX_SESSION_PAGE_SIZE = 100


class E2EClientError(RuntimeError):
    """网络、登录或接口错误；由 runner 转成用例失败原因，不中断整轮。"""


class E2EUsageError(RuntimeError):
    """缺少必要配置（如登录口令）；属于用法错误，退出码 2。"""


class StreamResult:
    """一次 SSE 请求的结果；非 2xx 时只保留错误体，不解析事件。"""

    def __init__(
        self,
        status_code: int,
        headers: dict[str, str],
        frames: tuple[SseFrame, ...],
        body: str = "",
    ) -> None:
        self.status_code = status_code
        self.headers = headers
        self.frames = frames
        self.body = body


class ServiceClient:
    """面向已启动四端的同步客户端；评测是低频人工操作，不需要异步并发。"""

    def __init__(
        self,
        *,
        agent_base_url: str,
        java_base_url: str,
        username: str,
        password: SecretStr,
        timeout_seconds: float,
    ) -> None:
        self._agent_base_url = agent_base_url.rstrip("/")
        self._java_base_url = java_base_url.rstrip("/")
        self._username = username
        self._password = password
        self._timeout = httpx.Timeout(
            connect=10.0,
            read=timeout_seconds,
            write=30.0,
            pool=10.0,
        )
        self._http = httpx.Client(timeout=self._timeout)
        self._token: str | None = None
        self._token_expires_at = 0.0

    def close(self) -> None:
        self._http.close()

    def login(self) -> str:
        """调用 Java 登录取访问令牌；响应是统一信封，取出 `data.accessToken`。"""
        try:
            response = self._http.post(
                f"{self._java_base_url}{JAVA_LOGIN_PATH}",
                json={
                    "username": self._username,
                    "password": self._password.get_secret_value(),
                },
            )
        except httpx.HTTPError as exc:
            raise E2EClientError(f"登录请求失败：{type(exc).__name__}") from exc

        if response.status_code != httpx.codes.OK:
            raise E2EClientError(
                f"登录失败：HTTP {response.status_code} {_body_preview(response)}"
            )
        data = _unwrap_java_envelope(response)
        access_token = data.get("accessToken")
        if not isinstance(access_token, str) or not access_token:
            raise E2EClientError("登录响应缺少 accessToken")
        expires_in = data.get("expiresIn")
        lifetime = expires_in if isinstance(expires_in, int) and expires_in > 0 else 600
        self._token = access_token
        self._token_expires_at = monotonic() + max(
            lifetime - TOKEN_REFRESH_MARGIN_SECONDS, TOKEN_REFRESH_MARGIN_SECONDS
        )
        return access_token

    def _ensure_token(self) -> str:
        if self._token is None or monotonic() >= self._token_expires_at:
            return self.login()
        return self._token

    def stream_chat(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> StreamResult:
        """发起一轮对话并读取完整 SSE；401 时重登一次后重试。"""
        headers = {
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {self._ensure_token()}",
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        url = f"{self._agent_base_url}{AGENT_CHAT_PATH}"

        for attempt in (0, 1):
            try:
                with self._http.stream(
                    "POST", url, json=payload, headers=headers
                ) as response:
                    if response.status_code == httpx.codes.UNAUTHORIZED and attempt == 0:
                        # 令牌可能在上一轮执行期间过期：续期后重试一次
                        headers["Authorization"] = f"Bearer {self.login()}"
                        continue
                    if response.status_code >= httpx.codes.BAD_REQUEST:
                        return StreamResult(
                            response.status_code,
                            dict(response.headers),
                            (),
                            _stream_body_preview(response),
                        )
                    frames = tuple(parse_frames(response.iter_lines()))
                    return StreamResult(response.status_code, dict(response.headers), frames)
            except httpx.HTTPError as exc:
                raise E2EClientError(
                    f"对话请求失败：{type(exc).__name__}"
                ) from exc

        raise E2EClientError("对话请求在重新登录后仍返回 401")

    def list_sessions(self) -> dict[str, Any]:
        return self._get_json(AGENT_SESSIONS_PATH, params={"size": MAX_SESSION_PAGE_SIZE})

    def list_messages(self, thread_id: str) -> dict[str, Any]:
        return self._get_json(f"{AGENT_SESSIONS_PATH}/{thread_id}/messages")

    def delete_session(self, thread_id: str) -> bool:
        """删除会话并清理服务端数据；404 视为已清理，便于重复运行。"""
        response = self._request("DELETE", f"{AGENT_SESSIONS_PATH}/{thread_id}")
        return response.status_code in (httpx.codes.NO_CONTENT, httpx.codes.NOT_FOUND)

    def _get_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._request("GET", path, **kwargs)
        if response.status_code != httpx.codes.OK:
            raise E2EClientError(
                f"{path} 返回 HTTP {response.status_code} {_body_preview(response)}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise E2EClientError(f"{path} 响应不是 JSON 对象")
        return payload

    def _request(
        self,
        method: str,
        path: str,
        *,
        allow_404: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        """普通 JSON 请求；401 时重登一次，其余错误交给调用方判断状态码。"""
        for attempt in (0, 1):
            headers = {"Authorization": f"Bearer {self._ensure_token()}"}
            try:
                response = self._http.request(
                    method,
                    f"{self._agent_base_url}{path}",
                    headers=headers,
                    **kwargs,
                )
            except httpx.HTTPError as exc:
                raise E2EClientError(f"{path} 请求失败：{type(exc).__name__}") from exc
            if response.status_code == httpx.codes.UNAUTHORIZED and attempt == 0:
                self.login()
                continue
            return response
        raise E2EClientError(f"{path} 在重新登录后仍返回 401")


def _unwrap_java_envelope(response: httpx.Response) -> dict[str, Any]:
    """Java 成功响应使用 `{code, message, data}` 信封；兼容裸 JSON 便于本地调试。"""
    try:
        payload = response.json()
    except ValueError as exc:
        raise E2EClientError("登录响应不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise E2EClientError("登录响应不是 JSON 对象")
    if "accessToken" in payload:
        return payload
    code = payload.get("code")
    if code not in (0, "0"):
        message = payload.get("message")
        raise E2EClientError(f"登录被拒绝：code={code} message={message}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise E2EClientError("登录响应缺少 data")
    return data


def _body_preview(response: httpx.Response) -> str:
    try:
        text = response.text
    except Exception:  # pragma: no cover - 防御已关闭/未读取的响应
        return ""
    return text[:ERROR_BODY_CHARS].replace("\n", " ")


def _stream_body_preview(response: httpx.Response) -> str:
    """流式响应出错时读取少量字节；错误体是裸 JSON 或空。"""
    try:
        return response.read().decode("utf-8", "replace")[:ERROR_BODY_CHARS].replace(
            "\n", " "
        )
    except Exception:  # pragma: no cover - 连接已断开时无法读取
        return ""
