"""Adapter for OpenAI-compatible local and hosted model endpoints.

Supports local inference servers (Ollama, vLLM, LM Studio, llama.cpp,
LocalAI, TGI when configured for its OpenAI-compatible route) and hosted
providers exposing /v1/chat/completions. No third-party dependency required.
"""
from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import math
import ipaddress
from typing import Dict, List, Optional, Tuple

from .runner import GuardrailRunError

# Defaults are convenience presets only; --base-url overrides them.
PRESET_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "vllm": "http://localhost:8000/v1",
    "lm-studio": "http://localhost:1234/v1",
    "llama-cpp": "http://localhost:8080/v1",
    "localai": "http://localhost:8080/v1",
    # Hosted OpenAI-compatible providers. Each needs its own API key
    # (see PRESET_API_KEY_ENVS) and a --model.
    "deepseek": "https://api.deepseek.com/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "moonshot": "https://api.moonshot.ai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
}
PRESET_API_KEY_ENVS = {
    "deepseek": "DEEPSEEK_API_KEY",
    "glm": "ZHIPUAI_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "together": "TOGETHER_API_KEY",
}

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 60.0


def _is_finite_number(value):
    """Return whether value is finite, excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _sleep_before_retry(attempt, headers):
    """Backoff before a retry: honor Retry-After when the server sent
    one, otherwise exponential backoff, capped. A negative, NaN, or
    infinite Retry-After is not a usable delay; fall back to backoff."""
    delay = None
    if headers is not None:
        raw = headers.get("Retry-After")
        if raw:
            try:
                parsed = float(raw)
            except ValueError:
                parsed = None
            if parsed is not None and math.isfinite(parsed) and parsed >= 0:
                delay = parsed
    if delay is None:
        delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
    time.sleep(min(delay, BACKOFF_MAX_SECONDS))


def _chat_url(base_url: str, *, has_api_key: bool = False) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise GuardrailRunError("OpenAI-compatible base URL cannot be empty")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise GuardrailRunError("base URL must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise GuardrailRunError("base URL must not contain credentials, query parameters, or a fragment")
    host = parsed.hostname.casefold()
    is_loopback = host == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if parsed.scheme != "https" and not is_loopback:
        raise GuardrailRunError("HTTPS is required for non-local endpoints; plain HTTP is allowed only on loopback")
    if has_api_key and parsed.scheme != "https" and not is_loopback:
        raise GuardrailRunError("refusing to send an API key over non-HTTPS transport")
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        return value
    return value + "/chat/completions"


def call_openai_compatible(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str],
    base_url: Optional[str] = None,
    api_key_env: str = "OPENAI_COMPAT_API_KEY",
    timeout: float = 90.0,
    max_tokens: Optional[int] = None,
) -> Tuple[str, str, Dict]:
    """Call an OpenAI Chat Completions-compatible endpoint.

    Local endpoints may omit an API key. Hosted endpoints should set the
    environment variable named by api_key_env. The key is only sent in the
    Authorization header and is never written to evidence reports.

    When max_tokens is set it is sent in the request payload. Some hosted
    providers price a request against the full requested output ceiling
    (when omitted they assume the model's maximum), so capping it keeps
    low-balance accounts usable.
    """
    if not isinstance(messages, list) or not messages:
        raise GuardrailRunError("messages must be a non-empty list")
    for item in messages:
        if (not isinstance(item, dict)
                or item.get("role") not in ("system", "user", "assistant")
                or not isinstance(item.get("content"), str)):
            raise GuardrailRunError("messages must contain role/content text objects")

    chosen_model = model or os.getenv("OPENAI_COMPAT_MODEL")
    if not chosen_model:
        raise GuardrailRunError("Set --model or OPENAI_COMPAT_MODEL for this endpoint")
    chosen_url = base_url or os.getenv("OPENAI_COMPAT_BASE_URL")
    if not chosen_url:
        raise GuardrailRunError("Set a base URL with --base-url or OPENAI_COMPAT_BASE_URL")

    if not _is_finite_number(timeout) or timeout <= 0:
        raise GuardrailRunError("timeout must be a finite positive number")
    if max_tokens is not None and (
            isinstance(max_tokens, bool) or not isinstance(max_tokens, int)
            or max_tokens <= 0):
        raise GuardrailRunError("max_tokens must be a positive integer")
    api_key = os.getenv(api_key_env) if api_key_env else None
    endpoint = _chat_url(chosen_url, has_api_key=bool(api_key))
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload_data = {"model": chosen_model, "messages": messages}
    if max_tokens is not None:
        payload_data["max_tokens"] = max_tokens
    payload = json.dumps(payload_data).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload,
                                     headers=headers, method="POST")
    started = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1500]
            if api_key and api_key in detail:
                detail = detail.replace(api_key, "***")
            retryable = exc.code == 429 or exc.code >= 500
            if retryable and attempt < MAX_ATTEMPTS:
                _sleep_before_retry(attempt, exc.headers)
                continue
            raise GuardrailRunError(
                f"Compatible endpoint HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError,
                http.client.IncompleteRead,
                http.client.RemoteDisconnected) as exc:
            if attempt < MAX_ATTEMPTS:
                _sleep_before_retry(attempt, None)
                continue
            raise GuardrailRunError(
                f"Compatible endpoint connection failed: {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GuardrailRunError(
                f"Compatible endpoint returned invalid JSON: {exc}") from exc

    if not isinstance(body, dict):
        raise GuardrailRunError("Compatible endpoint response must be a JSON object")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise GuardrailRunError("Compatible endpoint response lacks choices[0] as a valid object")
    message = choices[0].get("message")
    if not isinstance(message, dict) or "content" not in message:
        raise GuardrailRunError("Compatible endpoint response lacks choices[0].message.content")
    content = message["content"]
    if isinstance(content, list):
        # Some compatible servers return content-part arrays.
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                part_text = part.get("text")
                if isinstance(part_text, str):
                    text_parts.append(part_text)
        content = "\n".join(text_parts)
    if not isinstance(content, str):
        raise GuardrailRunError("Compatible endpoint returned non-text message content")

    actual_model = body.get("model") or chosen_model
    usage = body.get("usage")
    if usage is not None and not isinstance(usage, (dict, list, str, int, float, bool)):
        usage = str(usage)
    metadata = {
        "request_id": body.get("id") if isinstance(body.get("id"), (str, int)) else None,
        "finish_reason": choices[0].get("finish_reason") if isinstance(choices[0].get("finish_reason"), (str, int, float, bool)) else None,
        "usage": usage,
        "endpoint_type": "openai-compatible",
        "latency_seconds": round(time.monotonic() - started, 3),
    }
    return actual_model, content, {key: value for key, value in metadata.items() if value is not None}
