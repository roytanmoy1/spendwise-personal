import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from app.domain.insights import categorize_merchant, spending_summary


class InsightsTests(unittest.TestCase):
    def test_summary_groups_current_and_previous_month_in_minor_units(self):
        transactions = [
            SimpleNamespace(
                amount_minor=1250,
                category="Food",
                method="card",
                occurred_at=datetime(2026, 10, 2, tzinfo=UTC),
            ),
            SimpleNamespace(
                amount_minor=800,
                category="Groceries",
                method="upi",
                occurred_at=datetime(2026, 10, 3, tzinfo=UTC),
            ),
            SimpleNamespace(
                amount_minor=1500,
                category="Food",
                method="upi",
                occurred_at=datetime(2026, 9, 20, tzinfo=UTC),
            ),
        ]

        summary = spending_summary(transactions, now=datetime(2026, 10, 4, tzinfo=UTC))

        self.assertEqual(summary["total_spent_minor"], 3550)
        self.assertEqual(summary["this_month_minor"], 2050)
        self.assertEqual(summary["last_month_minor"], 1500)
        self.assertEqual(
            summary["by_category"],
            [
                {"category": "Food", "amount_minor": 1250},
                {"category": "Groceries", "amount_minor": 800},
            ],
        )
        self.assertEqual(
            summary["monthly"],
            [
                {"month": "2026-09", "amount_minor": 1500},
                {"month": "2026-10", "amount_minor": 2050},
            ],
        )

    def test_empty_summary_and_merchant_fallback(self):
        summary = spending_summary([], now=datetime(2026, 10, 4, tzinfo=UTC))

        self.assertEqual(summary["total_spent_minor"], 0)
        self.assertEqual(summary["monthly"], [])
        self.assertEqual(categorize_merchant(" Apollo Pharmacy "), "Health")
        self.assertEqual(categorize_merchant("Unknown Merchant"), "Other")


if __name__ == "__main__":
    unittest.main()
