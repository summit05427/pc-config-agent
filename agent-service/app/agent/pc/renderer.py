"""确定性 Markdown 渲染与前端卡片投影。

为什么不用 LLM 生成正文：型号、价格、链接必须来自 Java 结构化结果，
让模型复述会带来虚构价格/链接的风险。LLM 只生成一段不含型号与数字的推荐说明。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agent.pc.schemas import REQUIRED_CATEGORIES
from app.agent.pc.status import (
    EMPTY_CANDIDATES_MESSAGE,
    STATUS_ABORTED,
    STATUS_CLARIFICATION,
    STATUS_COMPATIBILITY_FAILED,
    STATUS_INVALID,
    STATUS_NO_CANDIDATES,
    STATUS_NO_SOLUTION,
    STATUS_UPSTREAM_ERROR,
    UPSTREAM_ERROR_MESSAGE,
)

MOCK_PRICE_SOURCE = "MOCK_DEMO"
DEMO_PRICE_NOTICE = (
    "> **价格说明：当前方案包含演示价格，非真实在售，不能作为已核验报价使用。**"
)

CATEGORY_LABELS: dict[str, str] = {
    "CPU": "CPU",
    "MOTHERBOARD": "主板",
    "MEMORY": "内存",
    "GPU": "显卡",
    "PSU": "电源",
    "CASE": "机箱",
    "COOLER": "散热器",
    "STORAGE": "硬盘",
}

COMPATIBILITY_LABELS: dict[str, str] = {
    "PASS": "通过",
    "WARNING": "需要注意",
    "FAIL": "不通过",
    "UNKNOWN": "未验证",
}

BUDGET_LABELS: dict[str, str] = {
    "WITHIN_BUDGET": "预算内",
    "OVER_BUDGET": "超出预算",
    "NO_BUDGET": "未设置预算",
}

SCENARIO_LABELS: dict[str, str] = {
    "GENERAL": "综合均衡",
    "GAMING": "游戏",
    "VIDEO_EDITING": "视频编辑",
    "PROGRAMMING": "编程开发",
    "RENDERING": "渲染",
    "AI_INFERENCE": "本地 AI 推理",
    "CREATIVE": "创作",
    "WORKSTATION": "工作站",
    "OFFICE": "办公",
    "BALANCED": "均衡",
}


def as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_int(value: Any, default: int = 0) -> int:
    """只接受真正的整数；金额禁止经过浮点。"""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def as_text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) and value else default


def format_fen(amount_fen: int) -> str:
    """整数分格式化为人民币元，全程不经过浮点。"""
    sign = "-" if amount_fen < 0 else ""
    yuan, fen = divmod(abs(amount_fen), 100)
    return f"{sign}¥{yuan:,}.{fen:02d}"


def has_demo_price(build: dict[str, Any]) -> bool:
    """只要存在演示价，最终输出就必须显式提示，不能被说成已核验。"""
    if as_int(build.get("demoOfferCount")) > 0:
        return True
    for component in as_list(build.get("components")):
        item = as_mapping(component)
        if item.get("priceSource") == MOCK_PRICE_SOURCE:
            return True
        if item.get("priceSource") and item.get("verifiedPrice") is False:
            return True
    return False


def safe_url(value: Any) -> str | None:
    url = as_text(value)
    if url.startswith("https://") or url.startswith("http://"):
        return url
    return None


def _escape_cell(value: str) -> str:
    return value.replace("|", "／").replace("\n", " ").strip()


def _benchmark_text(item: dict[str, Any]) -> str:
    benchmark_type = as_text(item.get("benchmarkType"))
    score = item.get("benchmarkScore")
    if not benchmark_type or not isinstance(score, (int, float)) or isinstance(score, bool):
        return "—"
    return f"{benchmark_type} {score:g}"


def _compatibility_label(status: str) -> str:
    return COMPATIBILITY_LABELS.get(status, "未验证")


def overall_compatibility(report: dict[str, Any]) -> str:
    """整体兼容性结论；UNKNOWN 一律保留为未验证，不得折算成通过。"""
    status = as_text(report.get("overallStatus"))
    if status:
        return status
    checks = [as_mapping(item) for item in as_list(report.get("checks"))]
    statuses = {as_text(item.get("status")) for item in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "UNKNOWN" in statuses:
        return "UNKNOWN"
    if "WARNING" in statuses:
        return "WARNING"
    return "PASS"


def _demo_notice(build: dict[str, Any]) -> list[str]:
    return [DEMO_PRICE_NOTICE, ""] if has_demo_price(build) else []


def _requirements_line(build: dict[str, Any]) -> str:
    requirements = as_mapping(build.get("requirements"))
    scenario = SCENARIO_LABELS.get(as_text(requirements.get("scenario")), "均衡")
    budget = requirements.get("budgetMaxFen")
    if isinstance(budget, int) and not isinstance(budget, bool):
        return f"场景：{scenario}；预算上限：{format_fen(budget)}"
    return f"场景：{scenario}；预算上限：未设置"


def _component_row(item: dict[str, Any]) -> str:
    category = as_text(item.get("category"))
    label = CATEGORY_LABELS.get(category, category or "未知")
    model = _escape_cell(as_text(item.get("modelName"), "—"))
    spec = _escape_cell(as_text(item.get("specSummary"), "—"))
    price = format_fen(as_int(item.get("priceFen")))
    url = safe_url(item.get("purchaseUrl"))
    link = f"[购买]({url})" if url else "—"
    verified = as_text(item.get("verifiedAt"), "未核验")
    source = as_text(item.get("priceSource"))
    if source == MOCK_PRICE_SOURCE:
        price = f"{price}（演示）"
    return (
        f"| {label} | {model} | {spec} | {price} | "
        f"{_benchmark_text(item)} | {link} | {verified} |"
    )


def build_components_in_order(build: dict[str, Any]) -> list[dict[str, Any]]:
    """按固定类别顺序返回组件，缺失类别补空位以便前端稳定渲染。"""
    by_category = {
        as_text(as_mapping(item).get("category")): as_mapping(item)
        for item in as_list(build.get("components"))
    }
    return [
        by_category.get(category.value, {"category": category.value})
        for category in REQUIRED_CATEGORIES
    ]


def render_build_markdown(build: dict[str, Any], reason_summary: str) -> str:
    """把 Java 的结构化结果渲染成确定性 Markdown。"""
    lines: list[str] = []
    lines.extend(_demo_notice(build))
    lines.append("## 推荐配置")
    lines.append("")
    lines.append(_requirements_line(build))
    lines.append("")
    lines.append("| 类别 | 型号 | 规格 | 单价 | 跑分 | 链接 | 核验时间 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    lines.extend(_component_row(item) for item in build_components_in_order(build))

    total = format_fen(as_int(build.get("totalPriceFen")))
    budget_status = as_text(build.get("budgetStatus"))
    lines.append("")
    lines.append(
        f"**总价：{total}　预算状态：{BUDGET_LABELS.get(budget_status, '未知')}**"
    )
    lines.append("")
    lines.extend(_compatibility_section(as_mapping(build.get("compatibilityReport"))))
    if reason_summary:
        lines.append("")
        lines.append(f"**推荐说明：**{reason_summary}")
    if has_demo_price(build):
        lines.append("")
        lines.append(DEMO_PRICE_NOTICE)
    lines.append("")
    lines.append(
        "价格与库存为查询时快照，下单前请以商品页实时信息为准。"
    )
    return "\n".join(lines)


def _compatibility_section(report: dict[str, Any]) -> list[str]:
    overall = overall_compatibility(report)
    lines = [
        f"**兼容性：{_compatibility_label(overall)}**",
    ]
    if overall == "UNKNOWN":
        lines.append("")
        lines.append("存在未验证项（例如机箱最大散热高度缺少数据），不能视为已确认兼容。")
    checks = [as_mapping(item) for item in as_list(report.get("checks"))]
    if checks:
        lines.append("")
        lines.append("| 规则 | 结论 | 说明 |")
        lines.append("| --- | --- | --- |")
        for check in checks:
            rule = _escape_cell(
                as_text(check.get("ruleName"), as_text(check.get("ruleId"), "规则"))
            )
            status = _compatibility_label(as_text(check.get("status")))
            message = _escape_cell(as_text(check.get("message"), "—"))
            lines.append(f"| {rule} | {status} | {message} |")
    return lines


def build_frontend_payload(
    build: dict[str, Any],
    reason_summary: str,
    *,
    fallback_scenario: str | None = None,
) -> dict[str, Any]:
    """投影出 `done.build_result` 的前端消费子集。

    `fallback_scenario` 是本地解析出的用途：Java 未返回 `workloadProfile` 时用它回退，
    避免用固定默认值冒充 Java 的判定结果。
    """
    components = []
    for item in build_components_in_order(build):
        category = as_text(item.get("category"))
        benchmark_type = as_text(item.get("benchmarkType"))
        score = item.get("benchmarkScore")
        benchmark = (
            {"type": benchmark_type, "score": score}
            if benchmark_type and isinstance(score, (int, float)) and not isinstance(score, bool)
            else None
        )
        components.append(
            {
                "category": category,
                # 前端按 hardware_id 把逐件理由对到具体硬件行，缺失时理由不会被展示
                "hardware_id": as_text(item.get("hardwareId")) or None,
                "model_name": as_text(item.get("modelName")),
                "brand": as_text(item.get("brand")) or None,
                "title": as_text(item.get("title")) or None,
                "platform": as_text(item.get("platform")) or None,
                "seller": as_text(item.get("seller")) or None,
                "price_source": as_text(item.get("priceSource")) or None,
                "spec_summary": as_text(item.get("specSummary")),
                "image_url": safe_url(item.get("imageUrl")),
                "price_fen": as_int(item.get("priceFen")),
                "purchase_url": safe_url(item.get("purchaseUrl")),
                "benchmark": benchmark,
                "offer_verified_at": as_text(item.get("verifiedAt")) or None,
            }
        )

    report = as_mapping(build.get("compatibilityReport"))
    requirements = as_mapping(build.get("requirements"))
    compatibility: list[dict[str, Any]] = []
    for check in (as_mapping(item) for item in as_list(report.get("checks"))):
        entry = {
            "rule": as_text(check.get("ruleName"), as_text(check.get("ruleId"), "规则")),
            "status": as_text(check.get("status")),
            "message": as_text(check.get("message")),
        }
        # 风险等级缺失时直接省略，不能让前端把缺失误读成「无风险」
        risk_level = as_text(check.get("riskLevel"))
        if risk_level:
            entry["risk_level"] = risk_level
        compatibility.append(entry)

    # 优先用 Java 的用途判定；缺失时回退本地场景，两者都没有才留空
    workload_profile = (
        as_text(requirements.get("workloadProfile"))
        or as_text(fallback_scenario)
        or as_text(requirements.get("scenario"))
    )

    payload: dict[str, Any] = {
        "build_id": as_text(build.get("buildId")) or None,
        "components": components,
        "total_price_fen": as_int(build.get("totalPriceFen")),
        "budget_max_fen": build.get("budgetMaxFen")
        if isinstance(build.get("budgetMaxFen"), int)
        else None,
        "budget_status": as_text(build.get("budgetStatus")),
        "compatibility": compatibility,
        "overall_status": as_text(report.get("overallStatus")) or None,
        # 演示价条数由逐项 priceSource 派生，前端据此常驻展示「演示价格」横幅
        "demo_offer_count": sum(
            1 for item in components if item.get("price_source") == "MOCK_DEMO"
        ),
        "reason_summary": reason_summary,
    }
    if workload_profile:
        payload["workload_profile"] = workload_profile
    scoring_version = as_text(build.get("scoringVersion")) or as_text(
        requirements.get("scoringVersion")
    )
    if scoring_version:
        payload["scoring_version"] = scoring_version
    # 逐件选择理由由 Java 生成，这里原样透传；缺失或格式异常时省略整个字段
    component_reasons = build.get("componentReasons")
    if isinstance(component_reasons, (dict, list)) and component_reasons:
        payload["component_reasons"] = component_reasons
    return payload


def render_failure_markdown(state: Mapping[str, Any]) -> str:
    """失败路径的确定性文案；每种状态都必须有明确说明，不能返回空串。"""
    status = as_text(state.get("workflow_status"))

    if status in {STATUS_CLARIFICATION, STATUS_INVALID}:
        validation = as_mapping(state.get("validation_result"))
        message = as_text(validation.get("message"))
        if message:
            return message
        return "请补充预算和主要用途，我再为你推荐具体配置。"

    if status == STATUS_NO_CANDIDATES:
        pool = as_mapping(state.get("candidate_pool"))
        missing = [as_text(item) for item in as_list(pool.get("missing_categories"))]
        if missing:
            labels = "、".join(CATEGORY_LABELS.get(item, item) for item in missing)
            return f"{EMPTY_CANDIDATES_MESSAGE}缺少类别：{labels}。"
        return EMPTY_CANDIDATES_MESSAGE

    if status == STATUS_NO_SOLUTION:
        failure = as_mapping(state.get("build_failure"))
        return _render_solve_failure(failure)

    if status == STATUS_COMPATIBILITY_FAILED:
        report = as_mapping(state.get("compatibility_report"))
        lines = ["## 暂时没有找到兼容的配置", ""]
        lines.append("自动重试后仍存在硬性兼容冲突，未生成推荐方案。")
        lines.extend(_compatibility_section(report))
        return "\n".join(lines)

    if status == STATUS_UPSTREAM_ERROR:
        return UPSTREAM_ERROR_MESSAGE

    if status == STATUS_ABORTED:
        return "已按你的选择终止本轮方案。你可以调整预算或用途后重新提问。"

    return UPSTREAM_ERROR_MESSAGE


def _render_solve_failure(failure: dict[str, Any]) -> str:
    reason = as_text(failure.get("reason"))
    minimum = failure.get("minimumRequiredBudgetFen")
    message = as_text(failure.get("message"))
    lines = ["## 当前条件下没有可行配置", ""]
    if reason == "BUDGET_EXCEEDED" and isinstance(minimum, int):
        lines.append(
            f"预算不足以覆盖最低可行总价 {format_fen(minimum)}。"
            "我没有放宽你的预算；可以提高预算或放宽容量/场景要求后重试。"
        )
    elif reason == "NO_CANDIDATES":
        missing = [as_text(item) for item in as_list(failure.get("missingCategories"))]
        labels = "、".join(CATEGORY_LABELS.get(item, item) for item in missing) or "部分类别"
        lines.append(f"缺少可用候选硬件：{labels}。")
    elif reason == "NO_COMPATIBLE_BUILD":
        lines.append("现有候选无法组成兼容配置，我没有放宽预算或忽略兼容性。")
    else:
        lines.append("没有满足全部约束的配置，我没有自行放宽预算。")
    if message and message not in lines[-1]:
        lines.append("")
        lines.append(f"说明：{message}")
    return "\n".join(lines)


def build_failure_categories(failure: dict[str, Any]) -> list[str]:
    return [as_text(item) for item in as_list(failure.get("missingCategories"))]
