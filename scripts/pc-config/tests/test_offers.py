"""报价模板校验与入库转换的单元测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ingest_offers as offers  # noqa: E402

CATALOG = {
    "catalog_version": "test-1",
    "hardware": [{"hardware_id": "cpu-test"}],
}

VALID_ENTRY = {
    "offer_id": "offer-cpu-test-01",
    "hardware_id": "cpu-test",
    "category": "CPU",
    "platform": "京东",
    "seller": "AMD 自营旗舰店",
    "title": "AMD 锐龙 5 9600X 盒装",
    "platform_sku": "100012345",
    "price_cny": 1299.0,
    "price_type": "NORMAL",
    "purchase_url": "https://item.jd.com/100012345.html",
    "verified_at": "2026-11-08",
    "valid_until": "2026-11-15",
    "match_status": "VERIFIED",
}


class PriceConversionTest(unittest.TestCase):
    def test_converts_yuan_to_fen(self) -> None:
        self.assertEqual(offers.price_to_fen(1299.0), 129900)
        self.assertEqual(offers.price_to_fen("0.01"), 1)

    def test_rejects_more_than_two_decimals(self) -> None:
        with self.assertRaises(offers.OfferValidationError):
            offers.price_to_fen("12.345")

    def test_rejects_non_positive(self) -> None:
        with self.assertRaises(offers.OfferValidationError):
            offers.price_to_fen(0)


class OfferValidationTest(unittest.TestCase):
    def test_valid_entry_is_converted(self) -> None:
        result = offers.validate_offer(VALID_ENTRY, {"cpu-test"})
        self.assertEqual(result["price_fen"], 129900)
        self.assertEqual(result["purchase_url"], VALID_ENTRY["purchase_url"])

    def test_allows_non_product_link(self) -> None:
        entry = {**VALID_ENTRY, "purchase_url": "https://pcpartpicker.com/product/x"}
        result = offers.validate_offer(entry, {"cpu-test"})
        self.assertEqual(result["purchase_url"], "https://pcpartpicker.com/product/x")

    def test_allows_missing_link(self) -> None:
        entry = {**VALID_ENTRY, "purchase_url": None}
        result = offers.validate_offer(entry, {"cpu-test"})
        self.assertIsNone(result["purchase_url"])

    def test_rejects_unsafe_link_scheme(self) -> None:
        entry = {**VALID_ENTRY, "purchase_url": "javascript:alert(1)"}
        with self.assertRaises(offers.OfferValidationError):
            offers.validate_offer(entry, {"cpu-test"})

    def test_rejects_expired_range(self) -> None:
        entry = {**VALID_ENTRY, "valid_until": "2026-11-01"}
        with self.assertRaises(offers.OfferValidationError):
            offers.validate_offer(entry, {"cpu-test"})

    def test_rejects_unknown_hardware(self) -> None:
        with self.assertRaises(offers.OfferValidationError):
            offers.validate_offer({**VALID_ENTRY, "hardware_id": "cpu-missing"}, {"cpu-test"})


class BuildOffersTest(unittest.TestCase):
    def test_skips_pending_and_reports_invalid_verified(self) -> None:
        template = {
            "offers": [
                {**VALID_ENTRY, "match_status": "PENDING"},
                {**VALID_ENTRY, "offer_id": "offer-2", "price_cny": -1},
            ]
        }
        payload, issues = offers.build_offers(template, CATALOG, "2026-11-08T00:00:00+00:00")
        self.assertEqual(payload["offers"], [])
        self.assertEqual(payload["skipped_pending"], 1)
        self.assertEqual(len(issues), 1)

    def test_mock_entry_is_marked_and_not_counted_as_verified(self) -> None:
        mock_entry = {
            **VALID_ENTRY,
            "offer_id": "offer-mock-01",
            "platform": "MOCK_DEMO",
            "purchase_url": None,
            "verified_at": None,
            "valid_until": None,
            "match_status": "MOCK",
        }
        template = {"offers": [VALID_ENTRY, mock_entry]}
        payload, issues = offers.build_offers(template, CATALOG, "2026-11-08T00:00:00+00:00")
        self.assertEqual(issues, [])
        self.assertEqual(payload["data_status"], "MIXED_DEMO")
        self.assertEqual(payload["verified_offer_count"], 1)
        self.assertEqual(payload["mock_offer_count"], 1)
        self.assertEqual(payload["offers"][1]["price_source"], "MOCK_DEMO")
        self.assertIsNone(payload["offers"][1]["purchase_url"])

    def test_verified_only_payload_has_owner_verified_status(self) -> None:
        payload, issues = offers.build_offers(
            {"offers": [VALID_ENTRY]}, CATALOG, "2026-11-08T00:00:00+00:00"
        )
        self.assertEqual(issues, [])
        self.assertEqual(payload["data_status"], "OWNER_VERIFIED")
        self.assertEqual(payload["offers"][0]["price_source"], "OWNER_VERIFIED")


if __name__ == "__main__":
    unittest.main()
