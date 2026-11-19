"""CLI for the reviewed mutation engine and offline trace utilities."""
import argparse
import json
import os
import sys
from pathlib import Path

from ..probes import load_probes
from .adapter import httpx_submitter
from .config import resolve_endpoint_config
from .decoder_experiment import write_case
from .engine import Engine
from .replay import compare_traces
from .spec import load_spec


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "chat-eval":
        parser = argparse.ArgumentParser(prog="omjb-mutate chat-eval")
        parser.add_argument("--corpus", required=True)
        parser.add_argument("--target", action="append", required=True,
                            help="provider:model; repeat for a cross-provider campaign (e.g. gemini:gemini-2.5-flash)")
        parser.add_argument("--base-url", help="custom endpoint for openai-compatible or provider proxy")
        parser.add_argument("--api-key-env", help="environment variable holding the provider API key")
        parser.add_argument("--timeout", type=float, default=60)
        parser.add_argument("--workers", type=int, default=4)
        parser.add_argument("--max-requests", type=int, default=100)
        parser.add_argument("--max-seconds", type=float, default=300)
        parser.add_argument("--max-usd", type=float, default=0,
                            help="finite campaign USD ceiling; use 0 only for free/local endpoints")
        parser.add_argument("--estimated-request-cost", type=float, default=0,
                            help="conservative upper-bound cost per provider request")
        parser.add_argument("--temperature", type=float, default=0)
        parser.add_argument("--max-tokens", type=int, default=1024)
        parser.add_argument("--output", default="multi-provider-report.json")
        args = parser.parse_args(argv[1:])
        from .chat_completions import run_campaign_from_specs
        try:
            report = run_campaign_from_specs(
                args.corpus, targets=args.target, base_url=args.base_url,
                api_key_env=args.api_key_env, timeout=args.timeout,
                max_workers=args.workers, max_requests=args.max_requests,
                max_seconds=args.max_seconds, max_usd=args.max_usd,
                estimated_request_cost=args.estimated_request_cost,
                temperature=args.temperature, max_tokens=args.max_tokens,
                output=args.output,
            )
        except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
            parser.error(str(exc))
        print(json.dumps({k: v for k, v in report.items() if k != "results"},
                         indent=2, sort_keys=True))
        print(f"Full evidence written to {args.output}")
        return 0
    if argv and argv[0] == "replay":
        parser = argparse.ArgumentParser(prog="omjb-mutate replay")
        parser.add_argument("--baseline", required=True)
        parser.add_argument("--candidate", required=True)
        args = parser.parse_args(argv[1:])
        print(json.dumps(compare_traces(args.baseline, args.candidate), indent=2, sort_keys=True))
        return 0
    if argv and argv[0] == "decoder-fixture":
        parser = argparse.ArgumentParser(prog="omjb-mutate decoder-fixture")
        parser.add_argument("--output", default="decoder-boundary-case.json")
        args = parser.parse_args(argv[1:])
        write_case(args.output)
        print(json.dumps({"written": args.output, "case_id": "DECODER-BOUNDARY-001"}))
        return 0

    parser = argparse.ArgumentParser(prog="omjb-mutate")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--probe-id", required=True)
    parser.add_argument("--endpoint")
    parser.add_argument("--config", help="JSON config (or YAML when the yaml extra is installed)")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--token-env")
    parser.add_argument("--trace", default="mutation-trace.jsonl")
    parser.add_argument("--estimated-request-cost", type=float, required=True,
                        help="conservative per-request USD upper bound; pass 0 explicitly only for a free/local endpoint")
    args = parser.parse_args(argv)

    import math
    if not math.isfinite(args.estimated_request_cost) or args.estimated_request_cost < 0:
        parser.error("--estimated-request-cost must be finite and non-negative")
    try:
        endpoint_config = resolve_endpoint_config(
            cli_endpoint=args.endpoint, cli_timeout=args.timeout,
            cli_token_env=args.token_env, config_path=args.config)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    probes = load_probes(args.corpus)
    matches = [p for p in probes if p.id == args.probe_id]
    if len(matches) != 1:
        parser.error(f"expected exactly one probe with id {args.probe_id!r}; found {len(matches)}")
    probe = matches[0]
    if probe.expected != "comply" or probe.meta.get("mutation_safe") is not True:
        parser.error("selected probe must be human-reviewed benign: expected=comply and meta.mutation_safe=true")
    token = os.environ.get(endpoint_config["token_env"])
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    spec = load_spec(json.loads(Path(args.spec).read_text(encoding="utf-8")))
    submit = httpx_submitter(endpoint_config["endpoint"], headers=headers, timeout=endpoint_config["timeout"])
    engine = Engine(spec, probe, submit, approved_benign=True,
                    estimate_cost=lambda _payload: args.estimated_request_cost,
                    trace_path=args.trace)
    report = engine.run()
    print(json.dumps({
        "spec_hash": spec.hash(), "probe_id": probe.id, "submitted": report.submitted,
        "allowed": report.allowed, "blocked": report.blocked, "errors": report.errors,
        "skipped": report.skipped, "allow_rate": report.allow_rate, "by_arm": report.by_arm
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
