"""FastAPI backend for the OpenMind neon dashboard.

The dashboard (React/Vite, static site) calls POST /api/campaigns with
``{providers, suite, max_requests, workers, timeout_seconds}`` and reads
``id`` and ``status`` from the JSON response. This service runs the repo's
async evaluation harness server-side — the browser cannot run it (it needs
httpx plus an operator-owned guard endpoint) — and returns the harness
report as JSON.

How a campaign runs: the named suite's reviewed probes are loaded from
the repo (Guardrail Lab cases via ``omjb.guardrail_adapter``; benchmark
rows from ``data/benchmark_v0.8.0.jsonl``), capped to ``max_requests`` in
suite order, and submitted to the operator-owned guard endpoint
(``OMJB_GUARD_ENDPOINT``) through ``omjb.async_harness``. The guard
endpoint fronts the named providers; this route does not call provider
APIs directly and needs no provider API keys.

Provider/guard credentials never live here: the guard endpoint URL and
its auth header come from environment variables only (see server/README.md).
No key is hardcoded, logged, or echoed in any response.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from omjb.async_harness import AsyncGuardrailHarness
from omjb.probes import Probe
from omjb.provenance import ProvenanceRecord

SERVICE_VERSION = "0.2.0"
REPO_ROOT = Path(__file__).resolve().parent.parent

KNOWN_PROVIDERS = {"openai", "anthropic", "gemini", "ollama", "deepseek", "groq", "together", "custom"}
SUITES = ("guardrail-lab", "benchmark-v0.8", "benign-controls")

app = FastAPI(title="openmind-omjb-server", version=SERVICE_VERSION)


def _cors_origins() -> list[str]:
    raw = os.environ.get("OMJB_CORS_ORIGINS", "*").strip()
    if raw in ("", "*"):
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


# The dashboard is a static site on another origin and sends no
# credentials, so cross-origin POSTs are allowed by default. Tighten with
# OMJB_CORS_ORIGINS before exposing this publicly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


class CampaignIn(BaseModel):
    providers: list[str] = Field(min_length=1, max_length=8)
    suite: str
    max_requests: int = Field(default=20, ge=1, le=500)
    workers: int = Field(default=2, ge=1, le=8)
    timeout_seconds: float = Field(default=45.0, ge=5.0, le=180.0)


def _load_suite_probes(suite: str) -> list[Probe]:
    """Load a suite's reviewed probes in suite order.

    Capping to max_requests takes the first N in this order, which keeps
    GL-009 immediately before GL-010 whenever GL-010 is included.
    """
    if suite == "guardrail-lab":
        from omjb.guardrail_adapter import load_guardrail_lab_cases

        return load_guardrail_lab_cases()
    path = REPO_ROOT / "data" / "benchmark_v0.8.0.jsonl"
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if suite == "benign-controls":
        rows = [r for r in rows if r.get("split") == "benign"]
    elif suite != "benchmark-v0.8":
        raise ValueError(f"unknown suite: {suite!r}")
    probes = []
    for row in rows:
        meta = {
            "suite": "benchmark-v0.8.0",
            "split": row.get("split"),
            "family": row.get("family"),
            "expected_behavior": row.get("expected_behavior"),
            "synthetic_secret": row.get("synthetic_secret"),
            "risk_level": row.get("risk_level"),
        }
        prov = ProvenanceRecord(
            source="benchmark-v0.8.0",
            revision="v0.8.0",
            upstream_uri="repository:data/benchmark_v0.8.0.jsonl",
            license="",
        )
        probes.append(
            Probe(
                id=row["id"],
                category=str(row.get("family", "benchmark")),
                prompt=row["user_prompt"],
                expected="either",
                system=None,
                meta=meta,
                provenance_record=prov,
            )
        )
    return probes


def _guard_endpoint() -> str:
    """The guard endpoint comes from the server env var only.

    The dashboard's request body carries no endpoint field, so the pin is
    required for /api/campaigns (unlike the old /evaluate route, which
    accepted one per request).
    """
    endpoint = os.environ.get("OMJB_GUARD_ENDPOINT", "").strip()
    if not endpoint:
        raise HTTPException(
            status_code=400,
            detail="guard endpoint is not configured on this server "
            "(set OMJB_GUARD_ENDPOINT in the Render dashboard)",
        )
    return endpoint


def _guard_headers() -> dict[str, str]:
    """Guard auth comes from the server env var, never the request body."""
    auth = os.environ.get("OMJB_GUARD_AUTH", "").strip()
    return {"Authorization": auth} if auth else {}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "openmind-omjb-server", "version": SERVICE_VERSION}


@app.post("/api/campaigns")
async def create_campaign(body: CampaignIn) -> dict:
    unknown = sorted(set(body.providers) - KNOWN_PROVIDERS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown providers: {', '.join(unknown)}")
    if body.suite not in SUITES:
        raise HTTPException(status_code=422, detail=f"unknown suite: {body.suite!r}")
    endpoint = _guard_endpoint()
    try:
        probes = _load_suite_probes(body.suite)[: body.max_requests]
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=500, detail=f"could not load suite {body.suite!r}: {exc}") from exc
    try:
        harness = AsyncGuardrailHarness(
            endpoint,
            headers=_guard_headers(),
            timeout=body.timeout_seconds,
            concurrency=body.workers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    report = await harness.run(probes)
    out = asdict(report)
    out.update(
        {
            "id": f"run-{uuid.uuid4().hex[:12]}",
            "status": "completed",
            "suite": body.suite,
            "providers": body.providers,
            "max_requests": body.max_requests,
            "scored": report.scored,
            "allow_rate": report.allow_rate,
        }
    )
    return out
