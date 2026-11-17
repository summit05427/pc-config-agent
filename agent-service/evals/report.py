"""评测报告：终端摘要与 JSON 结构化输出。

三种状态刻意区分：`passed` / `failed` / `skipped`。
假模型模式无法验证内容断言，这类用例记为 `skipped` 而不是 `passed`，
避免"没校验也算通过"的假绿。
"""

from dataclasses import dataclass, field
from math import ceil
from typing import Any

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
MODE_E2E_LOCAL = "e2e-local"
MODE_E2E_SERVICE = "e2e-service"

MODE_DESCRIPTIONS = {
    MODE_FAKE: "假模型（只校验 Profile、工具绑定与图结构，零 API 费用）",
    MODE_REAL: "真实模型（会真正调用模型，产生 token 费用）",
    MODE_E2E_LOCAL: "E2E 本地契约（进程内 ASGI + 确定性假图，零 API 费用）",
    MODE_E2E_SERVICE: "E2E 真实服务（登录 + HTTP/SSE + 会话落库，产生 token 费用）",
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
    # 计费调用次数与折算成本：未采集到或未配置单价时保持 None
    llm_calls: int | None = None
    cost: float | None = None
    # 图终态与修正轮次：用于计算修正成功率与硬约束统计
    workflow_status: str | None = None
    repair_count: int | None = None
    # 只有期望产出配置的用例才计入修正成功率；负向用例失败是预期行为
    expects_success: bool = True
    # 单轮最大调用次数：多轮用例按轮统计，门禁口径是「单轮 ≤5 次」
    max_turn_llm_calls: int | None = None
    # 质量评审结论：None 表示该用例没有进入评审（如纯澄清），不参与分母
    quality_passed: bool | None = None
    # PASS / FAIL / UNKNOWN / None（未产出配置，不参与硬约束统计）
    hard_constraint: str | None = None
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
            "llm_calls": self.llm_calls,
            "cost": self.cost,
            "workflow_status": self.workflow_status,
            "repair_count": self.repair_count,
            "max_turn_llm_calls": self.max_turn_llm_calls,
            "quality_passed": self.quality_passed,
            "hard_constraint": self.hard_constraint,
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
    # 成本币种随定价配置走；未配置单价时所有成本字段为 None
    currency: str = "CNY"

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

    @property
    def p95_latency_ms(self) -> int | None:
        """最近秩法 p95：只看真正跑起来的用例。

        额度耗尽、模型未解析这类用例在几毫秒内就失败，计入会把 p95 拉成假绿。
        """
        latencies = sorted(
            result.latency_ms
            for result in self.results
            if result.latency_ms is not None and result.error is None
        )
        if not latencies:
            return None
        index = max(0, ceil(0.95 * len(latencies)) - 1)
        return latencies[index]

    @property
    def max_llm_calls(self) -> int | None:
        calls = [
            result.llm_calls for result in self.results if result.llm_calls is not None
        ]
        return max(calls) if calls else None

    @property
    def max_turn_llm_calls(self) -> int | None:
        """单轮最大调用次数：多轮用例不能把两轮之和当一轮，门禁看的是单轮。"""
        calls = [
            result.max_turn_llm_calls
            for result in self.results
            if result.max_turn_llm_calls is not None
        ]
        return max(calls) if calls else None

    @property
    def total_prompt_tokens(self) -> int | None:
        return self._sum_tokens("prompt_tokens")

    @property
    def total_completion_tokens(self) -> int | None:
        return self._sum_tokens("completion_tokens")

    @property
    def total_cost(self) -> float | None:
        """所有用例成本之和；任一条缺定价时返回 None，不用 0 冒充已核算。"""
        costs = [result.cost for result in self.results]
        if any(cost is None for cost in costs):
            return None
        return round(sum(cost for cost in costs if cost is not None), 6)

    def _sum_tokens(self, attribute: str) -> int | None:
        values = [
            getattr(result, attribute)
            for result in self.results
            if getattr(result, attribute) is not None
        ]
        return sum(values) if values else None

    @property
    def quality_stats(self) -> dict[str, Any]:
        """质量评审通过率：只统计进入过评审的用例，缺失不算通过。"""
        evaluated = [
            result for result in self.results if result.quality_passed is not None
        ]
        passed = [result for result in evaluated if result.quality_passed]
        return {
            "evaluated": len(evaluated),
            "passed": len(passed),
            "pass_rate": (
                round(len(passed) / len(evaluated), 4) if evaluated else None
            ),
        }

    @property
    def hard_constraint_stats(self) -> dict[str, Any]:
        """硬约束通过率：UNKNOWN 一律不算通过，未产出配置的用例不参与分母。"""
        counts = {STATUS_PASSED: 0, STATUS_FAILED: 0, "unknown": 0, "not_applicable": 0}
        for result in self.results:
            if result.hard_constraint is None:
                counts["not_applicable"] += 1
            elif result.hard_constraint == "PASS":
                counts[STATUS_PASSED] += 1
            elif result.hard_constraint == "FAIL":
                counts[STATUS_FAILED] += 1
            else:
                counts["unknown"] += 1
        applicable = counts[STATUS_PASSED] + counts[STATUS_FAILED] + counts["unknown"]
        return {
            **counts,
            "pass_rate": (
                round(counts[STATUS_PASSED] / applicable, 4) if applicable else None
            ),
        }

    @property
    def repair_stats(self) -> dict[str, Any]:
        """修正成功率：只统计真正进入过修正的用例，成功以图终态 success 为准。"""
        attempted = [
            result
            for result in self.results
            if (result.repair_count or 0) > 0 and result.expects_success
        ]
        succeeded = [
            result for result in attempted if result.workflow_status == "success"
        ]
        return {
            "attempted": len(attempted),
            "succeeded": len(succeeded),
            "success_rate": (
                round(len(succeeded) / len(attempted), 4) if attempted else None
            ),
        }

    @property
    def metrics(self) -> dict[str, object]:
        """门禁所需的量化口径；缺样本时显式给 None，不编造数字。"""
        return {
            "p95_latency_ms": self.p95_latency_ms,
            "max_llm_calls": self.max_llm_calls,
            "max_turn_llm_calls": self.max_turn_llm_calls,
            "tokens": {
                "prompt": self.total_prompt_tokens,
                "completion": self.total_completion_tokens,
            },
            "cost": {
                "total": self.total_cost,
                "currency": self.currency,
            },
            "hard_constraint": self.hard_constraint_stats,
            "quality": self.quality_stats,
            "repair": self.repair_stats,
        }

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
            "metrics": self.metrics,
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
            self._render_gate_metrics(),
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
        if result.llm_calls is not None:
            parts.append(f" calls {result.llm_calls}")
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
        if result.cost is not None:
            parts.append(f" cost {result.cost:.6f}")
        return "".join(parts)

    def _render_gate_metrics(self) -> str:
        """门禁口径单独一行，缺失值显式写「未采集」，不让人误读成 0。"""
        p95 = self.p95_latency_ms
        max_calls = self.max_turn_llm_calls
        total_cost = self.total_cost
        hard = self.hard_constraint_stats
        quality = self.quality_stats
        repair = self.repair_stats
        hard_rate = hard["pass_rate"]
        quality_rate = quality["pass_rate"]
        repair_rate = repair["success_rate"]
        return (
            "门禁指标："
            f"p95 时延 {p95 if p95 is not None else '未采集'}ms"
            f" ｜ 单轮最大 LLM 调用 {max_calls if max_calls is not None else '未采集'}"
            f" ｜ tokens {self.total_prompt_tokens or 0}/{self.total_completion_tokens or 0}"
            f" ｜ 成本 "
            f"{f'{total_cost:.6f} {self.currency}' if total_cost is not None else '未定价'}"
            f" ｜ 硬约束通过率 "
            f"{f'{hard_rate * 100:.1f}%' if hard_rate is not None else '无样本'}"
            f"（通过 {hard['passed']} / 失败 {hard['failed']} / UNKNOWN {hard['unknown']}）"
            f" ｜ 质量评审通过率 "
            f"{f'{quality_rate * 100:.1f}%' if quality_rate is not None else '无样本'}"
            f"（{quality['passed']}/{quality['evaluated']}）"
            f" ｜ 修正成功率 "
            f"{f'{repair_rate * 100:.1f}%' if repair_rate is not None else '无样本'}"
            f"（{repair['succeeded']}/{repair['attempted']}）"
        )
