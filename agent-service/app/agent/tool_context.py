"""工具执行上下文：一次对话回合内的角色与调用配额。

LangGraph 的工具节点拿不到 HTTP 请求对象，但工具治理必须知道「当前是谁在调用」，
以及「本轮某个工具已经调用了几次」。这里用 ContextVar 传递，而不是给每个工具
加参数：后者会污染模型可见的工具 schema，也容易漏传。

只暴露 `ToolTurn` 一个 seam：
- 进入回合时写入角色并重置计数，退出时复位，调用方无法只做一半；
- registry 通过 `get_current_tool_turn()` 读取，无需持有实例；
- 没有回合上下文（脚本直接调工具）时按「无角色、不限次」处理。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any


class ToolTurn:
    """一次对话回合的工具上下文；同一回合内所有工具调用共享计数。

    用法：`with ToolTurn(user_roles): ...`，退出（含异常与生成器取消）都会复位，
    避免上一轮的角色或配额泄漏到下一轮请求。
    """

    def __init__(self, roles: tuple[str, ...]) -> None:
        self.roles = roles
        self._call_counts: dict[str, int] = {}
        self._token: Token[ToolTurn | None] | None = None

    def __enter__(self) -> ToolTurn:
        self._token = _current_turn.set(self)
        return self

    def __exit__(self, *exc_info: Any) -> None:
        if self._token is not None:
            _current_turn.reset(self._token)
            self._token = None

    def acquire(self, tool_name: str, limit: int) -> bool:
        """占用一次调用额度；超过上限返回 False，由调用方给模型返回提示文本。"""
        used = self._call_counts.get(tool_name, 0)
        if used >= limit:
            return False
        self._call_counts[tool_name] = used + 1
        return True


_current_turn: ContextVar[ToolTurn | None] = ContextVar("tool_turn", default=None)


def get_current_tool_turn() -> ToolTurn | None:
    """读取当前回合上下文；没有回合时返回 None。"""
    return _current_turn.get()
