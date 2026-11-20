# openmind-omjb-server

Minimal FastAPI wrapper around `omjb.async_harness`, which cannot run in
the browser: it needs httpx plus an operator-owned guard endpoint. This
service runs the harness server-side and returns its report as JSON.

## Endpoints

- `GET /health` → `{"status": "ok", ...}` (Render health check).
- `POST /evaluate` — body:
  ```json
  {
    "endpoint": "https://guard.example.com/evaluate",
    "probes": [{"id": "P-001", "prompt": "...", "category": "uncategorized"}],
    "concurrency": 4,
    "timeout": 15.0,
    "headers": {}
  }
  ```
  Returns the harness `EndpointReport` as JSON (`endpoint`, `total`,
  `allowed`, `blocked`, `review`, `errors`, `scored`, `allow_rate`,
  `results`). At most 200 probes per request; concurrency 1–16;
  timeout 1–120 s. The guard endpoint must be HTTPS (HTTP only for
  loopback), enforced by the harness.

## Credentials — environment variables only

No key is hardcoded, committed, or logged. Set these in the Render
dashboard (or your shell for local runs); the service deploys with
neither set.

- `OMJB_GUARD_ENDPOINT` — pins the guard endpoint. When set, a request
  may omit `endpoint` (the pin is used) but may not override it. When
  unset, `endpoint` is required in the request body.
- `OMJB_GUARD_AUTH` — full `Authorization` header value for the guard
  endpoint, applied server-side. When set, any `Authorization` header in
  the request body is ignored, so credentials never travel through the
  client. Prefer this over per-request headers.

## Run locally

```bash
pip install -r server/requirements.txt
OMJB_GUARD_ENDPOINT=https://guard.example.com/evaluate \
OMJB_GUARD_AUTH="Bearer ..." \
uvicorn server.main:app --host 127.0.0.1 --port 8000
```

## Deploy on Render (free tier)

Render dashboard → New → Web Service → Build and deploy from a Git
repository → pick `tjcrims0nx/OpenMind-Jailbreak-Lab` (or use this
repo's `render.yaml` blueprint). Free plan. After deploy, set
`OMJB_GUARD_ENDPOINT` and `OMJB_GUARD_AUTH` in the service's
Environment tab.

Free-tier limit: Render free services sleep after 15 minutes idle and
take about a minute to wake on the next request.

## Tests

```bash
python -m unittest discover -s tests -p 'test_server.py' -v
```

Tests use a local loopback stub guard server; no external network.
Skipped automatically when FastAPI/httpx are not installed.
