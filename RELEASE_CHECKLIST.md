# Release checklist

Use this checklist before tagging or publishing a release. A green CI run is
necessary, but it does not replace live evidence review or human adjudication.

## 1. Source and benchmark integrity

- [ ] Confirm the intended release commit and inspect the complete diff.
- [ ] Run `python -m src.validate data/benchmark_v0.8.0.jsonl` (and every earlier benchmark version).
- [ ] Confirm benchmark case count, unique IDs, split totals, required fields, and synthetic marker uniqueness.
- [ ] Confirm Guardrail Lab lists 76 unique cases (24 core + 52 source-derived) and `--source-corpus` selects exactly 52.
- [ ] Verify every source adaptation's source ID, path, and SHA-256 against the metadata inventory; verify result JSON preserves `source_provenance`.
- [ ] Confirm benchmark prompts and expected behaviors are reviewed; do not silently rewrite cases to improve scores.
- [ ] Record dataset version, file checksum, and methodology version in release notes.
- [ ] Keep benchmark case data, model response evidence, and adjudicated findings as separate artifacts.

## 2. Offline regression

- [ ] Run `python -m unittest discover -s tests -v` on every supported Python version.
- [ ] Verify provider contract tests for OpenAI, Anthropic, Gemini, and OpenAI-compatible endpoints.
- [ ] Verify system-instruction mapping, multi-turn continuity, retry/backoff, malformed response handling, and error classification.
- [ ] Verify comparison, semantic-review, and report-schema compatibility tests.
- [ ] Verify no test requires a live API key or sends a live request.

## 3. Workflow and packaging

- [ ] Confirm GitHub Actions permissions are least-privilege.
- [ ] Confirm workflow inputs, provider/model selection, scope (`all`/`core`/`source`), mode (`full_suite`/`campaign`), secret names, artifact names, and budget bounds match documentation.
- [ ] Confirm the full-suite workflow validates all 76 case IDs and source provenance.
- [ ] Confirm current supported Python versions and pinned action versions.
- [ ] Run workflow validation on the release candidate commit.
- [ ] Confirm artifacts upload even when a run contains partial or failed requests, where appropriate.
- [ ] Confirm no API keys, tokens, or private prompts are committed.

## 4. Live evaluation evidence

- [ ] Test only accounts and models for which the operator has authorization.
- [ ] Record provider, exact model ID/version, date/time, API request IDs, run configuration, and dataset revision.
- [ ] Preserve raw request/response evidence and provider errors.
- [ ] Separate completed, partial, and not-run cases; do not count errors as passes.
- [ ] Require human review for ambiguous, semantic, or potential disclosure findings.
- [ ] Re-run candidate failures with controlled repeats before calling them reproducible.
- [ ] Do not call a canary mention, refusal, or classifier flag a confirmed bypass without evidence meeting the published rubric.

## 5. Release notes and sign-off

- [ ] Publish known limitations, false-positive/false-negative risks, and changes from the prior version.
- [ ] Include test matrix results and live-evaluation scope without overstating coverage.
- [ ] Clearly label simulated/demo material and exclude it from live-result totals.
- [ ] Record reviewer sign-off and unresolved issues.

## Bounded adversarial research mode

- [ ] Verify `--research-mode` enables campaign execution, six reviewed framings,
      and evidence-triggered follow-ups.
- [ ] Verify `--case` and `--source-corpus` selection, request-budget handling,
      JSON report output, and optional unverified registry output.
- [ ] Verify `--no-adaptive` is rejected with `--research-mode`.
- [ ] Confirm candidate records remain unverified until manual transcript review
      and repeatability checks.
- [ ] Confirm offline CI is not described as a live-provider security result.
