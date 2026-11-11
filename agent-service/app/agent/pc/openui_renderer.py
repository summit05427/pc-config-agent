"""把结构化配置投影成 OpenUI Lang。

为什么由代码生成而不是让模型写 DSL：型号与价格必须与 Java 结果逐字一致，
模型复述会带来虚构值。这里只做确定性投影，模型仍然只负责一段不含数字的推荐说明。
"""

from __future__ import annotations

from typing import Any

from app.agent.pc.renderer import (
    BUDGET_LABELS,
    CATEGORY_LABELS,
    as_int,
    as_text,
    build_components_in_order,
    format_fen,
    has_demo_price,
    overall_compatibility,
)

OPENUI_FENCE = "openui"

# 详情面板按钮：前端库注册同名自定义动作，点击后由宿主 React 打开固定样式面板
DETAIL_ACTION = "@OpenBuildDetail()"


def _lang_string(value: str) -> str:
    """转义为 openui-lang 双引号字符串，换行压成空格避免破坏逐行语法。"""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\r", " ").replace("\n", " ")
    return f'"{escaped}"'


def _column(label: str, values: list[str]) -> str:
    """一列数据 → `Col("表头", ["a", "b"])`；单元格只能是字符串/数字，不能放组件。"""
    joined = ", ".join(_lang_string(value) for value in values)
    return f'Col({_lang_string(label)}, [{joined}])'


def _list_program(build: dict[str, Any]) -> str:
    # 八件硬件合并成一张表：比每件一张卡片更紧凑，也避免清单滚动过长
    components = [
        item
        for item in build_components_in_order(build)
        if as_text(item.get("modelName")) and as_text(item.get("category")) in CATEGORY_LABELS
    ]
    labels = [CATEGORY_LABELS[as_text(item.get("category"))] for item in components]
    models = [as_text(item.get("modelName")) for item in components]
    prices = [format_fen(as_int(item.get("priceFen"))) for item in components]

    total = format_fen(as_int(build.get("totalPriceFen")))
    budget_status = BUDGET_LABELS.get(as_text(build.get("budgetStatus")), "未设置预算")
    budget_max = as_int(build.get("budgetMaxFen"))
    subtext = (
        f"{budget_status} · 预算上限 {format_fen(budget_max)}" if budget_max else budget_status
    )

    return "\n".join(
        [
            'title = Text("推荐配置清单", "heading")',
            f"typeCol = {_column('硬件类型', labels)}",
            f"modelCol = {_column('硬件名称', models)}",
            f"priceCol = {_column('参考价格', prices)}",
            "table = Table([typeCol, modelCol, priceCol])",
            f'totalItem = StatItem({_lang_string(f"总价 {total}")}, {_lang_string(subtext)})',
            "total = StatGroup([totalItem])",
            'root = Stack([title, table, total], "vertical", "md")',
        ]
    )


def _detail_program() -> str:
    return "\n".join(
        [
            'root = Stack([detailButton], "vertical", "sm")',
            f'detailButton = Button("查看配置详情", {DETAIL_ACTION}, "primary")',
        ]
    )


def _closing_sentence(build: dict[str, Any], report: dict[str, Any]) -> str:
    parts = ["以上为本次推荐配置"]
    if overall_compatibility(report) != "PASS":
        parts.append("部分兼容性项尚未验证，装机前请再次确认")
    if has_demo_price(build):
        parts.append("当前方案包含演示价格，不能作为已核验报价使用")
    parts.append("价格与库存为查询时快照，下单前请以商品页实时信息为准")
    return "；".join(parts) + "。"


def _fence(program: str) -> str:
    return f"```{OPENUI_FENCE}\n{program}\n```"


def render_build_openui(build: dict[str, Any], reason_summary: str) -> str:
    """推荐理由（Markdown）→ 清单（OpenUI）→ 结尾（Markdown）→ 详情按钮（OpenUI）。"""
    report = build.get("compatibilityReport")
    blocks: list[str] = []
    if reason_summary:
        blocks.append(reason_summary)
    blocks.append(_fence(_list_program(build)))
    blocks.append(_closing_sentence(build, report if isinstance(report, dict) else {}))
    blocks.append(_fence(_detail_program()))
    return "\n\n".join(blocks) + "\n"
