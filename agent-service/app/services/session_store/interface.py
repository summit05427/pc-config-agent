"""会话存储接口：一次定义「会话目录 + 消息转写」的全部契约。

为什么把两张表合进一个接口：
`session_meta` 与 `session_messages` 共用同一个池、同一个 `(user_id, thread_id)` 键，
并且有三条跨表不变量（本轮消息与活跃时间一起写、删除两表一起删、标题只首写一次）。
按表拆开会把这三条规则重新漏回每个调用方。

后端选择属于装配层：接口只描述行为，Postgres 与内存是两个等价适配器。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class SessionEntry:
    """会话目录项；`title` 为空表示还没生成标题，`model_key` 为空表示 Auto。"""

    thread_id: str
    title: str | None
    last_active_at: datetime
    model_key: str | None = None
    updated_at: datetime | None = None
    # 置顶项排在未置顶项之前；归档项不出现在默认列表中
    is_pinned: bool = False
    is_archived: bool = False


class SessionStore(Protocol):
    """会话读写的唯一接口；调用方与测试都只跨这个 seam。"""

    async def setup(self) -> None:
        """绑定后执行一次性初始化；内存适配器为空实现。"""
        ...

    async def record_turn(
        self,
        user_id: str,
        thread_id: str,
        messages: list[Any],
        title: str | None,
        replace_existing: bool = False,
        build_result: dict[str, Any] | None = None,
        citations: list[dict[str, Any]] | None = None,
        had_reasoning: bool = False,
    ) -> None:
        """写入本轮消息并刷新活跃时间；标题只在首次写入时生效。

        `replace_existing=True` 用于「重新生成」：同一序号的消息会被覆盖，
        而不是按 `ON CONFLICT DO NOTHING` 跳过。
        `build_result` 挂在本轮最后一条助手消息上，随历史一起返回，
        保证刷新页面后详情面板仍能取到结构化数据。
        `citations` 与 `had_reasoning` 写入同一条助手消息的元数据：
        引用刷新后仍可回放；思考正文不落库，只标记该回合产生过思考内容。
        """
        ...

    async def list_sessions(
        self,
        user_id: str,
        page: int,
        size: int,
        archived: bool = False,
    ) -> tuple[list[SessionEntry], int]:
        """按置顶优先、最近活跃倒序分页返回当前用户的会话。"""
        ...

    async def set_pinned(self, user_id: str, thread_id: str, pinned: bool) -> SessionEntry | None:
        """设置置顶状态；会话不存在或不属于当前用户返回 `None`。"""
        ...

    async def set_archived(
        self, user_id: str, thread_id: str, archived: bool
    ) -> SessionEntry | None:
        """设置归档状态；会话不存在或不属于当前用户返回 `None`。"""
        ...

    async def get_session(self, user_id: str, thread_id: str) -> SessionEntry | None:
        """读取单个会话；不存在或不属于当前用户都返回 `None`。"""
        ...

    async def rename_session(self, user_id: str, thread_id: str, title: str) -> bool:
        """重命名会话；返回是否命中该用户名下的一行。"""
        ...

    async def delete_session(self, user_id: str, thread_id: str) -> bool:
        """删除会话目录与该会话的全部消息；返回是否删掉了任何数据。"""
        ...

    async def read_messages(
        self,
        user_id: str,
        thread_id: str,
        page: int,
        size: int,
        order: str = "asc",
    ) -> tuple[list[dict[str, Any]], int]:
        """按窗口读取消息，读取量只与 `size` 有关。"""
        ...

    async def get_model_key(self, user_id: str, thread_id: str) -> str | None:
        """读取会话级模型选择；`None` 表示 Auto。"""
        ...

    async def set_model_key(
        self,
        user_id: str,
        thread_id: str,
        model_key: str | None,
    ) -> datetime | None:
        """写入会话级模型选择并返回新的 `updated_at`；会话不存在返回 `None`。"""
        ...
