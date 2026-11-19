"""Run validated probes through guardrails and optional model providers."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

from .async_harness import AsyncGuardrailHarness, EndpointReport
from .mutations import MutationEngine
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
    mutation_cases: list[dict[str, Any]] | None = None

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
            "mutation_cases": self.mutation_cases or [],
        }


class ProviderEvaluationPipeline:
    """Evaluation pipeline with opt-in benign mutation robustness testing."""

    def __init__(self, registry: ProviderRegistry):
        self.registry = registry

    async def run(self, probes: list[Probe], *, endpoint: str,
                  provider_name: str | None = None, model: str | None = None,
                  headers: dict[str, str] | None = None,
                  concurrency: int = 4, max_tokens: int = 256,
                  mutation_profile: str | None = None,
                  max_mutations_per_probe: int = 16) -> EvaluationResult:
        if mutation_profile not in (None, "robustness"):
            raise ValueError("mutation_profile must be None or 'robustness'")
        evaluated = list(probes)
        mutation_cases: list[dict[str, Any]] = []
        if mutation_profile == "robustness":
            engine = MutationEngine(max_variants=max_mutations_per_probe)
            for probe in probes:
                for case in engine.generate(probe):
                    mutation_cases.append(case.to_dict())
                    evaluated.append(Probe(
                        id=case.id, category=case.category, prompt=case.prompt,
                        expected=case.expected, system=probe.system,
                        meta={**probe.meta, **case.meta, "parent_probe_id": probe.id,
                              "mutation_names": case.mutation_names,
                              "mutation_families": case.families},
                        provenance_record=probe.provenance_record,
                    ))

        harness = AsyncGuardrailHarness(endpoint, headers=headers, concurrency=concurrency)
        guard_report = await harness.run(evaluated)
        provider_results: list[ProviderResult] = []
        if provider_name and model:
            provider = self.registry.get(provider_name)
            allowed_ids = {row.probe_id for row in guard_report.results
                           if row.decision == "allow"}
            # Only explicitly human-reviewed benign probes may be forwarded to a model API.\n            selected = [probe for probe in evaluated\n                        if probe.id in allowed_ids and probe.expected == "comply"\n                        and probe.meta.get("mutation_safe") is True]
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
        return EvaluationResult(guard_report, provider_results,
                                self.registry.quota.summary(), mutation_cases)
