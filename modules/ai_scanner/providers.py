"""Minimal standard-library adapters for provider APIs."""
import http.client
import ipaddress
import json
import math
import os
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit


class ProviderError(RuntimeError):
    """Provider failure with stable machine-readable classification."""
    def __init__(self, message, category="provider_error", code="provider_error", http_status=None, retryable=False):
        super().__init__(message)
        self.category, self.code = category, code
        self.http_status, self.retryable = http_status, retryable

    def as_dict(self):
        return {"category": self.category, "code": self.code, "http_status": self.http_status, "retryable": self.retryable, "message": str(self)}


MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 60.0


def _present(fields):
    """Drop keys whose value is None, so metadata only carries what the
    provider actually returned."""
    return {key: value for key, value in fields.items() if value is not None}


def _sleep_before_retry(attempt, headers):
    """Backoff before a retry: honor Retry-After when the provider sent
    one, otherwise exponential backoff, capped."""
    delay = None
    if headers is not None:
        raw = headers.get("Retry-After")
        if raw:
            try:
                parsed = float(raw)
            except ValueError:
                parsed = None
            # A negative, NaN, or infinite Retry-After is not a usable
            # delay (time.sleep would raise); fall back to backoff.
            if parsed is not None and math.isfinite(parsed) and parsed >= 0:
                delay = parsed
    if delay is None:
        delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
    time.sleep(min(delay, BACKOFF_MAX_SECONDS))


def _scrub_error_detail(detail: str, headers=None) -> str:
    """Remove API-key material an endpoint may echo back in an error body.

    A hostile or misconfigured endpoint can reflect the Authorization or
    x-goog-api-key header value inside its error response. Error details flow
    into local evidence reports, so any echoed key material is replaced
    before the message is raised. Also removes header values sent with the
    request (except Content-Type) when headers are supplied.
    """
    scrubbed = detail
    secrets = []
    if headers:
        for name, value in headers.items():
            if name.casefold() != "content-type":
                secrets.append(str(value))
                if name.casefold() == "authorization":
                    # The endpoint may echo only the token without the
                    # "Bearer" scheme; scrub both forms.
                    parts = str(value).split(None, 1)
                    if len(parts) == 2:
                        secrets.append(parts[1])
    for secret in secrets:
        if secret and secret in scrubbed:
            scrubbed = scrubbed.replace(secret, "***")
    return scrubbed


def _post(url, headers, payload, timeout=60, max_attempts=MAX_ATTEMPTS):
    """POST JSON and return the parsed body.

    Retries transient failures (HTTP 429, HTTP 5xx, connection errors,
    timeouts) up to max_attempts times. Other 4xx errors fail at once:
    retrying a bad request cannot succeed.
    """
    data = json.dumps(payload).encode("utf-8")
    attempt = 0
    while True:
        attempt += 1
        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            detail = _scrub_error_detail(detail, headers)
            retryable = exc.code == 429 or exc.code >= 500
            if retryable and attempt < max_attempts:
                _sleep_before_retry(attempt, exc.headers)
                continue
            if exc.code in (401, 403):
                category, code, hint = "authentication", "invalid_or_unauthorized_credentials", "Check API key and project permissions."
            elif exc.code == 404:
                category, code, hint = "model_or_endpoint", "model_or_endpoint_not_found", "Check the model ID and API endpoint."
            elif exc.code == 429:
                category, code, hint = "rate_limit", "rate_limited", "Check quota/billing, reduce request rate, and retry later."
            elif exc.code == 400:
                category, code, hint = "invalid_request", "provider_rejected_request", "Check model-specific request parameters."
            elif exc.code >= 500:
                category, code, hint = "provider_service", "provider_server_error", "Provider service failed; retry later."
            else:
                category, code, hint = "http_error", "provider_http_error", "Check provider API documentation."
            raise ProviderError(f"HTTP {exc.code} ({code}): {hint} Provider detail: {detail}", category=category, code=code, http_status=exc.code, retryable=retryable) from exc
        except (urllib.error.URLError, TimeoutError,
                http.client.IncompleteRead,
                http.client.RemoteDisconnected) as exc:
            if attempt < max_attempts:
                _sleep_before_retry(attempt, None)
                continue
            raise ProviderError(str(exc), category="network", code="network_or_timeout", retryable=True) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Invalid provider response: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ProviderError(
                "Invalid provider response: expected a JSON object"
            )
        return parsed


def _with_latency(metadata, started):
    metadata["latency_seconds"] = round(time.monotonic() - started, 3)
    return metadata


def _compat_chat_url(base_url):
    """Resolve an OpenAI-compatible base URL to its chat endpoint.

    Mirrors the guardrail lab's rules: HTTPS for non-loopback hosts,
    no credentials, query, or fragment in the URL. Appends
    /chat/completions unless the path already ends with it.
    """
    value = base_url.strip().rstrip("/")
    if not value:
        raise ProviderError("OpenAI-compatible base URL cannot be empty")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ProviderError("base URL must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError(
            "base URL must not contain credentials, query parameters, "
            "or a fragment"
        )
    host = parsed.hostname.casefold()
    is_loopback = host == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if parsed.scheme != "https" and not is_loopback:
        raise ProviderError(
            "HTTPS is required for non-local endpoints; plain HTTP is "
            "allowed only on loopback"
        )
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        return value
    return value + "/chat/completions"


def _gemini_content(message):
    """Map one chat message to a Gemini content block."""
    role = "model" if message["role"] == "assistant" else "user"
    return {"role": role, "parts": [{"text": message["content"]}]}


def call_provider_messages(provider, messages, model=None, base_url=None,
                         api_key_env="OPENAI_COMPAT_API_KEY"):
    """Call one provider with a full message list and return
    (model, text, metadata).

    messages is a list of {"role": "system"|"user"|"assistant", "content": str}
    in conversation order, so multi-turn sessions send the real
    conversation so far. Single-turn callers pass one user message.
    metadata carries the provider's request id, usage, and
    finish/status information when the provider returns it, plus
    latency_seconds. The key is never placed in a URL: Gemini
    authenticates with the x-goog-api-key request header, OpenAI
    and Anthropic with their usual authorization headers.
    The "openai-compatible" provider talks to any /v1/chat/completions
    endpoint (DeepSeek, GLM, Moonshot, NVIDIA, OpenRouter, Groq,
    Together, local servers). It takes its base URL from base_url or
    OPENAI_COMPAT_BASE_URL, its key from api_key_env (may be empty for
    local servers), and its model from model or OPENAI_COMPAT_MODEL.
    """
    provider = provider.lower()
    if not messages or not all(
        isinstance(item, dict)
        and item.get("role") in ("system", "user", "assistant")
        and isinstance(item.get("content"), str)
        for item in messages
    ):
        raise ProviderError(
            "messages must be a non-empty list of system/user/assistant messages"
        )
    started = time.monotonic()
    # OPENAI
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ProviderError("OPENAI_API_KEY is not set; add it to environment or CI secrets.", category="configuration", code="missing_api_key")
        model = model or os.getenv(
            "OPENAI_MODEL",
            "gpt-4.1-mini",
        )
        body = _post(
            "https://api.openai.com/v1/responses",
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "input": messages,
            },
        )
        output = body.get("output", [])
        if not isinstance(output, list):
            raise ProviderError(
                "Invalid provider response: 'output' must be a list")
        parts = []
        for output_item in output:
            if not isinstance(output_item, dict):
                continue
            content = output_item.get("content", [])
            if not isinstance(content, list):
                raise ProviderError(
                    "Invalid provider response: 'content' must be a list")
            for item in content:
                if not isinstance(item, dict):
                    continue
                if (item.get("type") == "output_text"
                        and isinstance(item.get("text"), str)
                        and item["text"]):
                    parts.append(item["text"])
                elif (item.get("type") == "refusal"
                      and isinstance(item.get("refusal"), str)
                      and item["refusal"]):
                    parts.append(f"[refusal] {item['refusal']}")
        text = "\n".join(parts)
        metadata = _with_latency(_present({
            "request_id": body.get("id"),
            "status": body.get("status"),
            "incomplete_details": body.get("incomplete_details"),
            "usage": body.get("usage"),
            "model": body.get("model"),
        }), started)
        return model, text, metadata
    # ANTHROPIC
    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("ANTHROPIC_API_KEY is not set; add it to environment or CI secrets.", category="configuration", code="missing_api_key")
        model = model or os.getenv(
            "ANTHROPIC_MODEL",
            "claude-3-7-sonnet-latest",
        )
        system_text = "\n\n".join(
            item["content"] for item in messages if item["role"] == "system"
        )
        conversation = [
            item for item in messages if item["role"] != "system"
        ]
        payload = {
            "model": model,
            "max_tokens": 1200,
            "messages": conversation,
        }
        if system_text:
            payload["system"] = system_text
        body = _post(
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload,
        )
        content = body.get("content", [])
        if not isinstance(content, list):
            raise ProviderError(
                "Invalid provider response: 'content' must be a list")
        text = "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        )
        metadata = _with_latency(_present({
            "request_id": body.get("id"),
            "stop_reason": body.get("stop_reason"),
            "usage": body.get("usage"),
            "model": body.get("model"),
        }), started)
        return model, text, metadata
    # GOOGLE GEMINI
    if provider == "gemini":
        key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        if not key:
            raise ProviderError(
                "GEMINI_API_KEY or GOOGLE_API_KEY is not set; add one to environment or CI secrets.", category="configuration", code="missing_api_key"
            )
        model = model or os.getenv(
            "GEMINI_MODEL",
            "gemini-2.5-flash",
        )
        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{quote(model, safe='')}:generateContent"
        )
        system_text = "\n\n".join(
            item["content"] for item in messages if item["role"] == "system"
        )
        conversation = [
            item for item in messages if item["role"] != "system"
        ]
        payload = {
            "contents": [
                _gemini_content(item) for item in conversation
            ]
        }
        if system_text:
            payload["systemInstruction"] = {
                "parts": [{"text": system_text}]
            }
        body = _post(
            url,
            {
                "Content-Type": "application/json",
                "x-goog-api-key": key,
            },
            payload,
        )
        candidates = body.get("candidates", [])
        if not isinstance(candidates, list):
            raise ProviderError(
                "Invalid provider response: 'candidates' must be a list")
        text_parts = []
        finish = None
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if finish is None:
                finish = candidate.get("finishReason")
            content = candidate.get("content", {})
            if not isinstance(content, dict):
                continue
            parts = content.get("parts", [])
            if not isinstance(parts, list):
                continue
            for part in parts:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    text_parts.append(part["text"])
        text = "\n".join(text_parts)
        # Preserve provider-side prompt blocking and candidate safety
        # annotations so an empty response is distinguishable from a clean pass.
        safety_ratings = []
        for candidate in candidates:
            if isinstance(candidate, dict):
                ratings = candidate.get("safetyRatings")
                if isinstance(ratings, list):
                    safety_ratings.extend(
                        rating for rating in ratings
                        if isinstance(rating, dict)
                    )
        prompt_feedback = body.get("promptFeedback")
        metadata = _with_latency(_present({
            "request_id": body.get("responseId"),
            "model_version": body.get("modelVersion"),
            "usage": body.get("usageMetadata"),
            "finish_reason": finish,
            "prompt_feedback": prompt_feedback
                if isinstance(prompt_feedback, dict) else None,
            "safety_ratings": safety_ratings,
        }), started)
        # Keep finish_reason present even when None: a blocked prompt has
        # no candidates, so None here (with prompt_feedback set) is the
        # signal that distinguishes a block from a clean pass. _present
        # above drops None-valued keys, so restore it explicitly.
        metadata["finish_reason"] = finish
        return model, text, metadata
    # OPENAI-COMPATIBLE (DeepSeek, GLM, Moonshot, NVIDIA, OpenRouter,
    # Groq, Together, local servers, and any /v1/chat/completions host)
    if provider == "openai-compatible":
        model = model or os.getenv("OPENAI_COMPAT_MODEL")
        if not model:
            raise ProviderError(
                "Set --model or OPENAI_COMPAT_MODEL for this endpoint", category="configuration", code="missing_model"
            )
        chosen_url = base_url or os.getenv("OPENAI_COMPAT_BASE_URL")
        if not chosen_url:
            raise ProviderError(
                "Set a base URL with --base-url or OPENAI_COMPAT_BASE_URL", category="configuration", code="missing_base_url"
            )
        api_key = os.getenv(api_key_env) if api_key_env else None
        endpoint = _compat_chat_url(chosen_url)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body = _post(
            endpoint,
            headers,
            {"model": model, "messages": messages},
        )
        choices = body.get("choices")
        if (not isinstance(choices, list) or not choices
                or not isinstance(choices[0], dict)):
            raise ProviderError(
                "Invalid provider response: 'choices[0]' must be an object"
            )
        message = choices[0].get("message")
        if not isinstance(message, dict) or "content" not in message:
            raise ProviderError(
                "Invalid provider response: "
                "'choices[0].message.content' is required"
            )
        content = message["content"]
        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
                and isinstance(part.get("text"), str)
            )
        if not isinstance(content, str):
            raise ProviderError(
                "Invalid provider response: message content must be text"
            )
        metadata = _with_latency(_present({
            "request_id": body.get("id"),
            "finish_reason": choices[0].get("finish_reason"),
            "usage": body.get("usage"),
            "model": body.get("model"),
            "endpoint_type": "openai-compatible",
        }), started)
        return model, content, metadata
    raise ProviderError(f"Unsupported provider: {provider}", category="configuration", code="unsupported_provider")


def call_provider(provider, prompt, model=None, base_url=None,
                  api_key_env="OPENAI_COMPAT_API_KEY"):
    """Call one provider with a single user prompt.

    Thin wrapper over call_provider_messages; returns
    (model, text, metadata) exactly as before.
    """
    return call_provider_messages(
        provider,
        [{"role": "user", "content": prompt}],
        model,
        base_url=base_url,
        api_key_env=api_key_env,
    )
