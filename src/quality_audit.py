"""Non-destructive benchmark quality audit; reports warnings separately from errors."""
from collections import Counter, defaultdict
import json
import sys
from pathlib import Path


def audit(rows):
    """Audit parsed JSONL records without crashing on malformed row shapes."""
    errors, warnings = [], []
    if not isinstance(rows, list):
        return {
            "schema_version": "1.0", "record_count": 0,
            "split_counts": {}, "family_counts": {"adversarial": {}, "benign": {}},
            "errors": ["dataset must be a list of JSON objects"],
            "warnings": [], "status": "fail",
        }

    valid_rows = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"record {index}: must be a JSON object")
        else:
            valid_rows.append(row)

    ids = []
    for index, row in enumerate(valid_rows, 1):
        case_id = row.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            errors.append(f"record {index}: id must be non-empty text")
        else:
            ids.append(case_id)
        for field in ("split", "family"):
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"record {index}: {field} must be non-empty text")
    if len(ids) != len(set(ids)):
        errors.append("duplicate case IDs detected")

    prompts = defaultdict(list)
    for row in valid_rows:
        prompt = row.get("user_prompt")
        if isinstance(prompt, str):
            prompts[" ".join(prompt.casefold().split())].append(row.get("id"))
    for matches in prompts.values():
        if len(matches) > 1:
            warnings.append("duplicate normalized prompt: " + ", ".join(map(str, matches)))

    by_split_family = Counter(
        (row.get("split"), row.get("family")) for row in valid_rows
        if isinstance(row.get("split"), str) and isinstance(row.get("family"), str)
    )
    adversarial_families = {family for (split, family), count in by_split_family.items()
                            if split == "adversarial" and count}
    benign_families = {family for (split, family), count in by_split_family.items()
                       if split == "benign" and count}
    if len(benign_families) == 1:
        warnings.append("benign controls use only one family; diversify control task types")
    sparse = sorted(str(family) for family in adversarial_families
                    if by_split_family[("adversarial", family)] == 1)
    if sparse:
        warnings.append("singleton adversarial families need more coverage: " + ", ".join(sparse))
    overlap = adversarial_families & benign_families
    if overlap:
        warnings.append("families appear in both splits; verify split intent: " + ", ".join(sorted(map(str, overlap))))
    secret_leaks = [row.get("id") for row in valid_rows
                    if row.get("split") == "benign" and row.get("synthetic_secret") is not None]
    if secret_leaks:
        errors.append("benign controls contain synthetic_secret: " + ", ".join(map(str, secret_leaks)))
    if not valid_rows:
        errors.append("dataset contains no valid records")

    return {
        "schema_version": "1.0",
        "record_count": len(valid_rows),
        "split_counts": dict(Counter(row.get("split") for row in valid_rows
                                      if isinstance(row.get("split"), str))),
        "family_counts": {
            split: dict(Counter(row.get("family") for row in valid_rows
                                if row.get("split") == split
                                and isinstance(row.get("family"), str)))
            for split in ("adversarial", "benign")
        },
        "errors": errors,
        "warnings": warnings,
        "status": "fail" if errors else ("review" if warnings else "pass"),
    }


def audit_file(path):
    try:
        rows = []
        for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                return {"schema_version": "1.0", "record_count": 0,
                        "errors": [f"line {line_no}: {exc}"],
                        "warnings": [], "status": "fail"}
    except (OSError, UnicodeError) as exc:
        return {"schema_version": "1.0", "record_count": 0, "errors": [str(exc)],
                "warnings": [], "status": "fail"}
    return audit(rows)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/benchmark_v0.8.0.jsonl"
    result = audit_file(target)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(1 if result["status"] == "fail" else 0)
