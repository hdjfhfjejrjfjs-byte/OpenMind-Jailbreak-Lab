"""Compare saved Guardrail Lab reports without scoring incomplete evidence."""
import argparse
import json
from pathlib import Path

INCONCLUSIVE_ASSESSMENTS = {
    "inconclusive", "partial_run", "not_run", "incomplete",
    "partial", "empty", "not_received", "unknown",
}
INCONCLUSIVE_RESPONSE_STATUSES = {
    "incomplete", "partial", "empty", "not_received", "truncated", "length",
}


def _outcome(item):
    """Return (assessment, comparable) without treating incomplete evidence as a score."""
    assessment = item.get("assessment", "unknown")
    if not isinstance(assessment, str):
        assessment = "unknown"
    assessment = assessment.strip() or "unknown"
    response_status = item.get("provider_response_status")
    if response_status is None:
        response_status = item.get("response_status")
    response_status = (
        response_status.strip().casefold()
        if isinstance(response_status, str) else ""
    )
    finish_reason = item.get("finish_reason")
    if isinstance(finish_reason, str):
        finish_reason = finish_reason.strip().casefold()
    truncated = item.get("truncated") is True or finish_reason == "length"
    comparable = (
        assessment.casefold() not in INCONCLUSIVE_ASSESSMENTS
        and response_status not in INCONCLUSIVE_RESPONSE_STATUSES
        and not truncated
    )
    return assessment, comparable


def config_equivalence(reports):
    """Compare reproduction attributes across reports.

    A missing or unknown config is reported as not_measured; it is never
    assumed equivalent. Divergence means the reports cannot support a
    controlled comparison.
    """
    blocks = []
    for report in reports:
        prov = report.get("provenance") or {}
        blocks.append({
            "label": report.get("provider", "unknown"),
            "config_hash": prov.get("config_hash"),
            "not_measured_count": len(prov.get("not_measured") or []),
        })
    hashes = {b["config_hash"] for b in blocks}
    if any(h is None for h in hashes):
        return {
            "status": "not_measured",
            "reason": "one or more reports lack a config_hash",
            "blocks": blocks,
        }
    if len(hashes) != 1:
        return {
            "status": "divergent",
            "reason": "reports were produced under different measured configurations",
            "blocks": blocks,
        }
    return {"status": "equivalent", "blocks": blocks}


def compare_reports(reports, *, strict_config=False):
    if len(reports) < 2:
        raise ValueError("at least two reports are required")
    equivalence = config_equivalence(reports)
    indexed = []
    source_labels = set()
    for report in reports:
        results = report.get("results")
        if not isinstance(results, list):
            raise ValueError("each report must contain a results array")
        mapping = {}
        for item in results:
            case_id = item.get("case_id")
            if not isinstance(case_id, str) or not case_id:
                raise ValueError("every result must have a non-empty case_id")
            if case_id in mapping:
                raise ValueError("duplicate case_id in report: " + case_id)
            mapping[case_id] = _outcome(item)
        provider = report.get("provider", "unknown")
        model = report.get("model")
        label = f"{provider}/{model or 'unspecified'}"
        if label in source_labels:
            raise ValueError("duplicate provider/model report label: " + label)
        source_labels.add(label)
        indexed.append((provider, model, mapping))
    common = set.intersection(*(set(item[2]) for item in indexed))
    union = set.union(*(set(item[2]) for item in indexed))
    rows, disagreements = [], []
    comparable_case_ids = []
    config_incomparable = strict_config and equivalence["status"] != "equivalent"
    for case_id in sorted(union):
        outcomes = {}
        all_present = True
        all_comparable = True
        scored_values = []
        for provider, model, mapping in indexed:
            label = f"{provider}/{model or 'unspecified'}"
            entry = mapping.get(case_id)
            if entry is None:
                all_present = False
                all_comparable = False
                outcomes[label] = None
                continue
            assessment, comparable = entry
            outcomes[label] = assessment
            if comparable:
                scored_values.append(assessment)
            else:
                all_comparable = False
        agreement = (
            len(scored_values) == len(indexed)
            and len(set(scored_values)) == 1
        )
        case_comparable = all_present and all_comparable and not config_incomparable
        if case_comparable:
            comparable_case_ids.append(case_id)
        rows.append({
            "case_id": case_id,
            "outcomes": outcomes,
            "comparable": case_comparable,
            "agreement": agreement if case_comparable else None,
        })
        if not (case_comparable and agreement):
            disagreements.append(case_id)
    agreement_rate = (
        sum(row["agreement"] for row in rows if row["comparable"])
        / len(comparable_case_ids)
        if comparable_case_ids else None
    )
    provider_summaries = []
    for provider, model, mapping in indexed:
        counts = {}
        inconclusive_count = 0
        for assessment, comparable in mapping.values():
            counts[assessment] = counts.get(assessment, 0) + 1
            if not comparable:
                inconclusive_count += 1
        provider_summaries.append({
            "provider": provider,
            "model": model,
            "case_count": len(mapping),
            "inconclusive_count": inconclusive_count,
            "assessment_counts": counts,
        })
    # Descriptive dispersion only. One row per case per provider with repeated
    # measures and provider-level correlation; a naive independent-Bernoulli
    # confidence interval would imply false precision. NOT a confidence bound.
    n_observations = sum(len(mapping) for _, _, mapping in indexed)
    uncertainty = {
        "kind": "descriptive_dispersion",
        "n_observations": n_observations,
        "comparable_case_count": len(comparable_case_ids),
        "excluded_case_count": len(union) - len(comparable_case_ids),
        "agreement_rate": agreement_rate,
        "note": (
            "Descriptive only: n_observations counts case-provider rows, not "
            "independent trials. Repeated measures and provider-level "
            "correlation require a cluster/bootstrap design before any "
            "confidence claim. No uncertainty interval is published."
        ),
    }
    interpretation = (
        "Agreement is calculated only when every report contains a scored "
        "assessment for the case. Inconclusive, partial, empty, not-received, "
        "truncated, and not-run outcomes are excluded from the agreement "
        "denominator; missing cases remain distinct. Agreement compares "
        "automated labels only and is not a security score or proof of "
        "equivalent model behavior. Review full transcripts and normalize "
        "run conditions before drawing conclusions."
    )
    if equivalence["status"] == "not_measured":
        interpretation += (
            " Config equivalence could not be established: one or more reports "
            "lack reproduction attributes; treat any comparison as uncontrolled."
        )
    elif equivalence["status"] == "divergent":
        interpretation += (
            " Config equivalence failed: reports used different measured "
            "settings; disagreement may be config drift, not model behavior."
        )
    if config_incomparable:
        interpretation += (
            " Strict config mode marked every case incomparable and suppressed "
            "agreement rates."
        )
    return {
        "schema_version": "1.2",
        "config_equivalence": equivalence,
        "strict_config": strict_config,
        "providers": provider_summaries,
        "common_case_count": len(common),
        "union_case_count": len(union),
        "comparable_case_count": len(comparable_case_ids),
        "excluded_inconclusive_case_count": len(common) - len(comparable_case_ids),
        "missing_case_ids": {
            f"{p}/{m or 'unspecified'}": sorted(union - set(mapping))
            for p, m, mapping in indexed
        },
        "agreement_rate_on_comparable_common_cases": agreement_rate,
        "agreement_rate_on_common_cases": agreement_rate,
        "disagreement_or_missing_or_inconclusive_case_ids": disagreements,
        "cases": rows,
        "uncertainty": uncertainty,
        "interpretation": interpretation,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", help="two or more Guardrail Lab JSON report paths")
    parser.add_argument("--output", help="optional JSON output path")
    parser.add_argument(
        "--allow-unknown-config", action="store_true",
        help="compare legacy reports without reproduction attributes (uncontrolled)",
    )
    args = parser.parse_args(argv)
    try:
        reports = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.reports]
        result = compare_reports(reports, strict_config=not args.allow_unknown_config)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
