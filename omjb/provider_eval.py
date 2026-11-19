"""Run validated corpus probes through an endpoint and optionally a model provider."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

from .async_harness import AsyncGuardrailHarness, EndpointReport
from .probes import Probe
from .providers import ProviderRegistry


@dataclass
class ProviderResult:
    probe_id: str
    provider: str
    model: str
    response: str | None
    input_tokens: int
    output_tokens: int
    error: str | None = None


@dataclass
class EvaluationResult:
    guardrail: EndpointReport
    provider_results: list[ProviderResult]
    quota: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "guardrail": {
                "endpoint": self.guardrail.endpoint,
                "total": self.guardrail.total,
                "allowed": self.guardrail.allowed,
                "blocked": self.guardrail.blocked,
                "review": self.guardrail.review,
                "errors": self.guardrail.errors,
                "allow_rate": self.guardrail.allow_rate,
                "results": [asdict(item) for item in self.guardrail.results],
            },
            "provider_results": [asdict(item) for item in self.provider_results],
            "quota": self.quota,
        }


class ProviderEvaluationPipeline:
    """Evaluates only original probes; it does not mutate or chain prompt text."""

    def __init__(self, registry: ProviderRegistry):
        self.registry = registry

    async def run(self, probes: list[Probe], *, endpoint: str,
                  provider_name: str | None = None, model: str | None = None,
                  headers: dict[str, str] | None = None,
                  concurrency: int = 4, max_tokens: int = 256) -> EvaluationResult:
        harness = AsyncGuardrailHarness(endpoint, headers=headers, concurrency=concurrency)
        guard_report = await harness.run(probes)
        provider_results: list[ProviderResult] = []
        if provider_name and model:
            provider = self.registry.get(provider_name)
            allowed_ids = {row.probe_id for row in guard_report.results
                           if row.decision == "allow"}
            selected = [probe for probe in probes if probe.id in allowed_ids]
            semaphore = asyncio.Semaphore(concurrency)

            async def inspect(probe: Probe) -> ProviderResult:
                async with semaphore:
                    try:
                        completion = await provider.complete(
                            model, [{"role": "user", "content": probe.prompt}],
                            max_tokens=max_tokens,
                        )
                        return ProviderResult(probe.id, provider_name, model,
                                              completion.text, completion.input_tokens,
                                              completion.output_tokens)
                    except Exception as exc:
                        return ProviderResult(probe.id, provider_name, model, None,
                                              0, 0, f"{type(exc).__name__}: {exc}")

            provider_results = await asyncio.gather(*(inspect(p) for p in selected))
        return EvaluationResult(guard_report, provider_results, self.registry.quota.summary())
