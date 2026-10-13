"""Behavioral checks for timing leakage, scale errors and invalid financial ratios."""

from decimal import Decimal
import unittest

from verify_research import dividend_cover, market_cap, time_check, valuation_cap


class ResearchChecks(unittest.TestCase):
    def test_historical_retrieval_after_cutoff_is_allowed(self):
        result = time_check("2025-04-30T15:00:00+08:00", "2025-04-29T18:00:00+08:00",
                            "2025-04-29T18:00:00+08:00", "2026-09-26T16:00:00+08:00")
        self.assertEqual(result["status"], "CHECK_PASS")

    def test_after_close_filing_cannot_inform_prior_close(self):
        result = time_check("2026-09-25T15:00:00+08:00", "2026-09-25T18:00:00+08:00",
                            "2026-09-25T18:00:00+08:00", "2026-09-26T16:00:00+08:00")
        self.assertIn("NOT_PUBLICLY_AVAILABLE_AT_CUTOFF", result["issues"])

    def test_equivalent_timezones(self):
        result = time_check("2026-09-25T10:00:00Z", "2026-09-25T18:00:00+08:00",
                            "2026-09-25T10:00:00Z", "2026-09-25T18:01:00+08:00")
        self.assertEqual(result["status"], "CHECK_PASS")

    def test_timezone_missing(self):
        with self.assertRaises(ValueError):
            time_check("2026-09-25", "2026-09-24T10:00:00Z",
                       "2026-09-24T10:00:00Z", "2026-09-26T10:00:00Z")

    def test_inconsistent_publication_order(self):
        result = time_check("2026-09-26T10:00:00Z", "2026-09-25T10:00:00Z",
                            "2026-09-24T10:00:00Z", "2026-09-23T10:00:00Z")
        self.assertIn("AVAILABLE_BEFORE_PUBLICATION", result["issues"])
        self.assertIn("RETRIEVED_BEFORE_AVAILABILITY", result["issues"])

    def test_currency_scale_typo(self):
        result = market_cap("10", "100000000", "100000", ".005")
        self.assertEqual(result["status"], "REVIEW_REQUIRED")

    def test_exact_decimal_and_zero_tolerance(self):
        result = market_cap("0.1", "3", "0.3", "0")
        self.assertEqual(result["status"], "CHECK_PASS")

    def test_valuation_revision_invalidates_old_cap(self):
        self.assertEqual(Decimal(valuation_cap("10", ".2")["buy_cap"]), Decimal("8"))
        self.assertEqual(Decimal(valuation_cap("7", ".2")["buy_cap"]), Decimal("5.6"))

    def test_negative_cash_flow_not_safe_dividend_ratio(self):
        self.assertEqual(dividend_cover("-100", "60")["status"], "NOT_MEANINGFUL")
        self.assertIsNone(dividend_cover("-100", "60")["payout_ratio"])

    def test_no_dividend_has_no_infinite_safety_claim(self):
        self.assertEqual(dividend_cover("100", "0")["status"], "NOT_MEANINGFUL")

    def test_undercovered_dividend_reports_deficit(self):
        result = dividend_cover("60", "100")
        self.assertEqual(Decimal(result["cash_surplus_after_dividend"]), Decimal("-40"))
        self.assertLess(Decimal(result["coverage"]), 1)

    def test_invalid_numbers_and_margin(self):
        for value in ("NaN", "Infinity", "bad"):
            with self.assertRaises(ValueError):
                valuation_cap(value, ".2")
        with self.assertRaises(ValueError):
            valuation_cap("10", "1.2")


if __name__ == "__main__":
    unittest.main()
