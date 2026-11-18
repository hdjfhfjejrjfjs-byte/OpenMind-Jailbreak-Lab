#!/usr/bin/env python3
"""Run one Guardrail Lab campaign against an OrcaRouter free model.

Takes --model and --output so several models can run in parallel with
separate reports. Uses the stored custom.orcarouter credential via a
dynamic-credentials surrogate (key only in-process, never printed or
stored). Same settings as the other 24-case campaigns: budget 36,
variants 6, delay 5. Base URL https://api.orcarouter.ai/v1 (OpenAI-compatible).

OrcaRouter free tier was capacity-limited (HTTP 429) through 2026-11-17
afternoon; the 18:05 CST retry probe on 2026-11-17 found it back, with
deepseek-v4-flash-free answering a test completion. The five free models
listed then were deepseek-v4-flash-free, deepseek-v4.1-flash-free,
tencent/hy3-free, tencent/hy4-preview-free, z-ai/glm-5.3-flash-free;
only deepseek-v4-flash-free was test-completed.

Run: python3 run_orcarouter_campaign.py
       [--model deepseek-v4.1-flash-free] [--output <path>]
Report: ~/workspace/jailbreak-lab-test-env/orcarouter-campaign-deepseek-v4-flash-free-2026-11-17.json
"""
import argparse
import os
import sys
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request  # noqa: E402

REPO = "/home/hatch/workspace/openmind-jailbreak-lab-git"
DEFAULT_MODEL = "deepseek-v4-flash-free"
DEFAULT_OUTPUT = (
    "/home/hatch/workspace/jailbreak-lab-test-env/"
    "orcarouter-campaign-deepseek-v4-flash-free-2026-11-17.json"
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--budget", default="36")
    parser.add_argument("--variants", default="6")
    parser.add_argument("--delay", default="5")
    parser.add_argument("--max-tokens", default=None,
                        help="Cap the model's maximum output tokens per request")
    args = parser.parse_args()

    req = urllib.request.Request("https://api.orcarouter.ai/v1/models")
    add_surrogate_to_request(req, "custom.orcarouter", allowed_hosts=["api.orcarouter.ai"])
    auth = req.get_header("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise SystemExit("no bearer <redacted> returned")
    os.environ["ORCAROUTER_API_KEY"] = auth[len("Bearer "):]

    sys.path.insert(0, REPO)
    os.chdir(REPO)
    from modules.guardrail_lab.cli import main as campaign_main
    argv = [
        "--provider", "openai-compatible",
        "--base-url", "https://api.orcarouter.ai/v1",
        "--model", args.model,
        "--api-key-env", "ORCAROUTER_API_KEY",
        "--campaign",
        "--budget", args.budget,
        "--variants", args.variants,
        "--delay", args.delay,
        "--output", args.output,
    ]
    if args.max_tokens is not None:
        argv += ["--max-tokens", args.max_tokens]
    return campaign_main(argv)


if __name__ == "__main__":
    sys.exit(main())
