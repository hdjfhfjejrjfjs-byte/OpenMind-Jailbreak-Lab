"""Minimal FastAPI wrapper around the OMJB async guardrail harness.

The browser cannot run ``omjb.async_harness`` (it needs httpx plus an
operator-owned guard endpoint), so this service runs it server-side and
returns the harness report as JSON.

Provider/guard credentials never live here: the guard endpoint URL and its
auth header come from environment variables only (see server/README.md).
No key is hardcoded, logged, or echoed in any response.
"""

from __future__ import annotations

import os
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from omjb.async_harness import AsyncGuardrailHarness
from omjb.probes import Probe

SERVICE_VERSION = "0.1.0"
MAX_PROBES = 200

app = FastAPI(title="openmind-omjb-server", version=SERVICE_VERSION)


class ProbeIn(BaseModel):
    id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    category: str = "uncategorized"
    system: str | None = None


class EvaluateIn(BaseModel):
    endpoint: str | None = None
    probes: list[ProbeIn] = Field(min_length=1, max_length=MAX_PROBES)
    concurrency: int = Field(default=4, ge=1, le=16)
    timeout: float = Field(default=15.0, ge=1.0, le=120.0)
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("probes")
    @classmethod
    def _unique_probe_ids(cls, probes: list[ProbeIn]) -> list[ProbeIn]:
        ids = [p.id for p in probes]
        if len(set(ids)) != len(ids):
            raise ValueError("probe ids must be unique")
        return probes


def _resolve_endpoint(requested: str | None) -> str:
    """Pin the guard endpoint with OMJB_GUARD_ENDPOINT when it is set.

    When the pin is set, a request may omit the endpoint (the pin is used)
    but may not override it. When it is not set, the request must supply one.
    """
    pinned = os.environ.get("OMJB_GUARD_ENDPOINT", "").strip()
    if pinned:
        if requested is not None and requested.strip() != pinned:
            raise HTTPException(
                status_code=400,
                detail="endpoint is pinned by OMJB_GUARD_ENDPOINT on this server",
            )
        return pinned
    if not requested or not requested.strip():
        raise HTTPException(
            status_code=400,
            detail="endpoint is required (or set OMJB_GUARD_ENDPOINT on the server)",
        )
    return requested.strip()


def _resolve_headers(requested: dict[str, str]) -> dict[str, str]:
    """Guard auth comes from the server env var when set, never the request.

    OMJB_GUARD_AUTH holds the full Authorization header value. When it is
    set, any Authorization header in the request body is ignored so
    credentials never travel through the client.
    """
    headers = {k: v for k, v in requested.items() if k.lower() != "authorization"}
    auth = os.environ.get("OMJB_GUARD_AUTH", "").strip()
    if auth:
        headers["Authorization"] = auth
    return headers


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "openmind-omjb-server", "version": SERVICE_VERSION}


@app.post("/evaluate")
async def evaluate(body: EvaluateIn) -> dict:
    endpoint = _resolve_endpoint(body.endpoint)
    headers = _resolve_headers(body.headers)
    probes = [
        Probe(id=p.id, category=p.category, prompt=p.prompt, system=p.system)
        for p in body.probes
    ]
    try:
        harness = AsyncGuardrailHarness(
            endpoint, headers=headers, timeout=body.timeout, concurrency=body.concurrency
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    report = await harness.run(probes)
    out = asdict(report)
    out["scored"] = report.scored
    out["allow_rate"] = report.allow_rate
    return out
