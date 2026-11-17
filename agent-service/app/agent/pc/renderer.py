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
    FAILURE_BUDGET_EXCEEDED,
    FAILURE_CANDIDATE_NOT_IN_POOL,
    FAILURE_COMPATIBILITY_CONFLICT,
    FAILURE_MODEL_UNAVAILABLE,
    FAILURE_OFFER_UNAVAILABLE,
    FAILURE_OUTPUT_TRUNCATED,
    FAILURE_TOOL_ERROR,
    FAILURE_USER_TOKEN_MISSING,
    STATUS_ABORTED,
    STATUS_ARCHITECT_FAILED,
    STATUS_CLARIFICATION,
    STATUS_INVALID,
    STATUS_NO_CANDIDATES,
    STATUS_UPSTREAM_ERROR,
    UPSTREAM_ERROR_MESSAGE,
)

MOCK_PRICE_SOURCE = "MOCK_DEMO"
OBSERVED_PRICE_SOURCE = "PLATFORM_OBSERVED"
OBSERVED_ONLY_DATA_STATUS = "PLATFORM_OBSERVED_ONLY"
DEMO_PRICE_NOTICE = (
    "> **价格说明：当前方案包含演示价格，非真实在售，不能作为已核验报价使用。**"
)
# 平台观测价是真实在售商品的检索价，与占位演示价不同，不能合并成同一句提示
OBSERVED_PRICE_NOTICE = (
    "> **价格说明：当前方案价格为电商平台检索到的参考价，未经人工核验；"
    "其中估算条目可能与实际售价有偏差，下单前请以商品页为准。**"
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


def _price_sources(build: dict[str, Any]) -> list[str]:
    return [
        as_text(as_mapping(component).get("priceSource"))
        for component in as_list(build.get("components"))
    ]


def has_demo_price(build: dict[str, Any]) -> bool:
    """只有占位演示价才触发「非真实在售」提示。

    平台观测价同样是未核验价，但商品真实在售，语义不同。Java 的
    `demoOfferCount` 统计的是「非 OWNER_VERIFIED」，会把观测价一起计入，
    因此只在逐件来源缺失（历史快照）时用它兜底。
    """
    sources = _price_sources(build)
    if MOCK_PRICE_SOURCE in sources:
        return True
    return not any(sources) and as_int(build.get("demoOfferCount")) > 0


def has_observed_price(build: dict[str, Any]) -> bool:
    """存在平台观测/估算价时为真；一旦同时含演示价，交给演示价提示处理。"""
    if has_demo_price(build):
        return False
    return (
        as_text(build.get("offerDataStatus")) == OBSERVED_ONLY_DATA_STATUS
        or OBSERVED_PRICE_SOURCE in _price_sources(build)
    )


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


def _price_notice(build: dict[str, Any]) -> str | None:
    if has_demo_price(build):
        return DEMO_PRICE_NOTICE
    if has_observed_price(build):
        return OBSERVED_PRICE_NOTICE
    return None


def _requirements_line(build: dict[str, Any]) -> str:
    requirements = as_mapping(build.get("requirements"))
    scenario = SCENARIO_LABELS.get(as_text(requirements.get("scenario")), "均衡")
    budget = requirements.get("budgetMaxFen")
    if isinstance(budget, int) and not isinstance(budget, bool):
        return f"场景：{scenario}；预算上限：{format_fen(budget)}"
    return f"场景：{scenario}；预算上限：未设置"


def _selected_components(build: dict[str, Any]) -> list[dict[str, Any]]:
    """只保留真正有选型的类别，避免把空位当成「已配置」。"""
    return [
        item for item in build_components_in_order(build) if as_text(item.get("modelName"))
    ]


def _core_budget_line(build: dict[str, Any], total: int) -> str | None:
    """核心计算部件占比：用真实金额计算，不做「性能强弱」这类无法从数据证明的判断。"""
    if total <= 0:
        return None
    core_categories = {"CPU", "GPU"}
    core_total = sum(
        as_int(item.get("priceFen"))
        for item in _selected_components(build)
        if as_text(item.get("category")) in core_categories
    )
    if core_total <= 0:
        return None
    percent = round(core_total * 100 / total)
    return (
        f"预算分配：CPU 与显卡合计 {format_fen(core_total)}，占总价 {percent}%，"
        "其余预算覆盖主板、内存、硬盘、电源、散热与机箱。"
    )


def _selection_line(build: dict[str, Any]) -> str | None:
    """核心部件的确定性选型说明：型号/规格/跑分全部来自 Java 结果。"""
    parts: list[str] = []
    for item in _selected_components(build):
        category = as_text(item.get("category"))
        if category not in {"CPU", "GPU"}:
            continue
        label = CATEGORY_LABELS[category]
        model = as_text(item.get("modelName"))
        spec = as_text(item.get("specSummary"))
        benchmark = _benchmark_text(item)
        detail = f"规格 {spec}" if spec else ""
        if benchmark != "—":
            detail = f"{detail}；{benchmark}" if detail else benchmark
        parts.append(f"{label}选用「{model}」" + (f"（{detail}）" if detail else ""))
    if not parts:
        return None
    return "核心部件：" + "；".join(parts) + "。"


def recommendation_overview(build: dict[str, Any]) -> str:
    """
    生成配置清单前的确定性推荐总览。

    为什么由代码生成：优越性必须能落到可核验的事实（预算占比、选型规格、跑分、
    兼容性结论、价格口径）。这些值只能来自 Java 结构化结果，交给模型复述会产生
    虚构风险，因此这里逐条拼装，模型只补充不含数字的定性说明。
    """
    requirements = as_mapping(build.get("requirements"))
    scenario = SCENARIO_LABELS.get(as_text(requirements.get("scenario")), "均衡")
    total = as_int(build.get("totalPriceFen"))
    budget_max = as_int(build.get("budgetMaxFen"))
    budget_status = as_text(build.get("budgetStatus"))
    components = _selected_components(build)
    report = as_mapping(build.get("compatibilityReport"))

    lines = ["### 为什么推荐这套配置", ""]
    if budget_max > 0:
        delta = budget_max - total
        if delta >= 0:
            conclusion = f"预算内，剩余 {format_fen(delta)}"
        else:
            conclusion = f"超出预算 {format_fen(-delta)}"
        lines.append(
            f"- **场景与预算**：面向「{scenario}」场景，整机总价 {format_fen(total)}，"
            f"预算上限 {format_fen(budget_max)}，结论为{conclusion}。"
        )
    else:
        lines.append(
            f"- **场景与预算**：面向「{scenario}」场景，整机总价 {format_fen(total)}，"
            "未设置预算上限。"
        )

    core_line = _core_budget_line(build, total)
    if core_line:
        lines.append(f"- {core_line}")

    selection_line = _selection_line(build)
    if selection_line:
        lines.append(f"- {selection_line}")

    if components:
        labels = "、".join(
            CATEGORY_LABELS.get(as_text(item.get("category")), "未知") for item in components
        )
        lines.append(
            f"- **整机完整性**：已覆盖 {len(components)} 个类别（{labels}），"
            "无需单独补齐配件。"
        )

    overall = overall_compatibility(report)
    compatibility = f"- **兼容性**：平台校验整体结论为「{_compatibility_label(overall)}」"
    if overall != "PASS":
        compatibility += "，装机前请按提示复核未验证项"
    compatibility += "。"
    lines.append(compatibility)

    if has_demo_price(build):
        lines.append("- **价格口径**：当前包含演示价格，不能作为已核验报价使用。")
    elif has_observed_price(build):
        lines.append("- **价格口径**：当前为平台检索参考价，未经人工核验，下单前请以商品页为准。")

    if budget_status == "OVER_BUDGET":
        lines.append("- **调整建议**：若需要压回预算，可优先下调显卡或存储容量，其余部件保持不变。")

    return "\n".join(lines)


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


def markdown_intro(build: dict[str, Any]) -> str:
    """`render_build_markdown` 中位于模型文案之前的确定性部分。

    单独暴露给流式生成：这部分只依赖 Java 结构化结果，可以在模型生成前先下发。
    """
    notice = _price_notice(build)
    overview = recommendation_overview(build)
    return f"{notice}\n\n{overview}" if notice else overview


def render_build_markdown(build: dict[str, Any], reason_summary: str) -> str:
    """把 Java 的结构化结果渲染成确定性 Markdown。"""
    notice = _price_notice(build)
    # 推荐理由必须先于清单出现：用户需要先理解「为什么是这套」，再核对具体型号与价格
    lines: list[str] = [markdown_intro(build), ""]
    if reason_summary:
        lines.extend([f"**推荐说明：**{reason_summary}", ""])
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
    if notice:
        lines.append("")
        lines.append(notice)
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

    if status == STATUS_ARCHITECT_FAILED:
        return _render_architect_failure(as_mapping(state.get("build_failure")))

    if status == STATUS_UPSTREAM_ERROR:
        return UPSTREAM_ERROR_MESSAGE

    if status == STATUS_ABORTED:
        return "已按你的选择终止本轮方案。你可以调整预算或用途后重新提问。"

    return UPSTREAM_ERROR_MESSAGE


ARCHITECT_FAILURE_MESSAGES: dict[str, str] = {
    FAILURE_BUDGET_EXCEEDED: "所选配置超出预算上限，未生成推荐方案。",
    FAILURE_OFFER_UNAVAILABLE: "所选硬件缺少可用报价，未生成推荐方案。",
    FAILURE_COMPATIBILITY_CONFLICT: "所选硬件存在兼容性冲突，未生成推荐方案。",
    FAILURE_CANDIDATE_NOT_IN_POOL: "选型未通过候选校验，未能生成可用方案。",
    FAILURE_MODEL_UNAVAILABLE: "选型模型未能返回可用方案，本次未生成推荐配置。",
    FAILURE_USER_TOKEN_MISSING: "缺少用户身份，无法生成配置，请重新登录后再试。",
    FAILURE_OUTPUT_TRUNCATED: "配置结果不完整，未能生成推荐方案。",
    FAILURE_TOOL_ERROR: UPSTREAM_ERROR_MESSAGE,
}


def _render_architect_failure(failure: dict[str, Any]) -> str:
    """LLM 选型失败必须有明确文案；绝不把未验证提案渲染成推荐结果。"""
    failure_type = as_text(
        failure.get("failure_type"), as_text(failure.get("reason"), "UNKNOWN")
    )
    message = ARCHITECT_FAILURE_MESSAGES.get(
        failure_type, "本次未能生成通过验证的配置，请稍后重试。"
    )
    lines = ["## 暂时没有生成可用配置", "", message]
    detail = as_text(failure.get("authoritative_error_details"))
    if detail and detail not in message:
        lines.extend(["", f"说明：{detail}"])
    return "\n".join(lines)


def build_failure_categories(failure: dict[str, Any]) -> list[str]:
    return [as_text(item) for item in as_list(failure.get("missingCategories"))]
