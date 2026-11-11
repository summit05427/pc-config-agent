"""PC 配置推荐流水线的输入 Schema。

金额字段统一使用整数分（`*_fen`），禁止浮点数，避免预算比较出现精度漂移。
LLM 只负责把自然语言解析成这里的结构，硬件、价格与链接一律来自 Java 内部接口。
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

MAX_BUDGET_FEN = 100_000_000  # 100 万元，超出视为输入异常而不是真实需求
MAX_MEMORY_GB = 512
MAX_STORAGE_GB = 8_192


class BuildScenario(StrEnum):
    """与 Java `BuildScenario` 枚举保持一致。

    前六个是当前主推用途；后四个为历史值，仍可兜底输出。
    """

    GENERAL = "GENERAL"
    GAMING = "GAMING"
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

    def to_solve_request(self, *, require_verified_offers: bool | None = None) -> dict[str, object]:
        """转换成 Java `SolveRequest` 的 camelCase JSON。"""
        verified = (
            self.require_verified_offers
            if require_verified_offers is None
            else require_verified_offers
        )
        return {
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
