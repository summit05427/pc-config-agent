"""PC 配置推荐流水线的输入 Schema。

金额字段统一使用整数分（`*_fen`），禁止浮点数，避免预算比较出现精度漂移。
LLM 只负责把自然语言解析成这里的结构，硬件、价格与链接一律来自 Java 内部接口。
"""

from enum import StrEnum
from typing import Literal

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


class RequirementExtraction(PCRequirements):
    """LLM 结构化输出的形状；与状态里的需求保持同一份 Schema。"""


class StrategyId(StrEnum):
    """配置策略标识；只决定解题方向，不决定具体型号。"""

    GPU_FIRST = "GPU_FIRST"
    CPU_FIRST = "CPU_FIRST"
    BALANCED = "BALANCED"
    QUIET = "QUIET"
    POWER_EFFICIENT = "POWER_EFFICIENT"
    UPGRADEABLE = "UPGRADEABLE"
    VALUE = "VALUE"


class BudgetTendency(StrEnum):
    """类别预算倾向：只有方向，没有金额，避免被当成硬预算表。"""

    HIGHER = "HIGHER"
    BALANCED = "BALANCED"
    LOWER = "LOWER"


# Stage 2 不启用 Specialist：激活计划只允许为空或明确标注 deferred
ACTIVATION_PLAN_DEFERRED = "deferred"


class BudgetGuidance(BaseModel):
    """单个类别的预算软倾向；金额一律由 Java 决定，模型不得给出预算数字。"""

    model_config = ConfigDict(extra="forbid")

    category: HardwareCategory
    tendency: BudgetTendency
    note: str = Field(default="", max_length=120)


class ComponentPriority(BaseModel):
    """组件优先关注点，例如「显存容量优先于频率」。"""

    model_config = ConfigDict(extra="forbid")

    category: HardwareCategory
    focus: str = Field(min_length=1, max_length=120)


class BuildStrategy(BaseModel):
    """策略节点产物；属于软规划，不得覆盖用户硬约束与 Java 预算校验。

    `budget_allocation_guidance` 只表达类别之间的取向（更高/均衡/更低），
    禁止出现金额，也不能被 Architect 当成必须服从的硬预算。
    """

    model_config = ConfigDict(extra="forbid")

    strategy_id: StrategyId
    rationale_summary: str = Field(min_length=1, max_length=MAX_REASON_SUMMARY_LENGTH)
    budget_allocation_guidance: list[BudgetGuidance] = Field(
        default_factory=list, max_length=8
    )
    component_priorities: list[ComponentPriority] = Field(
        default_factory=list, max_length=8
    )
    tradeoff_policy: list[str] = Field(default_factory=list, max_length=5)
    retrieval_notes: list[str] = Field(default_factory=list, max_length=5)
    activation_plan: str | None = Field(default=None, max_length=200)

    @field_validator("activation_plan")
    @classmethod
    def _only_deferred_activation(cls, value: str | None) -> str | None:
        """Stage 2 还没有 Specialist：只接受空值或 deferred，其他值视为非法输出。"""
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if trimmed.lower().startswith(ACTIVATION_PLAN_DEFERRED):
            return ACTIVATION_PLAN_DEFERRED
        raise ValueError("activation_plan 只允许为空或 deferred")

    @model_validator(mode="after")
    def _validate_unique_categories(self) -> "BuildStrategy":
        """同一类别只允许一条倾向/优先点，重复会让策略自相矛盾。"""
        for field_name in ("budget_allocation_guidance", "component_priorities"):
            categories = [entry.category for entry in getattr(self, field_name)]
            if len(set(categories)) != len(categories):
                raise ValueError(f"{field_name} 存在重复类别")
        return self


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


class SpecialistRole(StrEnum):
    """并行分析角色；只负责给出方向性意见，不产出最终选型。"""

    PERFORMANCE = "PERFORMANCE"
    PLATFORM = "PLATFORM"


class SpecialistReport(BaseModel):
    """单个 Specialist 的分析产物。

    为什么限制 `evidence`：证据只能是上下文中真实出现的候选 ID 或知识来源 ID，
    否则报告会把编造的型号/跑分当成依据，最终污染 Architect 的上下文。
    """

    model_config = ConfigDict(extra="forbid")

    role: SpecialistRole
    # 期望 100-500 字；上限放宽到 2000，避免正常中文分析被 Schema 判为非法
    summary: str = Field(min_length=1, max_length=2000)
    # 只给方向（例如「优先高显存」），不允许指定最终型号
    recommendations: list[str] = Field(min_length=1, max_length=5)
    risks: list[str] = Field(default_factory=list, max_length=5)
    affected_categories: list[HardwareCategory] = Field(min_length=1, max_length=8)
    # 只能是候选 hardware_id 或 knowledge source_id，由提示词约束、不在代码里做匹配
    evidence: list[str] = Field(default_factory=list, max_length=8)


class CriticDecision(StrEnum):
    """独立评审结论；REVISE 在存在 HIGH/MEDIUM 问题时触发一次受限修正。"""

    PASS = "PASS"
    REVISE = "REVISE"
    PASS_WITH_DISCLOSURE = "PASS_WITH_DISCLOSURE"


class CriticIssue(BaseModel):
    """Critic 发现的问题；`hardware_ids` 可空，问题不一定绑定具体硬件。"""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["LOW", "MEDIUM", "HIGH"]
    categories: list[HardwareCategory] = Field(max_length=8)
    hardware_ids: list[str] = Field(default_factory=list, max_length=8)
    description: str = Field(min_length=1, max_length=500)


class CriticReport(BaseModel):
    """对已通过 Java 校验方案的独立评审结果；不改方案、不改价格。"""

    model_config = ConfigDict(extra="forbid")

    decision: CriticDecision
    summary: str = Field(min_length=1, max_length=2000)
    issues: list[CriticIssue] = Field(default_factory=list, max_length=8)

