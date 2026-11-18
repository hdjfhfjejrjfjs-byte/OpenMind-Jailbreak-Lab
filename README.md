# OpenMind Jailbreak Lab

<p align="center">
  <img src="assets/logo.jpg" alt="OpenMind Jailbreak Lab logo" width="420">
</p>

<p align="center"><strong>Provider-neutral toolkit for authorized AI security testing and guardrail evaluation.</strong></p>

OpenMind combines bounded adversarial tests, provider-backed scanning, benchmark evaluation, and evidence reporting. It supports repeatable assessment; a test run is not proof of a vulnerability or a guarantee of a successful jailbreak.

**[Open the live Hugging Face Space](https://huggingface.co/spaces/Grimxlock/OpenMind-Jailbreak-Lab)** · [Manual review workspace](manual_reviews/README.md)

## Get started

- [Start Here](START_HERE.md) — quick setup, GitHub Actions, and mobile use.
- [Installation](INSTALLATION.md) — providers, credentials, and advanced setup.
- [Guardrail Lab guide](modules/guardrail_lab/README.md) — defensive cases, campaigns, and reports.
- [Original Source Corpus](modules/original_source_corpus/README.md) — separate provenance browser and review workflow.

## Components

- **Guardrail Lab:** 76 runnable cases (24 core and 52 source-derived safe adaptations), provider adapters, bounded campaigns, JSON reports, and a findings registry.
- **Original Source Corpus:** separate metadata-only browser for authentic archive records, source paths, sizes, hashes, and manual review. Original raw prompts are not sent to the Guardrail Lab runner.
- **AI Scanner:** [provider-backed checks and response evidence](modules/ai_scanner/README.md).
- **OpenMind Benchmark:** [versioned evaluation set](SCORING.md); current file: [benchmark_v0.8.0.jsonl](data/benchmark_v0.8.0.jsonl) (81 cases, incl. 6 matched benign twins).
- **JB-002:** [manual finding records and validation](modules/jb002/README.md).

The optional `--research-mode` runs six reviewed framings with evidence-triggered follow-ups within the configured budget. It is for authorized testing and evidence collection; it does not create unrestricted harmful bypasses or execute model-generated tool instructions.

## Quick start

Requires Python 3.10+ and Git.

```bash
git clone https://github.com/tjcrims0nx/OpenMind-Jailbreak-Lab.git
cd OpenMind-Jailbreak-Lab
python -m unittest discover -s tests -v
python -m src.validate
python -m modules.guardrail_lab --list
python -m modules.original_source_corpus --search gemini
```

Example Gemini campaign:

```bash
export GEMINI_API_KEY="YOUR_API_KEY"
python -m modules.guardrail_lab --provider gemini --research-mode \
  --source-corpus --budget 100 \
  --output reports/gemini-research.json \
  --registry findings/registry.jsonl
```

Use the environment variable for your provider and keep API keys out of source files and commits. See the [provider matrix](modules/guardrail_lab/PROVIDER_MATRIX.md) for supported configurations.

## Source collections

The 52 source-derived Guardrail Lab cases retain source IDs, paths, and hashes, but replace risky instructions with inert markers. They are **not verbatim source prompts** and remain in the defensive benchmark.

The **Original Source Corpus** is separate. Its inventory preserves authentic archive provenance without copying raw prompt bodies into the public repository or executing them. Browse records with `python -m modules.original_source_corpus`; create a human-review template with `--id SRC-### --export-review-template PATH`. The inventory loader validates JSONL records, rejects non-object values and malformed fields with a clear error, and enforces that every original-source record remains non-runnable. The checked-in review template is regression-tested against the generator. Details: [Original Source Corpus guide](modules/original_source_corpus/README.md).

## Providers and automation

Adapters cover OpenAI, Anthropic, Gemini, DeepSeek, GLM/Zhipu, Moonshot, NVIDIA NIM, OpenRouter, Groq, Together, and compatible endpoints such as Ollama, vLLM, LM Studio, llama.cpp server, and LocalAI. Availability depends on credentials, model IDs, endpoint support, and provider limits.

The manually triggered [multi-provider GitHub Actions workflow](.github/workflows/multi-provider-red-team.yml) accepts a provider, model, scope, and run mode:

- `core`: 24 core cases; `source`: 52 adaptations; `all`: 76 cases.
- `full_suite`: separate run per selected case; `campaign`: bounded campaign of up to six reviewed framings.

Add keys under **Settings → Secrets and variables → Actions**, then run **Actions → Manual multi-provider Guardrail Lab**. Download the JSON artifact from the workflow. Hosted runners cannot access services bound only to your local machine. API use may incur charges.

## Interpreting results

| Label | Meaning |
|---|---|
| `potential_guardrail_failure` | Candidate signal; review and reproduce |
| `ambiguous_canary_mention` | Canary appears; context matters |
| `boundary_held` | Expected boundary observed |
| `control_passed` | Benign control behaved as expected |
| `manual_review` | Automated assessment inconclusive |
| `partial_run` | Run did not complete |

Reports include case IDs, provider/model metadata, prompts, responses, errors, and available assessment labels. A canary quoted in an explanation or warning is not proof of a bypass. Rate limits, authentication failures, and proxy errors are infrastructure outcomes. Treat candidate findings as unverified until manually reviewed and reproduced. Use the [manual review workspace](manual_reviews/README.md) and copy its JSON template once per case; keep original run reports unchanged.

## Evaluation snapshot — 16 November 2026

| Tested configuration | Adjudicated findings |
|---|---:|
| GPT-5.6-sol (AgentRouter) | 1 / 64 answered |
| Claude Haiku 5.5 (Qronos) | 2 / 63 answered |
| Gemini 3.5 Flash Lite | 7 / 66 |
| NVIDIA Nemotron 3 Nano Omni | 9 / 61 text-bearing |

Blocked and no-text cases were unscored, not passes. The benchmark, Guardrail Lab, and AI Scanner are separate instruments; do not combine their scores. These results apply only to the tested configurations and gateways. See [methodology](METHODOLOGY.md), [scoring](SCORING.md), and the dated evidence report.

## Responsible testing

Test only systems you own or are authorized to assess. Follow provider terms, rate limits, and applicable law. Use non-sensitive test data; do not seek real credentials, private data, or hidden secrets. Protect keys, review transcripts before sharing, and reproduce findings before disclosure. Revoke and replace any exposed key.

## Documentation

[Installation](INSTALLATION.md) · [Guardrail Lab](modules/guardrail_lab/README.md) · [Original Source Corpus](modules/original_source_corpus/README.md) · [Provider matrix](modules/guardrail_lab/PROVIDER_MATRIX.md) · [Discovery engine](modules/guardrail_lab/DISCOVERY_ENGINE.md) · [Registry](modules/guardrail_lab/REGISTRY.md) · [Archive import](modules/guardrail_lab/EXTERNAL_ARCHIVE_IMPORT.md) · [Research contributions](RESEARCH_CONTRIBUTIONS.md) · [Methodology](METHODOLOGY.md) · [Release checklist](RELEASE_CHECKLIST.md) · [Release status](RELEASE_STATUS.md)

## Quality checks

```bash
python -m unittest discover -s tests -v
python -m src.quality_audit data/benchmark_v0.8.0.jsonl
python -m modules.guardrail_lab.compare \
  reports/gemini.json reports/openai.json \
  --output reports/comparison.json
```

For an offline demonstration: `python -m modules.guardrail_lab.demo --output reports/synthetic-demo.json`. Its output is fictional, not live-model evidence.

## Status and license

OpenMind is experimental software, not a certification. Provider behavior changes and not every configuration has been live-tested. Check [release status](RELEASE_STATUS.md) for CI and release gates, and [LICENSE](LICENSE) for terms.
