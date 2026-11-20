# openmind-omjb-server

FastAPI backend for the OpenMind neon dashboard (React/Vite static site).
The dashboard calls `POST /api/campaigns` and reads `id` and `status`
from the JSON response. This service runs the repo's async evaluation
harness server-side — the browser cannot run it (it needs httpx plus an
operator-owned guard endpoint) — and returns the harness report as JSON.

## Endpoint

- `GET /health` → `{"status": "ok", ...}` (Render health check).
- `POST /api/campaigns` — body:
  ```json
  {
    "providers": ["gemini"],
    "suite": "guardrail-lab",
    "max_requests": 20,
    "workers": 2,
    "timeout_seconds": 45
  }
  ```
  Suites: `guardrail-lab` (76 reviewed cases), `benchmark-v0.8`
  (81 benchmark rows), `benign-controls` (37 benign benchmark rows).
  Providers: `openai`, `anthropic`, `gemini`, `ollama`, `deepseek`,
  `groq`, `together`, `custom`. Limits: `max_requests` 1–500,
  `workers` 1–8, `timeout_seconds` 5–180.

  Response: `{"id": "run-…", "status": "completed", "suite": …,
  "providers": …, "endpoint": …, "total": …, "allowed": …, "blocked": …,
  "review": …, "errors": …, "scored": …, "allow_rate": …, "results": […]}`.
  Each result carries `probe_id`, `category`, `decision`
  (`allow` / `block` / `review` / `error`), `latency_ms`, and the guard's
  response or an error string.

## How a campaign runs

The suite's reviewed probes are loaded from the repo in suite order and
capped to `max_requests` (taking the first N keeps GL-009 immediately
before GL-010 whenever GL-010 is included). They are submitted to the
operator-owned guard endpoint through `omjb.async_harness`. The guard
endpoint fronts the named providers; this route does not call provider
APIs directly and needs no provider API keys.

CORS is enabled for the dashboard's origin (default `*`, no
credentials). Tighten it with `OMJB_CORS_ORIGINS` (comma-separated
origins) before exposing this publicly.

## Credentials — environment variables only

No key is hardcoded, committed, or logged. Set these in the Render
dashboard (or your shell for local runs); the service deploys with
neither set.

- `OMJB_GUARD_ENDPOINT` — **required** for `/api/campaigns`. The
  dashboard's request body carries no endpoint field, so the guard URL
  must be pinned here. Without it the route returns 400.
- `OMJB_GUARD_AUTH` — full `Authorization` header value for the guard
  endpoint, applied server-side. Optional.
- `OMJB_CORS_ORIGINS` — comma-separated allowed origins (default `*`).

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
Environment tab. Then point the dashboard at it: set `VITE_API_BASE_URL`
to the service URL in the dashboard's hosting settings (Vercel project
settings or Render static site env vars).

Free-tier limit: Render free services sleep after 15 minutes idle and
take about a minute to wake on the next request.

## Tests

```bash
python -m unittest discover -s tests -p 'test_server.py' -v
```

Tests use a local loopback stub guard server; no external network.
Skipped automatically when FastAPI/httpx are not installed.
