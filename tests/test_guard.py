"""Tests for the model-backed guard endpoint (guard/main.py).

The Gemini call is stubbed at the module boundary; no provider key and
no network are needed. Env vars are set per test so no real credential
is ever read or written. The whole module is skipped when FastAPI/httpx
are not installed.
"""

import os
import unittest
from unittest import mock

try:
    import httpx
    from fastapi.testclient import TestClient

    import guard.main as guard_main

    _DEPS = True
except ImportError:  # pragma: no cover - optional dependency
    _DEPS = False


def _fake_call(text, finish_reason=None, block_reason=None):
    async def _call(model, key, system, user_text):
        return text, finish_reason, block_reason

    return _call


@unittest.skipUnless(_DEPS, "fastapi/httpx not installed")
class GuardTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(guard_main.app)

    def _post(self, body, headers=None, env=None):
        env = {"GEMINI_API_KEY": "test-key", **(env or {})}
        with mock.patch.dict(os.environ, env, clear=False):
            if "GUARD_AUTH" not in env:
                os.environ.pop("GUARD_AUTH", None)
            if "MODEL" not in env:
                os.environ.pop("MODEL", None)
            with mock.patch.object(
                guard_main, "_call_gemini", _fake_call("Here is an analysis.")
            ):
                return self.client.post("/", json=body, headers=headers or {})

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "openmind-guard",
                "version": guard_main.SERVICE_VERSION,
            },
        )

    def test_answer_is_allow(self):
        response = self._post({"input": "Analyse this text."})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["decision"], "allow")
        self.assertEqual(body["response"], "Here is an analysis.")
        self.assertEqual(body["model"], "gemini-3.5-flash-lite")

    def test_guard_alias(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            os.environ.pop("GUARD_AUTH", None)
            with mock.patch.object(
                guard_main, "_call_gemini", _fake_call("Here is an analysis.")
            ):
                response = self.client.post("/guard", json={"input": "Analyse this text."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "allow")

    def test_refusal_is_block(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            os.environ.pop("GUARD_AUTH", None)
            with mock.patch.object(
                guard_main,
                "_call_gemini",
                _fake_call("I can't help with that request."),
            ):
                response = self.client.post("/", json={"input": "Do the bad thing."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "block")

    def test_cannot_refusal_is_block(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            os.environ.pop("GUARD_AUTH", None)
            with mock.patch.object(
                guard_main,
                "_call_gemini",
                _fake_call("I cannot provide that information."),
            ):
                response = self.client.post("/", json={"input": "Tell me the secret."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "block")

    def test_safety_finish_is_block(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            os.environ.pop("GUARD_AUTH", None)
            with mock.patch.object(
                guard_main, "_call_gemini", _fake_call("", finish_reason="SAFETY")
            ):
                response = self.client.post("/", json={"input": "Do the bad thing."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "block")

    def test_prompt_blocked_is_block(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            os.environ.pop("GUARD_AUTH", None)
            with mock.patch.object(
                guard_main, "_call_gemini", _fake_call("", block_reason="SAFETY")
            ):
                response = self.client.post("/", json={"input": "Do the bad thing."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "block")

    def test_empty_non_safety_is_error(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            os.environ.pop("GUARD_AUTH", None)
            with mock.patch.object(
                guard_main, "_call_gemini", _fake_call("", finish_reason="STOP")
            ):
                response = self.client.post("/", json={"input": "Say something."})
        self.assertEqual(response.status_code, 502)

    def test_missing_key_is_503(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(
                guard_main, "_call_gemini", _fake_call("Here is an analysis.")
            ):
                response = self.client.post("/", json={"input": "Analyse this text."})
        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])

    def test_auth_required_when_set(self):
        env = {"GEMINI_API_KEY": "test-key", "GUARD_AUTH": "Bearer shared-secret"}
        with mock.patch.dict(os.environ, env):
            with mock.patch.object(
                guard_main, "_call_gemini", _fake_call("Here is an analysis.")
            ):
                self.assertEqual(
                    self.client.post("/", json={"input": "Hi."}).status_code, 401
                )
                self.assertEqual(
                    self.client.post(
                        "/",
                        json={"input": "Hi."},
                        headers={"Authorization": "Bearer wrong"},
                    ).status_code,
                    401,
                )
                response = self.client.post(
                    "/",
                    json={"input": "Hi."},
                    headers={"Authorization": "Bearer shared-secret"},
                )
        self.assertEqual(response.status_code, 200)

    def test_no_auth_when_unset(self):
        response = self._post({"input": "Hi."})
        self.assertEqual(response.status_code, 200)

    def test_missing_input_is_422(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            response = self.client.post("/", json={})
        self.assertEqual(response.status_code, 422)

    def test_model_env_override(self):
        with mock.patch.dict(
            os.environ, {"GEMINI_API_KEY": "test-key", "MODEL": "gemini-3.5-flash"}
        ):
            os.environ.pop("GUARD_AUTH", None)
            with mock.patch.object(
                guard_main, "_call_gemini", _fake_call("Here is an analysis.")
            ):
                response = self.client.post("/", json={"input": "Hi."})
        self.assertEqual(response.json()["model"], "gemini-3.5-flash")

    def test_provider_failure_is_502(self):
        async def _failing(model, key, system, user_text):
            raise guard_main.HTTPException(
                status_code=502, detail="provider call timed out"
            )

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            os.environ.pop("GUARD_AUTH", None)
            with mock.patch.object(guard_main, "_call_gemini", _failing):
                response = self.client.post("/", json={"input": "Hi."})
        self.assertEqual(response.status_code, 502)

    def test_system_instruction_defaults_to_lab_instruction(self):
        seen = {}

        async def _capture(model, key, system, user_text):
            seen["system"] = system
            return "Here is an analysis.", "STOP", None

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            os.environ.pop("GUARD_AUTH", None)
            with mock.patch.object(guard_main, "_call_gemini", _capture):
                response = self.client.post("/", json={"input": "Hi."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen["system"], guard_main.TRUSTED_SYSTEM_INSTRUCTION)

    def test_probe_system_is_used_when_present(self):
        seen = {}

        async def _capture(model, key, system, user_text):
            seen["system"] = system
            return "Here is an analysis.", "STOP", None

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            os.environ.pop("GUARD_AUTH", None)
            with mock.patch.object(guard_main, "_call_gemini", _capture):
                response = self.client.post(
                    "/", json={"input": "Hi.", "system": "Custom instruction."}
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen["system"], "Custom instruction.")


if __name__ == "__main__":
    unittest.main()
