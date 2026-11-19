"""Synchronous adapter for an operator-controlled guardrail endpoint."""
from __future__ import annotations
from .core import Verdict

def httpx_submitter(endpoint: str, *, headers: dict[str,str] | None = None, timeout: float = 15.0):
    if not endpoint.startswith("https://") and not endpoint.startswith("http://localhost") and not endpoint.startswith("http://127.0.0.1"):
        raise ValueError("endpoint must use HTTPS (HTTP is allowed only for localhost)")
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("install the optional API dependencies: pip install 'openmind-omjb[api]'") from exc

    def submit(payload: str) -> Verdict:
        with httpx.Client(timeout=timeout) as client:
            response=client.post(endpoint,json={"input":payload},headers=headers or {})
            response.raise_for_status()
            data=response.json()
        if "decision" in data:
            decision=str(data["decision"]).lower()
            if decision not in ("allow","review","block"):
                raise ValueError("unrecognized decision value")
            allowed=decision=="allow"
        elif "safe" in data:
            allowed=bool(data["safe"])
        elif "flagged" in data:
            allowed=not bool(data["flagged"])
        else:
            raise ValueError("response must include decision, safe, or flagged")
        return Verdict(allowed=allowed,latency_ms=response.elapsed.total_seconds()*1000,raw=data)
    return submit
