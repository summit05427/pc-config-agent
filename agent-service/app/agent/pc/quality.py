"""配置方案的质量评审。

为什么需要这一层：Java 只保证「装得下、预算内」，不保证「搭得合理」。
低端 CPU 配旗舰显卡、办公场景买高端独显，都能通过兼容性校验；
这里用确定性规则兜住质量底线，并把可修正的问题转成结构化反馈交给 Architect。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.pc.renderer import as_int, as_mapping, as_text
from app.agent.pc.schemas import REQUIRED_CATEGORIES, BuildScenario, PCRequirements
from app.agent.pc.state import PCConfigState
from app.agent.pc.status import (
    FAILURE_QUALITY_CONSTRAINT,
    STATUS_RETRY,
    STATUS_SUCCESS,
)

# 独显低于该价格时视为亮机卡，不再要求 CPU/GPU 价格比例
GPU_BALANCE_MIN_PRICE_FEN = 200_000
# CPU 价格至少为显卡价格的 15%，否则视为明显瓶颈（5600 + 5080 = 7.7%）
CPU_GPU_MIN_RATIO_PERCENT = 15
# 重解时把 CPU 门槛抬高到显卡价格的 25%，给选型留出跨越档位的空间
CPU_GPU_RETRY_RATIO_PERCENT = 25
# 办公/影音场景显卡不超过预算的 15%，避免为轻负载购买旗舰显卡
OFFICE_GPU_BUDGET_PERCENT = 15
OFFICE_GPU_PRICE_CAP_FEN = 150_000
# 总价低于预算下限的 80% 时只提示，不强制重解：省钱本身不是错误
BUDGET_MIN_NOTICE_PERCENT = 80
MAX_QUALITY_RETRIES = 1

BALANCE_SCENARIOS = frozenset(
    {
        BuildScenario.GAMING,
        BuildScenario.GENERAL,
        BuildScenario.BALANCED,
        BuildScenario.CREATIVE,
        BuildScenario.VIDEO_EDITING,
        BuildScenario.RENDERING,
        BuildScenario.PROGRAMMING,
    }
)
OFFICE_SCENARIOS = frozenset({BuildScenario.OFFICE, BuildScenario.MEDIA})

NOTICE_IMBALANCE = "当前预算下 CPU 与显卡档位仍不均衡，建议提高预算或下调显卡档位。"
NOTICE_OFFICE_GPU = "办公/影音场景未找到更低功耗的显卡，方案可能偏重图形性能。"
NOTICE_BUDGET_RANGE = "当前总价低于预算下限，方案优先保证性价比，余量可留作显示器与外设。"


@dataclass(frozen=True)
class QualityReview:
    """一次质量评审的结果；`retry` 为真时由调用方向 Architect 下发反馈。"""

    issues: tuple[str, ...]
    notices: tuple[str, ...]
    retry: bool
    findings: tuple[dict[str, Any], ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "issues": list(self.issues),
            "notices": list(self.notices),
            "retry": self.retry,
        }

    def to_feedback(self, repair_attempt: int) -> dict[str, Any]:
        """结构化反馈：只描述类别、现状与方向，不下发任何求解器参数。"""
        affected = {
            category
            for finding in self.findings
            for category in finding["affected_categories"]
        }
        all_categories = [category.value for category in REQUIRED_CATEGORIES]
        return {
            "failure_type": FAILURE_QUALITY_CONSTRAINT,
            "findings": [dict(finding) for finding in self.findings],
            "must_preserve_categories": [
                category for category in all_categories if category not in affected
            ],
            "allowed_changes": sorted(affected),
            "repair_attempt": repair_attempt,
        }


def _component(build: dict[str, Any], category: str) -> dict[str, Any]:
    for item in build.get("components") or []:
        entry = as_mapping(item)
        if as_text(entry.get("category")) == category:
            return entry
    return {}


def _ceil_percent(value: int, percent: int) -> int:
    """整数向上取整，避免 25% 门槛被截断后仍然低于临界值。"""
    return (value * percent + 99) // 100


def _cpu_gpu_imbalance(cpu_price: int, gpu_price: int) -> dict[str, Any] | None:
    """CPU 明显低于显卡档位时返回发现项与目标价格。"""
    if gpu_price < GPU_BALANCE_MIN_PRICE_FEN or cpu_price <= 0:
        return None
    if cpu_price * 100 >= gpu_price * CPU_GPU_MIN_RATIO_PERCENT:
        return None
    target = max(cpu_price, _ceil_percent(gpu_price, CPU_GPU_RETRY_RATIO_PERCENT))
    return {
        "issue": "cpu_gpu_imbalance",
        "affected_categories": ["CPU"],
        "current_value_fen": cpu_price,
        "target_value_fen": target,
        "direction": "increase",
    }


def _office_gpu_overspend(
    budget_max: int | None, gpu_price: int
) -> dict[str, Any] | None:
    """办公/影音场景显卡超预算比例时返回发现项与目标价格。"""
    if gpu_price <= 0:
        return None
    cap = (
        budget_max * OFFICE_GPU_BUDGET_PERCENT // 100
        if budget_max
        else OFFICE_GPU_PRICE_CAP_FEN
    )
    if gpu_price <= cap:
        return None
    target = max(0, min(cap, gpu_price - 1))
    return {
        "issue": "office_gpu_overspend",
        "affected_categories": ["GPU"],
        "current_value_fen": gpu_price,
        "target_value_fen": target,
        "direction": "decrease",
    }


def review_build(
    *,
    requirements: PCRequirements,
    build: dict[str, Any],
    retry_count: int,
) -> QualityReview:
    """按确定性规则评审一套已通过兼容性校验的配置。

    :param requirements: 本轮结构化需求
    :param build: Java 返回的配置结果
    :param retry_count: 已发生的质量重解次数
    """
    issues: list[str] = []
    notices: list[str] = []
    findings: list[dict[str, Any]] = []
    retryable = False

    cpu_price = as_int(_component(build, "CPU").get("priceFen"))
    gpu_price = as_int(_component(build, "GPU").get("priceFen"))
    total_price = as_int(build.get("totalPriceFen"))
    budget_max = requirements.budget_max_fen
    scenario = requirements.scenario

    imbalance = _cpu_gpu_imbalance(cpu_price, gpu_price)
    if scenario in BALANCE_SCENARIOS and imbalance is not None:
        issues.append("cpu_gpu_imbalance")
        findings.append(imbalance)
        retryable = True

    overspend = _office_gpu_overspend(budget_max, gpu_price)
    if scenario in OFFICE_SCENARIOS and overspend is not None:
        issues.append("office_gpu_overspend")
        findings.append(overspend)
        retryable = True

    budget_min = requirements.budget_min_fen
    if (
        budget_min is not None
        and total_price > 0
        and total_price * 100 < budget_min * BUDGET_MIN_NOTICE_PERCENT
    ):
        # 预算区间只约束上限；低于下限说明方案偏省，提示即可，不强迫加钱
        issues.append("budget_below_range")
        notices.append(NOTICE_BUDGET_RANGE)

    if retryable and retry_count >= MAX_QUALITY_RETRIES:
        retryable = False
        if "cpu_gpu_imbalance" in issues:
            notices.append(NOTICE_IMBALANCE)
        if "office_gpu_overspend" in issues:
            notices.append(NOTICE_OFFICE_GPU)

    return QualityReview(
        issues=tuple(issues),
        notices=tuple(dict.fromkeys(notices)),
        retry=retryable,
        findings=tuple(findings),
    )


async def quality_review(state: PCConfigState) -> dict[str, Any]:
    """质量评审节点：只处理已生成成功的方案，最多触发一次重解。"""
    if as_text(state.get("workflow_status")) != STATUS_SUCCESS:
        return {}
    try:
        requirements = PCRequirements.model_validate(state.get("requirements") or {})
    except ValueError:
        return {}

    retry_count = as_int(state.get("quality_retry_count"))
    review = review_build(
        requirements=requirements,
        build=as_mapping(state.get("build_result")),
        retry_count=retry_count,
    )
    if review.retry:
        return {
            "workflow_status": STATUS_RETRY,
            "quality_retry_count": retry_count + 1,
            "quality_review": review.to_payload(),
            "quality_feedback": review.to_feedback(retry_count + 1),
        }

    update: dict[str, Any] = {"quality_review": review.to_payload()}
    if review.notices:
        update["quality_notice"] = "；".join(review.notices)
    return update
