#!/usr/bin/env python3
"""Generate dashboard/public/cases.json from the repo Guardrail Lab CASES.

Same export shape as the HF Space build script (verify_cases_json):
case_id, category, prompt, expected_signal, canary, control, source_id,
source_path, source_sha256 — 76 rows (24 core + 52 source-derived).

Usage:
    python3 scripts/generate_cases.py [--repo PATH] [--out PATH]

--repo defaults to the git checkout that contains this dashboard
(dashboard/../), falling back to ~/workspace/openmind-jailbreak-lab-git.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FIELDS = (
    "case_id",
    "category",
    "prompt",
    "expected_signal",
    "canary",
    "control",
    "source_id",
    "source_path",
    "source_sha256",
)


def export_cases(repo: Path) -> list[dict]:
    sys.path.insert(0, str(repo))
    from modules.guardrail_lab.cases import CASES

    return [{f: getattr(c, f) for f in FIELDS} for c in CASES]


def main() -> int:
    here = Path(__file__).resolve()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=None, help="repo checkout root")
    ap.add_argument("--out", default=None, help="output cases.json path")
    args = ap.parse_args()

    if args.repo:
        repo = Path(args.repo)
    else:
        # dashboard/scripts/ -> repo root is parents[1] when this lives in
        # the monorepo; otherwise fall back to the known checkout.
        candidate = here.parents[1]
        repo = candidate if (candidate / "modules" / "guardrail_lab").is_dir() else Path.home() / "workspace" / "openmind-jailbreak-lab-git"
    out = Path(args.out) if args.out else here.parents[1] / "public" / "cases.json"

    rows = export_cases(repo)
    if len(rows) != 76:
        print(f"error: expected 76 cases, got {len(rows)}", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core = sum(1 for r in rows if not r["case_id"].startswith("GL-SRC"))
    print(f"wrote {out}: {len(rows)} rows ({core} core + {len(rows) - core} source)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
