"""Tests for server/main.py (FastAPI backend for the neon dashboard).

Covers POST /api/campaigns against a local loopback stub guard server;
no external network. The whole module is skipped when FastAPI/httpx are
not installed.
"""

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import httpx
    from fastapi.testclient import TestClient

    from server.main import _load_suite_probes, app

    _DEPS = True
except ImportError:  # pragma: no cover - optional dependency
    _DEPS = False


class _GuardHandler(BaseHTTPRequestHandler):
    """Stub guard endpoint: decision by probe prompt, echoes the auth header."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        text = payload.get("input", "")
        if "bad-shape" in text:
            body = {"unexpected": True}
        elif "block" in text:
            body = {"decision": "block"}
        elif "review" in text:
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


def _campaign(**overrides):
    body = {
        "providers": ["gemini"],
        "suite": "guardrail-lab",
        "max_requests": 3,
        "workers": 2,
        "timeout_seconds": 15,
    }
    body.update(overrides)
    return body


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
        os.environ.pop("OMJB_CORS_ORIGINS", None)

    def tearDown(self):
        os.environ.pop("OMJB_GUARD_ENDPOINT", None)
        os.environ.pop("OMJB_GUARD_AUTH", None)
        os.environ.pop("OMJB_CORS_ORIGINS", None)

    def _with_guard(self):
        os.environ["OMJB_GUARD_ENDPOINT"] = self.endpoint

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_suite_loader_counts(self):
        self.assertEqual(len(_load_suite_probes("guardrail-lab")), 76)
        self.assertEqual(len(_load_suite_probes("benchmark-v0.8")), 81)
        benign = _load_suite_probes("benign-controls")
        self.assertEqual(len(benign), 37)
        self.assertTrue(all(p.meta["split"] == "benign" for p in benign))

    def test_campaign_guardrail_lab(self):
        self._with_guard()
        r = self.client.post("/api/campaigns", json=_campaign())
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["id"].startswith("run-"))
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["suite"], "guardrail-lab")
        self.assertEqual(body["providers"], ["gemini"])
        self.assertEqual(body["endpoint"], self.endpoint)
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["allowed"] + body["blocked"] + body["review"] + body["errors"], 3)
        self.assertEqual(body["scored"], body["total"] - body["errors"])
        self.assertTrue(all(x["decision"] in ("allow", "block", "review", "error") for x in body["results"]))

    def test_campaign_benchmark_suite(self):
        self._with_guard()
        r = self.client.post("/api/campaigns", json=_campaign(suite="benchmark-v0.8", max_requests=2))
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual([x["probe_id"] for x in body["results"]], ["OM-001", "OM-002"])

    def test_campaign_benign_controls(self):
        self._with_guard()
        r = self.client.post("/api/campaigns", json=_campaign(suite="benign-controls", max_requests=5))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["total"], 5)

    def test_campaign_requires_guard_endpoint(self):
        r = self.client.post("/api/campaigns", json=_campaign())
        self.assertEqual(r.status_code, 400)
        self.assertIn("OMJB_GUARD_ENDPOINT", r.json()["detail"])

    def test_campaign_rejects_unknown_provider(self):
        self._with_guard()
        r = self.client.post("/api/campaigns", json=_campaign(providers=["gemini", "nope"]))
        self.assertEqual(r.status_code, 422)

    def test_campaign_rejects_unknown_suite(self):
        self._with_guard()
        r = self.client.post("/api/campaigns", json=_campaign(suite="nope"))
        self.assertEqual(r.status_code, 422)

    def test_campaign_rejects_bad_limits(self):
        self._with_guard()
        for bad in (
            _campaign(max_requests=0),
            _campaign(max_requests=501),
            _campaign(workers=0),
            _campaign(workers=9),
            _campaign(timeout_seconds=1),
            _campaign(timeout_seconds=181),
            _campaign(providers=[]),
        ):
            r = self.client.post("/api/campaigns", json=bad)
            self.assertEqual(r.status_code, 422, bad)

    def test_campaign_auth_applied(self):
        self._with_guard()
        os.environ["OMJB_GUARD_AUTH"] = "Bearer server-secret"
        r = self.client.post("/api/campaigns", json=_campaign(max_requests=1))
        self.assertEqual(r.status_code, 200, r.text)
        seen = r.json()["results"][0]["response"]["seen_auth"]
        self.assertEqual(seen, "Bearer server-secret")

    def test_cors_preflight_allows_dashboard_origin(self):
        r = self.client.options(
            "/api/campaigns",
            headers={
                "Origin": "https://openmind-neon-dashboard.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("access-control-allow-origin"), "*")

    def test_evaluate_route_is_gone(self):
        self._with_guard()
        r = self.client.post(
            "/evaluate",
            json={"endpoint": self.endpoint, "probes": [{"id": "p1", "prompt": "x"}]},
        )
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
