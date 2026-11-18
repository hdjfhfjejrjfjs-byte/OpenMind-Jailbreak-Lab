"""Uncertainty-display tests (research-purposes-only).

G: descriptive dispersion only. Repeated measures and provider-level
correlation forbid a naive independent-Bernoulli confidence interval;
the display must never publish one, and missing cases stay distinct.
"""
import json
import unittest

from modules.guardrail_lab.compare import compare_reports


def _report(provider, case_ids, assessment="boundary_held"):
    return {
        "provider": provider,
        "model": "m",
        "provenance": {},
        "results": [
            {"case_id": cid, "assessment": assessment, "response_status": "ok"}
            for cid in case_ids
        ],
    }


class UncertaintyDisplayTests(unittest.TestCase):
    def test_three_reports_dispersion_is_descriptive_only(self):
        result = compare_reports([
            _report("a", ["GL-001", "GL-002"]),
            _report("b", ["GL-001", "GL-002"]),
            _report("c", ["GL-001", "GL-002"]),
        ])
        u = result["uncertainty"]
        self.assertEqual(u["kind"], "descriptive_dispersion")
        self.assertEqual(u["n_observations"], 6)
        self.assertEqual(u["comparable_case_count"], 2)
        self.assertIn("No uncertainty interval is published", u["note"])

    def test_no_confidence_or_significance_keys_are_published(self):
        rendered = json.dumps(compare_reports([
            _report("a", ["GL-001"]), _report("b", ["GL-001"]),
        ])).casefold()
        for forbidden in ("confidence_interval", "p_value", "pvalue",
                          "standard_error", "margin_of_error", "ci_95"):
            self.assertNotIn(forbidden, rendered)

    def test_missing_cases_stay_distinct_from_disagreement(self):
        result = compare_reports([
            _report("a", ["GL-001", "GL-002"]),
            _report("b", ["GL-001"]),
        ])
        self.assertEqual(result["union_case_count"], 2)
        self.assertEqual(result["common_case_count"], 1)
        self.assertEqual(result["missing_case_ids"]["b/m"], ["GL-002"])
        self.assertEqual(result["uncertainty"]["excluded_case_count"], 1)

    def test_inconclusive_cases_are_not_in_the_denominator(self):
        second = _report("b", ["GL-001"])
        second["results"][0]["assessment"] = "inconclusive"
        result = compare_reports([_report("a", ["GL-001"]), second])
        u = result["uncertainty"]
        self.assertEqual(u["comparable_case_count"], 0)
        self.assertEqual(result["agreement_rate_on_comparable_common_cases"], None)


if __name__ == "__main__":
    unittest.main()
