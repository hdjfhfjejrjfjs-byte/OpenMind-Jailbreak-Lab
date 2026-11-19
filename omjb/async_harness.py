"""Async evaluation of validated OMJB probes against an operator-owned guard endpoint.

This module submits original, reviewed probe text without mutation or chaining.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from .probes import Probe


@dataclass
class EndpointResult:
    probe_id: str
    category: str
    decision: str
    latency_ms: float
    response: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class EndpointReport:
    endpoint: str
    total: int
    allowed: int
    blocked: int
    review: int
    errors: int
    results: list[EndpointResult] = field(default_factory=list)

    @property
    def scored(self) -> int:
        return self.allowed + self.blocked + self.review

    @property
    def allow_rate(self) -> float:
        return self.allowed / self.scored if self.scored else 0.0


def parse_decision(data: dict[str, Any]) -> str:
    """Normalize common guard response shapes; fail closed on unknown shapes."""
    if not isinstance(data, dict):
        raise ValueError("guard response must be a JSON object")
    if "decision" in data:
        value = str(data["decision"]).strip().lower()
        mapping = {"allow": "allow", "safe": "allow", "pass": "allow",
                   "block": "block", "blocked": "block", "deny": "block",
                   "review": "review", "flag": "review"}
        if value in mapping:
            return mapping[value]
    if "verdict" in data:
        value = str(data["verdict"]).strip().lower()
        mapping = {"allow": "allow", "safe": "allow", "pass": "allow",
                   "block": "block", "blocked": "block", "deny": "block",
                   "review": "review", "flag": "review"}
        if value in mapping:
            return mapping[value]
    if "safe" in data and isinstance(data["safe"], bool):
        return "allow" if data["safe"] else "block"
    if "flagged" in data and isinstance(data["flagged"], bool):
        return "review" if data["flagged"] else "allow"
    raise ValueError("unrecognized guard response; expected decision, verdict, safe, or flagged")


class AsyncGuardrailHarness:
    def __init__(self, endpoint: str, *, headers: dict[str, str] | None = None,
                 timeout: float = 15.0, concurrency: int = 4):
        parsed = urlparse(endpoint)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in local_hosts):
            raise ValueError("endpoint must use HTTPS (HTTP is allowed only for loopback)")
        if not parsed.hostname:
            raise ValueError("endpoint must include a hostname")
        if timeout <= 0 or concurrency < 1:
            raise ValueError("timeout and concurrency must be positive")
        self.endpoint = endpoint
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.concurrency = concurrency

    async def _one(self, client: httpx.AsyncClient, semaphore: asyncio.Semaphore,
                   probe: Probe) -> EndpointResult:
        async with semaphore:
            started = time.perf_counter()
            try:
                payload = {"input": probe.prompt}
                if probe.system is not None:
                    payload["system"] = probe.system
                response = await client.post(self.endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
                decision = parse_decision(data)
                return EndpointResult(probe.id, probe.category, decision,
                                      (time.perf_counter() - started) * 1000, data)
            except Exception as exc:
                return EndpointResult(probe.id, probe.category, "error",
                                      (time.perf_counter() - started) * 1000,
                                      error=f"{type(exc).__name__}: {exc}")

    async def run(self, probes: list[Probe]) -> EndpointReport:
        semaphore = asyncio.Semaphore(self.concurrency)
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            results = await asyncio.gather(
                *(self._one(client, semaphore, probe) for probe in probes)
            )
        counts = {name: sum(r.decision == name for r in results)
                  for name in ("allow", "block", "review", "error")}
        return EndpointReport(self.endpoint, len(results), counts["allow"],
                              counts["block"], counts["review"], counts["error"],
                              results)
