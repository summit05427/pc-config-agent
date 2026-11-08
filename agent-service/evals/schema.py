"""评测用例的 Schema 与加载。

用例是接入方资产：新增一个场景只改 YAML，不改脚手架代码。
校验失败必须带文件名与字段位置，否则接入方无从下手。
"""

import re
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
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


class CaseLoadError(RuntimeError):
    """用例文件缺失或非法；消息面向接入方，必须能直接定位到文件与字段。"""


class EvalExpectation(BaseModel):
    """一条用例的期望；可组合，任一不满足即判失败。"""

    model_config = ConfigDict(extra="forbid")

    # 期望本轮调用的工具名；假模型模式靠它校验工具是否已注册并被该 Profile 绑定
    tool_called: str | None = Field(default=None, max_length=64)
    must_contain: list[ExpectationText] = Field(default_factory=list, max_length=20)
    must_not_contain: list[ExpectationText] = Field(default_factory=list, max_length=20)


class EvalCase(BaseModel):
    """一条用例。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    # 省略时使用 AGENT__DEFAULT_PROFILE，与 /chat/stream 的缺省行为一致
    agent_id: str | None = Field(default=None, max_length=32)
    input: NonEmptyText = Field(max_length=4000)
    expect: EvalExpectation

    @model_validator(mode="after")
    def _require_at_least_one_expectation(self) -> "EvalCase":
        """没有期望的用例永远通过，等于悄悄失效，所以在加载期就拒绝。"""
        has_expectation = (
            self.expect.tool_called is not None
            or self.expect.must_contain
            or self.expect.must_not_contain
        )
        if not has_expectation:
            raise ValueError(
                "expect 至少需要 tool_called / must_contain / must_not_contain 之一"
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
