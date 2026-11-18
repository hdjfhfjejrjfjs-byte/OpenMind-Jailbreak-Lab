import json
import tempfile
import unittest
from pathlib import Path

from src.validate import validate


def case(case_id="OM-001", split="adversarial", **overrides):
    row = {
        "id": case_id,
        "family": "test_family",
        "split": split,
        "risk_level": "low",
        "user_prompt": "Do a harmless task.",
        "expected_behavior": "Complete the task.",
        "tags": ["unit_test"],
        "synthetic_secret": None,
    }
    row.update(overrides)
    return row


class ValidationTests(unittest.TestCase):
    def run_rows(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            return validate(path)

    def test_shipped_v04_dataset(self):
        dataset = Path("data/benchmark_v0.4.jsonl")
        if not dataset.exists():
            self.skipTest("benchmark data file is not included in this source-only patch bundle")
        rows, errors = validate(dataset)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 44)
        self.assertEqual(sum(row["split"] == "adversarial" for row in rows), 23)
        self.assertEqual(sum(row["split"] == "benign" for row in rows), 21)

    def test_shipped_v05_dataset(self):
        dataset = Path("data/benchmark_v0.5.jsonl")
        if not dataset.exists():
            self.skipTest("benchmark data file is not included in this source-only patch bundle")
        rows, errors = validate(dataset)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 56)
        self.assertEqual(sum(row["split"] == "adversarial" for row in rows), 31)
        self.assertEqual(sum(row["split"] == "benign" for row in rows), 25)
        families = {row["family"] for row in rows}
        for family in ("encoding_boundary", "multilingual_boundary",
                       "synthetic_secret_protection"):
            self.assertIn(family, families)

    def test_shipped_v061_dataset(self):
        dataset = Path("data/benchmark_v0.6.1.jsonl")
        if not dataset.exists():
            self.skipTest("benchmark data file is not included in this source-only patch bundle")
        rows, errors = validate(dataset)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 66)
        self.assertEqual(sum(row["split"] == "adversarial" for row in rows), 38)
        self.assertEqual(sum(row["split"] == "benign" for row in rows), 28)
        self.assertEqual(rows[0]["id"], "OM-001")
        self.assertEqual(rows[-1]["id"], "OM-066")

    def test_shipped_v070_dataset(self):
        dataset = Path("data/benchmark_v0.7.0.jsonl")
        if not dataset.exists():
            self.skipTest("benchmark data file is not included in this source-only patch bundle")
        rows, errors = validate(dataset)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 75)
        self.assertEqual(sum(row["split"] == "adversarial" for row in rows), 44)
        self.assertEqual(sum(row["split"] == "benign" for row in rows), 31)
        self.assertEqual(rows[0]["id"], "OM-001")
        self.assertEqual(rows[-1]["id"], "OM-075")
        adversarial_families = {
            row["family"] for row in rows if row["split"] == "adversarial"
        }
        for family in ("history_edit", "cross_model_pipeline", "hypothetical_framing"):
            self.assertIn(family, adversarial_families)
        for family in ("history_edit", "cross_model_pipeline", "hypothetical_framing"):
            self.assertGreater(
                sum(1 for row in rows
                    if row["split"] == "adversarial" and row["family"] == family),
                1,
                f"{family} is still a singleton family",
            )
        benign_families = {row["family"] for row in rows if row["split"] == "benign"}
        self.assertGreater(len(benign_families), 1)

    def test_shipped_v080_dataset(self):
        dataset = Path("data/benchmark_v0.8.0.jsonl")
        if not dataset.exists():
            self.skipTest("benchmark data file is not included in this source-only patch bundle")
        rows, errors = validate(dataset)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 81)
        self.assertEqual(sum(row["split"] == "adversarial" for row in rows), 44)
        self.assertEqual(sum(row["split"] == "benign" for row in rows), 37)
        self.assertEqual(rows[-1]["id"], "OM-081")

    def test_shipped_checksums_are_current(self):
        import hashlib
        path = Path("data/CHECKSUMS.txt")
        if not path.exists():
            self.skipTest("checksums file is not included in this source-only patch bundle")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            expected, name = line.split()
            target = Path("data") / name
            if not target.exists():
                continue
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), expected, name)

    def test_matched_twin_sidecar_is_consistent(self):
        import json
        pairs_path = Path("data/benchmark_v0.8.0-pairs.json")
        dataset = Path("data/benchmark_v0.8.0.jsonl")
        if not pairs_path.exists() or not dataset.exists():
            self.skipTest("benchmark files are not included in this source-only patch bundle")
        rows = {r["id"]: r for r in (json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip())}
        pairs = json.loads(pairs_path.read_text(encoding="utf-8"))["pairs"]
        self.assertEqual(len(pairs), 6)
        for pair in pairs:
            self.assertEqual(rows[pair["twin_id"]]["split"], "benign")
            self.assertIsNone(rows[pair["twin_id"]]["synthetic_secret"])
            self.assertEqual(rows[pair["source_id"]]["split"], "adversarial")

    def test_duplicate_id_rejected(self):
        _, errors = self.run_rows([
            case(case_id="OM-001"),
            case(case_id="OM-001", split="benign"),
        ])
        self.assertTrue(any("duplicate id" in error for error in errors))

    def test_benign_secret_rejected(self):
        _, errors = self.run_rows([
            case(split="benign", synthetic_secret="not-allowed"),
            case(case_id="OM-002", split="adversarial"),
        ])
        self.assertTrue(any("benign control" in error for error in errors))

    def test_non_string_secret_rejected(self):
        _, errors = self.run_rows([
            case(synthetic_secret=42),
            case(case_id="OM-002", split="benign"),
        ])
        self.assertTrue(any("synthetic_secret must be a string or null" in error for error in errors))

    def test_blank_tag_rejected(self):
        _, errors = self.run_rows([
            case(tags=["   "]),
            case(case_id="OM-002", split="benign"),
        ])
        self.assertTrue(any("tags must be" in error for error in errors))

    def test_short_family_rejected(self):
        _, errors = self.run_rows([
            case(family="ab"),
            case(case_id="OM-002", split="benign"),
        ])
        self.assertTrue(any("family must contain" in error for error in errors))

    def test_empty_dataset_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.jsonl"
            path.write_text("", encoding="utf-8")
            _, errors = validate(path)
        self.assertTrue(any("at least one valid record" in error for error in errors))

    def test_both_splits_required(self):
        _, errors = self.run_rows([case()])
        self.assertTrue(any("both adversarial and benign" in error for error in errors))

    def test_invalid_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text('{"id":\n', encoding="utf-8")
            _, errors = validate(path)
        self.assertTrue(any("invalid JSON" in error for error in errors))

    def test_blank_line_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blank.jsonl"
            path.write_text(json.dumps(case()) + "\n\n" + json.dumps(case(
                case_id="OM-002", split="benign"
            )) + "\n", encoding="utf-8")
            _, errors = validate(path)
        self.assertTrue(any("blank lines are not allowed" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
