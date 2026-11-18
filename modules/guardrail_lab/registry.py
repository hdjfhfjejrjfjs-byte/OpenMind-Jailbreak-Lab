"""Persistent, evidence-first finding registry for Guardrail Lab."""
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUSES = {
    "unverified", "intermittent", "confirmed", "rejected",
    # Negative evidence is preserved as typed, append-only records. Old rows
    # are never rewritten: a supersession adds a new row that points back.
    "superseded", "not_reproduced", "not_measured",
}
REQUIRED = ("finding_id", "title", "provider", "model", "category", "status", "discovered_at", "evidence_ref", "summary")

def _text(item, key):
    value = item.get(key)
    return isinstance(value, str) and bool(value.strip())

def _hash(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def validate_finding(item: dict[str, Any], allow_confirmed: bool = False,
                     known_ids=None) -> dict[str, Any]:
    """Validate a finding. ``known_ids`` enables supersession chain checks.

    Append-only discipline: superseded records are new rows that reference
    the original and its replacement; no existing row is ever modified.
    """
    if not isinstance(item, dict):
        raise ValueError("finding must be a JSON object")
    missing = [k for k in REQUIRED if not isinstance(item.get(k), str) or not item[k].strip()]
    if missing:
        raise ValueError("missing required non-empty fields: " + ", ".join(missing))
    if item["status"] not in STATUSES:
        raise ValueError("invalid status")
    if item["status"] == "confirmed":
        if not allow_confirmed:
            raise ValueError("confirmed status requires --confirm-review")
        if not isinstance(item.get("review_notes"), str) or not item["review_notes"].strip():
            raise ValueError("confirmed findings require review_notes")
        runs, successes = item.get("repeat_runs"), item.get("repeat_successes")
        if (isinstance(runs, bool) or not isinstance(runs, int) or runs < 2
            or isinstance(successes, bool) or not isinstance(successes, int) or not 2 <= successes <= runs):
            raise ValueError("confirmed findings require repeat_runs >= 2 and 2 <= repeat_successes <= repeat_runs")
        if item.get("assessment") != "potential_guardrail_failure":
            raise ValueError("confirmed findings require assessment=potential_guardrail_failure")
        if item.get("reproducible") is not True:
            raise ValueError("confirmed findings require reproducible=true")
    if item["status"] == "superseded":
        if not _text(item, "supersedes") or not _text(item, "superseded_by"):
            raise ValueError("superseded findings require supersedes and superseded_by")
        if item["supersedes"] == item["superseded_by"]:
            raise ValueError("a finding cannot be superseded by itself")
        if known_ids is not None and item["supersedes"] not in known_ids:
            raise ValueError("supersedes references a finding_id not in the registry")
        if known_ids is not None and item["superseded_by"] not in known_ids:
            raise ValueError("superseded_by references a finding_id not in the registry")
    if item["status"] == "not_reproduced":
        runs, successes = item.get("repeat_runs"), item.get("repeat_successes")
        if (isinstance(runs, bool) or not isinstance(runs, int) or runs < 2
            or isinstance(successes, bool) or not isinstance(successes, int)
            or not 0 <= successes <= runs):
            raise ValueError("not_reproduced findings require repeat_runs >= 2 and 0 <= repeat_successes <= repeat_runs")
        if successes >= 2:
            raise ValueError("not_reproduced requires fewer than two successful repeats")
    if item["status"] == "not_measured" and not _text(item, "not_measured_reason"):
        raise ValueError("not_measured findings require a not_measured_reason")
    row = dict(item)
    row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    row["record_sha256"] = _hash({k:v for k,v in row.items() if k != "record_sha256"})
    return row

def add_finding(registry: Path, item: dict[str, Any], allow_confirmed: bool = False) -> dict[str, Any]:
    existing = load_registry(registry)
    known_ids = {row.get("finding_id") for row in existing}
    row = validate_finding(item, allow_confirmed, known_ids=known_ids)
    registry.parent.mkdir(parents=True, exist_ok=True)
    if row["finding_id"] in known_ids:
        raise ValueError("finding_id already exists: " + row["finding_id"])
    with registry.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row

def load_registry(registry: Path) -> list[dict[str, Any]]:
    if not registry.exists(): return []
    rows = []
    with registry.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip(): continue
            try: row = json.loads(line)
            except json.JSONDecodeError as exc: raise ValueError(f"invalid JSON on registry line {n}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"registry line {n} must contain a JSON object")
            if row.get("record_sha256") != _hash({k:v for k,v in row.items() if k != "record_sha256"}):
                raise ValueError(f"registry integrity check failed on line {n}")
            rows.append(row)
    return rows

def record_supersession(registry: Path, original_id: str, replacement_id: str,
                        reason: str, *, discovered_at: str | None = None) -> dict[str, Any]:
    """Append a typed supersession record; never modify the original row.

    The replacement must already exist in the registry, so the chain always
    resolves to a real record. Failures are preserved as negative evidence.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("supersession requires a reason")
    rows = load_registry(registry)
    by_id = {row.get("finding_id"): row for row in rows}
    if original_id not in by_id:
        raise ValueError("original finding_id is not in the registry")
    if replacement_id not in by_id:
        raise ValueError("replacement finding_id is not in the registry")
    original = by_id[original_id]
    suffix = 1
    while f"{original_id}-SUP-{suffix}" in by_id:
        suffix += 1
    record = {
        "finding_id": f"{original_id}-SUP-{suffix}",
        "title": f"Supersession record for {original_id}",
        "provider": original["provider"],
        "model": original["model"],
        "category": original["category"],
        "status": "superseded",
        "discovered_at": discovered_at or datetime.now(timezone.utc).isoformat(),
        "evidence_ref": original["evidence_ref"],
        "summary": "Original conclusion superseded; original row preserved verbatim.",
        "supersedes": original_id,
        "superseded_by": replacement_id,
        "supersession_reason": reason,
    }
    return add_finding(registry, record)


def save_candidate_records(report: dict[str, Any], evidence_path: str, registry: Path) -> list[dict[str, Any]]:
    """Persist exact canary-only signals as unverified; never auto-confirm them."""
    if not isinstance(report, dict) or not isinstance(report.get("results"), list):
        raise ValueError("report must contain a results list")
    existing = load_registry(registry)
    known = {row.get("finding_id") for row in existing}
    saved = []
    for result in report["results"]:
        if not isinstance(result, dict) or result.get("assessment") != "potential_guardrail_failure":
            continue
        evidence_hash = result.get("evidence_sha256")
        if (not isinstance(evidence_hash, str) or len(evidence_hash) != 64
                or any(ch not in "0123456789abcdef" for ch in evidence_hash.casefold())):
            raise ValueError("candidate result is missing a valid hexadecimal evidence_sha256")
        case_id = result.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("candidate result is missing case_id")
        finding_id = "OM-FND-" + hashlib.sha256(
            (str(report.get("provider")) + "|" + str(report.get("model")) + "|" +
             case_id + "|" + evidence_hash).encode("utf-8")
        ).hexdigest()[:12].upper()
        if finding_id in known:
            continue
        row = {
            "finding_id": finding_id,
            "title": f"Potential synthetic-canary signal in {case_id}",
            "provider": str(report.get("provider") or "unknown"),
            "model": str(result.get("model") or report.get("model") or "unknown"),
            "category": str(result.get("category") or "instruction_boundary"),
            "status": "unverified",
            "discovered_at": str(result.get("started_at") or report.get("generated_at") or
                                 datetime.now(timezone.utc).isoformat()),
            "evidence_ref": f"{evidence_path}#{case_id}",
            "evidence_sha256": evidence_hash,
            "case_id": case_id,
            "assessment": "potential_guardrail_failure",
            "summary": "Automated exact-canary signal saved for human review. This is not a confirmed vulnerability.",
        }
        saved.append(add_finding(registry, row))
        known.add(finding_id)
    return saved


def export_markdown(rows: list[dict[str, Any]], destination: Path) -> None:
    lines = ["# OpenMind Vulnerability Findings", "", "Exported: " + datetime.now(timezone.utc).isoformat(), "",
    "> Researcher-assigned statuses are not vendor acknowledgements. Unverified and intermittent results are not confirmed vulnerabilities.", ""]
    if not rows: lines.append("No findings recorded.")
    for r in rows:
        lines += [f"## {r['finding_id']} — {r['title']}", "", f"- Status: {r['status']}",
        f"- Provider/model: {r['provider']} / {r['model']}", f"- Category: {r['category']}",
        f"- Discovered: {r['discovered_at']}", f"- Evidence: {r['evidence_ref']}",
        f"- Evidence SHA-256: {r.get('evidence_sha256', 'not supplied')}",
        f"- Record SHA-256: {r['record_sha256']}", "", r["summary"], ""]
        if r.get("review_notes"): lines += ["Review notes:", "", r["review_notes"], ""]
        if r.get("reproduction_steps"): lines += ["Reproduction notes:", "", r["reproduction_steps"], ""]
        if r.get("repeat_runs") is not None:
            lines += [f"Repeatability: {r.get('repeat_successes', 0)}/{r['repeat_runs']} runs", ""]
        if r["status"] == "superseded":
            lines += [
                "Supersession chain (append-only; original row preserved):", "",
                f"- Supersedes: {r.get('supersedes', 'not supplied')}",
                f"- Superseded by: {r.get('superseded_by', 'not supplied')}",
                f"- Reason: {r.get('supersession_reason', 'not supplied')}", "",
            ]
        elif r["status"] == "not_reproduced":
            lines += [
                f"Not reproduced: {r.get('repeat_successes', 0)}/"
                f"{r.get('repeat_runs', 0)} repeat runs succeeded. "
                "Negative evidence preserved; not a confirmed failure.", "",
            ]
        elif r["status"] == "not_measured":
            lines += [
                f"Not measured: {r.get('not_measured_reason', 'not supplied')}. "
                "Unknown, not a pass.", "",
            ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registry", default="findings/registry.jsonl")
    s = p.add_subparsers(dest="command", required=True)
    a = s.add_parser("add"); a.add_argument("--input", required=True); a.add_argument("--confirm-review", action="store_true")
    l = s.add_parser("list"); l.add_argument("--status", choices=sorted(STATUSES))
    e = s.add_parser("export"); e.add_argument("--format", choices=("markdown","json"), default="markdown"); e.add_argument("--out", default="reports/findings.md")
    args = p.parse_args(argv)
    try:
        path = Path(args.registry)
        if args.command == "add":
            item = json.loads(Path(args.input).read_text(encoding="utf-8"))
            row = add_finding(path, item, args.confirm_review)
            print(f"added {row['finding_id']} status={row['status']} sha256={row['record_sha256']}")
        else:
            rows = load_registry(path)
            if args.command == "list":
                for r in rows:
                    if args.status is None or r["status"] == args.status:
                        print(f"{r['finding_id']}\t{r['status']}\t{r['provider']}\t{r['model']}\t{r['title']}")
                print(f"total={len(rows)}")
            elif args.format == "markdown":
                export_markdown(rows, Path(args.out)); print(f"exported {len(rows)} findings to {args.out}")
            else:
                dest = Path(args.out); dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"exported {len(rows)} findings to {args.out}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("error: " + str(exc), file=sys.stderr); return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
