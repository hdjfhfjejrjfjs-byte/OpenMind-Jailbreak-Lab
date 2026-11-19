import asyncio
import unittest

from omjb.async_harness import parse_decision
from omjb.providers import CostTable, QuotaTracker


class DecisionParsingTests(unittest.TestCase):
    def test_common_shapes(self):
        self.assertEqual(parse_decision({"safe": True}), "allow")
        self.assertEqual(parse_decision({"flagged": True}), "review")
        self.assertEqual(parse_decision({"verdict": "block"}), "block")
        self.assertEqual(parse_decision({"decision": "review"}), "review")

    def test_unknown_shape_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_decision({"ok": True})


class CostTests(unittest.TestCase):
    def test_cost_calculation(self):
        table = CostTable({"model-x": (2.0, 4.0)})
        self.assertAlmostEqual(table.cost("model-x", 1000, 500), 0.004)

    def test_quota_records_and_reports(self):
        quota = QuotaTracker(cost_table=CostTable({"model-x": (2.0, 4.0)}))
        asyncio.run(quota.record("provider-x", "model-x", 1000, 500))
        summary = quota.summary()
        self.assertEqual(summary["provider-x:model-x"]["requests"], 1)
        self.assertEqual(summary["provider-x:model-x"]["input_tokens"], 1000)
        self.assertAlmostEqual(summary["total_cost_usd"], 0.004)

    def test_quota_cap_raises(self):
        quota = QuotaTracker(cost_table=CostTable({"model-x": (2.0, 4.0)}),
                             max_total_usd=0.001)
        with self.assertRaises(RuntimeError):
            asyncio.run(quota.record("provider-x", "model-x", 1000, 500))


if __name__ == "__main__":
    unittest.main()
