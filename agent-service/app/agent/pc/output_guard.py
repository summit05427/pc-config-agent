"""输出层事实校验：给确定性渲染加一道可回归的断言网。

为什么需要它：渲染器本身按 Java 返回的数据渲染，但一旦上游数据自相矛盾
（分项与总价不一致、预算状态与总价矛盾），或未验证项被表述成已确认，
用户会直接看到错误结论。这里只做可判定的确定性校验，不对自由文本做型号穷举。
"""

from dataclasses import dataclass
from typing import Any

import structlog

from app.agent.pc.renderer import (
    as_int,
    as_list,
    as_mapping,
    as_text,
    overall_compatibility,
)
from app.core.metrics import OUTPUT_GUARD_VIOLATIONS

logger = structlog.get_logger(__name__)

# 模型文案只允许谈取舍；数字、渠道与价格一律视为越界
REASON_FORBIDDEN_WORDS = ("http", "www", "京东", "淘宝", "天猫", "¥", "元", "￥")
REASON_MAX_CHARS = 300
# 「已确认」类表述只允许在整体结论为 PASS 时出现
CONFIRMED_COMPATIBILITY_CLAIMS = ("完全兼容", "已确认兼容", "全部通过", "全部兼容")
# 否定语境（如「不能视为已确认兼容」）不算虚假宣称，命中词前 6 个字内出现即视为否定
NEGATION_PREFIXES = ("不能", "不可", "无法", "并非", "尚未", "不算", "未", "不", "非")

RULE_PRICE_TOTAL_MISMATCH = "price_total_mismatch"
RULE_BUDGET_STATUS_MISMATCH = "budget_status_mismatch"
RULE_UNKNOWN_CLAIMED_COMPATIBLE = "unknown_claimed_compatible"
RULE_REASON_UNSAFE = "reason_unsafe"

GUARD_NOTICE_MESSAGES = {
    RULE_PRICE_TOTAL_MISMATCH: "价格分项与总价不一致，以上价格仅供参考。",
    RULE_BUDGET_STATUS_MISMATCH: "预算状态与总价不一致，请以实际结算价格为准。",
    RULE_UNKNOWN_CLAIMED_COMPATIBLE: "存在未验证的兼容性项，不能视为已确认兼容。",
    RULE_REASON_UNSAFE: "推荐说明未通过内容自检，已改用确定性说明。",
}


@dataclass(frozen=True)
class GuardViolation:
    rule: str
    detail: str


def sanitize_reason(text: str | None, build: dict[str, Any]) -> str | None:
    """模型文案只允许谈取舍；出现数字、型号、价格或渠道一律丢弃。

    上游 prompt 已要求「不得出现具体型号与价格」，这里是最后一道防线：
    宁可不展示模型文案，也不让越界内容进入回答。
    """
    if not text:
        return None
    reason = " ".join(text.split()).strip()
    if not reason or len(reason) > REASON_MAX_CHARS:
        return None
    if any(char.isdigit() for char in reason):
        return None
    if any(keyword in reason for keyword in REASON_FORBIDDEN_WORDS):
        return None
    lowered = reason.lower()
    for component in as_list(build.get("components")):
        item = as_mapping(component)
        for field in ("modelName", "brand"):
            value = as_text(item.get(field))
            if value and value.lower() in lowered:
                return None
    return reason


def _reason_problems(reason: str, build: dict[str, Any]) -> list[str]:
    """最终文案的兜底检查；与 sanitize_reason 同规则，用于发现绕过入口的改动。"""
    problems = []
    if any(char.isdigit() for char in reason):
        problems.append("包含数字")
    if any(keyword in reason for keyword in REASON_FORBIDDEN_WORDS):
        problems.append("包含价格或渠道词")
    lowered = reason.lower()
    selected = [
        as_text(as_mapping(component).get(field))
        for component in as_list(build.get("components"))
        for field in ("modelName", "brand")
    ]
    if any(value and value.lower() in lowered for value in selected):
        problems.append("提到具体型号")
    return problems


def _price_violation(build: dict[str, Any]) -> GuardViolation | None:
    prices = [
        price
        for price in (
            as_mapping(component).get("priceFen")
            for component in as_list(build.get("components"))
        )
        if isinstance(price, int) and not isinstance(price, bool)
    ]
    total = as_int(build.get("totalPriceFen"))
    if not prices or total <= 0:
        return None
    if sum(prices) == total:
        return None
    return GuardViolation(
        RULE_PRICE_TOTAL_MISMATCH,
        f"分项合计 {sum(prices)} 分 ≠ 总价 {total} 分",
    )


def _budget_violation(build: dict[str, Any]) -> GuardViolation | None:
    total = as_int(build.get("totalPriceFen"))
    budget_max = as_int(build.get("budgetMaxFen"))
    budget_status = as_text(build.get("budgetStatus"))
    if budget_max <= 0 or total <= budget_max or budget_status != "WITHIN_BUDGET":
        return None
    return GuardViolation(
        RULE_BUDGET_STATUS_MISMATCH,
        f"总价 {total} 分超出预算 {budget_max} 分，却标记为预算内",
    )


def _has_unnegated_claim(text: str, claim: str) -> bool:
    """判断文本是否在非否定语境下宣称了某个结论。"""
    start = 0
    while True:
        index = text.find(claim, start)
        if index < 0:
            return False
        prefix = text[max(0, index - 6) : index]
        if not any(negation in prefix for negation in NEGATION_PREFIXES):
            return True
        start = index + len(claim)


def check_build_output(
    *,
    build: dict[str, Any],
    compatibility_report: dict[str, Any],
    reason: str,
    markdown: str,
) -> list[GuardViolation]:
    """校验最终回答与构建数据是否自洽；返回空列表表示通过。"""
    violations: list[GuardViolation] = []

    for violation in (_price_violation(build), _budget_violation(build)):
        if violation is not None:
            violations.append(violation)

    overall = overall_compatibility(compatibility_report)
    if overall != "PASS":
        claim_text = f"{reason}\n{markdown}"
        claims = [
            claim
            for claim in CONFIRMED_COMPATIBILITY_CLAIMS
            if _has_unnegated_claim(claim_text, claim)
        ]
        if claims:
            violations.append(
                GuardViolation(
                    RULE_UNKNOWN_CLAIMED_COMPATIBLE,
                    f"兼容性结论为 {overall}，但回答出现「{'、'.join(claims)}」",
                )
            )

    problems = _reason_problems(reason, build)
    if problems:
        violations.append(GuardViolation(RULE_REASON_UNSAFE, "、".join(problems)))

    return violations


def render_guard_notice(violations: list[GuardViolation]) -> str:
    """把命中项以用户可见的提示追加到回答；数据问题必须让用户知道，不能静默。"""
    lines = ["", "> 输出校验提示："]
    seen: set[str] = set()
    for violation in violations:
        message = GUARD_NOTICE_MESSAGES.get(violation.rule, "该结论未通过自检。")
        if message in seen:
            continue
        seen.add(message)
        lines.append(f"> - {message}")
    return "\n".join(lines)


def record_violations(violations: list[GuardViolation], *, agent_id: str) -> None:
    """指标按规则聚合；日志保留明细，便于定位是数据问题还是文案问题。"""
    for violation in violations:
        OUTPUT_GUARD_VIOLATIONS.labels(rule=violation.rule).inc()
    logger.warning(
        "agent.output_guard.violation",
        agent_id=agent_id,
        rules=[violation.rule for violation in violations],
        details=[violation.detail for violation in violations],
    )
