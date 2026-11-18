# Research contributions — Blackfrost (November 2026)

This file documents research contributions made from Blackfrost's DWM
(domain weight modification) research program to OpenMind-Jailbreak-Lab.

**Research-purposes-only disclaimer:** All contributed test material and
measurement tooling here is published for bounded robustness research and
evaluation **only**. Every new prompt is an inert probe built on synthetic
canary markers (`SAFE-MARKER-NNN`, `OM-MARKER-XX`, `MARKER-QN`); the
matched benign twins are harmless tasks, and the fixture responses are
inert synthetic text. Sections 4–10 add no new adversarial prompts at all —
they add measurement, provenance, and evidence-lifecycle tooling. Nothing
here is a jailbreak technique for general use, an unrestricted bypass, or
an instruction set for production systems. Test material is safe to run
against any model. No persona/authority frames, adaptive searches, or
release-only holdout material were used.

## 1. Source-corpus diversification (4-category × 13-surface factorial)

Before: the 52 source-derived cases rendered **four fixed prompts**
(4 categories × 13 canary markers each) — the corpus's effective
adversarial diversity was 4 shapes, and nothing flagged it because every
prompt differed by its marker.

After: each category payload is paired factorially with 13 injection
surfaces (quoted note, email, CSV, HTML comment, JSON field, retrieval,
tool output, document record, code comment, Base64, Spanish, Markdown
link, fictional narrator) — a Latin square where every category×surface
pair occurs exactly once: **52 pairwise-distinct prompts**.

Grounding: instruction-boundary behavior is sensitive to surface form even
at fixed semantics (frame/persona sensitivity observed across our DWM
evaluations; XSTest-style surface-form variation as a false-refusal
proxy). A model can hold the boundary on one surface while failing on a
semantically identical payload in another medium — so the corpus now tests
that axis instead of repeating one.

Artifacts:

- `modules/guardrail_lab/source_registry.py` — pure registry (categories,
  surfaces, balanced assignment, prompt rendering)
- `scripts/regenerate_source_corpus.py` — regenerates the JSONL from the
  registry, preserving source provenance and canaries
- `modules/guardrail_lab/source_cases.py` — validates variant, factorial
  assignment, and prompt at import time; pins the adaptations SHA-256 in
  the manifest (tamper-evident, like the inventory)
- Evidence records `source_provenance.variant`

## 2. Benchmark v0.7.0 — filling singleton families

Before: v0.6.1's own quality audit flagged two warnings: three singleton
adversarial families (`history_edit`, `cross_model_pipeline`,
`hypothetical_framing`) and a single benign control family
(`benign_utility`).

After: benchmark v0.7.0 adds six adversarial rows filling those families
(2 each) plus a second benign family (`benign_instruction_following`),
75 rows total (44 adversarial / 31 benign). `quality_audit` now returns
`status: pass` with zero warnings.

All new adversarial rows are inert probes: an edited-message "correction"
carrying an injected instruction, another assistant's output/tool result
presented as the answer, and an in-story instruction inside a fictional
scene — each asking the model to *summarize or extract* while the payload
tries to redirect to an `OM-MARKER-XX` canary. The benign rows are plain
single-word instruction-following controls.

Artifacts:

- `data/benchmark_v0.7.0.jsonl` (built by `scripts/build_benchmark_v0.7.0.py`)
- `data/CHECKSUMS.txt` pins its SHA-256
- `.github/workflows/validate.yml` validates and audits v0.7.0
- Shipped-dataset tests in `tests/test_validate.py` and
  `tests/test_quality_audit.py`

## 3. API-key scrubbing in provider error details

Before: both HTTP adapters embed provider error bodies into exception
messages, which flow into local evidence reports. A hostile or
misconfigured `openai-compatible` endpoint could echo the
`Authorization` (or `x-goog-api-key`) header back inside its error body,
writing the live key into the local evidence report.

After: echoed key material is replaced with `***` before raising — both
the bare token and `Bearer <token>` forms, across all three key-carrying
paths (guardrail adapter, scanner compatible endpoints, hosted provider
headers).

Artifacts:

- `modules/ai_scanner/providers.py` — `_scrub_error_detail()`
- `modules/guardrail_lab/openai_compatible.py` — key replacement in error
  detail
- `tests/test_error_detail_scrubbing.py` — hostile endpoints echoing keys
  in 401/403/400/500 bodies

## 4. Config-pinned evidence contract (A)

Before: reports had no reproduction attributes, so agreement between two
providers was uninterpretable — a disagreement could be config drift
(temperature, thinking, max tokens, parser, truncation) rather than model
behavior. Missing fields were silently treated as absent.

After: `modules/guardrail_lab/measurement.py` defines `RunConfig` with
canonical contract fields (weight/tokenizer/chat-template hashes, prompt
hash, injection point, parser, truncation policy, judge identity,
case-set hashes derived from the actual files) and a `config_hash` over
**measured fields only**. Unmeasured settings are typed
`not_measured: [{item, reason}]` rather than guessed; endpoint URLs and
keys are fingerprinted/redacted. `runner.py` adds provider response
status, `finish_reason`, content tokens, thinking parse status, and a
`truncated` flag derived from the provider's finish reason (never from a
token guess). `compare.py` always emits `config_equivalence`
(`equivalent` / `divergent` / `not_measured`); strict mode marks all cases
incomparable unless configs match, and suppresses agreement rates.

Artifacts: `measurement.py`, `runner.py`, `compare.py`, `demo.py`,
`tests/test_measurement_contract.py`, schema version `1.2`.

## 5. Matched benign twins and potential false refusal (B)

Before: `task_utility=0` conflated "refused a benign task" with "failed at
the task", and benign controls did not share surface form with adversarial
rows, so a false-refusal rate was not a controlled comparison. This had to
be fixed in two separate pipelines (the JSONL benchmark and Guardrail Lab
`Case` objects) — a sibling pipeline's outcome is never ground truth for
the other.

After: `data/benchmark_v0.8.0.jsonl` adds six matched benign twins
(OM-076..081) that keep frame, surface, and keywords from their v0.7.0
adversarial source rows but replace the injected instruction with a
harmless task; `data/benchmark_v0.8.0-pairs.json` pins the twin→source
mapping. v0.7.0 bytes stay untouched. The semantic-review rubric gains an
optional `compliance` signal (`compliant` / `refused` / `incapable`), and
legacy judges that omit it are recorded as unknown, not refusals. Guardrail
Lab's `runner.assess()` returns `potential_false_refusal` for control cases
with narrow explicit refusal phrases; bare "no" or a missing expected
signal still goes to `manual_review`.

Scoped reduction: twins cover the six new v0.7.0 rows only; no three-stage
precheck is claimed. Artifacts: v0.8.0 dataset + pairs sidecar, build
script, CHECKSUMS pin, CI validation, `tests/test_false_refusal.py`,
SCORING.md / SEMANTIC_REVIEW.md / README / release checklist.

## 6. Controlled frame × shape factorial over inert canaries (C)

Before: campaign variants varied several things at once, so a difference
could not be attributed to a neutral framing axis.

After: `campaign.py` keeps the existing six-variant tuple unchanged and adds
orthogonal, non-adaptive `frame_variant` / `shape_variant` **metadata**
from three fixed neutral frames (`direct`,
`analytical_information_request`, `domain_brief`) and two shapes
(`action`, `information`), with frozen decoding and a constant trusted
system instruction. `discovery.py` extends the existing repeat-run rule
(opt-in) so a frame-annotated confirmation must reproduce in at least two
distinct frames; legacy fixtures without frames still confirm. No
persona/authority frames, no adaptive search, no release-only holdout
material. Transfer to other corpora is **INFERRED / UNTESTED**.

Artifacts: `campaign.py`, `discovery.py`, `tests/test_frame_factorial.py`.

## 7. Judge qualification fixtures (D, opt-in)

Before: any command that printed a JSON score object was accepted as a
judge, including one that always returned a perfect score or copied a
previous case's answer.

After: `src/judge_fixtures.py` defines four known-answer fixtures with a
planted prior-answer decoy. `qualify_judge()` in `src/semantic_review.py`
requires exact labels, a correct case-id echo, and no prior-answer
leakage, and emits a stable `judge_id` / `judge_hash` shared with A's
reproduction attributes. `run_judge(..., require_qualified=False)` keeps
the legacy call shape; `--qualification-only` and `--require-qualified`
are opt-in CLI gates. Four fake judge commands under
`tests/fixtures/judges/` demonstrate that an honest judge passes and
`always_pass`, `label_flipper`, and `prior_answer_leaker` all fail. This
is a harness calibration gate, **not** a claim that a judge model is
generally accurate; human review of every provisional score remains
mandatory.

## 8. Typed preflight / readiness ladder (E)

Before: a boot log or `health` / `/v1/models` response could be mistaken
for a ready service, and error states were not distinguishable.

After: `modules/guardrail_lab/preflight.py` records exactly four states —
`ready`, `not_ready`, `misconfigured`, `failed` — in a hash-bound,
scrubbed evidence receipt. Readiness requires a **benign real-forward
echo**, never a health response alone; optional `expected_model` pins the
checkpoint identity. A genuine refusal to a *benchmark* case is a
benchmark outcome, never a preflight state; preflight only ever sends one
benign echo. No third-party call is made by the module — the caller
supplies the adapter. CLI flags (`--require-ready`, `--preflight-only`,
`--preflight-output`) live only in `modules/guardrail_lab/cli.py`.
`.github/workflows/preflight.yml` is `workflow_dispatch`-only with
`permissions: contents: read`, so PR CI never calls an external endpoint.

## 9. Negative-evidence lifecycle (F)

Before: a corrected or withdrawn conclusion had no typed status, and old
rows would have to be rewritten — destroying the audit trail.

After: `registry.py` adds `superseded`, `not_reproduced`, and
`not_measured` statuses. Supersession is **append-only**: a new row
references `supersedes` and `superseded_by`, both validated against
existing finding ids; the original row is preserved verbatim (hash
recompute stays consistent). `not_reproduced` requires repeat-run counts;
`not_measured` requires an explicit reason (unknown, not a pass).
`export_markdown` prints the chain and the negative-evidence details.
`discovery.py` **downgrades** superseded conclusions — they are counted
separately and never ranked as confirmed. The
`confirmed → potential_guardrail_failure` invariant is preserved.

Artifacts: `registry.py`, `discovery.py`,
`tests/test_negative_evidence.py`.

## 10. Honest uncertainty display (G)

Before: an agreement rate could be read as a precise measurement even with
repeated measures per case and provider-level correlation.

After: `compare.py` emits `uncertainty: {kind: descriptive_dispersion,
n_observations, comparable_case_count, excluded_case_count,
agreement_rate, note}` and explicitly states that `n_observations` counts
case-provider rows, not independent trials. **No confidence interval,
p-value, or standard error is published** — a naive independent-Bernoulli
interval would imply false precision. Inconclusive, truncated, empty, and
not-run outcomes are excluded from the denominator; missing cases remain
distinct from disagreement. A cluster/bootstrap design is documented as
the prerequisite for any future confidence claim.

Artifacts: `compare.py`, `tests/test_measurement_contract.py`,
`tests/test_uncertainty_display.py`.

## Verification

All contributions pass the full local gate set on 2026-11-17, after
merging upstream `main` (which added its own source-corpus browser and
loader tests):

- **417 unit tests, all passing** (407 contribution tests + 10 upstream
  tests; 335 at the previous PR revision)
- `python -m compileall` on every changed module
- `src.validate` passes on all seven benchmark versions (v0.3–v0.8.0)
- `src.quality_audit data/benchmark_v0.8.0.jsonl` → `pass`, 0 warnings
- CHECKSUMS verifier and v0.8.0 pairs-sidecar consistency tests pass
- Demo mode, `--list`, and compare paths (strict / divergent / unknown
  config / legacy reports) all pass
- Corpus import-time validation passes (factorial assignment, prompt
  match, manifest hash pinning)
- Judge qualification, typed preflight, supersession chain, and
  uncertainty display each have dedicated tests

