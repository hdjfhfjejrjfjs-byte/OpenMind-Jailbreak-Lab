# OpenMind Jailbreak Lab — Release Candidate Notes

**Suggested release tag:** `v0.7.0-rc.3`
**Target commit:** the final `main` commit containing this release-notes file
**Release type:** Pre-release candidate

## What changed since v0.7.0-rc.2

Research contributions from Blackfrost (PR #3, merged as `bb601ef`) — measurement science for guardrail evaluation, research-purposes-only. All new test material is inert probes on synthetic canary markers; no new bypass techniques.

- **Benchmark v0.7.0 (75 cases: 44 adversarial / 31 benign):** fills the three singleton adversarial families (`history_edit`, `cross_model_pipeline`, `hypothetical_framing`, 2 cases each) and adds a second benign family (`benign_instruction_following`). The quality audit now returns `status: pass` with zero warnings.
- **Benchmark v0.8.0 (81 cases: 44 adversarial / 37 benign):** adds six matched benign twins (OM-076..081) that keep frame, surface, and keywords from their v0.7.0 adversarial source rows but replace the injected instruction with a harmless task; `benchmark_v0.8.0-pairs.json` pins the twin→source mapping. v0.7.0 bytes stay untouched.
- **Source-corpus factorial:** the 52 source-derived cases are now 52 pairwise-distinct prompts — a 4-category × 13-surface Latin square (quoted note, email, CSV, HTML comment, JSON field, retrieval, tool output, document record, code comment, Base64, Spanish, Markdown link, fictional narrator), one pair each. Before, they rendered four fixed prompts differing only by marker.
- **API-key scrubbing:** provider error bodies are scrubbed of echoed key material (`***` replaces bare tokens and `Bearer <token>` forms) before reaching evidence reports, across the guardrail adapter, scanner compatible endpoints, and hosted provider headers.
- **Config-pinned evidence contract:** `RunConfig` with canonical contract fields (weight/tokenizer/chat-template hashes, prompt hash, injection point, parser, truncation policy, judge identity, case-set hashes) and a `config_hash` over measured fields only; unmeasured settings are typed `not_measured`, never guessed. Comparisons always emit `config_equivalence`; strict mode marks cases incomparable unless configs match.
- **Matched benign twins and potential false refusal:** the semantic-review rubric gains an optional `compliance` signal; Guardrail Lab `assess()` returns `potential_false_refusal` for control cases with narrow explicit refusal phrases.
- **Frame × shape factorial metadata:** orthogonal, non-adaptive `frame_variant` / `shape_variant` metadata (3 fixed neutral frames × 2 shapes) with frozen decoding and a constant trusted system instruction; repeat-run confirmation must reproduce in at least two distinct frames.
- **Judge qualification fixtures (opt-in):** four known-answer fixtures with a planted prior-answer decoy; `qualify_judge()` requires exact labels, correct case-id echo, and no prior-answer leakage. `--qualification-only` and `--require-qualified` are opt-in gates; human review of every provisional score remains mandatory.
- **Typed preflight:** exactly four readiness states (`ready`, `not_ready`, `misconfigured`, `failed`) in a hash-bound, scrubbed evidence receipt. Readiness requires a benign real-forward echo, never a health response alone. The preflight workflow is manual-dispatch-only and never calls an external endpoint from PR CI.
- **Negative-evidence lifecycle:** `superseded`, `not_reproduced`, and `not_measured` statuses. Supersession is append-only — the original row is preserved verbatim and linked both ways; superseded conclusions are counted separately and never ranked as confirmed.
- **Honest uncertainty display:** comparisons emit descriptive dispersion (`n_observations`, comparable/excluded counts, agreement rate) and explicitly state that no confidence interval, p-value, or standard error is published.
- **Guardrail Lab 0.6.0** (was 0.5.9). Full suite now **417 tests**.
- **README:** evaluation snapshot for 17 November 2026 added — GPT-5.6-sol re-test 0 / 65 answered (OM-057 intermittent, 1 failure in 2 runs), GPT-6.1-sol first full lab test 0 / 63 answered; Gemini 76-case Guardrail Lab suite 0 potential failures (fully adjudicated).

## Verification

The [Validate benchmark run 44222085189](https://github.com/tjcrims0nx/OpenMind-Jailbreak-Lab/actions/runs/44222085189) passed on commit `bb601ef` on Python 3.10, 3.11, and 3.12, and the [Provider adapter regression matrix run 44222085147](https://github.com/tjcrims0nx/OpenMind-Jailbreak-Lab/actions/runs/44222085147) passed on the same commit on all three Pythons. The validation workflow compiled all Python sources, validated all seven benchmark versions (v0.3–v0.8.0), ran the quality audit (v0.7.0 and v0.8.0 both `pass`, zero warnings) and module smoke tests, and executed the complete unit-test suite (417 tests). The full unit-test suite (417 tests) and benchmark validation on all seven versions were also run locally on the release commit and passed.

The 76-case live provider suite and selectable multi-provider Actions workflow have not been live-executed as part of this offline CI verification.

## Known limitations

- The current benchmark (v0.8.0) has 81 cases: 44 adversarial and 37 benign.
- Live cross-provider comparisons against Gemini, Claude, and OpenAI remain outstanding.
- Full-suite GitHub Actions runs can send 52 or 76 live requests depending on selected scope and may incur provider charges; no live model results are implied by CI.
- A green workflow validates software paths; it does not prove a jailbreak, certify a model, or establish universal security.

## Before publishing this candidate

1. Tag the final `main` commit containing this release-notes file.
2. Create the tag `v0.7.0-rc.3` at that commit.
3. Publish as a GitHub **pre-release**, not a stable v1.0 release.
4. Keep live model findings separate from offline CI results.
