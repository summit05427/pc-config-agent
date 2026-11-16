"""PC 配置推荐流水线的输入 Schema。

金额字段统一使用整数分（`*_fen`），禁止浮点数，避免预算比较出现精度漂移。
LLM 只负责把自然语言解析成这里的结构，硬件、价格与链接一律来自 Java 内部接口。
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_BUDGET_FEN = 100_000_000  # 100 万元，超出视为输入异常而不是真实需求
MAX_MEMORY_GB = 512
MAX_STORAGE_GB = 8_192
# 单条选型理由是展示给用户的摘要，不是隐藏思维链
MAX_REASON_SUMMARY_LENGTH = 500


class BuildScenario(StrEnum):
    """与 Java `BuildScenario` 枚举保持一致。

    前六个是当前主推用途；后四个为历史值，仍可兜底输出。
    """

    GENERAL = "GENERAL"
    GAMING = "GAMING"
    MEDIA = "MEDIA"
    VIDEO_EDITING = "VIDEO_EDITING"
    PROGRAMMING = "PROGRAMMING"
    RENDERING = "RENDERING"
    AI_INFERENCE = "AI_INFERENCE"
    CREATIVE = "CREATIVE"
    WORKSTATION = "WORKSTATION"
    OFFICE = "OFFICE"
    BALANCED = "BALANCED"


class Preference(StrEnum):
    """选型偏好；`None` 表示用户未表达倾向，不能默认成性能优先。

    `VALUE` 仅在预算存在时生效，由 Java 按性价比排序；`PERFORMANCE` 按性能总分排序。
    """

    PERFORMANCE = "PERFORMANCE"
    VALUE = "VALUE"


class RenderMode(StrEnum):
    """渲染负载的执行单元；`None` 表示用户尚未说明，不允许自行猜测。"""

    CPU = "CPU"
    GPU = "GPU"
    BOTH = "BOTH"


class HardwareCategory(StrEnum):
    """与 Java `HardwareCategory` 枚举保持一致，顺序即渲染顺序。"""

    CPU = "CPU"
    MOTHERBOARD = "MOTHERBOARD"
    MEMORY = "MEMORY"
    GPU = "GPU"
    PSU = "PSU"
    CASE = "CASE"
    COOLER = "COOLER"
    STORAGE = "STORAGE"


REQUIRED_CATEGORIES: tuple[HardwareCategory, ...] = tuple(HardwareCategory)


class PCRequirements(BaseModel):
    """结构化装机需求。

    `scenario_explicit` 记录用户是否明确表达了用途，用于区分「没提用途」与
    「明确要求均衡配置」，否则缺省值会把追问条件吞掉。
    """

    model_config = ConfigDict(extra="ignore")

    budget_min_fen: int | None = Field(default=None, ge=0, le=MAX_BUDGET_FEN)
    budget_max_fen: int | None = Field(default=None, ge=0, le=MAX_BUDGET_FEN)
    scenario: BuildScenario = BuildScenario.BALANCED
    scenario_explicit: bool = False
    preference: Preference | None = None
    render_mode: RenderMode | None = None
    min_memory_gb: int | None = Field(default=None, ge=1, le=MAX_MEMORY_GB)
    min_storage_gb: int | None = Field(default=None, ge=1, le=MAX_STORAGE_GB)
    require_verified_offers: bool = False
    needs_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=300)
    missing_fields: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def _validate_budget_range(self) -> "PCRequirements":
        """区间必须自洽；「20000 元以上」只有下限，不能反推出上限。"""
        if (
            self.budget_min_fen is not None
            and self.budget_max_fen is not None
            and self.budget_min_fen > self.budget_max_fen
        ):
            raise ValueError("budget_min_fen 不能大于 budget_max_fen")
        return self

    def to_solve_request(self, *, require_verified_offers: bool | None = None) -> dict[str, object]:
        """转换成 Java `SolveRequest` 的 camelCase JSON。"""
        verified = (
            self.require_verified_offers
            if require_verified_offers is None
            else require_verified_offers
        )
        return {
            "budgetMinFen": self.budget_min_fen,
            "budgetMaxFen": self.budget_max_fen,
            "scenario": self.scenario.value,
            "preference": self.preference.value if self.preference else None,
            "renderMode": self.render_mode.value if self.render_mode else None,
            "minMemoryGb": self.min_memory_gb,
            "minStorageGb": self.min_storage_gb,
            "requireVerifiedOffers": verified,
        }


class RequirementExtraction(PCRequirements):
    """LLM 结构化输出的形状；与状态里的需求保持同一份 Schema。"""


class SelectedComponent(BaseModel):
    """Architect 提案里的单个组件。

    只允许「类别 + 硬件标识 + 理由」：价格、型号文本与链接必须以 Java 结果为准，
    模型输出中出现这些字段时由 `extra="forbid"` 直接判为非法。
    """

    model_config = ConfigDict(extra="forbid")

    category: HardwareCategory
    hardware_id: str = Field(min_length=1, max_length=128)
    reason_summary: str = Field(min_length=1, max_length=MAX_REASON_SUMMARY_LENGTH)

    @field_validator("hardware_id")
    @classmethod
    def _reject_blank_id(cls, value: str) -> str:
        """全空白 ID 与空字符串等价，不能作为可选硬件标识。"""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("hardware_id 不能为空")
        return trimmed


class BuildProposal(BaseModel):
    """八类组件唯一主方案；重复、缺失或额外类别都属于非法提案。"""

    model_config = ConfigDict(extra="forbid")

    selected_components: list[SelectedComponent]

    @model_validator(mode="after")
    def _validate_category_coverage(self) -> "BuildProposal":
        categories = [component.category for component in self.selected_components]
        if len(categories) != len(REQUIRED_CATEGORIES):
            raise ValueError("selected_components 必须恰好包含八个类别")
        if len(set(categories)) != len(categories):
            raise ValueError("selected_components 存在重复类别")
        if set(categories) != set(REQUIRED_CATEGORIES):
            raise ValueError("selected_components 缺少必需类别")
        return self

