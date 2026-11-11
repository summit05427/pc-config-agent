from __future__ import annotations

import re
from typing import Any

from app.agent.pc.openui_renderer import render_build_openui
from app.agent.pc.renderer import MOCK_PRICE_SOURCE

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

    assert content.startswith("这套配置均衡覆盖游戏与日常创作。")
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


def test_purchase_link_and_image_are_not_rendered() -> None:
    build = _build()
    build["components"][0]["purchaseUrl"] = "https://item.jd.com/100012043978.html"
    build["components"][0]["imageUrl"] = "https://cdn.example.com/cpu.jpg"

    content = render_build_openui(build, "推荐理由。")

    # 清单只保留类型 / 名称 / 参考价三项，购买按钮与图片不再进入 OpenUI
    assert "@OpenUrl" not in content
    assert "去购买" not in content
    assert "Image(" not in content
    assert "https://item.jd.com/100012043978.html" not in content


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


def test_every_defined_node_is_referenced() -> None:
    content = render_build_openui(_build(), "推荐理由。")

    for name in _DEFINITION.findall(content):
        if name == "root":
            continue
        assert content.count(name) >= 2, f"未被引用的节点：{name}"
