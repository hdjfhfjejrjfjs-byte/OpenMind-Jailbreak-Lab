"""Config-pinned evidence contract tests (research-purposes-only)."""
import json
import unittest
from unittest.mock import patch

from modules.guardrail_lab.measurement import (
    RunConfig, case_set_hashes, fingerprint_endpoint, redact_config,
)
from modules.guardrail_lab.compare import compare_reports, config_equivalence
from modules.guardrail_lab.runner import run_suite


def _report(provider, assessment="boundary_held", config_hash=None, **extra):
    provenance = {}
    if config_hash is not None:
        provenance["config_hash"] = config_hash
    item = {
        "case_id": "GL-001",
        "assessment": assessment,
        "response_status": "ok",
    }
    item.update(extra)
    return {
        "provider": provider,
        "model": "m",
        "provenance": provenance,
        "results": [item],
    }


class MeasurementTests(unittest.TestCase):
    def test_config_hash_is_stable_and_excludes_unmeasured_reasons(self):
        a = RunConfig(model="m", provider="p", temperature=1.0)
        b = RunConfig(
            model="m", provider="p", temperature=1.0,
            not_measured=[{"item": "seed", "reason": "not transmitted"}],
        )
        self.assertEqual(a.config_hash(), b.config_hash())
        self.assertEqual(len(a.config_hash()), 64)

    def test_config_hash_changes_with_measured_setting(self):
        a = RunConfig(model="m", provider="p", thinking=True)
        b = RunConfig(model="m", provider="p", thinking=False)
        self.assertNotEqual(a.config_hash(), b.config_hash())

    def test_validate_rejects_bool_as_number(self):
        with self.assertRaises(ValueError):
            RunConfig(temperature=True).validate()

    def test_redaction_scrubs_token_like_material(self):
        block = RunConfig(
            model="m", provider="p",
            metadata={"api_key": "sk-secret"},
        ).evidence_block()
        rendered = json.dumps(block)
        self.assertNotIn("sk-secret", rendered)

    def test_endpoint_fingerprint_is_stable_and_redacted(self):
        url = "https://host.example/v1/chat/completions?api_key=something-secret"
        fp = fingerprint_endpoint(url)
        self.assertEqual(fp, fingerprint_endpoint("https://host.example/v1/chat/completions"))
        self.assertIsNotNone(fp)
        self.assertNotIn("something-secret", fp)

    def test_case_set_hashes_cover_actual_files(self):
        hashes = case_set_hashes()
        self.assertIn("core_cases", hashes)
        self.assertIn("source_cases", hashes)
        self.assertTrue(all(len(h) == 64 for h in hashes.values()))

    def test_not_measured_entries_are_typed(self):
        with self.assertRaises(ValueError):
            RunConfig(not_measured=[{"item": "seed"}]).validate()


class CompareConfigTests(unittest.TestCase):
    def test_legacy_reports_default_to_uncontrolled_comparison(self):
        result = compare_reports([_report("a"), _report("b")])
        self.assertEqual(result["config_equivalence"]["status"], "not_measured")
        self.assertIsNotNone(result["agreement_rate_on_comparable_common_cases"])
        self.assertIn("Config equivalence could not be established", result["interpretation"])

    def test_strict_mode_with_unknown_config_marks_everything_incomparable(self):
        result = compare_reports([_report("a"), _report("b")], strict_config=True)
        self.assertEqual(result["comparable_case_count"], 0)
        self.assertIsNone(result["agreement_rate_on_comparable_common_cases"])
        self.assertTrue(result["strict_config"])

    def test_strict_mode_with_divergent_configs_marks_everything_incomparable(self):
        result = compare_reports(
            [_report("a", config_hash="a" * 64), _report("b", config_hash="b" * 64)],
            strict_config=True,
        )
        self.assertEqual(result["config_equivalence"]["status"], "divergent")
        self.assertEqual(result["comparable_case_count"], 0)
        self.assertIsNone(result["agreement_rate_on_comparable_common_cases"])

    def test_equivalent_configs_allow_comparison_in_strict_mode(self):
        result = compare_reports(
            [_report("a", config_hash="c" * 64), _report("b", config_hash="c" * 64)],
            strict_config=True,
        )
        self.assertEqual(result["config_equivalence"]["status"], "equivalent")
        self.assertEqual(result["comparable_case_count"], 1)
        self.assertEqual(result["agreement_rate_on_comparable_common_cases"], 1.0)

    def test_truncated_responses_are_excluded_from_agreement(self):
        result = compare_reports([
            _report("a", truncated=True, finish_reason="length"),
            _report("b", config_hash=None),
        ])
        self.assertEqual(result["comparable_case_count"], 0)

    def test_uncertainty_is_descriptive_not_a_confidence_claim(self):
        result = compare_reports([_report("a"), _report("b")])
        u = result["uncertainty"]
        self.assertEqual(u["kind"], "descriptive_dispersion")
        self.assertEqual(u["n_observations"], 2)
        self.assertIn("No uncertainty interval is published", u["note"])


class RunSuiteProvenanceTests(unittest.TestCase):
    def test_run_suite_records_reproduction_attributes(self):
        def call(messages):
            return "The quote is untrusted content."

        report = run_suite(call, provider="mock", case_ids=["GL-001"])
        prov = report["provenance"]
        self.assertIn("run_config", prov)
        self.assertIn("config_hash", prov)
        self.assertEqual(prov["schema_version"], "1.2")
        self.assertTrue(any(e["item"] == "temperature" for e in prov["not_measured"]))
        self.assertEqual(report["schema_version"], "1.2")

    def test_run_case_records_response_completeness_fields(self):
        def call(messages):
            return "The quote is untrusted content."

        report = run_suite(call, provider="mock", case_ids=["GL-001"])
        row = report["results"][0]
        for key in (
            "provider_response_status", "finish_reason", "content_tokens",
            "thinking_parse_status", "truncated",
        ):
            self.assertIn(key, row)
        self.assertFalse(row["truncated"])


if __name__ == "__main__":
    unittest.main()
