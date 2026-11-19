# Reproducible mutation robustness engine

This implementation adapts the supplied typed pipeline design for reviewed benign
robustness probes. It includes transform I/O kinds, deterministic per-candidate
RNG, canonical spec hashing, trace-based replay, deduplication, candidate/USD/time
budgets plus a build-attempt ceiling, cost-aware UCB sampling, JSONL tracing,
transform version records, and a decorator-based extension registry.

## Safety gate

Construct Engine with approved_benign=True only after human review confirms the
target is benign. The built-in transforms have semantic_delta=0 and are limited
to formatting, Unicode normalization, and representation encoding. The engine
does not ship authority overrides, safeguard evasion, concealed instructions,
homoglyph/zero-width filter attacks, instruction splitting, or decode-and-execute
operators. Adaptive reward is based on expected handling of benign robustness
cases, not harmful bypass yield.

## Spec and API

Load a JSON-compatible dict with load_spec. Each stage declares arms and may be
optional. A transform can consume only its declared input kind; incompatible
required stages are skipped with a trace reason. Budget defaults are bounded;
max_build_attempts prevents endless loops when all candidates are skipped.

Use Engine(spec, benign_text, submit, approved_benign=True, trace_path="trace.jsonl").
The submit callback returns Verdict. The report contains submitted/allowed/blocked/
error/skipped counts and per-arm scheduler statistics.

Every candidate trace records the spec hash, seed, candidate index, selected
arms and transform versions, plus a SHA-256 output fingerprint. rebuild() uses
the recorded arm sequence and deterministic RNG to reproduce the payload. It
fails if a transform version has changed.

Extensions register through @transform(...) or a dedicated Registry instance.
Third-party transforms must declare input/output kinds, cost, semantic delta,
tags, and version. The engine rejects transforms with nonzero semantic_delta.

For a positive USD budget, Engine requires an estimate_cost callback. It must
return a conservative upper-bound estimate for each candidate before submission.
Candidates whose reservation would exceed the remaining budget are not sent.
The engine reconciles the reported actual cost against the reservation.

## CLI

Install the optional HTTP client and run against a guardrail endpoint you operate:

    pip install -e ".[api]"
    export OMJB_GUARDRAIL_TOKEN="..."
    omjb-mutate --spec configs/mutation-robustness.example.json \
      --corpus reviewed-benign-probes.jsonl --probe-id benign-001 \
      --endpoint https://guardrail.example/evaluate \
      --estimated-request-cost 0.001 --trace mutation-trace.jsonl

The corpus record must have expected=comply and meta.mutation_safe=true.
The CLI selects exactly one probe by ID and reads its bearer token from the
named environment variable; it never writes credentials into the trace.
For non-billable endpoints, the request-cost estimate may be zero. For a
billable endpoint, supply a conservative per-request upper bound.
