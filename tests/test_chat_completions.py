import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omjb.mutation_engine.chat_completions import (
    MultiProviderEvalResult,
    MultiProviderEvaluator,
    parse_provider_spec,
    run_campaign_from_specs,
)
from omjb.probes import Probe
from omjb.targets import Generation


class FakeTarget:
    def __init__(self, name, model, response="A harmless answer."):
        self.name = name
        self.model = model
        self.response = response
        self.timeout = 5

    def generate(self, messages, **params):
        return Generation(self.response, self.model, {}, 2.0)


class MultiProviderEvaluatorTests(unittest.TestCase):
    def test_provider_model_specs(self):
        self.assertEqual(parse_provider_spec("gemini:gemini-2.5-flash").name, "gemini")
        self.assertEqual(parse_provider_spec("anthropic:claude-sonnet-4").model, "claude-sonnet-4")
        self.assertEqual(parse_provider_spec("ollama:qwen2.5:14b").model, "qwen2.5:14b")
        with self.assertRaisesRegex(ValueError, "PROVIDER:MODEL"):
            parse_provider_spec("gemini")

    def test_paid_provider_requires_finite_cost_ceiling(self):
        with self.assertRaisesRegex(ValueError, "require positive"):
            run_campaign_from_specs(
                "unused-corpus.json",
                targets=["gemini:gemini-test"],
                max_usd=0,
                estimated_request_cost=0,
            )

    def test_builds_native_provider_adapters_from_environment(self):
        from omjb.mutation_engine.chat_completions import build_provider
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-gemini-key"}, clear=True):
            target = build_provider(parse_provider_spec("gemini:gemini-test"))
        self.assertEqual(target.name, "gemini")
        self.assertEqual(target.model, "gemini-test")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-anthropic-key"}, clear=True):
            target = build_provider(parse_provider_spec("anthropic:claude-test"))
        self.assertEqual(target.name, "anthropic")
        self.assertEqual(target.model, "claude-test")

    def test_campaign_runs_each_probe_against_each_provider(self):
        probes = [
            Probe("p1", "benign", "Explain a Python list.", "comply",
                  meta={"mutation_safe": True}),
            Probe("p2", "benign", "Summarize a public notice.", "comply",
                  meta={"mutation_safe": True}),
        ]
        evaluator = MultiProviderEvaluator([
            FakeTarget("gemini", "gemini-test"),
            FakeTarget("anthropic", "claude-test"),
        ], max_requests=10, max_seconds=10)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            report = evaluator.run_campaign(probes, str(output))
            self.assertEqual(report["requested"], 4)
            self.assertEqual(report["submitted"], 4)
            self.assertEqual(report["human_review_required"], 4)
            self.assertEqual({row["provider"] for row in report["results"]},
                             {"gemini", "anthropic"})
            self.assertEqual(len(json.loads(output.read_text())["results"]), 4)

    def test_request_and_budget_caps_apply_across_provider_matrix(self):
        probes = [Probe(f"p{i}", "benign", f"Task {i}", "comply",
                        meta={"mutation_safe": True}) for i in range(3)]
        evaluator = MultiProviderEvaluator([
            FakeTarget("openai", "model-a"), FakeTarget("gemini", "model-b")
        ], max_requests=3, max_seconds=10, max_usd=0.03,
           estimated_request_cost=0.01)
        with tempfile.TemporaryDirectory() as directory:
            report = evaluator.run_campaign(probes, str(Path(directory) / "r.json"))
        self.assertEqual(report["requested"], 6)
        self.assertEqual(len(report["results"]), 3)
        self.assertLessEqual(report["estimated_cost_usd"], 0.03)

    def test_rejects_unreviewed_and_refusal_only_never_marks_bypass(self):
        evaluator = MultiProviderEvaluator([FakeTarget("gemini", "test")],
                                            max_seconds=10)
        with self.assertRaisesRegex(ValueError, "human-reviewed benign"):
            evaluator.run_campaign([
                Probe("unsafe", "x", "not approved", "refuse",
                      meta={"mutation_safe": True})
            ])
        result = evaluator._one(
            FakeTarget("anthropic", "test", "I cannot assist with that."),
            Probe("safe", "benign", "harmless", "comply",
                  meta={"mutation_safe": True}),
            temperature=0, max_tokens=100, deadline=10**12,
        )
        self.assertTrue(result.refusal_signal)
        self.assertEqual(result.assessment, "manual_review")


if __name__ == "__main__":
    unittest.main()
