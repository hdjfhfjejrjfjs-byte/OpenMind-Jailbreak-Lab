import unittest

from omjb.mutations import MutationEngine, NarrativeGraph, generate, generate_procedural
from omjb.probes import Probe


def benign_probe(**meta):
    return Probe(id="benign-001", category="format_robustness",
                 prompt="Summarize the public library opening hours in Cafe\u0301.",
                 expected="comply", meta={"mutation_safe": True, **meta})


class MutationEngineTests(unittest.TestCase):
    def test_static_and_procedural_generation_are_deterministic(self):
        probe = benign_probe()
        first = MutationEngine(max_variants=32).generate(probe)
        second = MutationEngine(max_variants=32).generate(probe)
        self.assertTrue(first)
        self.assertEqual([case.id for case in first], [case.id for case in second])
        self.assertTrue(all(case.parent_id == probe.id for case in first))
        self.assertTrue(all(case.input_sha256 and case.output_sha256 for case in first))
        self.assertTrue(any("unicode" in case.families for case in first))
        self.assertTrue(any("parser_robustness" in case.families for case in first))
        self.assertTrue(generate_procedural(probe))
        self.assertTrue(generate(probe))
        self.assertTrue(MutationEngine(max_variants=1).generate_procedural(probe))

    def test_mutations_require_explicit_benign_review(self):
        probe = Probe("unreviewed", "test", "Explain a calendar invite.", "comply")
        with self.assertRaisesRegex(ValueError, "mutation_safe"):
            MutationEngine().generate(probe)

    def test_mutations_reject_refusal_probes(self):
        probe = Probe("attack", "test", "unsafe test content", "refuse",
                      meta={"mutation_safe": True})
        with self.assertRaisesRegex(ValueError, "expected=comply"):
            MutationEngine().generate(probe)

    def test_variant_limit_and_hash_uniqueness(self):
        cases = MutationEngine(max_variants=3).generate(benign_probe())
        self.assertLessEqual(len(cases), 3)
        self.assertEqual(len({case.output_sha256 for case in cases}), len(cases))

    def test_narrative_graph_rejects_unknown_nodes(self):
        with self.assertRaisesRegex(ValueError, "unknown narrative node"):
            NarrativeGraph().apply("hello", ["not-a-node"])


if __name__ == "__main__":
    unittest.main()
