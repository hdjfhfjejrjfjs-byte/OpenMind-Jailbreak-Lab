"""Load validated, source-attributed safe adaptations into Guardrail Lab."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .cases import Case
from .source_registry import (
    CATEGORIES,
    SURFACES,
    EXPECTED_TOTAL,
    case_number,
    expected_assignment,
    expected_prompt,
)

_ROOT = Path(__file__).resolve().parents[2]
_DATA = _ROOT / "data" / "source_corpus" / "safe_adaptations.jsonl"
_INVENTORY = _ROOT / "data" / "source_corpus" / "source_inventory.jsonl"
_MANIFEST = _ROOT / "data" / "source_corpus" / "manifest.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_TEXT = (
    "case_id", "source_id", "source_path", "source_sha256",
    "category", "variant", "prompt", "expected_signal", "canary",
)


def _read_jsonl(path: Path):
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in {path.name} line {line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"expected a JSON object in {path.name} line {line_no}")
            rows.append((line_no, row))
    return rows


def load_source_cases():
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    inventory_bytes = _INVENTORY.read_bytes()
    if hashlib.sha256(inventory_bytes).hexdigest() != manifest.get("inventory_sha256"):
        raise ValueError("source inventory SHA-256 does not match manifest")
    adaptations_bytes = _DATA.read_bytes()
    if hashlib.sha256(adaptations_bytes).hexdigest() != manifest.get("adaptations_sha256"):
        raise ValueError("safe adaptations SHA-256 does not match manifest")
    inventory = {}
    for line_no, row in _read_jsonl(_INVENTORY):
        source_id = row.get("id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError(f"missing source inventory ID on line {line_no}")
        if source_id in inventory:
            raise ValueError(f"duplicate source inventory ID: {source_id}")
        inventory[source_id] = row

    cases = []
    seen_case_ids = set()
    seen_source_ids = set()
    seen_canaries = set()
    for line_no, row in _read_jsonl(_DATA):
        for field in _REQUIRED_TEXT:
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"missing or invalid {field} in safe adaptations line {line_no}")
        if row.get("runnable") is not True or row.get("adaptation") != "safe_pattern_adaptation":
            raise ValueError(f"unsafe or invalid source case on line {line_no}")
        if not row["case_id"].startswith("GL-SRC-"):
            raise ValueError(f"invalid source case ID on line {line_no}")
        if not _SHA256.fullmatch(row["source_sha256"]):
            raise ValueError(f"invalid source SHA-256 on line {line_no}")
        if not re.fullmatch(r"SAFE-MARKER-[0-9]{3}", row["canary"]):
            raise ValueError(f"invalid safe canary on line {line_no}")
        category = row["category"]
        variant = row["variant"]
        if category not in CATEGORIES or variant not in SURFACES:
            raise ValueError(f"unapproved source adaptation category or variant on line {line_no}")
        if row["expected_signal"] != CATEGORIES[category][0]:
            raise ValueError(f"unapproved source adaptation category or signal on line {line_no}")
        expected_category, expected_variant = expected_assignment(case_number(row["case_id"]))
        if (category, variant) != (expected_category, expected_variant):
            raise ValueError(
                f"source adaptation {row['case_id']} breaks the balanced factorial assignment "
                f"(expected {expected_category}/{expected_variant})"
            )
        if row["prompt"] != expected_prompt(category, variant, row["canary"]):
            raise ValueError(f"source adaptation does not match an approved safe template on line {line_no}")
        for value, seen, label in (
            (row["case_id"], seen_case_ids, "case ID"),
            (row["source_id"], seen_source_ids, "source ID"),
            (row["canary"], seen_canaries, "canary"),
        ):
            if value in seen:
                raise ValueError(f"duplicate {label} in source adaptations: {value}")
            seen.add(value)

        source = inventory.get(row["source_id"])
        if source is None:
            raise ValueError(f"unknown source ID {row['source_id']} on line {line_no}")
        if (source.get("path") != row["source_path"]
                or source.get("sha256") != row["source_sha256"]):
            raise ValueError(f"source provenance mismatch for {row['source_id']}")
        if source.get("status") != "metadata_only" or source.get("runnable") is True:
            raise ValueError(f"source {row['source_id']} is not eligible for adaptation")
        if source.get("bytes", 0) <= 1:
            raise ValueError(f"empty source {row['source_id']} cannot produce a test case")

        cases.append(Case(
            row["case_id"],
            "source_" + row["category"],
            row["prompt"],
            row["expected_signal"],
            row["canary"],
            False,
            row["source_id"],
            row["source_path"],
            row["source_sha256"],
            row["variant"],
        ))

    if len(cases) != EXPECTED_TOTAL:
        raise ValueError(f"expected {EXPECTED_TOTAL} safe source adaptations, found {len(cases)}")
    return tuple(cases)


SOURCE_CASES = load_source_cases()
