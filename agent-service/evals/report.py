"""评测报告：终端摘要与 JSON 结构化输出。

三种状态刻意区分：`passed` / `failed` / `skipped`。
假模型模式无法验证内容断言，这类用例记为 `skipped` 而不是 `passed`，
避免"没校验也算通过"的假绿。
"""

from dataclasses import dataclass, field

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

STATUS_LABELS = {
    STATUS_PASSED: "通过",
    STATUS_FAILED: "失败",
    STATUS_SKIPPED: "未校验",
}

MODE_FAKE = "fake"
MODE_REAL = "real"

MODE_DESCRIPTIONS = {
    MODE_FAKE: "假模型（只校验 Profile、工具绑定与图结构，零 API 费用）",
    MODE_REAL: "真实模型（会真正调用模型，产生 token 费用）",
}

MISSING_TOKENS_NOTICE = "-"


@dataclass(frozen=True)
class CheckResult:
    """一条断言的结果。"""

    name: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class CaseResult:
    """一条用例的完整结果。"""

    case_id: str
    agent_id: str
    checks: list[CheckResult] = field(default_factory=list)
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None

    @property
    def status(self) -> str:
        """任一断言失败即失败；只有一部分断言被跳过时记为「未校验」。"""
        if self.error is not None:
            return STATUS_FAILED
        statuses = {check.status for check in self.checks}
        if STATUS_FAILED in statuses:
            return STATUS_FAILED
        if STATUS_SKIPPED in statuses:
            return STATUS_SKIPPED
        return STATUS_PASSED

    @property
    def failure_details(self) -> list[str]:
        """失败原因，按「断言名: 说明」逐条列出。"""
        details = []
        if self.error is not None:
            details.append(f"执行失败: {self.error}")
        for check in self.checks:
            if check.status == STATUS_FAILED:
                details.append(f"{check.name}: {check.detail or '断言未通过'}")
        return details

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "agent_id": self.agent_id,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "tokens": {
                "prompt": self.prompt_tokens,
                "completion": self.completion_tokens,
            },
            "checks": [
                {"name": check.name, "status": check.status, "detail": check.detail}
                for check in self.checks
            ],
            "error": self.error,
        }


@dataclass(frozen=True)
class EvalReport:
    """一次运行的汇总。"""

    mode: str
    results: list[CaseResult]
    duration_ms: int = 0

    @property
    def counts(self) -> dict[str, int]:
        counts = {STATUS_PASSED: 0, STATUS_FAILED: 0, STATUS_SKIPPED: 0}
        for result in self.results:
            counts[result.status] += 1
        return counts

    @property
    def pass_rate(self) -> float:
        """已校验用例中的通过率；全部跳过时无法判定，返回 0。"""
        verified = self.counts[STATUS_PASSED] + self.counts[STATUS_FAILED]
        return self.counts[STATUS_PASSED] / verified if verified else 0.0

    @property
    def has_failures(self) -> bool:
        return self.counts[STATUS_FAILED] > 0

    def to_dict(self) -> dict[str, object]:
        counts = self.counts
        return {
            "mode": self.mode,
            "duration_ms": self.duration_ms,
            "summary": {
                "total": len(self.results),
                **counts,
                "pass_rate": round(self.pass_rate, 4),
            },
            "cases": [result.to_dict() for result in self.results],
        }

    def render_text(self) -> str:
        """人类可读摘要：结论在前，失败原因在后。"""
        counts = self.counts
        lines = [
            f"评测模式：{MODE_DESCRIPTIONS.get(self.mode, self.mode)}",
            (
                f"用例 {len(self.results)} 条：通过 {counts[STATUS_PASSED]}"
                f" / 失败 {counts[STATUS_FAILED]}"
                f" / 未校验 {counts[STATUS_SKIPPED]}"
                f" ｜ 校验通过率 {self.pass_rate * 100:.1f}%"
                f" ｜ 耗时 {self.duration_ms}ms"
            ),
            "",
        ]
        for result in self.results:
            lines.append(f"[{STATUS_LABELS[result.status]}] {result.case_id}"
                         f" (agent={result.agent_id}){self._render_metrics(result)}")
            for check in result.checks:
                if check.status == STATUS_FAILED:
                    lines.append(f"    - {check.name}: {check.detail or '断言未通过'}")
                elif check.status == STATUS_SKIPPED and check.detail:
                    lines.append(f"    - {check.name}: {check.detail}")
            if result.error is not None:
                lines.append(f"    - 执行失败: {result.error}")

        if counts[STATUS_FAILED]:
            lines.extend(["", "失败明细："])
            for result in self.results:
                for detail in result.failure_details:
                    lines.append(f"- {result.case_id} → {detail}")
        return "\n".join(lines)

    @staticmethod
    def _render_metrics(result: CaseResult) -> str:
        parts = []
        if result.latency_ms is not None:
            parts.append(f" {result.latency_ms}ms")
        if result.prompt_tokens is not None or result.completion_tokens is not None:
            prompt = (
                result.prompt_tokens
                if result.prompt_tokens is not None
                else MISSING_TOKENS_NOTICE
            )
            completion = (
                result.completion_tokens
                if result.completion_tokens is not None
                else MISSING_TOKENS_NOTICE
            )
            parts.append(f" tokens {prompt}/{completion}")
        return "".join(parts)
