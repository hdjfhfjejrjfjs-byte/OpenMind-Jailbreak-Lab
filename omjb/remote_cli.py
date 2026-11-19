"""Command-line entry point for bounded endpoint/provider evaluation."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .probes import load_probes
from .provider_eval import ProviderEvaluationPipeline
from .providers import ProviderRegistry, QuotaTracker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, help="Validated OMJB probe corpus")
    parser.add_argument("--endpoint", required=True, help="Operator-owned guard HTTP(S) endpoint")
    parser.add_argument("--token-env", default="OMJB_GUARD_TOKEN",
                        help="Environment variable containing the endpoint bearer token")
    parser.add_argument("--provider", help="Configured provider name, e.g. openai or anthropic")
    parser.add_argument("--model", help="Provider model identifier")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--max-usd", type=float, default=2.0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--out", default="omjb_remote_report.json")
    args = parser.parse_args()

    if args.max_tokens < 1 or args.concurrency < 1:
        parser.error("--max-tokens and --concurrency must be positive")
    if bool(args.provider) != bool(args.model):
        parser.error("--provider and --model must be supplied together")

    headers = {}
    import os
    token = os.getenv(args.token_env)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    probes = load_probes(args.corpus)
    quota = QuotaTracker(max_total_usd=args.max_usd)
    registry = ProviderRegistry.from_env(quota)
    pipeline = ProviderEvaluationPipeline(registry)
    result = asyncio.run(pipeline.run(
        probes, endpoint=args.endpoint, provider_name=args.provider,
        model=args.model, headers=headers, concurrency=args.concurrency,
        max_tokens=args.max_tokens,
    ))
    Path(args.out).write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
