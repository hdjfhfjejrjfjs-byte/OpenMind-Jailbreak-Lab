import json
import tempfile
import unittest
from pathlib import Path

from omjb.mutation_engine.chat_completions import (
    ChatEvalResult,
    ConcurrentChatCompletionsEvaluator,
    _refusal_signal,
    _validate_endpoint,
)


class ChatCompletionsEvaluatorTests(unittest.TestCase):
    def test_endpoint_requires_https_except_loopback(self):
        self.assertEqual(
            _validate_endpoint("http://localhost:11434"),
            "http://localhost:11434/v1/chat/completions",
        )
        self.assertEqual(
            _validate_endpoint("https://api.example/v1/chat/completions"),
            "https://api.example/v1/chat/completions",
        )
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            _validate_endpoint("http://api.example")

    def test_refusal_detector_is_only_a_signal(self):
        self.assertTrue(_refusal_signal("I'm sorry, I cannot assist with that."))
        self.assertFalse(_refusal_signal("Here is a harmless explanation."))
        evaluator = ConcurrentChatCompletionsEvaluator(
            "http://127.0.0.1:11434", "local-model",
            max_requests=3, max_seconds=10, max_usd=0,
        )
        self.assertEqual(evaluator.max_requests, 3)

    def test_rejects_non_benign_probe_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probes.json"
            path.write_text(json.dumps([{
                "id": "unsafe", "prompt": "test", "expected": "refuse",
                "meta": {"mutation_safe": True},
            }]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not approved benign"):
                ConcurrentChatCompletionsEvaluator.load_payloads(str(path))

    def test_campaign_records_manual_review_and_enforces_request_cap(self):
        class StubEvaluator(ConcurrentChatCompletionsEvaluator):
            def _send(self, probe):
                return ChatEvalResult(
                    probe_id=probe.id, prompt_preview=probe.prompt,
                    response_preview="response", raw_response="response",
                    latency_ms=1, refusal_signal=False,
                )

        with tempfile.TemporaryDirectory() as directory:
            probes_path = Path(directory) / "probes.json"
            probes_path.write_text(json.dumps([
                {"id": f"p{i}", "prompt": f"benign task {i}", "expected": "comply",
                 "meta": {"mutation_safe": True}}
                for i in range(4)
            ]), encoding="utf-8")
            probes = StubEvaluator.load_payloads(str(probes_path))
            evaluator = StubEvaluator(
                "http://localhost:11434", "local-model", max_requests=2,
                max_workers=2, max_seconds=10, max_usd=0,
            )
            output = Path(directory) / "report.json"
            report = evaluator.run_campaign(probes, str(output))
            self.assertEqual(report["requested"], 4)
            self.assertEqual(report["submitted"], 2)
            self.assertEqual(report["human_review_required"], 2)
            self.assertEqual(report["no_refusal_signals"], 2)
            self.assertEqual(len(json.loads(output.read_text())["results"]), 2)


if __name__ == "__main__":
    unittest.main()
