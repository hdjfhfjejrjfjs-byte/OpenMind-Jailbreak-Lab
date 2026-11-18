"""Hostile-endpoint key-scrubbing tests.

A misconfigured or hostile endpoint can echo the Authorization or
x-goog-api-key header back inside its error body. Error details flow into
local evidence reports, so the adapters must scrub echoed key material
before raising.

Research-purposes-only: all probes use fake keys and fake endpoints.
"""
import json
import unittest
import urllib.error
from unittest.mock import patch

from modules.ai_scanner.providers import ProviderError, call_provider_messages
from modules.guardrail_lab.openai_compatible import call_openai_compatible
from modules.guardrail_lab.runner import GuardrailRunError


class FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, code, body):
        super().__init__("fake", code, "error", None, None)
        self._body = body.encode("utf-8")

    def read(self):
        return self._body


def _raise(exc):
    def side_effect(*args, **kwargs):
        raise exc
    return side_effect


class ErrorDetailScrubbingTests(unittest.TestCase):
    def test_guardrail_openai_compatible_scrubs_echoed_bearer_key(self):
        key = "sk-test-abcdef1234567890"
        body = json.dumps({"error": {"message": f"Unauthorized: {key}"}})
        with patch.dict("os.environ", {"OM_TEST_KEY": key}):
            with patch("urllib.request.urlopen",
                       side_effect=_raise(FakeHTTPError(401, body))):
                with self.assertRaises(GuardrailRunError) as caught:
                    call_openai_compatible(
                        [{"role": "user", "content": "test"}],
                        model="m", base_url="https://host.example/v1",
                        api_key_env="OM_TEST_KEY",
                    )
        message = str(caught.exception)
        self.assertNotIn(key, message)
        self.assertIn("***", message)

    def test_guardrail_openai_compatible_scrubs_echoed_key_on_5xx(self):
        key = "sk-test-9876543210fedcba"
        body = f"server error while authenticating {key} downstream"
        with patch.dict("os.environ", {"OM_TEST_KEY": key}):
            with patch("urllib.request.urlopen",
                       side_effect=_raise(FakeHTTPError(500, body))):
                with self.assertRaises(GuardrailRunError) as caught:
                    call_openai_compatible(
                        [{"role": "user", "content": "test"}],
                        model="m", base_url="https://host.example/v1",
                        api_key_env="OM_TEST_KEY",
                    )
        self.assertNotIn(key, str(caught.exception))

    def test_scanner_compatible_scrubs_echoed_bearer_key(self):
        key = "sk-test-1111222233334444"
        body = json.dumps({"error": f"bad key {key}"})
        with patch.dict("os.environ", {"OM_TEST_KEY": key}):
            with patch("urllib.request.urlopen",
                       side_effect=_raise(FakeHTTPError(403, body))):
                with self.assertRaises(ProviderError) as caught:
                    call_provider_messages(
                        "openai-compatible",
                        [{"role": "user", "content": "test"}],
                        model="m", base_url="https://host.example/v1",
                        api_key_env="OM_TEST_KEY",
                    )
        message = str(caught.exception)
        self.assertNotIn(key, message)
        self.assertIn("***", message)

    def test_scanner_gemini_header_key_is_scrubbed(self):
        key = "AIza-test-5555666677778888"
        body = json.dumps({"error": {"message": f"API key {key} not valid"}})
        with patch.dict("os.environ", {"GEMINI_API_KEY": key}):
            with patch("urllib.request.urlopen",
                       side_effect=_raise(FakeHTTPError(400, body))):
                with self.assertRaises(ProviderError) as caught:
                    call_provider_messages(
                        "gemini",
                        [{"role": "user", "content": "test"}],
                    )
        message = str(caught.exception)
        self.assertNotIn(key, message)

    def test_scanner_openai_header_key_is_scrubbed(self):
        key = "sk-test-openai-99990000"
        body = json.dumps({"error": {"message": f"key {key} expired"}})
        with patch.dict("os.environ", {"OPENAI_API_KEY": key}):
            with patch("urllib.request.urlopen",
                       side_effect=_raise(FakeHTTPError(401, body))):
                with self.assertRaises(ProviderError) as caught:
                    call_provider_messages(
                        "openai",
                        [{"role": "user", "content": "test"}],
                    )
        self.assertNotIn(key, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
