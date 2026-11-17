"""知识库领域模型与检索器之间的最小数据结构。

字段只覆盖「导入 → 存储 → 检索」所需的语义；权限字段单独成列，
是为了让过滤条件能进 WHERE 与索引，而不是在应用层先查后筛。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceType = Literal["INTERNAL_NOTE", "OFFICIAL_SPEC", "PROJECT_DOC", "DATASET_SNAPSHOT"]
ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]
Visibility = Literal["public", "role", "private"]

SOURCE_TYPES: tuple[str, ...] = (
    "INTERNAL_NOTE",
    "OFFICIAL_SPEC",
    "PROJECT_DOC",
    "DATASET_SNAPSHOT",
)
CONFIDENCE_LEVELS: tuple[str, ...] = ("HIGH", "MEDIUM", "LOW")
VISIBILITIES: tuple[str, ...] = ("public", "role", "private")


class KnowledgeCard(BaseModel):
    """一张知识卡片的规范形态；Markdown front matter 与 JSON 都归一到这里。"""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    title: str = Field(min_length=1, max_length=200)
    source_type: SourceType = "INTERNAL_NOTE"
    source_name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200_000)
    source_url: str | None = Field(default=None, max_length=2000)
    published_at: datetime | None = None
    collected_at: datetime | None = None
    valid_until: datetime | None = None
    confidence_level: ConfidenceLevel = "MEDIUM"
    version: int = Field(default=1, ge=1, le=1000)
    # 权限字段：public 对所有人可见；role 需要角色交集；private 只对 owner 可见
    visibility: Visibility = "public"
    allowed_roles: tuple[str, ...] = ()
    owner_user_id: str | None = Field(default=None, max_length=64)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        """只接受 http(s)，避免把 javascript: 之类的地址写进引用区。"""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("source_url 必须是 http(s) 地址")
        return normalized

    @field_validator("content")
    @classmethod
    def validate_content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content 不能为空")
        return value

    @model_validator(mode="after")
    def validate_permission_scope(self) -> KnowledgeCard:
        """role/private 缺少对应维度会让过滤条件永远不命中，属于配置错误。"""
        if self.visibility == "role" and not self.allowed_roles:
            raise ValueError("visibility=role 时必须提供 allowed_roles")
        if self.visibility == "private" and not self.owner_user_id:
            raise ValueError("visibility=private 时必须提供 owner_user_id")
        return self


@dataclass(frozen=True)
class TextChunk:
    """切片只描述内容与稳定标识；embedding 由导入流程单独注入。"""

    chunk_id: str
    document_id: str
    content: str
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddedChunk:
    """待写入的切片：文本 + 向量 + 生成向量的模型名。"""

    chunk: TextChunk
    embedding: tuple[float, ...]
    embedding_model: str


@dataclass(frozen=True)
class DocumentState:
    """已入库文档的指纹；用于判断是否需要重新切片/重新生成向量。"""

    content_hash: str
    embedding_model: str | None
    chunk_count: int


@dataclass(frozen=True)
class SearchHit:
    """单个通道的召回结果；`score` 只用于观察，融合阶段只用名次。

    `source_name` / `confidence_level` 来自文档元数据，用于告诉模型证据可信度；
    老实现或测试可以省略，默认空串表示「未提供」。
    """

    chunk_id: str
    document_id: str
    title: str
    content: str
    score: float
    source_name: str = ""
    confidence_level: str = ""


@dataclass(frozen=True)
class ImportReport:
    """一次导入的计数摘要，便于脚本输出与测试断言。"""

    imported: int = 0
    updated: int = 0
    skipped: int = 0
    chunks_written: int = 0
