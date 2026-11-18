"""Typed preflight tests (research-purposes-only)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules.guardrail_lab.preflight import (
    SMOKE_MARKER, SMOKE_MESSAGES, STATES, preflight,
)


class PreflightStateTests(unittest.TestCase):
    def _kwargs(self, **extra):
        base = {"provider": "openai-compatible", "model": "test-checkpoint"}
        base.update(extra)
        return base

    def test_ready_requires_real_forward_echo(self):
        calls = []

        def call(messages):
            calls.append(messages)
            return SMOKE_MARKER

        receipt = preflight(call, **self._kwargs())
        self.assertEqual(receipt["state"], "ready")
        self.assertTrue(receipt["identity_confirmed"])
        self.assertEqual(len(calls), 1)
        self.assertIn(SMOKE_MARKER, calls[0][-1]["content"])
        self.assertEqual(len(receipt["receipt_sha256"]), 64)

    def test_health_or_models_list_does_not_count_as_ready(self):
        # A canned /v1/models-style response cannot confirm a real forward.
        receipt = preflight(
            lambda messages: '{"data": [{"id": "test-checkpoint"}]}',
            **self._kwargs(),
        )
        self.assertEqual(receipt["state"], "not_ready")
        self.assertFalse(receipt["identity_confirmed"])

    def test_empty_response_is_not_ready(self):
        receipt = preflight(lambda messages: "   ", **self._kwargs())
        self.assertEqual(receipt["state"], "not_ready")

    def test_benchmark_refusal_is_not_a_preflight_state(self):
        # Preflight only ever sends the benign echo. Any refusal text is
        # classified as an unconfirmed forward, never a benchmark outcome.
        receipt = preflight(
            lambda messages: "I cannot help with that request.", **self._kwargs(),
        )
        self.assertEqual(receipt["state"], "not_ready")
        self.assertNotIn("refusal", receipt["state"])

    def test_missing_model_is_misconfigured(self):
        receipt = preflight(lambda messages: SMOKE_MARKER, provider="openai-compatible")
        self.assertEqual(receipt["state"], "misconfigured")
        self.assertIn("model", receipt["reason"])

    def test_model_identity_pin(self):
        receipt = preflight(
            lambda messages: SMOKE_MARKER,
            **self._kwargs(expected_model="pinned-checkpoint"),
        )
        self.assertEqual(receipt["state"], "misconfigured")

    def test_auth_error_is_misconfigured(self):
        def call(messages):
            raise RuntimeError("401 unauthorized: invalid api key")

        receipt = preflight(call, **self._kwargs())
        self.assertEqual(receipt["state"], "misconfigured")

    def test_transport_error_is_not_ready(self):
        def call(messages):
            raise TimeoutError("connection timed out")

        receipt = preflight(call, **self._kwargs())
        self.assertEqual(receipt["state"], "not_ready")

    def test_unexpected_error_is_failed(self):
        def call(messages):
            raise RuntimeError("unexpected internal condition XYZ")

        receipt = preflight(call, **self._kwargs())
        self.assertEqual(receipt["state"], "failed")

    def test_all_states_are_declared(self):
        self.assertEqual(set(STATES), {"ready", "not_ready", "misconfigured", "failed"})

    def test_config_is_scrubbed_and_no_raw_url(self):
        secret = "sk-" + "A" * 40
        receipt = preflight(
            lambda messages: SMOKE_MARKER,
            **self._kwargs(
                base_url="https://secret.example/v1",
                config={"api_key": secret, "nested": {"token": secret}},
            ),
        )
        rendered = json.dumps(receipt)
        self.assertNotIn(secret, rendered)
        self.assertNotIn("secret.example", rendered)
        self.assertEqual(receipt["config"]["api_key"], "***")
        self.assertEqual(receipt["config"]["nested"]["token"], "***")

    def test_smoke_messages_are_benign_and_constant(self):
        self.assertEqual(len(SMOKE_MESSAGES), 2)
        rendered = " ".join(m["content"] for m in SMOKE_MESSAGES).casefold()
        for forbidden in ("persona", "authority", "demon", "holdout", "jailbreak"):
            self.assertNotIn(forbidden, rendered)


class PreflightCliTests(unittest.TestCase):
    def test_require_ready_blocks_when_not_ready(self):
        from modules.guardrail_lab.cli import main
        with mock.patch("modules.guardrail_lab.cli._adapter",
                        return_value=lambda messages: "no echo"), \
             mock.patch.dict("os.environ", {"OPENAI_COMPAT_API_KEY": "test"}, clear=True):
            code = main([
                "--provider", "openai-compatible", "--model", "m",
                "--base-url", "http://localhost:1/v1", "--require-ready",
            ])
        self.assertEqual(code, 2)

    def test_preflight_only_writes_scrubbed_receipt(self):
        from modules.guardrail_lab.cli import main
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "preflight.json"
            with mock.patch("modules.guardrail_lab.cli._adapter",
                            return_value=lambda messages: SMOKE_MARKER), \
                 mock.patch.dict("os.environ", {"OPENAI_COMPAT_API_KEY": "test"}, clear=True):
                code = main([
                    "--provider", "openai-compatible", "--model", "m",
                    "--base-url", "http://localhost:1/v1",
                    "--preflight-only", "--preflight-output", str(out),
                ])
            self.assertEqual(code, 0)
            receipt = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(receipt["state"], "ready")
            self.assertNotIn("localhost:1", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
