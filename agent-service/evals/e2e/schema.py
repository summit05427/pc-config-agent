"""E2E 用例 Schema 与加载。

与 `evals/schema.py` 分开的原因：那里的断言面向「图状态」，需要进程内拿到
最终 state；E2E 只能看到 HTTP 响应、SSE 事件与落库结果，因此另立一套字段，
避免在同一模型里塞入大量只在某一模式生效的字段。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
)

CASE_FILE_SUFFIX = ".yaml"
CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MAX_CASES_PER_FILE = 50

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ExpectationText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
ShortName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]

# 本轮允许的终态：正常完成 / HITL 暂停 / 流内错误
TerminalEvent = Literal["done", "interrupt", "error"]


class E2ECaseLoadError(RuntimeError):
    """用例文件缺失或非法；消息必须能直接定位到文件与字段。"""


class E2ELocalScript(BaseModel):
    """local 模式由假图产出的确定性脚本。

    service 模式忽略该字段：真实模型输出不能由用例预置。
    """

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(default="这是本地契约模式的确定性回答。", max_length=2000)
    # 是否产出 `done.build_result`；None 表示跟随 expect.expect_build_result
    build_result: bool | None = None
    # 假图会先发出这些工具事件，用于校验 SSE 工具事件契约
    tool_names: list[ShortName] = Field(default_factory=list, max_length=8)
    # 非空时首轮以 interrupt 结束；结构即 SSE interrupt 事件负载（不含 interrupt_id）
    interrupt: dict[str, Any] | None = None


class E2EResume(BaseModel):
    """HITL 恢复内容：首轮暂停后提交的结构化答案。

    与 `/chat/stream` 的 `resume` 字段同构；`message` 进入用户气泡，
    `answer` 交给门控节点校验。
    """

    model_config = ConfigDict(extra="forbid")

    message: str = Field(default="", max_length=4000)
    answer: dict[str, Any] = Field(default_factory=dict, max_length=16)


class E2EExpectation(BaseModel):
    """一条 E2E 用例的断言集合；契约层断言始终开启，这里只放可选加强项。"""

    model_config = ConfigDict(extra="forbid")

    # 期望的终态事件；HITL 用例写 interrupt，负向用例写 error
    terminal: TerminalEvent = "done"
    # 期望出现过的工具名（集合包含，不校验顺序）
    tool_names: list[ShortName] = Field(default_factory=list, max_length=8)
    must_contain: list[ExpectationText] = Field(default_factory=list, max_length=20)
    must_not_contain: list[ExpectationText] = Field(default_factory=list, max_length=20)
    # 是否要求 done.build_result 存在；存在时始终校验八类与价格一致性
    expect_build_result: bool = False
    # None 表示不关心；True/False 表示必须出现/必须不出现 citations 事件
    expect_citations: bool | None = None
    max_latency_ms: int | None = Field(default=None, ge=0)


class E2ECase(BaseModel):
    """一条 E2E 用例：一次请求、一次断言。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    # 省略时使用 AGENT__DEFAULT_PROFILE，与 /chat/stream 缺省行为一致
    agent_id: str | None = Field(default=None, max_length=32)
    message: NonEmptyText = Field(max_length=4000)
    expect: E2EExpectation = Field(default_factory=E2EExpectation)
    # 配置后首轮必须暂停在 interrupt；随后自动用同一 thread_id 提交恢复
    resume: E2EResume | None = None
    # 恢复回合的期望；省略时要求正常 done
    resume_expect: E2EExpectation | None = None
    local: E2ELocalScript = Field(default_factory=E2ELocalScript)


def _format_validation_error(exc: ValidationError) -> str:
    details = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"]) or "<root>"
        details.append(f"{location}: {error['msg']}")
    return "；".join(details)


def _load_file(path: Path) -> list[E2ECase]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise E2ECaseLoadError(f"用例文件 {path.name} 不是合法 YAML：{exc}") from exc

    if not isinstance(raw, list):
        raise E2ECaseLoadError(f"用例文件 {path.name} 必须是 YAML 列表（每条一个用例）")
    if len(raw) > MAX_CASES_PER_FILE:
        raise E2ECaseLoadError(
            f"用例文件 {path.name} 超过 {MAX_CASES_PER_FILE} 条，请拆分"
        )

    cases: list[E2ECase] = []
    for index, item in enumerate(raw, start=1):
        try:
            case = E2ECase.model_validate(item)
        except ValidationError as exc:
            raise E2ECaseLoadError(
                f"用例文件 {path.name} 第 {index} 条校验失败：{_format_validation_error(exc)}"
            ) from exc
        if not CASE_ID_PATTERN.fullmatch(case.id):
            raise E2ECaseLoadError(
                f"用例文件 {path.name} 第 {index} 条的 id 非法：{case.id}"
                "（需以小写字母或数字开头，只含小写字母/数字/下划线/连字符，最长 64）"
            )
        cases.append(case)
    return cases


def load_e2e_cases(directory: Path) -> list[E2ECase]:
    """加载目录下全部 `*.yaml`；id 跨文件唯一，否则报告无法区分用例。"""
    if not directory.is_dir():
        raise E2ECaseLoadError(f"用例目录不存在：{directory}")

    cases: list[E2ECase] = []
    seen: set[str] = set()
    for path in sorted(directory.glob(f"*{CASE_FILE_SUFFIX}")):
        for case in _load_file(path):
            if case.id in seen:
                raise E2ECaseLoadError(f"用例 id 重复：{case.id}（{path.name}）")
            seen.add(case.id)
            cases.append(case)

    if not cases:
        raise E2ECaseLoadError(
            f"用例目录为空：{directory}（参考 evals/e2e/cases/baseline.yaml）"
        )
    return cases
