from __future__ import annotations

import re
from typing import Any

from app.agent.pc.openui_renderer import openui_intro, render_build_openui
from app.agent.pc.renderer import (
    MOCK_PRICE_SOURCE,
    OBSERVED_PRICE_SOURCE,
    markdown_intro,
    render_build_markdown,
)

_DEFINITION = re.compile(r"^([A-Za-z_]\w*) = ", re.MULTILINE)


def _component(category: str, **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "category": category,
        "modelName": f"{category.title()} 型号",
        "priceFen": 100000,
        "purchaseUrl": None,
        "imageUrl": None,
    }
    item.update(overrides)
    return item


def _build(**overrides: Any) -> dict[str, Any]:
    build: dict[str, Any] = {
        "totalPriceFen": 800000,
        "budgetMaxFen": 800000,
        "budgetStatus": "WITHIN_BUDGET",
        "components": [
            _component("CPU"),
            _component("MOTHERBOARD"),
            _component("MEMORY"),
            _component("GPU"),
            _component("PSU"),
            _component("CASE"),
            _component("COOLER"),
            _component("STORAGE"),
        ],
        "compatibilityReport": {"overallStatus": "PASS"},
    }
    build.update(overrides)
    return build


def test_renders_single_table_and_detail_button() -> None:
    content = render_build_openui(_build(), "这套配置均衡覆盖游戏与日常创作。")

    # 推荐总览与推荐理由必须先于清单出现，用户先理解「为什么推荐」再核对型号价格
    assert content.startswith("### 为什么推荐这套配置")
    first_fence = content.index("```openui")
    assert "这套配置均衡覆盖游戏与日常创作。" in content[:first_fence]
    assert content.count("```openui") == 2
    assert content.count("```") == 4
    assert 'Text("推荐配置清单", "heading")' in content
    # 八件硬件必须合并进一张表，而不是每件一个 Card
    assert content.count("Table([typeCol, modelCol, priceCol])") == 1
    expected_labels = '["CPU", "主板", "内存", "显卡", "电源", "机箱", "散热器", "硬盘"]'
    assert f'Col("硬件类型", {expected_labels})' in content
    assert "Card(" not in content
    assert "StatGroup([totalItem])" in content
    assert '@OpenBuildDetail()' in content
    assert "以上为本次推荐配置" in content


def test_stream_intro_is_exact_prefix_of_rendered_body() -> None:
    """流式先下发的总览必须与最终正文前缀逐字一致，否则客户端会重复或丢内容。"""
    build = _build()
    assert render_build_openui(build, "推荐理由。").startswith(openui_intro(build))

    demo = _build()
    for component in demo["components"]:
        component["priceSource"] = MOCK_PRICE_SOURCE
    # 演示价提示位于总览之前，前缀必须把它包含进来
    assert "演示" in markdown_intro(demo)
    assert render_build_markdown(demo, "推荐理由。").startswith(markdown_intro(demo))


def test_purchase_link_is_hidden_but_image_column_is_rendered() -> None:
    build = _build()
    build["components"][0]["purchaseUrl"] = "https://item.jd.com/100012043978.html"
    build["components"][0]["imageUrl"] = "https://cdn.example.com/cpu.jpg"

    content = render_build_openui(build, "推荐理由。")

    # 购买链接不进入 OpenUI，避免把用户引到未经核验或存在佣金的页面
    assert "@OpenUrl" not in content
    assert "去购买" not in content
    assert "https://item.jd.com/100012043978.html" not in content
    # 图片列使用 Table 的 image 类型单元格，而不是单独的 Image 组件
    assert 'Col("图片", [' in content
    assert '"image"' in content
    assert "https://cdn.example.com/cpu.jpg" in content
    assert "Image(" not in content


def test_string_literals_escape_quotes_and_newlines() -> None:
    build = _build()
    build["components"][0]["modelName"] = 'i5 "特别版"\n14400'

    content = render_build_openui(build, "推荐理由。")

    assert '\\"特别版\\"' in content
    # 换行被压成空格，否则会截断 openui-lang 的逐行语法
    assert r'i5 \"特别版\" 14400' in content


def test_unknown_compatibility_and_demo_price_are_disclosed() -> None:
    build = _build(
        compatibilityReport={"overallStatus": "UNKNOWN"},
        components=[_component("CPU", priceSource=MOCK_PRICE_SOURCE), _component("GPU")],
    )

    content = render_build_openui(build, "推荐理由。")

    assert "部分兼容性项尚未验证" in content
    assert "演示价格" in content


def test_observed_price_is_disclosed_without_demo_wording() -> None:
    build = _build(
        offerDataStatus="PLATFORM_OBSERVED_ONLY",
        components=[
            _component("CPU", priceSource=OBSERVED_PRICE_SOURCE),
            _component("GPU"),
        ],
    )

    content = render_build_openui(build, "推荐理由。")

    assert "平台检索参考价" in content
    # 观测价是真实在售商品，不能被写成演示占位价
    assert "演示价格" not in content


def test_every_defined_node_is_referenced() -> None:
    content = render_build_openui(_build(), "推荐理由。")

    for name in _DEFINITION.findall(content):
        if name == "root":
            continue
        assert content.count(name) >= 2, f"未被引用的节点：{name}"
