"""Reproduction attributes for Guardrail Lab evidence.

Grounded in the canonical DWM measurement contract (config/weight/tokenizer/
chat-template hashes, prompt hash, injection point, thinking mode, parser,
truncation policy, typed not_measured with reasons) transferred to a
prompt-safety evaluation harness.

Two rules are enforced here:

1. Only *measured* fields enter config_hash. Unknown settings are recorded
   as not_measured with a reason, never guessed — a config that claims a
   setting the adapter never transmitted is worse than config drift.
2. Any token-like material is redacted before it can reach an evidence
   report (extends the provider error-detail scrubbing).

Research-purposes-only: this module contains measurement metadata only.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[2]

# Fields that enter config_hash when measured. Everything else is metadata.
_MEASURED_FIELDS = (
    "model", "provider", "base_url_fingerprint", "thinking", "temperature",
    "top_p", "max_tokens", "seed", "judge_id", "judge_hash",
    "case_set_hashes", "prompt_hash", "injection_point", "parser",
    "truncation_policy", "engine_version", "chat_template_hash",
    "tokenizer_hash", "weight_index_hash",
)

_TOKEN_LIKE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|token|secret|password)"
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def redact_config(value: Any) -> Any:
    """Redact token-like material from config values before evidence export."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if _TOKEN_LIKE.search(str(key)):
                out[key] = "***"
            elif isinstance(item, str) and (
                item.startswith("sk-") or item.startswith("AIza")
                or re.fullmatch(r"[A-Za-z0-9_\-]{32,}", item)
            ):
                out[key] = "***"
            else:
                out[key] = redact_config(item)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_config(item) for item in value]
    return value


def fingerprint_endpoint(base_url: Optional[str]) -> Optional[str]:
    """A redacted, stable identity for an endpoint (no key, no query)."""
    if not base_url:
        return None
    from urllib.parse import urlsplit

    parts = urlsplit(base_url)
    return hashlib.sha256(
        f"{parts.scheme}://{parts.hostname}:{parts.port or ''}{parts.path}".encode("utf-8")
    ).hexdigest()[:16]


def file_sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class RunConfig:
    """Reproduction attributes for one run. None = not measured."""

    model: Optional[str] = None
    provider: Optional[str] = None
    base_url_fingerprint: Optional[str] = None
    thinking: Optional[bool] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    seed: Optional[int] = None
    judge_id: Optional[str] = None
    judge_hash: Optional[str] = None
    case_set_hashes: Optional[dict] = None
    prompt_hash: Optional[str] = None
    injection_point: Optional[str] = None
    parser: Optional[str] = None
    truncation_policy: Optional[str] = None
    engine_version: Optional[str] = None
    chat_template_hash: Optional[str] = None
    tokenizer_hash: Optional[str] = None
    weight_index_hash: Optional[str] = None
    not_measured: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def validate(self) -> None:
        for name in ("temperature", "top_p"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ValueError(f"{name} must be a number, not a boolean")
        for name in ("max_tokens", "seed"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"{name} must be an integer")
        if self.thinking is not None and not isinstance(self.thinking, bool):
            raise ValueError("thinking must be a boolean")
        for item in self.not_measured:
            if not isinstance(item, dict) or "item" not in item or "reason" not in item:
                raise ValueError("not_measured entries require item and reason")

    def measured(self) -> dict:
        """Measured fields only — the sole input to config_hash."""
        return {
            name: getattr(self, name)
            for name in _MEASURED_FIELDS
            if getattr(self, name) is not None
        }

    def config_hash(self) -> str:
        """Stable hash of measured settings; not_measured reasons excluded."""
        return hashlib.sha256(_canonical(self.measured()).encode("utf-8")).hexdigest()

    def evidence_block(self) -> dict:
        """Redacted, hash-bound reproduction block for report provenance."""
        self.validate()
        return {
            "run_config": redact_config({
                k: v for k, v in asdict(self).items()
                if k not in ("metadata",)
            }),
            "config_hash": self.config_hash(),
            "not_measured": list(self.not_measured),
            "schema_version": "1.2",
        }


def case_set_hashes(benchmark_path: Optional[Path] = None) -> dict:
    """Hash the actual case files a run draws from (discovered, not guessed)."""
    candidates = {
        "core_cases": _ROOT / "modules" / "guardrail_lab" / "cases.py",
        "source_cases": _ROOT / "data" / "source_corpus" / "safe_adaptations.jsonl",
    }
    if benchmark_path is not None:
        candidates["benchmark"] = Path(benchmark_path)
    else:
        benchmarks = sorted((_ROOT / "data").glob("benchmark_v*.jsonl"))
        if benchmarks:
            candidates["benchmark"] = benchmarks[-1]
    return {name: file_sha256(path) for name, path in candidates.items()
            if file_sha256(path) is not None}


def not_measured_entry(item: str, reason: str) -> dict:
    return {"item": item, "reason": reason}


def default_not_measured(config: RunConfig, *, benchmark_path: Optional[Path] = None) -> list:
    """Reasons for fields that were not measured in a default CLI run."""
    reasons = {
        "temperature": "adapter does not transmit temperature; set only if provider supports it",
        "top_p": "adapter does not transmit top_p",
        "seed": "adapter does not transmit seed",
        "judge_id": "no judge attached to this run",
        "judge_hash": "no judge attached to this run",
        "prompt_hash": "prompt hash computed per case, not per run",
        "injection_point": "injection point is case-defined, not a run setting",
        "parser": "response parser is provider-defined",
        "truncation_policy": "truncation inferred from finish_reason only",
        "engine_version": "not reported by hosted provider",
        "chat_template_hash": "not reported by hosted provider",
        "tokenizer_hash": "not reported by hosted provider",
        "weight_index_hash": "not reported by hosted provider",
        "thinking": "not transmitted by this adapter",
    }
    for name, reason in reasons.items():
        if getattr(config, name) is None and name in _MEASURED_FIELDS:
            yield not_measured_entry(name, reason)
