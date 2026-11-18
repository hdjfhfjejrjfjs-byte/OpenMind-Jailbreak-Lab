"""Negative-evidence lifecycle tests (research-purposes-only)."""
import json
import tempfile
import unittest
from pathlib import Path

from modules.guardrail_lab.discovery import rank_findings
from modules.guardrail_lab.registry import (
    STATUSES, add_finding, export_markdown, load_registry,
    record_supersession, validate_finding,
)


def _base(**extra):
    item = {
        "finding_id": "OM-FND-2026-0001", "title": "Candidate",
        "provider": "mock", "model": "m", "category": "injection",
        "status": "unverified", "discovered_at": "2026-11-17T00:00:00Z",
        "evidence_ref": "evidence/example-1.json", "summary": "Candidate only.",
        "repeat_runs": 2, "repeat_successes": 1,
    }
    item.update(extra)
    return item


class SupersessionTests(unittest.TestCase):
    def test_new_statuses_are_declared(self):
        self.assertTrue({"superseded", "not_reproduced", "not_measured"} <= STATUSES)

    def test_superseded_requires_both_chain_ends(self):
        with self.assertRaisesRegex(ValueError, "supersedes"):
            validate_finding(_base(status="superseded"))

    def test_not_reproduced_requires_repeat_counts(self):
        with self.assertRaisesRegex(ValueError, "repeat_runs"):
            validate_finding(_base(status="not_reproduced", repeat_runs=None))
        with self.assertRaisesRegex(ValueError, "fewer than two"):
            validate_finding(_base(status="not_reproduced", repeat_successes=2))

    def test_not_measured_requires_reason(self):
        with self.assertRaisesRegex(ValueError, "not_measured_reason"):
            validate_finding(_base(status="not_measured"))
        row = validate_finding(_base(
            status="not_measured", not_measured_reason="adapter unavailable"))
        self.assertEqual(row["status"], "not_measured")

    def test_append_only_supersession_preserves_original_verbatim(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "registry.jsonl"
            original = add_finding(registry, _base())
            replacement = add_finding(registry, _base(
                finding_id="OM-FND-2026-0002", title="Corrected result",
                evidence_ref="evidence/example-2.json",
            ))
            before = load_registry(registry)
            original_before = next(r for r in before
                                   if r["finding_id"] == original["finding_id"])
            record = record_supersession(
                registry, original["finding_id"], replacement["finding_id"],
                "Re-measured under pinned config; prior conclusion withdrawn.",
            )
            after = load_registry(registry)
            original_after = next(r for r in after
                                  if r["finding_id"] == original["finding_id"])
            self.assertEqual(original_before, original_after)
            self.assertEqual(len(after), len(before) + 1)
            self.assertEqual(record["supersedes"], original["finding_id"])
            self.assertEqual(record["superseded_by"], replacement["finding_id"])
            # All rows, including the new one, pass load-time hash validation.
            self.assertEqual(len(after), 3)

    def test_chain_references_must_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "registry.jsonl"
            add_finding(registry, _base())
            with self.assertRaisesRegex(ValueError, "not in the registry"):
                add_finding(registry, _base(
                    finding_id="OM-FND-2026-0009", status="superseded",
                    supersedes="OM-FND-2026-0001",
                    superseded_by="OM-FND-2026-MISSING",
                ))

    def test_export_markdown_shows_chain_and_negative_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "registry.jsonl"
            out = Path(directory) / "FINDINGS.md"
            add_finding(registry, _base())
            add_finding(registry, _base(
                finding_id="OM-FND-2026-0002", title="Corrected result",
                evidence_ref="evidence/example-2.json",
            ))
            record_supersession(registry, "OM-FND-2026-0001",
                                "OM-FND-2026-0002", "Superseded by re-run.")
            add_finding(registry, _base(
                finding_id="OM-FND-2026-0003", status="not_reproduced",
                evidence_ref="evidence/example-3.json",
            ))
            add_finding(registry, _base(
                finding_id="OM-FND-2026-0004", status="not_measured",
                not_measured_reason="endpoint unavailable",
                evidence_ref="evidence/example-4.json",
            ))
            export_markdown(load_registry(registry), out)
            text = out.read_text(encoding="utf-8")
            self.assertIn("Supersedes: OM-FND-2026-0001", text)
            self.assertIn("Superseded by: OM-FND-2026-0002", text)
            self.assertIn("Not reproduced: 1/2", text)
            self.assertIn("Not measured: endpoint unavailable", text)


class SupersededRankingTests(unittest.TestCase):
    def _finding(self, **extra):
        base = {
            "provider": "mock", "model": "m", "evidence_ref": "e1",
            "review_status": "confirmed",
            "assessment": "potential_guardrail_failure",
            "impact": "moderate", "reproducible": True,
            "repeat_runs": 2, "repeat_successes": 2,
        }
        base.update(extra)
        return base

    def test_superseded_is_downgraded_not_ranked(self):
        output = rank_findings([self._finding(review_status="superseded")])
        self.assertEqual(output["confirmed_count"], 0)
        self.assertEqual(output["superseded_count"], 1)
        self.assertEqual(len(output["ranked_confirmed"]), 0)

    def test_not_reproduced_and_not_measured_go_to_triage(self):
        output = rank_findings([
            self._finding(review_status="not_reproduced"),
            self._finding(review_status="not_measured", evidence_ref="e2"),
        ])
        self.assertEqual(output["confirmed_count"], 0)
        self.assertEqual(output["triage_count"], 2)


if __name__ == "__main__":
    unittest.main()
