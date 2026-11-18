#!/usr/bin/env python3
"""Regenerate safe_adaptations.jsonl prompts from the source_cases registry.

Provenance fields (source_id, source_path, source_sha256) and canary
assignments are preserved from the existing file; only the prompts and the
variant field are rewritten to match the current approved registry. The output
must still pass load_source_cases() at import time.

Research-purposes-only: all prompts are inert robustness probes using
synthetic SAFE-MARKER-NNN canaries; no harmful payloads are introduced.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data" / "source_corpus" / "safe_adaptations.jsonl"

sys.path.insert(0, str(_ROOT))

from modules.guardrail_lab.source_registry import (  # noqa: E402
    CATEGORIES,
    case_number,
    expected_assignment,
    expected_prompt,
    EXPECTED_TOTAL,
)


def main() -> int:
    rows = [json.loads(line) for line in _DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != EXPECTED_TOTAL:
        print(f"expected {_EXPECTED_TOTAL} rows, found {len(rows)}", file=sys.stderr)
        return 2

    regenerated = 0
    for row in rows:
        number = case_number(row["case_id"])
        category, variant = expected_assignment(number)
        row["category"] = category
        row["variant"] = variant
        row["expected_signal"] = CATEGORIES[category][0]
        row["prompt"] = expected_prompt(category, variant, row["canary"])
        regenerated += 1

    lines = [json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows]
    _DATA.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Regenerated {regenerated} safe adaptations with factorial category/variant assignment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
