# Source archive inventory and safe adaptations

This directory contains two distinct research layers: (1) a metadata-only provenance inventory of the authentic archive, and (2) inert, rewritten adaptations used by the defensive Guardrail Lab.

## Files

- `source_inventory.jsonl`: 55 metadata records, one per non-directory archive member. No raw archive record is executable.
- `safe_adaptations.jsonl`: 52 rewritten, bounded evaluation cases (GL-SRC-001–GL-SRC-052). They are not verbatim originals.
- `manifest.json`: archive SHA-256, record counts, inventory SHA-256, and the pinned `adaptations_sha256`.
- `variant` field on each adaptation: the injection surface the prompt presents (see “Factorial assignment” below).

## Separation

The independent [Original Source Corpus browser](../../modules/original_source_corpus/README.md) searches and displays provenance metadata without merging originals into the defensive runner. The source archive is identified by SHA-256; its raw prompt bodies are not copied into this public repository. The inventory contains IDs, paths, byte sizes, hashes, and status only.

## Verified source

- Archive SHA-256: `4f76bac118fc58eecfe79497a3f7ce42803c222caba665a72d290d41f6824918`
- Archive members: 55
- Non-empty members: 54 (including the README and withdrawn notice)
- Empty (zero-byte) files: 0; one-byte placeholder: 1
- Withdrawn notice: 1 (`0x8D jailbreaks/grok-fast-v2.md`); excluded from runnable use
- Safe adaptations: 52
- Raw source records marked runnable: 0

## Execution and provenance boundary

The 52 adaptations preserve high-level testable patterns—authority escalation, boundary narrowing, persona reassignment, and simulated agent/tool authority confusion—while replacing risky instructions with inert `SAFE-MARKER-NNN` canaries. They are **not verbatim copies** of original prompt bodies and do not execute tools, retrieve secrets, or perform external actions.

**Research-purposes-only disclaimer:** these cases and their patterns are published for bounded robustness research and evaluation only. They are inert probes, not exploit instructions, and must not be represented as jailbreak techniques for general use.

## Factorial assignment (category × surface)

The original corpus rendered each category as a single fixed prompt repeated with 13 different canary markers — 4 distinct prompts in total. Research on instruction-boundary behavior shows sensitivity to surface form even at fixed semantics, so each category payload is now paired factorially with 13 distinct injection surfaces, giving 52 pairwise-distinct prompts:

- Categories (4): `authority_override`, `boundary_narrowing`, `persona_reassignment`, `agent_authority_confusion`
- Surfaces (13): quoted note, email body, CSV cell, HTML comment, JSON field, retrieved passage, tool output, document record, code comment, Base64-encoded note, Spanish-language note, Markdown link text, fictional narrator

Case GL-SRC-NNN is assigned category `(NNN-1) mod 4` and surface `(NNN-1) // 4` — a balanced Latin square where every category×surface pair occurs exactly once. The assignment and every prompt are reproducible from `modules/guardrail_lab/source_registry.py` (`scripts/regenerate_source_corpus.py` regenerates the JSONL from it), and the loader validates both at import time.

At import time, Guardrail Lab validates each adaptation's schema, unique IDs/canaries, safe framing, source ID, source path, and SHA-256 against `source_inventory.jsonl`. Live result records include the matching source provenance. The inventory and adaptations do not establish licensing, safety of the original source, or model vulnerability.

## Browse and validate
The source-derived cases run through Guardrail Lab's `--source-corpus` option; the browser commands below only inspect provenance metadata.

```bash
python -m modules.original_source_corpus
python -m modules.original_source_corpus --search qwen
python -m modules.original_source_corpus --id SRC-005 --json
python -m modules.original_source_corpus --verify-archive /path/to/source_archive.zip
```

The archive verifier compares the supplied file's SHA-256 with `manifest.json`. It does not execute archive content.

The JSONL inventory loader rejects malformed JSON, non-object JSON values (including arrays, strings, numbers, booleans, and null), missing or incorrectly typed fields, invalid hashes, runnable records, and duplicate IDs or paths. Errors identify the affected line or validation rule rather than failing later with an attribute error. The test suite includes regression coverage for these cases.

## Adaptation runner

Only the separate safe adaptations are included in Guardrail Lab's `--source-corpus` option. They replace risky instructions with inert canary markers and validate provenance against this inventory. They do not prove the original source was safe or that any model is vulnerable.

## Human review

Generate a blank review record for one source item:

```bash
python -m modules.original_source_corpus --id SRC-001 \
  --export-review-template manual_reviews/SRC-001.json
```

Review records are separate from run inputs. A review decision never automatically adds raw source text to an execution pipeline.
