# Release readiness status

**Status: validated development build; not yet a signed v1.0 release.**

This file records what has been verified on the current repository revision and what remains before a public release claim.

## Verified on 2026-11-17

Repository branch: `main`

Code and workflow verification commits:
Validate benchmark on `bb601ef`; provider matrix on `bb601ef` (contains all Python changes in this release; later commits are documentation-only).

GitHub Actions results:

| Workflow | Run | Result |
|---|---:|---|
| Validate benchmark | [44222085189](https://github.com/tjcrims0nx/OpenMind-Jailbreak-Lab/actions/runs/44222085189) | Success |
| Provider adapter regression matrix | [44222085147](https://github.com/tjcrims0nx/OpenMind-Jailbreak-Lab/actions/runs/44222085147) | Success |

Both workflows passed on Python 3.10, 3.11, and 3.12. Validation compiled all Python source and test files, validated benchmark versions 0.3 through 0.8.0, ran the benchmark quality audit (v0.7.0 and v0.8.0 both `pass`, zero warnings), smoke-tested JB-002, AI Scanner, Guardrail Lab, and the original source corpus browser, and ran the full unit-test suite (417 tests). The provider matrix passed its complete offline regression suite on all three Python versions.

## Guardrail Lab source-corpus integration

The Guardrail Lab now contains 76 registered cases: 24 core cases and 52 source-derived safe adaptations (`GL-SRC-001`–`GL-SRC-052`). The 52 adaptations are now a 4-category × 13-surface factorial — 52 pairwise-distinct prompts, one per category×surface pair. The raw uploaded archive remains a metadata-only inventory; original prompt bodies are not redistributed or executed.

The adaptation loader validates JSONL structure, safe framing, unique IDs and canaries, the inventory checksum, and every source ID/path/SHA-256 relationship. Per-case evidence reports include `source_provenance`. The CLI supports `--source-corpus`; the multi-provider Actions workflow supports `all` (76), `core` (24), and `source` (52) scopes in `full_suite` or bounded `campaign` mode. The dedicated Gemini full-suite workflow now validates all 76 cases.

The verification above is offline CI, not a live provider run. The updated manual multi-provider workflow and 52/76-case live suites still require an authorized, credentialed dispatch before any live-compatibility claim. Verification was re-done on the final head: the earlier draft cited commit `d5a5135`, which predates the research-mode CLI and source-template code changes.

## Remaining before v1.0

- [x] Expand benign controls across multiple meaningful families. (Done in v0.7.0: second benign family `benign_instruction_following`, 31 benign rows.)
- [x] Add additional cases for the singleton adversarial families, with observable expected behavior and matched benign controls. (Done in v0.7.0: 2 cases each for `history_edit`, `cross_model_pipeline`, `hypothetical_framing`; matched twins in v0.8.0.)
- [ ] Run the same frozen benchmark against at least Gemini, Claude, and OpenAI using authorized accounts; record exact model IDs, run dates, settings, raw evidence, and provider errors.
- [ ] Repeat candidate failures and have a human review ambiguous or potential findings.
- [ ] Confirm action versions and workflow permissions during the final release review.
- [ ] Complete the [release checklist](RELEASE_CHECKLIST.md), record reviewer sign-off, and publish scoped release notes.

## Interpretation and limitations

A green CI run verifies the tested repository code paths and offline fixtures. It does not prove every provider adapter works against a live service, certify a model, or demonstrate a jailbreak. A completed live campaign means its configured requests and evidence collection completed; a potential signal still requires reproduction and review.

Do not combine simulated demo fixtures with live results. Do not count API errors or incomplete cases as model passes. Do not publish secrets or sensitive transcripts in reports.

Until the remaining items are completed, describe this repository as a validated development build, not as a completed v1.0 release or a universal guardrail-bypass tool.



## Current main revision — 2026-11-17

Latest observed main commit: `bb601ef` (merge of PR #3, research contributions; code).

- [Validate benchmark — run 44222085189](https://github.com/tjcrims0nx/OpenMind-Jailbreak-Lab/actions/runs/44222085189): **success** on the current main commit.
- [Provider adapter regression matrix — run 44222085147](https://github.com/tjcrims0nx/OpenMind-Jailbreak-Lab/actions/runs/44222085147): **success** on the current main commit.
- The release-notes and release-status documentation now records the PR #3 research batch (benchmark v0.7.0/v0.8.0, source-corpus factorial, measurement contract, preflight, judge qualification, negative-evidence lifecycle, uncertainty display) and the 17 November AgentRouter re-test snapshot.

The earlier code/workflow verification results listed above remain tied to their exact commit. Re-run the complete release validation workflow on the final release candidate before tagging.

## Bounded adversarial research mode

The CLI now includes `--research-mode`, which selects the bounded campaign
runner, six fixed reviewed framings, and evidence-triggered follow-ups. It
supports source-corpus and individual-case selection, JSON evidence output,
and an optional registry for unverified candidates. The mode is documented in
the root README, installation guide, Guardrail Lab README, integration notes,
and discovery-engine guide.

Release gate: verify the latest GitHub Actions run for the exact commit before
marking this feature validated. No live provider evaluation is implied by
offline CI; candidate findings still require transcript review and repeatability
checks.
