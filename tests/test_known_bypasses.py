import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWN = ROOT / "data" / "known_bypasses.json"
BENCHMARK = ROOT / "data" / "benchmark_v0.8.0.jsonl"
SUBSET = ROOT / "data" / "benchmark_regression.jsonl"
CHECKSUMS = ROOT / "data" / "CHECKSUMS.txt"

OUTCOMES = {"exact_leak", "mention_failure", "mention_quoting_only",
            "held", "canary_only"}


def _load_known():
    return json.loads(KNOWN.read_text(encoding="utf-8"))


class KnownBypassesTests(unittest.TestCase):
    def test_file_is_valid_json_with_required_shape(self):
        doc = _load_known()
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["benchmark"], "data/benchmark_v0.8.0.jsonl")
        self.assertTrue(doc["entries"])
        for entry in doc["entries"]:
            self.assertIn(entry["instrument"],
                          ("benchmark", "guardrail", "scanner"))
            self.assertIn(entry["status"], ("confirmed", "intermittent"))
            self.assertTrue(entry["id"])
            self.assertTrue(entry["family"])
            for key in ("provider", "model", "date", "evidence_ref"):
                self.assertTrue(entry["first_seen"][key], key)
            self.assertGreaterEqual(entry["repeat_runs"], 0)
            self.assertGreaterEqual(entry["repeat_successes"], 0)
            self.assertLessEqual(entry["repeat_successes"],
                                 entry["repeat_runs"])
            for obs in entry["observations"]:
                self.assertIn(obs["outcome"], OUTCOMES)
                self.assertTrue(obs["provider"])
                self.assertTrue(obs["model"])
                self.assertTrue(obs["date"])
                self.assertTrue(obs["evidence_ref"])

    def test_ids_are_unique(self):
        doc = _load_known()
        ids = [entry["id"] for entry in doc["entries"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_benchmark_entries_exist_in_v080_with_stated_family(self):
        rows = {json.loads(line)["id"]: json.loads(line)
                for line in BENCHMARK.read_text(encoding="utf-8").splitlines()
                if line.strip()}
        doc = _load_known()
        for entry in doc["entries"]:
            if entry["instrument"] != "benchmark":
                continue
            row = rows.get(entry["id"])
            self.assertIsNotNone(row, entry["id"])
            self.assertEqual(row["family"], entry["family"], entry["id"])
            self.assertEqual(row["split"], "adversarial", entry["id"])
            self.assertTrue(row.get("synthetic_secret"), entry["id"])

    def test_guardrail_entry_exists_in_cases(self):
        from modules.guardrail_lab.cases import CASES
        by_id = {case.case_id: case for case in CASES}
        doc = _load_known()
        for entry in doc["entries"]:
            if entry["instrument"] != "guardrail":
                continue
            case = by_id.get(entry["id"])
            self.assertIsNotNone(case, entry["id"])
            self.assertEqual(case.category, entry["family"], entry["id"])

    def test_scanner_entries_exist_in_probes(self):
        from modules.ai_scanner.probes import PROBES
        by_id = {probe["id"]: probe for probe in PROBES}
        doc = _load_known()
        for entry in doc["entries"]:
            if entry["instrument"] != "scanner":
                continue
            probe = by_id.get(entry["id"])
            self.assertIsNotNone(probe, entry["id"])
            self.assertEqual(probe.get("category"), entry["family"],
                             entry["id"])

    def test_subset_rows_are_byte_identical_to_v080(self):
        source = {json.loads(line)["id"]: line
                  for line in BENCHMARK.read_text(encoding="utf-8").splitlines()
                  if line.strip()}
        subset = [line for line in
                  SUBSET.read_text(encoding="utf-8").splitlines() if line.strip()]
        doc = _load_known()
        expected = sorted(e["id"] for e in doc["entries"]
                          if e["instrument"] == "benchmark")
        actual = sorted(json.loads(line)["id"] for line in subset)
        self.assertEqual(actual, expected)
        for line in subset:
            case_id = json.loads(line)["id"]
            self.assertEqual(line, source[case_id], case_id)

    def test_subset_checksum_is_pinned(self):
        pinned = {}
        for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            expected, name = line.split()
            pinned[name] = expected
        self.assertIn("benchmark_regression.jsonl", pinned)
        self.assertEqual(
            hashlib.sha256(SUBSET.read_bytes()).hexdigest(),
            pinned["benchmark_regression.jsonl"])


if __name__ == "__main__":
    unittest.main()
