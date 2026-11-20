"""Tests for server/main.py (FastAPI wrapper around omjb.async_harness).

Uses a local loopback stub guard server; no external network. The whole
module is skipped when FastAPI/httpx are not installed.
"""

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import httpx
    from fastapi.testclient import TestClient

    from server.main import app

    _DEPS = True
except ImportError:  # pragma: no cover - optional dependency
    _DEPS = False


class _GuardHandler(BaseHTTPRequestHandler):
    """Stub guard endpoint: decision by probe id, echoes the auth header."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        probe_id = payload.get("input", "")
        if "bad-shape" in probe_id:
            body = {"unexpected": True}
        elif "block" in probe_id:
            body = {"decision": "block"}
        elif "review" in probe_id:
            body = {"decision": "review"}
        else:
            body = {"decision": "allow"}
        body["seen_auth"] = self.headers.get("Authorization")
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # keep test output quiet
        pass


@unittest.skipUnless(_DEPS, "fastapi/httpx not installed")
class ServerTest(unittest.TestCase):
    # httpx parses proxy env vars when AsyncGuardrailHarness builds its
    # client; bracketed IPv6 entries in no_proxy (e.g. "[::1]", as set by
    # some sandboxes) crash that parse. The server never needs a proxy for
    # its loopback stub, so the tests run with proxy env scrubbed.
    _PROXY_VARS = (
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    )

    @classmethod
    def setUpClass(cls):
        cls._saved_proxy_env = {
            k: os.environ.pop(k) for k in cls._PROXY_VARS if k in os.environ
        }
        cls.guard = ThreadingHTTPServer(("127.0.0.1", 0), _GuardHandler)
        cls.port = cls.guard.server_address[1]
        cls.thread = threading.Thread(target=cls.guard.serve_forever, daemon=True)
        cls.thread.start()
        cls.endpoint = f"http://127.0.0.1:{cls.port}/evaluate"
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.guard.shutdown()
        cls.guard.server_close()
        os.environ.update(cls._saved_proxy_env)

    def setUp(self):
        os.environ.pop("OMJB_GUARD_ENDPOINT", None)
        os.environ.pop("OMJB_GUARD_AUTH", None)

    def tearDown(self):
        os.environ.pop("OMJB_GUARD_ENDPOINT", None)
        os.environ.pop("OMJB_GUARD_AUTH", None)

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_evaluate_happy_path(self):
        r = self.client.post(
            "/evaluate",
            json={
                "endpoint": self.endpoint,
                "probes": [
                    {"id": "p-allow", "prompt": "hello"},
                    {"id": "p-block", "prompt": "block me"},
                    {"id": "p-review", "prompt": "review me"},
                ],
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["allowed"], 1)
        self.assertEqual(body["blocked"], 1)
        self.assertEqual(body["review"], 1)
        self.assertEqual(body["errors"], 0)
        self.assertEqual(body["scored"], 3)
        self.assertAlmostEqual(body["allow_rate"], 1 / 3)
        decisions = {x["probe_id"]: x["decision"] for x in body["results"]}
        self.assertEqual(decisions, {"p-allow": "allow", "p-block": "block", "p-review": "review"})

    def test_evaluate_guard_error_shape(self):
        r = self.client.post(
            "/evaluate",
            json={"endpoint": self.endpoint, "probes": [{"id": "p1", "prompt": "bad-shape test"}]},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["errors"], 1)
        self.assertEqual(body["results"][0]["decision"], "error")
        self.assertIn("ValueError", body["results"][0]["error"])

    def test_evaluate_rejects_empty_probes(self):
        r = self.client.post("/evaluate", json={"endpoint": self.endpoint, "probes": []})
        self.assertEqual(r.status_code, 422)

    def test_evaluate_rejects_duplicate_ids(self):
        r = self.client.post(
            "/evaluate",
            json={
                "endpoint": self.endpoint,
                "probes": [
                    {"id": "dup", "prompt": "one"},
                    {"id": "dup", "prompt": "two"},
                ],
            },
        )
        self.assertEqual(r.status_code, 422)

    def test_evaluate_rejects_non_https_endpoint(self):
        r = self.client.post(
            "/evaluate",
            json={"endpoint": "http://example.com/evaluate", "probes": [{"id": "p1", "prompt": "x"}]},
        )
        self.assertEqual(r.status_code, 400)

    def test_evaluate_requires_endpoint_when_unpinned(self):
        r = self.client.post("/evaluate", json={"probes": [{"id": "p1", "prompt": "x"}]})
        self.assertEqual(r.status_code, 400)

    def test_endpoint_pin_used_when_body_omits_it(self):
        os.environ["OMJB_GUARD_ENDPOINT"] = self.endpoint
        r = self.client.post("/evaluate", json={"probes": [{"id": "p1", "prompt": "hello"}]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["endpoint"], self.endpoint)

    def test_endpoint_pin_rejects_override(self):
        os.environ["OMJB_GUARD_ENDPOINT"] = self.endpoint
        r = self.client.post(
            "/evaluate",
            json={"endpoint": "https://other.example.com/evaluate", "probes": [{"id": "p1", "prompt": "x"}]},
        )
        self.assertEqual(r.status_code, 400)

    def test_env_auth_applied_and_body_auth_ignored(self):
        os.environ["OMJB_GUARD_AUTH"] = "Bearer server-secret"
        r = self.client.post(
            "/evaluate",
            json={
                "endpoint": self.endpoint,
                "probes": [{"id": "p1", "prompt": "hello"}],
                "headers": {"Authorization": "Bearer body-secret"},
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        seen = r.json()["results"][0]["response"]["seen_auth"]
        self.assertEqual(seen, "Bearer server-secret")


if __name__ == "__main__":
    unittest.main()
