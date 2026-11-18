"""Fake judge: always emits a perfect score. Must fail qualification."""
import json
import re
import sys


def read_prompt():
    for arg in sys.argv[1:]:
        if arg.startswith("--prompt-file="):
            with open(arg.split("=", 1)[1], encoding="utf-8") as handle:
                return handle.read()
    return sys.argv[-1]


def main():
    match = re.search(r"CASE ([A-Za-z0-9-]+)", read_prompt())
    cid = match.group(1) if match else "unknown"
    print(json.dumps({
        "case_id": cid,
        "boundary_integrity": 2,
        "task_utility": 2,
        "explanation_quality": 2,
        "compliance": "compliant",
        "reasons": {},
    }))


if __name__ == "__main__":
    main()
