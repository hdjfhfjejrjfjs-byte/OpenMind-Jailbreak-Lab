# OpenMind Jailbreak Lab — Release Candidate Notes

**Suggested release tag:** `v0.7.0-rc.4`
**Target commit:** the final `main` commit containing this release-notes file
**Release type:** Pre-release candidate

## What changed since v0.7.0-rc.3

181 commits since rc.3 (`b8d63fb` → `8fea5d3`, 2026-11-19). No benchmark version change: benchmark stays v0.8.0, Guardrail Lab stays 0.6.0, AI Scanner stays 0.3.5. The new work is the OMJB evaluation harness, the corpus importer, the mutation robustness engine, async/multi-provider evaluation, and campaign history.

- **OMJB evaluation harness 0.2.0 (new):** Guardrail Lab integration (PR #4, squash `b412f36`); reviewer-aware guard adjudication and pinned corpus fetching (PR #6, squash `3433cd7`); legacy reviewer migration coverage (PR #7, merge `25252a8`); installation and operator docs refresh (PR #14, merge `b629240`; PR #25, commit `8fea5d3`).
- **Corpus importer (CSV + Parquet):** CSV and Parquet corpus imports (PR #8, merge `59d2679`, including the `04ca261` push-paths filter fix) with real pinned Parquet verification tests (PR #9, merge `c51fa1c`, merged by the repo owner).
- **Mutation robustness engine:** integration (PR #11, merge `f13e96e`); reproducible engine (PR #12, merge `4b4a31e`); spec and verdict hardening (PR #16); explicit mutation CLI cost estimates (PR #17); mutation trace replay, endpoint config, and decoder canary (PR #22, commit `42e2192`).
- **Async and multi-provider evaluation:** async endpoint and provider evaluation (PR #10, merge `6f2c5d2`); bounded concurrent multi-provider evaluator (PR #23, merge `92382e0`, including the Ollama `num_predict` fix `261095c`).
- **Scalable benign robustness and campaign history:** configurable benign robustness testing (PR #18); capacity docs (PR #19); capacity controls in adaptive campaigns (PR #20); persisted campaign history with resume of untested coverage (PR #21, commit `39a1dd8`).
- **Regression set (new):** 14 known bypasses (`data/known_bypasses.json`), 11-row regression subset (`data/benchmark_regression.jsonl`), `scripts/regression_report.py`, per-family evaluator rollup, README "Tested configurations" section (`490874c`, `dbd23b8`, `a272ab7`).
- **README redesign** with neon cyber-security visuals (PR #24, commit `ce7da26`).
- **Closed unmerged:** PR #5 (OMJB install guide docs), PR #13 (typed-region mutation engine, superseded by #11/#12), PR #15 (install-guide refresh). No open PRs remain.

## Unchanged

- **Benchmark v0.8.0:** 81 rows (44 adversarial / 37 benign).
- **Guardrail Lab 0.6.0:** 76 cases (24 core + 52 source-derived safe adaptations).
- **AI Scanner 0.3.5:** 11 probes.
- **Results stay local:** the 17 November run evidence was published and then fully reverted; the repo is back to results-local.

## Verification

The [Validate benchmark run 44612084730](https://github.com/tjcrims0nx/OpenMind-Jailbreak-Lab/actions/runs/44612084730) passed on commit `8fea5d3` on Python 3.10, 3.11, and 3.12. The validation workflow compiled all Python sources, validated all benchmark versions (v0.3–v0.8.0), ran the quality audit and module smoke tests, and executed the complete unit-test suite.

The full unit-test suite was also run locally on the release commit: **545 tests, all passing** (2 skipped without the external-corpus flag; with `OMJB_RUN_EXTERNAL_CORPUS_TESTS=1` the 2 real Parquet import tests pass as well — one run hit a transient sandbox network timeout on the pinned-file download and passed on retry). The two errors seen in a bare system-Python run were a missing optional `httpx` dependency, not code failures; installing the `api` extra (`httpx`, plus `pyarrow` and `PyYAML`) clears them.

The OMJB and provider-matrix workflows did not run on the HEAD commit (path-filtered), so the full workflow matrix was not re-verified on the final commit. The 76-case live provider suite and selectable multi-provider Actions workflow have not been live-executed as part of this offline CI verification.

## Known limitations

- The current benchmark (v0.8.0) has 81 cases: 44 adversarial and 37 benign.
- Live cross-provider comparisons against Gemini, Claude, and OpenAI remain outstanding.
- Full-suite GitHub Actions runs can send 52 or 76 live requests depending on selected scope and may incur provider charges; no live model results are implied by CI.
- A green workflow validates software paths; it does not prove a jailbreak, certify a model, or establish universal security.

## Before publishing this candidate

1. Tag the final `main` commit containing this release-notes file.
2. Create the tag `v0.7.0-rc.4` at that commit.
3. Publish as a GitHub **pre-release**, not a stable v1.0 release.
4. Keep live model findings separate from offline CI results.
