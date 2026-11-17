"""Java PC 配置内部接口客户端（`/internal/v1/pc/**`）。

职责边界：
1. 服务令牌复用控制面客户端的缓存与单飞刷新，不重复实现换取逻辑；
2. 用户维度接口额外携带 `X-User-Token`，令牌只出现在请求头；
3. 统一解析 Java 信封并映射错误，供工具层转成安全文案。

工具层只调用本客户端的具名方法，禁止在节点里直接使用 httpx。
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from app.core.config import Settings, get_settings
from app.services.control_plane import (
    ControlPlaneClient,
    _network_error,
    _read_data,
    get_control_plane_client,
)

PC_CANDIDATES_PATH = "/internal/v1/pc/hardware/candidates"
PC_BENCHMARKS_PATH = "/internal/v1/pc/benchmarks"
PC_OFFERS_PATH = "/internal/v1/pc/offers"
PC_COMPOSE_PATH = "/internal/v1/pc/builds/compose"
PC_VALIDATE_PARTIAL_PATH = "/internal/v1/pc/builds/validate-partial"
PC_BUILD_PATH = "/internal/v1/pc/builds"

# 组装会落快照，耗时高于普通查询；超时下限单独放宽
PC_REQUEST_TIMEOUT_SECONDS = 20.0


class PcApiClient:
    """PC 内部接口客户端；所有响应都是 Java 信封里的 `data`。"""

    def __init__(
        self,
        settings: Settings,
        control_plane: ControlPlaneClient,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._control_plane = control_plane
        self._base_url = settings.control_plane.base_url.rstrip("/")
        self._timeout = max(
            settings.control_plane.timeout_seconds, PC_REQUEST_TIMEOUT_SECONDS
        )
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def _headers(self, user_token: str | None) -> dict[str, str]:
        service_token = await self._control_plane.get_service_token()
        return self._control_plane._authorized_headers(service_token, user_token)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        user_token: str | None = None,
        params: Mapping[str, str | int | bool | None] | None = None,
        json: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            response = await self._http().request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=json,
                headers=await self._headers(user_token),
            )
        except httpx.HTTPError:
            raise _network_error() from None
        return _read_data(response)

    async def list_candidates(self, *, category: str | None) -> dict[str, object]:
        params = {"category": category} if category else None
        return await self._request("GET", PC_CANDIDATES_PATH, params=params)

    async def list_benchmarks(
        self, *, hardware_id: str | None, category: str | None
    ) -> dict[str, object]:
        params: dict[str, str] = {}
        if hardware_id:
            params["hardwareId"] = hardware_id
        if category:
            params["category"] = category
        return await self._request(
            "GET", PC_BENCHMARKS_PATH, params=params or None
        )

    async def list_offers(
        self,
        *,
        hardware_id: str | None,
        category: str | None,
        verified_only: bool,
    ) -> dict[str, object]:
        params: dict[str, str | int | bool | None] = {"verifiedOnly": verified_only}
        if hardware_id:
            params["hardwareId"] = hardware_id
        if category:
            params["category"] = category
        return await self._request("GET", PC_OFFERS_PATH, params=params)

    async def compose(
        self, request: dict[str, object], *, user_token: str
    ) -> dict[str, object]:
        """按指定八类硬件生成方案并落快照。"""
        return await self._request(
            "POST", PC_COMPOSE_PATH, user_token=user_token, json=request
        )

    async def validate_partial(self, components: dict[str, str]) -> dict[str, object]:
        """增量校验：任意子集，最少一项；无需用户令牌，只跑依赖已选类别的规则。"""
        return await self._request(
            "POST", PC_VALIDATE_PARTIAL_PATH, json={"components": components}
        )

    async def get_build(self, build_id: str, *, user_token: str) -> dict[str, object]:
        return await self._request(
            "GET", f"{PC_BUILD_PATH}/{build_id}", user_token=user_token
        )

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
        self._client = None


_client_singleton: PcApiClient | None = None


def get_pc_client() -> PcApiClient:
    """进程内复用连接池；服务令牌仍由控制面客户端统一缓存。"""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = PcApiClient(get_settings(), get_control_plane_client())
    return _client_singleton


async def close_pc_client() -> None:
    global _client_singleton
    if _client_singleton is not None:
        await _client_singleton.aclose()
        _client_singleton = None


def reset_pc_client() -> None:
    """测试或配置热切换后丢弃单例。"""
    global _client_singleton
    _client_singleton = None


__all__ = [
    "PcApiClient",
    "close_pc_client",
    "get_pc_client",
    "reset_pc_client",
]
