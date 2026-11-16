"""RAG 契约：检索请求、引用结构与检索器接口。

边界：
- 本模块只定义机制，不内置知识库、切块策略或向量库；
- 权限过滤在检索**之前**由检索器按 `user_id` / `roles` 执行，禁止先检索再过滤；
- 引用片段是模型可见内容，接入方负责去敏（不要把密钥、内部地址写进片段）。
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    """一条可展示的来源引用；`source_id` 用于前端跳转与排查。

    `source_name` / `confidence_level` 只供工具把来源可信度带给模型，
    不进入 `to_payload()`：SSE 的 `citations` 事件必须保持既有四字段契约。
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=256)
    title: str = Field(default="", max_length=128)
    snippet: str = Field(min_length=1, max_length=4000)
    score: float | None = Field(default=None, ge=0, le=1)
    source_name: str = Field(default="", max_length=200)
    confidence_level: str = Field(default="", max_length=16)

    def to_payload(self) -> dict[str, object]:
        """只输出事件契约字段，避免新增字段漂移到前端。"""
        return {
            "source_id": self.source_id,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
        }


class RetrievalRequest(BaseModel):
    """一次检索的最小输入；角色即权限范围，检索器必须先按它过滤。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(min_length=1, max_length=64)
    roles: tuple[str, ...] = ()
    limit: int = Field(default=5, ge=1, le=20)


class Retriever(Protocol):
    """接入方实现 `retrieve`，返回已按权限过滤的引用列表。"""

    async def retrieve(self, request: RetrievalRequest) -> list[Citation]: ...


class NoopRetriever:
    """默认空实现：关闭 RAG 时不导入任何第三方依赖、不发外部请求。"""

    async def retrieve(self, request: RetrievalRequest) -> list[Citation]:
        return []


class RagConfigError(RuntimeError):
    """RAG 配置非法；消息必须包含具体变量与期望值。"""
