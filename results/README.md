# Published run evidence — 17 November 2026

Raw run files for the AgentRouter full-lab re-test (both GPT models) and
the Gemini 76-case Guardrail Lab suite, plus the dated comparison
supplement and the OrcaRouter campaign runner. Benchmark, campaign, and
scanner outputs are separate instruments; do not combine their scores.

## Contents

- `agentrouter-benchmark-v0.6.1-gpt56-2026-11-17.{jsonl,csv}` — GPT-5.6-sol
  benchmark re-run: 65/66 answered, 0 leaks, 1 mention (OM-041,
  quoting-only). OM-057 did not reproduce.
- `agentrouter-benchmark-v0.6.1-gpt61-2026-11-17.{jsonl,csv}` — GPT-6.1-sol
  first full benchmark: 63/66 answered, 0 leaks, 1 mention (OM-041).
- `agentrouter-campaign-gpt56-2026-11-17.json` and
  `agentrouter-campaign-gpt61-2026-11-17.json` — 36-case campaigns
  (budget-capped: 24 core + GL-SRC-001..012), 0 failures on both models.
- `agentrouter-scan-gpt56-0.3.5-2026-11-17.json` and
  `agentrouter-scan-gpt61-0.3.5.json` — scanner 0.3.5, 11/11, 0 failures.
- `gemini-suite-76.json` — Gemini 3.5 Flash Lite, full 76-case suite:
  22 boundary_held, 38 ambiguous mentions, 14 manual_review, 2 controls,
  0 potential failures.
- `gemini-suite-76-manual-review-adjudication.md` — the 14 manual-review
  responses read in full: 14/14 clean.
- `provider-comparison-2026-11-17-agentrouter.md` — dated supplement to
  the 16 November comparison; OM-057 is intermittent (1 failure in 2
  runs), not a standing failure.
- `run_orcarouter_campaign.py` — campaign runner for OrcaRouter free
  models. Test-env tool: it takes its key from the stored
  `custom.orcarouter` credential via a dynamic-credentials surrogate at
  run time (no key in the file) and hardcodes this machine's paths, so it
  is kept here with the outputs rather than in `scripts/`.

## Redaction

Provider request IDs in the five JSON run files (198 values: Azure
`resp_…` IDs in the AgentRouter files, Gemini response IDs in the suite
file) were replaced with `"REDACTED"` before publication. Campaign and
suite records carry `evidence_sha256`, computed over the whole record
including the request ID, so each affected record's hash was recomputed
with the repo's own `_evidence_sha256()` after redaction — every stored
hash verifies against the published content. Nothing else was changed:
the redacted files are identical to the originals except the request IDs
and the recomputed hashes. Unredacted originals stay in the local test
environment only.

The 16 November comparison report and result files, and the v0.6.1
mention adjudication files, stay local and are not published here.
