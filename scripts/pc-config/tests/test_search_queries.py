"""中文电商检索键：受控词典映射、型号保原文、未登记品牌英文兜底。"""

from __future__ import annotations

import search_queries as queries
from search_queries import (
    brand_display,
    build_search_queries,
    load_brand_map,
    load_series_rules,
    model_core,
    strip_brand,
)


def make_record(
    category: str,
    brand: str,
    model_name: str,
    specifications: dict | None = None,
    raw_name: str | None = None,
) -> dict:
    return {
        "hardware_id": f"{category.lower()}-test",
        "category": category,
        "brand": brand,
        "model_name": model_name,
        "specifications": specifications or {},
        "raw_specs": {"name": raw_name or model_name},
    }


def test_brand_dictionary_matches_common_diy_brands() -> None:
    brand_map = load_brand_map()
    assert brand_display("Asus", brand_map) == "华硕"
    assert brand_display("G.Skill", brand_map) == "芝奇"
    assert brand_display("be quiet!", brand_map) == "德商必酷"
    assert brand_display("Noctua", brand_map) == "猫头鹰"


def test_unregistered_brand_falls_back_to_english() -> None:
    assert brand_display("Sparkle", load_brand_map()) == "Sparkle"


def test_cpu_series_is_localized_but_model_stays_original() -> None:
    record = make_record(
        "CPU",
        "Intel",
        "Intel Core i5-12400F",
        {"socket": "LGA1700", "core_count": 6, "tdp_w": 65},
        raw_name="Intel Core i5-12400F 2.5 GHz 6-Core Processor",
    )
    result = build_search_queries(record)
    assert result["zh"] == "英特尔 酷睿 i5-12400F"
    assert result["model"] == "Core i5-12400F"
    assert result["en"] == "Intel Core i5-12400F"


def test_gpu_full_query_keeps_board_series_and_short_one_uses_chipset() -> None:
    record = make_record(
        "GPU",
        "Asus",
        "GeForce RTX 5060 Ti 16GB",
        {"chipset": "GeForce RTX 5060 Ti", "vram_gb": 16, "tdp_w": 180},
        raw_name="Asus TUF Gaming GeForce RTX 5060 Ti 16 GB Video Card",
    )
    result = build_search_queries(record)
    assert result["zh"] == "华硕 TUF Gaming GeForce RTX 5060 Ti 16 GB"
    assert result["zh_short"] == "华硕 RTX 5060 Ti 16GB"
    assert result["model"] == "RTX 5060 Ti 16GB"


def test_single_word_core_keeps_full_name_to_avoid_over_broad_search() -> None:
    record = make_record("CASE", "Aerocool", "Aerocool Bolt")
    assert model_core(record) == "Aerocool Bolt"
    # 品牌 + 短核心不能重复品牌
    assert build_search_queries(record)["zh_short"] == "爱乐酷 Bolt"


def test_empty_brand_does_not_break_query_building() -> None:
    record = make_record("PSU", "", "RM850x")
    result = build_search_queries(record)
    assert result["en"] == "RM850x"
    assert result["model"] == "RM850x"


def test_strip_brand_is_case_insensitive_and_requires_separator() -> None:
    assert strip_brand("ASUS ROG Strix B650E-F", "Asus") == "ROG Strix B650E-F"
    assert strip_brand("AsusPro B650M", "Asus") == "AsusPro B650M"


def test_series_rules_only_apply_to_declared_categories() -> None:
    rules = load_series_rules()
    assert queries.localize_series("Ryzen 5 9600X", "CPU", rules) == "锐龙 5 9600X"
    assert queries.localize_series("Ryzen 5 9600X", "GPU", rules) == "Ryzen 5 9600X"
