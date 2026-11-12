"""Stage 3A/3B 规则测试：生命周期映射与搜索区间抽取。"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import jd_union_client as jd  # noqa: E402
import stage3a_lifecycle as stage3a  # noqa: E402
import stage3b_price_sample as stage3b  # noqa: E402
import stage3c_bucket_prices as buckets  # noqa: E402
import stage3c_refresh as stage3c  # noqa: E402
import stage3c_tiers as tiers  # noqa: E402
import stage3d_finalize as finalize  # noqa: E402
import stage3e_compat as compat  # noqa: E402
import stage4_hot_shortlist as hot  # noqa: E402
import zh_alias  # noqa: E402


def _product(category: str, specs: dict) -> dict:
    return {"product_id": f"p-{category}", "category": category, "specifications": specs}


class LifecycleTest(unittest.TestCase):
    def test_cpu_microarchitecture_mapping(self) -> None:
        self.assertEqual(stage3a.classify(_product("CPU", {"microarchitecture": "Zen 5"}))[0], "CURRENT")
        self.assertEqual(stage3a.classify(_product("CPU", {"microarchitecture": "Zen 3"}))[0], "MATURE")
        self.assertEqual(stage3a.classify(_product("CPU", {"microarchitecture": "Excavator"}))[0], "LEGACY")
        self.assertEqual(stage3a.classify(_product("CPU", {"microarchitecture": "Zen 4"}))[0], "CURRENT")

    def test_cpu_socket_only_is_unknown(self) -> None:
        self.assertEqual(stage3a.classify(_product("CPU", {"socket": "AM5"}))[0], "UNKNOWN")

    def test_cpu_core_family_fallback(self) -> None:
        self.assertEqual(stage3a.classify(_product("CPU", {"core_family": "Raphael"}))[0], "CURRENT")
        self.assertEqual(stage3a.classify(_product("CPU", {"core_family": "Matisse"}))[0], "LEGACY")

    def test_gpu_chipset_mapping(self) -> None:
        self.assertEqual(stage3a.classify(_product("GPU", {"chipset": "GeForce RTX 5060"}))[0], "CURRENT")
        self.assertEqual(stage3a.classify(_product("GPU", {"chipset": "GeForce RTX 4060"}))[0], "MATURE")
        self.assertEqual(stage3a.classify(_product("GPU", {"chipset": "GeForce RTX 3060"}))[0], "LEGACY")
        self.assertEqual(stage3a.classify(_product("GPU", {"chipset": "Arc Pro B60"}))[0], "CURRENT")
        self.assertEqual(stage3a.classify(_product("GPU", {"chipset": "Radeon RX 9070 XT"}))[0], "CURRENT")
        self.assertEqual(stage3a.classify(_product("GPU", {"chipset": "FirePro 2270"}))[0], "LEGACY")

    def test_motherboard_chipset_mapping(self) -> None:
        self.assertEqual(stage3a.classify(_product("MOTHERBOARD", {"chipset": "B850"}))[0], "CURRENT")
        self.assertEqual(stage3a.classify(_product("MOTHERBOARD", {"chipset": "B650"}))[0], "MATURE")
        self.assertEqual(stage3a.classify(_product("MOTHERBOARD", {"chipset": "B450"}))[0], "LEGACY")
        self.assertEqual(stage3a.classify(_product("MOTHERBOARD", {"chipset": "A620"}))[0], "MATURE")

    def test_commodity_category_not_applicable(self) -> None:
        self.assertEqual(stage3a.classify(_product("CASE", {}))[0], "NOT_APPLICABLE")
        self.assertEqual(stage3a.classify(_product("PSU", {}))[0], "NOT_APPLICABLE")


class PriceExtractionTest(unittest.TestCase):
    def test_ok_range_requires_two_domains(self) -> None:
        results = [
            {"title": "RTX 5060 Ti 16GB ¥4999", "summary": "到手价 4899 元", "url": "https://a.com/1", "date": "2026-11-01"},
            {"title": "RTX 5060 Ti 16GB 价格", "summary": "售价 ¥5199", "url": "https://b.com/2", "date": "2026-11-02"},
        ]
        analysis = stage3b.analyze(results, "RTX 5060 Ti 16GB")
        self.assertEqual(analysis["status"], "OK")
        self.assertLessEqual(analysis["price_low_cny"], analysis["price_high_cny"])

    def test_no_price(self) -> None:
        results = [{"title": "RTX 5060 Ti 评测", "summary": "无价格", "url": "https://a.com", "date": None}]
        self.assertEqual(stage3b.analyze(results, "RTX 5060 Ti")["status"], "NO_PRICE")

    def test_model_mismatch(self) -> None:
        results = [
            {"title": "华擎 B850M Pro PLUS WiFi 1099元", "summary": "", "url": "https://a.com/1", "date": None},
            {"title": "华擎 B850M Riptide WiFi 1199元", "summary": "", "url": "https://b.com/2", "date": None},
        ]
        self.assertEqual(stage3b.analyze(results, "B850M Pro-A WiFi")["status"], "MODEL_MISMATCH")

    def test_wide_spread_is_low_confidence(self) -> None:
        results = [
            {"title": "金士顿 NV3 1TB ¥449", "summary": "", "url": "https://a.com/1", "date": None},
            {"title": "金士顿 NV3 1TB ¥1299", "summary": "", "url": "https://b.com/2", "date": None},
        ]
        self.assertEqual(stage3b.analyze(results, "NV3")["status"], "LOW_CONFIDENCE")

    def test_no_result(self) -> None:
        self.assertEqual(stage3b.analyze([], "RTX 5060 Ti")["status"], "NO_RESULT")

    def test_single_domain_low_confidence(self) -> None:
        results = [
            {"title": "RTX 5060 Ti ¥4999", "summary": "¥5099", "url": "https://a.com/1", "date": "2026-11-01"},
            {"title": "RTX 5060 Ti ¥5199", "summary": "", "url": "https://a.com/2", "date": None},
        ]
        self.assertEqual(stage3b.analyze(results, "RTX 5060 Ti")["status"], "LOW_CONFIDENCE")


    def test_spec_token_missing_is_low_confidence(self) -> None:
        results = [
            {"title": "RTX 5060 Ti 8GB ¥2999", "summary": "", "url": "https://a.com/1", "date": "2026-11-01"},
            {"title": "RTX 5060 Ti 8GB ¥3099", "summary": "", "url": "https://b.com/2", "date": "2026-11-01"},
        ]
        self.assertEqual(stage3b.analyze(results, "RTX 5060 Ti", ["16GB"])["status"], "SPEC_MISMATCH")

    def test_stale_result_is_rejected(self) -> None:
        results = [
            {"title": "RTX 5060 Ti 16GB ¥4999", "summary": "", "url": "https://a.com/1", "date": "2023-01-01"},
        ]
        self.assertEqual(stage3b.analyze(results, "RTX 5060 Ti", ["16GB"])["status"], "STALE_ONLY")


class ChineseAliasTest(unittest.TestCase):
    def test_brand_translation(self) -> None:
        self.assertEqual(zh_alias.brand_zh("ASRock"), "华擎")
        self.assertEqual(zh_alias.brand_zh("G.SKILL"), "芝奇")
        self.assertEqual(zh_alias.brand_zh("Acer"), "宏碁")
        self.assertEqual(zh_alias.brand_zh("UnknownBrand"), "UnknownBrand")

    def test_series_translation_by_category(self) -> None:
        self.assertEqual(zh_alias.model_zh("CPU", "Ryzen 5 9600X"), "锐龙 5 9600X")
        self.assertEqual(
            zh_alias.model_zh("MEMORY", "Predator Pallas II 32 GB"),
            "掠夺者 凌霜 II 32 GB",
        )
        self.assertEqual(
            zh_alias.model_zh("COOLER", "Peerless Assassin 120 Black"),
            "绝双刺客 120 Black",
        )
        self.assertEqual(
            zh_alias.model_zh("GPU", "VENTUS 3X OC (GeForce RTX 5060)"),
            "万图师 3X OC (GeForce RTX 5060)",
        )

    def test_rule_stays_in_category(self) -> None:
        self.assertEqual(zh_alias.model_zh("CASE", "Shadow"), "Shadow")

    def test_brand_duplicate_removed(self) -> None:
        product = {"brand": "Corsair", "category": "CASE", "model_name": "Corsair 2500D Airflow"}
        self.assertEqual(zh_alias.search_name_zh(product), "海盗船 2500D Airflow")

    def test_search_name_and_query(self) -> None:
        product = {
            "brand": "Acer",
            "category": "MEMORY",
            "model_name": "Predator Pallas II 32 GB",
            "specifications": {"capacity_gb": 32, "speed_mhz": 6000},
        }
        self.assertEqual(zh_alias.search_name_zh(product), "宏碁 掠夺者 凌霜 II 32 GB")
        query = stage3b.build_query(product)
        self.assertIn("宏碁", query)
        self.assertIn("掠夺者", query)
        self.assertIn("32GB", query)


    def test_hyphenated_model_token(self) -> None:
        text = "华擎 B850M Pro PLUS WiFi 主板 1099元"
        self.assertLess(stage3b.token_hit("B850M Pro-A WiFi", text), 0.8)
        self.assertGreaterEqual(stage3b.token_hit("B850M Pro-A WiFi", "华擎 B850M Pro-A WiFi 主板"), 0.5)

    def test_chinese_model_tokens(self) -> None:
        text = "宏碁掠夺者 凌霜 32G DDR5 6000 内存条 京东自营"
        self.assertGreaterEqual(stage3b.token_hit("宏碁 掠夺者 凌霜 II 32 GB", text), 0.5)


class TierTest(unittest.TestCase):
    def test_quantile(self) -> None:
        self.assertEqual(tiers.quantile([1, 2, 3, 4], 0.25), 1.75)
        self.assertEqual(tiers.quantile([10], 0.75), 10)

    def test_price_requires_ok(self) -> None:
        self.assertIsNone(tiers.price_of(None))
        self.assertIsNone(tiers.price_of({"status": "LOW_CONFIDENCE", "price_median_cny": 100}))
        self.assertEqual(tiers.price_of({"status": "OK", "price_median_cny": 100}), 100)


class BucketTest(unittest.TestCase):
    def test_gpu_bucket_uses_chipset_and_vram(self) -> None:
        product = {
            "product_id": "g1", "category": "GPU", "brand": "MSI",
            "model_name": "VENTUS 3X OC (GeForce RTX 5060 Ti)",
            "specifications": {"chipset": "GeForce RTX 5060 Ti", "vram_gb": 16},
        }
        key, query = buckets.bucket_of(product)
        self.assertEqual(key, "GPU|GeForce RTX 5060 Ti|16")
        self.assertIn("16GB", query)

    def test_cpu_bucket_is_per_model(self) -> None:
        product = {
            "product_id": "c1", "category": "CPU", "brand": "AMD",
            "model_name": "Ryzen 5 9600X", "specifications": {},
        }
        key, query = buckets.bucket_of(product)
        self.assertEqual(key, "CPU|Ryzen 5 9600X")
        self.assertIn("9600X", query)

    def test_summarize_median_and_trim(self) -> None:
        results = [
            {"title": f"价格 {price} 元", "summary": ""}
            for price in (100, 200, 300, 1000, 5000)
        ]
        summary = buckets.summarize(results)
        self.assertIsNotNone(summary["median_cny"])
        self.assertLess(summary["median_cny"], 1000)


class FinalizeTest(unittest.TestCase):
    def test_completeness(self) -> None:
        self.assertEqual(finalize.completeness({}), 0.0)
        self.assertEqual(finalize.completeness({"a": 1, "b": None}), 0.5)
        self.assertEqual(finalize.completeness({"a": 1, "b": "x"}), 1.0)

    def test_eligibility_filters_obsolete(self) -> None:
        self.assertFalse(finalize.is_eligible({"category": "MEMORY"}, {"memory_type": "DDR3", "capacity_gb": 16}))
        self.assertTrue(finalize.is_eligible({"category": "MEMORY"}, {"memory_type": "DDR5", "capacity_gb": 32}))
        self.assertFalse(finalize.is_eligible({"category": "CASE"}, {"case_type": "Rackmount 3U"}))
        self.assertTrue(finalize.is_eligible({"category": "CASE"}, {"case_type": "ATX Mid Tower"}))
        self.assertTrue(finalize.is_eligible({"category": "MOTHERBOARD"}, {"socket": "AM5", "chipset": "B850"}))
        self.assertFalse(finalize.is_eligible({"category": "MOTHERBOARD"}, {"socket": "AM3", "chipset": "A320"}))

    def test_parse_number_from_units(self) -> None:
        self.assertEqual(compat.parse_number("288 mm"), 288)
        self.assertEqual(compat.parse_number("2"), 2)
        self.assertEqual(compat.parse_number(""), None)
        self.assertEqual(compat.parse_number("No"), None)

    def test_label_capacity_and_speed(self) -> None:
        self.assertEqual(hot.label_capacity("DDR5 6000 32GB"), 32)
        self.assertEqual(hot.label_capacity("TiPlus7100 1TB"), 1024)
        self.assertEqual(hot.label_speed("DDR5 6000 32GB"), 6000)

    def test_gpu_match_requires_vram(self) -> None:
        entry = {"category": "GPU", "label": "RTX 5060 Ti 16GB", "tokens": ["RTX5060TI"], "vram_gb": 16}
        self.assertFalse(hot.matches(entry, {"display_name": "MSI VENTUS (RTX 5060 Ti)", "specifications": {"vram_gb": 8}}))
        self.assertTrue(hot.matches(entry, {"display_name": "MSI VENTUS (RTX 5060 Ti)", "specifications": {"vram_gb": 16}}))

    def test_select_group_covers_each_stratum(self) -> None:
        items = [
            {"product_id": "a1", "stratum": "s1", "price_cny": 100, "brand": "X", "completeness": 1.0},
            {"product_id": "a2", "stratum": "s1", "price_cny": 200, "brand": "Y", "completeness": 1.0},
            {"product_id": "b1", "stratum": "s2", "price_cny": 900, "brand": "Z", "completeness": 0.5},
        ]
        picked = finalize.select_group(items, limit=2)
        self.assertEqual(len(picked), 2)
        self.assertEqual({item["stratum"] for item in picked}, {"s1", "s2"})


class JdUnionTest(unittest.TestCase):
    def test_sign_is_order_independent(self) -> None:
        first = {"a": "1", "b": "2"}
        second = {"b": "2", "a": "1"}
        self.assertEqual(jd.sign(first, "secret"), jd.sign(second, "secret"))
        self.assertEqual(len(jd.sign(first, "secret")), 32)
        self.assertEqual(jd.sign(first, "secret"), jd.sign(first, "secret").upper())

    def test_build_request_payload(self) -> None:
        config = jd.JdUnionConfig("key", "secret", "site")
        params = jd.build_request(config, "RTX 5060 Ti", 10)
        self.assertEqual(params["method"], jd.METHOD)
        self.assertIn("sign", params)
        self.assertIn("RTX 5060 Ti", params["360buy_param_json"])

    def test_parse_nested_response(self) -> None:
        payload = {
            "jd_union_open_goods_query_responce": {
                "queryResult": json.dumps({
                    "data": [{
                        "skuId": 100,
                        "skuName": "微星 RTX 5060 Ti 16G",
                        "priceInfo": {"lowestPrice": 4399, "lowestCouponPrice": 4299},
                        "inOrderCount30Days": 120,
                        "shopInfo": {"shopName": "微星京东自营旗舰店"},
                        "materialUrl": "https://item.jd.com/100.html",
                    }]
                }, ensure_ascii=False)
            }
        }
        items = jd.parse_response(payload)
        self.assertEqual(items[0]["price_cny"], 4399)
        self.assertEqual(items[0]["sales_30d"], 120)

    def test_missing_credentials(self) -> None:
        with mock.patch.dict(os.environ, {"JD_UNION_APP_KEY": "", "JD_UNION_APP_SECRET": "", "JD_UNION_SITE_ID": ""}):
            with self.assertRaises(jd.JdUnionNotConfigured):
                jd.JdUnionConfig.from_env()


class RefreshTest(unittest.TestCase):
    def test_channel_mapping(self) -> None:
        self.assertEqual(stage3c.channel_of("https://item.jd.com/1.html"), "JD")
        self.assertEqual(stage3c.channel_of("https://detail.tmall.com/2"), "TAOBAO")
        self.assertEqual(stage3c.channel_of("https://detail.zol.com.cn/3"), "ZOL")
        self.assertEqual(stage3c.channel_of("https://example.com/4"), "OTHER")

    def test_availability(self) -> None:
        self.assertEqual(stage3c.availability_of([{"summary": "京东自营 现货"}]), "IN_STOCK")
        self.assertEqual(stage3c.availability_of([{"summary": "该商品已售罄"}]), "OUT_OF_STOCK")
        self.assertEqual(stage3c.availability_of([{"summary": "参考报价"}]), "UNKNOWN")


class SamplingTest(unittest.TestCase):
    def test_stratified_sample_size(self) -> None:
        products = [
            {"product_id": f"p-{category}-{index:03d}", "category": category,
             "quality_status": "GOOD", "brand": "B", "model_name": "M"}
            for category in ("CPU", "GPU", "CASE")
            for index in range(120)
        ]
        sample = stage3b.select_sample(products, 50)
        self.assertEqual(len(sample), 150)
        self.assertEqual(len({item["product_id"] for item in sample}), 150)


if __name__ == "__main__":
    unittest.main()
