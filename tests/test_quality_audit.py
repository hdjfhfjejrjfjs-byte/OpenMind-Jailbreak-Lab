import json
import tempfile
import unittest
from pathlib import Path

from src.quality_audit import audit, audit_file


class QualityAuditTests(unittest.TestCase):
    def test_shipped_v080_dataset_passes_audit_cleanly(self):
        dataset = Path("data/benchmark_v0.8.0.jsonl")
        if not dataset.exists():
            self.skipTest("benchmark data file is not included in this source-only patch bundle")
        result = audit_file(dataset)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["errors"], [])

    def test_shipped_v070_dataset_passes_audit_cleanly(self):
        dataset = Path("data/benchmark_v0.7.0.jsonl")
        if not dataset.exists():
            self.skipTest("benchmark data file is not included in this source-only patch bundle")
        result = audit_file(dataset)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["errors"], [])

    def test_reports_benign_family_concentration(self):
        rows = [
            {"id": "OM-001", "split": "adversarial", "family": "injection", "user_prompt": "A"},
            {"id": "OM-002", "split": "benign", "family": "benign_utility", "user_prompt": "B"},
        ]
        result = audit(rows)
        self.assertEqual(result["status"], "review")
        self.assertTrue(any("only one family" in warning for warning in result["warnings"]))

    def test_duplicate_prompt_is_warning_not_silent(self):
        rows = [
            {"id": "OM-001", "split": "adversarial", "family": "injection", "user_prompt": "same prompt"},
            {"id": "OM-002", "split": "benign", "family": "benign_utility", "user_prompt": " SAME   PROMPT "},
        ]
        result = audit(rows)
        self.assertTrue(any("duplicate normalized prompt" in warning for warning in result["warnings"]))

    def test_benign_secret_is_error(self):
        rows = [
            {"id": "OM-001", "split": "adversarial", "family": "injection", "user_prompt": "A"},
            {"id": "OM-002", "split": "benign", "family": "benign_utility", "user_prompt": "B", "synthetic_secret": "TEST"},
        ]
        result = audit(rows)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(result["errors"])

    def test_non_object_row_is_reported_not_crashed(self):
        result = audit([{"id": "OM-001"}, "not-an-object", None])
        self.assertEqual(result["status"], "fail")
        self.assertIn("record 2: must be a JSON object", result["errors"])
        self.assertIn("record 3: must be a JSON object", result["errors"])

    def test_jsonl_scalar_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text('{"id":"OM-001"}\n42\n', encoding="utf-8")
            result = audit_file(path)
        self.assertEqual(result["status"], "fail")
        self.assertIn("record 2: must be a JSON object", result["errors"])

    def test_malformed_jsonl_reports_line_number(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text('{"id":"OM-001"}\n{broken\n', encoding="utf-8")
            result = audit_file(path)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(result["errors"][0].startswith("line 2:"))

    def test_unhashable_or_invalid_fields_are_reported_not_crashed(self):
        result = audit([{"id": ["bad"], "split": ["bad"], "family": None}])
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("id must be non-empty text" in error for error in result["errors"]))
        self.assertTrue(any("split must be non-empty text" in error for error in result["errors"]))
        self.assertTrue(any("family must be non-empty text" in error for error in result["errors"]))
        self.assertEqual(result["split_counts"], {})
        self.assertEqual(result["family_counts"], {"adversarial": {}, "benign": {}})

    def test_empty_dataset_fails(self):
        result = audit([])
        self.assertEqual(result["status"], "fail")
        self.assertIn("dataset contains no valid records", result["errors"])


if __name__ == "__main__":
    unittest.main()
