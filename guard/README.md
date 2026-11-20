# openmind-guard — model-backed guard endpoint

The guard service the live backend (`server/main.py`, `POST /api/campaigns`)
forwards dashboard campaign probes to. It is the `OMJB_GUARD_ENDPOINT`
the backend requires: without it, `/api/campaigns` answers 400.

## Contract

The harness (`omjb/async_harness.py`) POSTs JSON to the endpoint URL:

```json
{"input": "<probe prompt>", "system": "<probe system instruction, when set>"}
```

and expects a JSON object with a `decision` (or `verdict`) in
`allow` / `block` / `review`, or a boolean `safe` / `flagged`. Unknown
shapes fail closed on the harness side. This service always answers:

```json
{"decision": "allow", "response": "<model text>", "model": "gemini-3.5-flash-lite"}
```

Routes:

- `GET /health` → `{"status": "ok", "service": "openmind-guard", "version": "0.1.0"}`
- `POST /` and `POST /guard` (alias) → the guard decision. The backend
  sets `OMJB_GUARD_ENDPOINT` to the full service URL, so root must work.

## Decision rule

The input is sent to Gemini as the user message, under the probe's
`system` instruction when present, otherwise under the lab's own system
instruction (`modules/guardrail_lab/runner.py::TRUSTED_SYSTEM_INSTRUCTION`
— the exact instruction Guardrail Lab campaigns run under).

- A clear refusal (`I can't` / `I cannot help` style) → `block`.
- Anything else → `allow`.
- A provider-side prompt block, or an empty reply with finish reason
  `SAFETY` → `block`.

The harness only sends prompt text, not the canary, so the guard cannot
check for markers — refusal vs answer is the honest signal here.
Canary-leak detection stays in the benchmark evaluator, not this route.

## Environment

| Variable | Required | Notes |
| --- | --- | --- |
| `GEMINI_API_KEY` | yes | Gemini API key. Without it, POST answers **503** "provider key not configured" — the guard never fakes a decision. |
| `MODEL` | no | Gemini model, default `gemini-3.5-flash-lite`. |
| `GUARD_AUTH` | no | If set, the `Authorization` header must equal it exactly (the backend sends its `OMJB_GUARD_AUTH` value as that header). If unset, requests are accepted unauthenticated. |

No key is hardcoded, logged, or echoed anywhere. Each model call is
bounded to 30s so the backend's per-probe timeout is respected.

## Run locally

```bash
pip install -r guard/requirements.txt
GEMINI_API_KEY=<key> uvicorn guard.main:app --host 0.0.0.0 --port 8000
```

## Deploy (Render, free web service)

Direct service creation from the repo (the Blueprint route rejects this
repo because it is not a connected GitHub repo for the Render workspace):

- Build command: `pip install -r guard/requirements.txt`
- Start command: `uvicorn guard.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`
- Set `GEMINI_API_KEY` in the service's Environment tab after creating it.

Then wire the backend: set `OMJB_GUARD_ENDPOINT` to the guard's URL on
the `openmind-omjb-server` service (the backend redeploys on the env
change). Leave `OMJB_GUARD_AUTH` unset unless `GUARD_AUTH` is set here.
