# Mutation robustness evaluation

The mutation engine is an opt-in extension for benign robustness probes. It
covers encoding/whitespace, Unicode normalization, structural envelopes,
meaning-preserving semantic framings, malformed-but-benign JSON/YAML boundary
inputs, bounded chaining, and a deterministic `NarrativeGraph`.

## Approval gate

A probe is eligible only when both conditions hold:

- `expected == "comply"`
- `meta.mutation_safe == true`, set after review confirms the prompt is benign.

Refusal/attack probes are rejected by the engine. The engine does not generate
policy overrides, false authority claims, hidden harmful payloads, or
safeguard-evasion instructions. Parser cases are malformed data envelopes for
testing parser error handling; they do not ask a model to fail open.

## Python API

```python
from omjb.mutations import MutationEngine, generate, generate_procedural

engine = MutationEngine(max_variants=16, max_chain_depth=2)
cases = engine.generate(reviewed_benign_probe)
procedural = engine.generate_procedural(reviewed_benign_probe)

# Convenience APIs:
cases = generate(reviewed_benign_probe)
procedural = generate_procedural(reviewed_benign_probe)
```

Each `MutationCase` includes its parent probe ID, deterministic ID, transform
names/families, and SHA-256 hashes of input and output. Duplicate outputs are
removed. Generation is capped by `max_variants`.

## Pipeline integration

The existing pipeline remains unchanged by default. Enable benign robustness
cases explicitly:

```python
result = await pipeline.run(
    probes,
    endpoint="https://your-guard.example/evaluate",
    mutation_profile="robustness",
    max_mutations_per_probe=16,
)
```

The report includes generated cases under `mutation_cases`; guardrail and
provider results include both original and generated probe IDs. Providers are
still called only for items the guard endpoint allows.
