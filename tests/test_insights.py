import unittest

from depipeline.insights import compute_insights
from depipeline.schema import parse_schema_fields


class TestInsights(unittest.TestCase):
    def test_compute_insights_produces_keywords_themes_and_breakdowns(self):
        schema = parse_schema_fields(
            [
                {"name": "platform", "type": "string"},
                {"name": "sentiment", "type": "enum", "enum": ["positive", "negative"]},
            ]
        )

        rows = [
            {
                "id": "1",
                "raw_text": "I had a payment issue on iOS. Payment failed twice.",
                "platform": "iOS",
                "sentiment": "negative",
            },
            {
                "id": "2",
                "raw_text": "Android payment issue resolved. Payment now works.",
                "platform": "Android",
                "sentiment": "positive",
            },
            {
                "id": "3",
                "raw_text": "Payment issue on iOS again.",
                "platform": "iOS",
                "sentiment": "negative",
            },
        ]

        first = compute_insights(rows, schema)
        second = compute_insights(rows, schema)

        self.assertEqual(first, second, "Insights should be reproducible on the same input")
        self.assertTrue(first.keywords, "Expected non-empty keyword list")
        self.assertTrue(first.themes, "Expected at least one theme bucket")
        self.assertIn("platform", first.field_breakdowns)
        self.assertIn("sentiment", first.field_breakdowns)

        platform_counts = dict(first.field_breakdowns["platform"])
        self.assertEqual(platform_counts.get("iOS"), 2)
        self.assertEqual(platform_counts.get("Android"), 1)
