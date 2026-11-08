"""会话元数据、历史接口与删除流程测试。

数据来源已从 Redis 索引迁移到 `session_meta`：本文件用进程内 memory 后端，
不依赖 Redis / Postgres，同时验证归属隔离与锁冲突分支。
"""

import asyncio
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.api.v1 import sessions as sessions_module
from app.core.config import get_settings
from app.core.exceptions import LockAcquisitionError
from app.main import app
from app.services import control_plane
from app.services.control_plane import ControlPlaneError
from app.services.session_store import (
    InMemorySessionStore,
    SessionEntry,
    bind_session_store,
    get_session_store,
    unbind_session_store,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_stores() -> Iterator[None]:
    """每个用例独立：内存适配器是进程内状态，必须显式替换。"""
    bind_session_store(InMemorySessionStore())
    yield
    unbind_session_store()


def _seed_session(user_id: str, thread_id: str, title: str | None = "标题") -> None:
    """同步用例里写内存存储；消息为空时只维护目录。"""
    asyncio.run(get_session_store().record_turn(user_id, thread_id, [], title))


def _seed_messages(user_id: str, thread_id: str, messages: list[Any]) -> None:
    asyncio.run(get_session_store().record_turn(user_id, thread_id, messages, None))


async def test_record_turn_keeps_first_title() -> None:
    """标题只在首次写入时生效，后续轮次不能用 None 覆盖。"""
    store = get_session_store()

    await store.record_turn("user-1", "demo", [], "第一句")
    await store.record_turn("user-1", "demo", [], None)
    await store.record_turn("user-1", "demo", [], "另一个标题")

    entries, total = await store.list_sessions("user-1", page=1, size=20)
    assert total == 1
    assert entries[0].title == "第一句"


async def test_list_orders_recent_first_and_paginates() -> None:
    """最近活跃倒序 + 分页；其他用户的会话不进入结果。"""
    clock = {"value": datetime(2026, 10, 29, 8, 0, tzinfo=UTC)}

    def tick() -> datetime:
        current = clock["value"]
        clock["value"] = current + timedelta(seconds=1)
        return current

    # 时钟是适配器的构造参数，测试不再 monkeypatch 模块级 `_now`
    bind_session_store(InMemorySessionStore(clock=tick))
    store = get_session_store()

    for thread_id in ("old", "mid", "new"):
        await store.record_turn("user-1", thread_id, [], thread_id)
    await store.record_turn("user-2", "other", [], "别人的会话")

    entries, total = await store.list_sessions("user-1", page=1, size=2)
    assert [entry.thread_id for entry in entries] == ["new", "mid"]
    assert total == 3

    second_page, _ = await store.list_sessions("user-1", page=2, size=2)
    assert [entry.thread_id for entry in second_page] == ["old"]


async def test_rename_and_delete_are_scoped_by_user() -> None:
    store = get_session_store()
    await store.record_turn("user-1", "demo", [], "原标题")

    assert await store.rename_session("user-1", "demo", "新标题") is True
    # 其他用户既不能重命名，也不能删除
    assert await store.rename_session("user-2", "demo", "劫持") is False
    assert await store.delete_session("user-2", "demo") is False

    entries, _ = await store.list_sessions("user-1", page=1, size=20)
    assert entries[0].title == "新标题"

    assert await store.delete_session("user-1", "demo") is True
    assert await store.list_sessions("user-1", page=1, size=20) == ([], 0)


async def test_pinned_sessions_sort_first_and_archived_are_filtered() -> None:
    """置顶优先；归档项只出现在 archived=true 的结果里。"""
    clock = {"value": datetime(2026, 10, 29, 8, 0, tzinfo=UTC)}

    def tick() -> datetime:
        current = clock["value"]
        clock["value"] = current + timedelta(seconds=1)
        return current

    bind_session_store(InMemorySessionStore(clock=tick))
    store = get_session_store()
    for thread_id in ("old", "new"):
        await store.record_turn("user-1", thread_id, [], thread_id)

    assert await store.set_pinned("user-1", "old", True) is not None
    assert await store.set_archived("user-1", "new", True) is not None

    visible, visible_total = await store.list_sessions("user-1", page=1, size=20)
    assert [entry.thread_id for entry in visible] == ["old"]
    assert visible[0].is_pinned is True
    assert visible_total == 1

    archived, archived_total = await store.list_sessions(
        "user-1", page=1, size=20, archived=True
    )
    assert [entry.thread_id for entry in archived] == ["new"]
    assert archived[0].is_archived is True
    assert archived_total == 1


def test_pin_and_archive_endpoints(token_factory: Callable[..., str]) -> None:
    """置顶与归档接口返回最新状态，并校验会话归属。"""
    _seed_session("user-1", "demo")
    headers = {"Authorization": f"Bearer {token_factory()}"}

    pinned = client.put("/api/v1/sessions/demo/pin", json={"pinned": True}, headers=headers)
    assert pinned.status_code == 200
    assert pinned.json()["is_pinned"] is True

    archived = client.put(
        "/api/v1/sessions/demo/archive", json={"archived": True}, headers=headers
    )
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True

    assert client.get("/api/v1/sessions", headers=headers).json()["total"] == 0
    archived_list = client.get(
        "/api/v1/sessions?archived=true", headers=headers
    ).json()
    assert archived_list["total"] == 1
    assert archived_list["list"][0]["thread_id"] == "demo"

    other_headers = {"Authorization": f"Bearer {token_factory('user-2')}"}
    missing = client.put(
        "/api/v1/sessions/demo/pin", json={"pinned": True}, headers=other_headers
    )
    assert missing.status_code == 404


def test_session_list_requires_token() -> None:
    response = client.get("/api/v1/sessions")

    assert response.status_code == 401


def test_session_list_returns_titles(
    monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    class FakeStore:
        async def list_sessions(
            self, user_id: str, page: int, size: int, archived: bool = False
        ) -> tuple[list[SessionEntry], int]:
            assert user_id == "user-1"
            moment = datetime(2026, 10, 29, 8, 0, tzinfo=UTC)
            return [SessionEntry("demo", "第一句", moment)], 1

    monkeypatch.setattr(sessions_module, "get_session_store", lambda: FakeStore())

    response = client.get(
        "/api/v1/sessions",
        headers={"Authorization": f"Bearer {token_factory()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["list"][0] == {
        "thread_id": "demo",
        "title": "第一句",
        "model_key": None,
        "last_active_at": "2026-10-29T08:00:00Z",
        "is_pinned": False,
        "is_archived": False,
    }


def test_rename_session_trims_and_persists(token_factory: Callable[..., str]) -> None:
    _seed_session("user-1", "demo", "原标题")
    headers = {"Authorization": f"Bearer {token_factory()}"}

    response = client.patch(
        "/api/v1/sessions/demo",
        json={"title": "  新标题  "},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {"thread_id": "demo", "title": "新标题"}

    entries = client.get("/api/v1/sessions", headers=headers).json()["list"]
    assert entries[0]["title"] == "新标题"


def test_rename_session_returns_404_for_other_user(
    token_factory: Callable[..., str],
) -> None:
    _seed_session("user-1", "demo", "原标题")

    response = client.patch(
        "/api/v1/sessions/demo",
        json={"title": "劫持"},
        headers={"Authorization": f"Bearer {token_factory('user-2')}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"


def test_rename_session_rejects_blank_and_overlong_title(
    token_factory: Callable[..., str],
) -> None:
    _seed_session("user-1", "demo", "原标题")
    headers = {"Authorization": f"Bearer {token_factory()}"}

    for title in ("   ", "x" * 81):
        response = client.patch("/api/v1/sessions/demo", json={"title": title}, headers=headers)
        assert response.status_code == 422, title
        assert response.json()["code"] == "validation_error"


def _disable_thread_lock(monkeypatch: Any) -> None:
    """测试环境 Redis 客户端未初始化：删除流程显式跳过锁，锁冲突另有用例。"""

    async def no_lock(thread_id: str) -> None:
        return None

    monkeypatch.setattr(sessions_module, "acquire_thread_lock", no_lock)


def test_delete_session_removes_meta_messages_and_checkpoint(
    monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    """删除后会话从列表消失、历史 404，并把检查点删除登记为墓碑。"""
    queued: list[tuple[str, str, str]] = []

    async def fake_enqueue(
        user_id: str, thread_id: str, checkpoint_thread_id: str
    ) -> bool:
        queued.append((user_id, thread_id, checkpoint_thread_id))
        return True

    _disable_thread_lock(monkeypatch)
    monkeypatch.setattr(sessions_module, "enqueue_session_deletion", fake_enqueue)
    _seed_session("user-1", "demo")
    _seed_messages("user-1", "demo", [HumanMessage("你好"), AIMessage("回复")])
    headers = {"Authorization": f"Bearer {token_factory()}"}

    response = client.delete("/api/v1/sessions/demo", headers=headers)

    assert response.status_code == 204
    assert response.content == b""
    assert queued == [("user-1", "demo", "user-1:demo")]
    assert client.get("/api/v1/sessions", headers=headers).json()["total"] == 0
    assert client.get("/api/v1/sessions/demo/messages", headers=headers).status_code == 404

    # 再删一次已不存在的会话应返回 404
    assert client.delete("/api/v1/sessions/demo", headers=headers).status_code == 404


def test_delete_session_keeps_other_users_data(
    monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    """其他用户用同一个 thread_id 删除只会命中自己的空结果，原会话不受影响。"""
    _disable_thread_lock(monkeypatch)
    _seed_session("user-1", "demo")

    response = client.delete(
        "/api/v1/sessions/demo",
        headers={"Authorization": f"Bearer {token_factory('user-2')}"},
    )

    assert response.status_code == 404
    # 同名 thread_id 属于 user-1 的数据不受影响
    entries = client.get(
        "/api/v1/sessions",
        headers={"Authorization": f"Bearer {token_factory()}"},
    ).json()["list"]
    assert [entry["thread_id"] for entry in entries] == ["demo"]


def test_delete_session_returns_409_when_lock_is_busy(
    monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    """生成中删除应返回 409，而不是把半轮消息删掉。"""
    _seed_session("user-1", "demo")

    async def busy_lock(thread_id: str) -> Any:
        raise LockAcquisitionError()

    monkeypatch.setattr(sessions_module, "acquire_thread_lock", busy_lock)

    response = client.delete(
        "/api/v1/sessions/demo",
        headers={"Authorization": f"Bearer {token_factory()}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "lock_not_acquired"


def test_delete_session_survives_checkpoint_failure(
    monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    """墓碑入队失败时退回一次性删除；删除异常也不能影响 204。"""
    _disable_thread_lock(monkeypatch)
    _seed_session("user-1", "demo")

    async def failed_enqueue(
        user_id: str, thread_id: str, checkpoint_thread_id: str
    ) -> bool:
        return False

    async def broken_delete(thread_id: str) -> bool:
        raise RuntimeError("checkpoint store down")

    monkeypatch.setattr(sessions_module, "enqueue_session_deletion", failed_enqueue)
    monkeypatch.setattr(sessions_module, "delete_thread_checkpoint", broken_delete)

    response = client.delete(
        "/api/v1/sessions/demo",
        headers={"Authorization": f"Bearer {token_factory()}"},
    )

    assert response.status_code == 204
    entries = client.get(
        "/api/v1/sessions",
        headers={"Authorization": f"Bearer {token_factory()}"},
    ).json()["list"]
    assert entries == []


def test_session_messages_are_scoped_by_user(
    monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    captured: list[tuple[str, str, int, int, str]] = []
    records = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "", "tool_calls": [{"name": "t", "args": {}}]},
        {"role": "tool", "content": "结果", "name": "t"},
        {"role": "assistant", "content": "完成"},
    ]

    class FakeStore:
        async def read_messages(
            self, user_id: str, thread_id: str, page: int, size: int, order: str = "asc"
        ) -> tuple[list[Any], int]:
            captured.append((user_id, thread_id, page, size, order))
            return records, len(records)

    monkeypatch.setattr(sessions_module, "get_session_store", lambda: FakeStore())

    response = client.get(
        "/api/v1/sessions/demo/messages",
        headers={"Authorization": f"Bearer {token_factory()}"},
    )

    assert response.status_code == 200
    # 归属隔离依赖查询条件里的 user_id，不再靠 thread_id 前缀
    assert captured == [("user-1", "demo", 1, 20, "asc")]
    body = response.json()
    assert [item["role"] for item in body["list"]] == ["user", "assistant", "tool", "assistant"]
    assert body["list"][1]["tool_calls"][0]["name"] == "t"
    assert body["total"] == 4
    assert body["page"] == 1
    assert body["order"] == "asc"


def test_session_messages_support_desc_order(token_factory: Callable[..., str]) -> None:
    """长会话可以按最新一页向前翻；返回顺序与请求方向一致。"""
    _seed_messages("user-1", "demo", [HumanMessage(f"m{index}") for index in range(5)])

    response = client.get(
        "/api/v1/sessions/demo/messages",
        params={"order": "desc", "size": 2},
        headers={"Authorization": f"Bearer {token_factory()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["content"] for item in body["list"]] == ["m4", "m3"]
    assert body["total"] == 5
    assert body["order"] == "desc"


def test_session_messages_return_404_when_empty(
    monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    class FakeStore:
        async def read_messages(
            self, user_id: str, thread_id: str, page: int, size: int, order: str = "asc"
        ) -> tuple[list[Any], int]:
            return [], 0

    monkeypatch.setattr(sessions_module, "get_session_store", lambda: FakeStore())

    response = client.get(
        "/api/v1/sessions/missing/messages",
        headers={"Authorization": f"Bearer {token_factory()}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"


def test_sessions_reject_out_of_range_pagination(
    token_factory: Callable[..., str],
) -> None:
    """分页越界统一返回 400，与 Java 的分页语义保持一致。"""
    headers = {"Authorization": f"Bearer {token_factory()}"}

    for path, params in (
        ("/api/v1/sessions", {"size": 101}),
        ("/api/v1/sessions/demo/messages", {"page": 0}),
    ):
        response = client.get(path, params=params, headers=headers)
        assert response.status_code == 400, (path, response.text)
        assert response.json()["code"] == "invalid_pagination"


async def test_store_windows_messages() -> None:
    messages = [HumanMessage(f"m{index}") for index in range(5)]
    store = get_session_store()

    await store.record_turn("user-1", "demo", messages, None)
    # 重复写入必须幂等：seq 冲突时跳过，而不是追加重复行
    await store.record_turn("user-1", "demo", messages, None)

    items, total = await store.read_messages("user-1", "demo", page=2, size=2)

    assert total == 5
    assert [item["content"] for item in items] == ["m2", "m3"]

    other_items, other_total = await store.read_messages("user-2", "demo", page=1, size=20)
    assert (other_items, other_total) == ([], 0)


async def test_store_desc_order_returns_latest_page() -> None:
    messages = [HumanMessage(f"m{index}") for index in range(5)]
    store = get_session_store()
    await store.record_turn("user-1", "demo", messages, None)

    items, total = await store.read_messages("user-1", "demo", page=1, size=2, order="desc")

    assert total == 5
    assert [item["content"] for item in items] == ["m4", "m3"]


async def test_store_deletes_only_target_user() -> None:
    store = get_session_store()
    await store.record_turn("user-1", "demo", [HumanMessage("我的")], None)
    await store.record_turn("user-2", "demo", [HumanMessage("别人的")], None)

    assert await store.delete_session("user-1", "demo") is True
    assert await store.read_messages("user-1", "demo", page=1, size=20) == ([], 0)
    assert await store.delete_session("user-2", "demo") is True


async def test_store_serializes_tool_calls() -> None:
    messages = [
        AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "c1"}]),
        ToolMessage(content="结果", tool_call_id="c1", name="t"),
        AIMessage("完成"),
    ]
    store = get_session_store()

    await store.record_turn("user-1", "t1", messages, None)
    items, total = await store.read_messages("user-1", "t1", page=1, size=20)

    assert total == 3
    assert items[0]["tool_calls"][0]["name"] == "t"
    assert items[1]["name"] == "t"
    assert items[2]["content"] == "完成"


class FakeModelAccessClient:
    """控制面替身：只实现 `check_model_access`，避免测试发起真实网络请求。"""

    def __init__(
        self,
        availability: Any = None,
        error: Exception | None = None,
    ) -> None:
        self._availability = availability
        self._error = error

    async def check_model_access(self, *, user_token: str, model_key: str) -> Any:
        if self._error is not None:
            raise self._error
        return self._availability


def _enable_runtime(monkeypatch: Any) -> None:
    monkeypatch.setattr(get_settings().model_runtime, "enabled", True)


def _use_model_access_client(monkeypatch: Any, client: FakeModelAccessClient) -> None:
    monkeypatch.setattr(
        sessions_module.control_plane, "get_control_plane_client", lambda: client
    )


def _session_model_key(user_id: str, thread_id: str) -> str | None:
    return asyncio.run(get_session_store().get_model_key(user_id, thread_id))


def _put_model(
    thread_id: str,
    payload: dict[str, Any],
    token: str,
) -> Any:
    return client.put(
        f"/api/v1/sessions/{thread_id}/model",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def test_set_session_model_persists_and_is_idempotent(
    monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    """显式模型校验通过后落库；重复提交相同值不改 updated_at。"""
    _seed_session("user-1", "demo")
    _enable_runtime(monkeypatch)
    availability = control_plane.ModelAvailability(
        provider="openai",
        model_key="openai:gpt-4o-mini",
        display_name="GPT-4o mini",
        capabilities=("text", "tool_calling"),
        context_window=128000,
    )
    _use_model_access_client(monkeypatch, FakeModelAccessClient(availability))

    first = _put_model("demo", {"model_key": "openai:gpt-4o-mini"}, token_factory())

    assert first.status_code == 200
    body = first.json()
    assert body["effective"] == "explicit"
    assert body["model"]["display_name"] == "GPT-4o mini"
    assert body["model"]["capabilities"] == ["text", "tool_calling"]
    assert body["updated_at"] is not None
    assert _session_model_key("user-1", "demo") == "openai:gpt-4o-mini"

    again = _put_model("demo", {"model_key": "openai:gpt-4o-mini"}, token_factory())
    assert again.status_code == 200
    assert again.json()["updated_at"] == body["updated_at"]

    entries = client.get(
        "/api/v1/sessions",
        headers={"Authorization": f"Bearer {token_factory()}"},
    ).json()["list"]
    assert entries[0]["model_key"] == "openai:gpt-4o-mini"


def test_set_session_model_null_restores_auto(
    monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    """传 null 恢复 Auto；恢复后再次提交不产生新的写入。"""
    _seed_session("user-1", "demo")
    _enable_runtime(monkeypatch)
    availability = control_plane.ModelAvailability(
        provider="openai",
        model_key="openai:gpt-4o-mini",
        display_name="GPT-4o mini",
        capabilities=(),
        context_window=None,
    )
    _use_model_access_client(monkeypatch, FakeModelAccessClient(availability))

    assert (
        _put_model("demo", {"model_key": "openai:gpt-4o-mini"}, token_factory()).status_code
        == 200
    )

    reset = _put_model("demo", {"model_key": None}, token_factory())
    assert reset.status_code == 200
    assert reset.json()["effective"] == "auto"
    assert reset.json()["model"] is None
    assert _session_model_key("user-1", "demo") is None

    again = _put_model("demo", {"model_key": None}, token_factory())
    assert again.json()["updated_at"] == reset.json()["updated_at"]


def test_set_session_model_rejects_other_user(
    monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    """其他用户即使猜到 thread_id 也不能改模型配置。"""
    _seed_session("user-1", "demo")
    _enable_runtime(monkeypatch)
    _use_model_access_client(monkeypatch, FakeModelAccessClient())

    response = _put_model("demo", {"model_key": "openai:gpt-4o-mini"}, token_factory("user-2"))

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"
    assert _session_model_key("user-1", "demo") is None


def test_set_session_model_does_not_persist_when_access_check_fails(
    monkeypatch: Any, token_factory: Callable[..., str]
) -> None:
    """目录校验失败必须原样返回错误，且不写入会话配置。"""
    _seed_session("user-1", "demo")
    _enable_runtime(monkeypatch)
    _use_model_access_client(
        monkeypatch,
        FakeModelAccessClient(
            error=ControlPlaneError(
                control_plane.MODEL_NOT_AVAILABLE, 403, "model not available"
            )
        ),
    )

    response = _put_model("demo", {"model_key": "openai:gpt-4o-mini"}, token_factory())

    assert response.status_code == 403
    assert response.json()["code"] == "model_not_available"
    assert _session_model_key("user-1", "demo") is None


def test_set_session_model_requires_runtime_enabled(token_factory: Callable[..., str]) -> None:
    """运行时关闭时不允许写入模型选择，避免前端以为切换已生效。"""
    _seed_session("user-1", "demo")

    response = _put_model("demo", {"model_key": "openai:gpt-4o-mini"}, token_factory())

    assert response.status_code == 503
    assert response.json()["code"] == "model_runtime_disabled"


def test_set_session_model_validates_model_reference(token_factory: Callable[..., str]) -> None:
    """非法字符在请求校验阶段就拒绝，不触达控制面。"""
    _seed_session("user-1", "demo")

    response = _put_model("demo", {"model_key": "OpenAI:GPT-4o"}, token_factory())

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
