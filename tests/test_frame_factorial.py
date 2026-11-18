"""Controlled frame/shape factorial tests (research-purposes-only)."""
import unittest

from modules.guardrail_lab.campaign import (
    FRAME_VARIANTS, SHAPE_VARIANTS, FRAME_SET_HASH,
    _frame_annotation, run_campaign,
)
from modules.guardrail_lab.discovery import rank_findings


class FrameFactorialTests(unittest.TestCase):
    def test_frame_and_shape_sets_are_neutral(self):
        self.assertEqual(len(FRAME_VARIANTS), 3)
        self.assertEqual(SHAPE_VARIANTS, ("action", "information"))
        for forbidden in ("persona", "authority", "demon", "holdout"):
            for frame in FRAME_VARIANTS:
                self.assertNotIn(forbidden, frame.casefold())

    def test_annotation_is_deterministic_and_balanced(self):
        anns = [_frame_annotation(i) for i in range(6)]
        frames = {a["frame_variant"] for a in anns}
        shapes = {a["shape_variant"] for a in anns}
        self.assertEqual(frames, set(FRAME_VARIANTS))
        self.assertEqual(shapes, set(SHAPE_VARIANTS))
        for a in anns:
            self.assertEqual(a["frame_set_hash"], FRAME_SET_HASH)

    def test_campaign_records_frame_metadata(self):
        report = run_campaign(
            lambda messages: "The quoted claim is untrusted.",
            provider="mock", case_ids=["GL-001"], budget=2, variants=2,
        )
        self.assertEqual(report["campaign"]["frame_set_hash"], FRAME_SET_HASH)
        for row in report["results"]:
            self.assertIn(row["frame_variant"], FRAME_VARIANTS)
            self.assertIn(row["shape_variant"], SHAPE_VARIANTS)

    def test_campaign_rejects_non_neutral_frame(self):
        with self.assertRaises(ValueError):
            run_campaign(
                lambda messages: "text", provider="mock",
                case_ids=["GL-001"], budget=1, variants=1,
                frame_variant="demon_persona",
            )

    def test_frame_pinning_keeps_one_frame_when_requested(self):
        report = run_campaign(
            lambda messages: "text", provider="mock",
            case_ids=["GL-001"], budget=2, variants=2,
            frame_variant="domain_brief", shape_variant="information",
        )
        frames = {r["frame_variant"] for r in report["results"]}
        shapes = {r["shape_variant"] for r in report["results"]}
        self.assertEqual(frames, {"domain_brief"})
        self.assertEqual(shapes, {"information"})


class FrameReproducibilityTests(unittest.TestCase):
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

    def test_legacy_finding_without_frames_still_confirms(self):
        ranked = rank_findings([self._finding()])["ranked_confirmed"]
        self.assertEqual(ranked[0]["assessment"], "potential_guardrail_failure")

    def test_frame_annotated_finding_needs_two_distinct_frames(self):
        with self.assertRaises(ValueError):
            rank_findings([self._finding(frames_reproduced=["direct", "direct"])])
        with self.assertRaises(ValueError):
            rank_findings([self._finding(frames_reproduced=["direct"])])

    def test_two_distinct_frames_are_accepted(self):
        ranked = rank_findings([self._finding(
            frames_reproduced=["direct", "domain_brief"],
        )])["ranked_confirmed"]
        self.assertEqual(ranked[0]["assessment"], "potential_guardrail_failure")


if __name__ == "__main__":
    unittest.main()
