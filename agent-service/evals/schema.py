"""评测用例的 Schema 与加载。

用例是接入方资产：新增一个场景只改 YAML，不改脚手架代码。
校验失败必须带文件名与字段位置，否则接入方无从下手。
"""

import re
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

CASE_FILE_SUFFIX = ".yaml"
# 与 Profile / 请求参数保持同一约束，避免出现只能在日志里查的非法 id
CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MAX_CASES_PER_FILE = 200

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ExpectationText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
ToolName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]

# 图跑完后可能的终态
WorkflowStatus = Literal[
    "success",
    "clarification",
    "invalid",
    "no_candidates",
    "architect_failed",
    "upstream_error",
    "aborted",
]
StructuredValue = str | int | float | bool
# 只允许 `a` / `a.b` 形式的点路径，避免断言里出现下标或表达式
FIELD_PATH_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


class CaseLoadError(RuntimeError):
    """用例文件缺失或非法；消息面向接入方，必须能直接定位到文件与字段。"""


class EvalResume(BaseModel):
    """HITL 恢复内容：首轮中断后提交的结构化答案。

    与 `/chat/stream` 的 `resume` 字段同构；`message` 是进入用户气泡的文本，
    `answer` 交给门控节点校验。仅 `--real` 执行，假模型模式只校验结构。
    """

    model_config = ConfigDict(extra="forbid")

    message: str = Field(default="", max_length=1000)
    answer: dict[str, StructuredValue] = Field(default_factory=dict, max_length=16)

    @model_validator(mode="after")
    def _require_message_or_answer(self) -> "EvalResume":
        if not self.message.strip() and not self.answer:
            raise ValueError("resume 至少需要 message 或 answer 之一")
        return self


class EvalExpectation(BaseModel):
    """一条用例的期望；可组合，任一不满足即判失败。

    结构类断言（tool_called / tool_sequence）在假模型模式即可校验；
    状态与内容类断言（workflow_status / missing_slots / structured_fields /
    price_consistency / 内容片段 / 延迟与 token 预算）必须用 `--real`。
    """

    model_config = ConfigDict(extra="forbid")

    # 期望本轮调用的工具名；假模型模式靠它校验工具是否已注册并被该 Profile 绑定
    tool_called: str | None = Field(default=None, max_length=64)
    # 期望的工具调用顺序，按子序列匹配（允许中间插入其它工具）
    tool_sequence: list[ToolName] = Field(default_factory=list, max_length=8)
    must_contain: list[ExpectationText] = Field(default_factory=list, max_length=20)
    must_not_contain: list[ExpectationText] = Field(default_factory=list, max_length=20)

    # 图跑完后的终态；给列表表示「任一命中即通过」，用于可能落到多种终态的场景
    workflow_status: WorkflowStatus | list[WorkflowStatus] | None = None
    # 期望出现在需求/校验结果 missing_fields 中的槽位；只校验包含关系
    missing_slots: list[ToolName] = Field(default_factory=list, max_length=8)
    # 期望的最终状态字段值，键为点路径（如 build_result.budgetStatus）
    structured_fields: dict[str, StructuredValue] = Field(default_factory=dict)
    # 校验总价与分项、预算上限的一致性；只在期望产出配置的用例上开启
    price_consistency: bool = False
    # 期望本轮在指定 HITL 交互类型上暂停（clarify_requirements / confirm_compatibility）
    interrupt_type: str | None = Field(default=None, max_length=64)
    max_latency_ms: int | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=0)

    @field_validator("structured_fields")
    @classmethod
    def _validate_field_paths(cls, value: dict[str, StructuredValue]) -> dict[str, StructuredValue]:
        invalid = [path for path in value if not FIELD_PATH_PATTERN.fullmatch(path)]
        if invalid:
            raise ValueError(f"structured_fields 的键必须是点路径：{'、'.join(invalid)}")
        return value

    def has_any(self) -> bool:
        """没有期望的用例永远通过，等于悄悄失效，因此加载期必须拦住。"""
        return any(
            (
                self.tool_called is not None,
                bool(self.tool_sequence),
                bool(self.must_contain),
                bool(self.must_not_contain),
                self.workflow_status is not None,
                bool(self.missing_slots),
                bool(self.structured_fields),
                self.price_consistency,
                self.interrupt_type is not None,
                self.max_latency_ms is not None,
                self.max_tokens is not None,
            )
        )


class EvalCase(BaseModel):
    """一条用例。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    # 省略时使用 AGENT__DEFAULT_PROFILE，与 /chat/stream 的缺省行为一致
    agent_id: str | None = Field(default=None, max_length=32)
    input: NonEmptyText = Field(max_length=4000)
    # 同一 thread 上的后续轮次，用于「改预算 / 补充槽位」这类多轮场景
    turns: list[NonEmptyText] = Field(default_factory=list, max_length=5)
    # HITL 恢复内容；配置后期望首轮暂停，仅 --real 执行
    resume: EvalResume | None = None
    expect: EvalExpectation

    @model_validator(mode="after")
    def _require_at_least_one_expectation(self) -> "EvalCase":
        if not self.expect.has_any():
            raise ValueError(
                "expect 至少需要 tool_called / tool_sequence / workflow_status / "
                "missing_slots / structured_fields / price_consistency / interrupt_type / "
                "must_contain / must_not_contain / max_latency_ms / max_tokens 之一"
            )
        return self


def _format_validation_error(exc: ValidationError) -> str:
    """压成「字段: 原因」的可读文本，便于直接改 YAML。"""
    details = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"]) or "<root>"
        details.append(f"{location}: {error['msg']}")
    return "；".join(details)


def _load_file(path: Path) -> list[EvalCase]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CaseLoadError(f"用例文件 {path.name} 不是合法 YAML：{exc}") from exc

    if not isinstance(raw, list):
        raise CaseLoadError(f"用例文件 {path.name} 必须是 YAML 列表（每条一个用例）")
    if len(raw) > MAX_CASES_PER_FILE:
        raise CaseLoadError(
            f"用例文件 {path.name} 超过 {MAX_CASES_PER_FILE} 条，请拆分为多个文件"
        )

    cases: list[EvalCase] = []
    for index, item in enumerate(raw, start=1):
        try:
            case = EvalCase.model_validate(item)
        except ValidationError as exc:
            raise CaseLoadError(
                f"用例文件 {path.name} 第 {index} 条校验失败：{_format_validation_error(exc)}"
            ) from exc
        if not CASE_ID_PATTERN.fullmatch(case.id):
            raise CaseLoadError(
                f"用例文件 {path.name} 第 {index} 条的 id 非法：{case.id}"
                "（需以小写字母或数字开头，只含小写字母/数字/下划线/连字符，最长 64）"
            )
        cases.append(case)
    return cases


def load_cases(directory: Path) -> list[EvalCase]:
    """加载目录下全部 `*.yaml`；id 跨文件唯一，否则报告无法区分用例。"""
    if not directory.is_dir():
        raise CaseLoadError(f"用例目录不存在：{directory}")

    cases: list[EvalCase] = []
    seen: set[str] = set()
    for path in sorted(directory.glob(f"*{CASE_FILE_SUFFIX}")):
        for case in _load_file(path):
            if case.id in seen:
                raise CaseLoadError(f"用例 id 重复：{case.id}（{path.name}）")
            seen.add(case.id)
            cases.append(case)

    if not cases:
        raise CaseLoadError(
            f"用例目录为空：{directory}（参考 cases/example.yaml 新增一条 YAML）"
        )
    return cases
