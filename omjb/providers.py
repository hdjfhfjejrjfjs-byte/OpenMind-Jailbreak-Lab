"""Async API clients for controlled OMJB model evaluations.

Keys are read from environment variables and are never serialized into reports.
"""
from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
}


class CostTable:
    def __init__(self, pricing: dict[str, tuple[float, float]] | None = None):
        self.pricing = dict(pricing or DEFAULT_PRICING)

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        input_rate, output_rate = self.pricing.get(model, (0.0, 0.0))
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


class QuotaTracker:
    def __init__(self, *, cost_table: CostTable | None = None,
                 max_total_usd: float | None = None,
                 max_tokens_per_model: int | None = None):
        if max_total_usd is not None and max_total_usd < 0:
            raise ValueError("max_total_usd must be non-negative")
        if max_tokens_per_model is not None and max_tokens_per_model < 1:
            raise ValueError("max_tokens_per_model must be positive")
        self.cost_table = cost_table or CostTable()
        self.max_total_usd = max_total_usd
        self.max_tokens_per_model = max_tokens_per_model
        self._records: dict[tuple[str, str], dict[str, int]] = {}
        self._lock = asyncio.Lock()

    async def record(self, provider: str, model: str, input_tokens: int,
                     output_tokens: int) -> None:
        if min(input_tokens, output_tokens) < 0:
            raise ValueError("token counts must be non-negative")
        async with self._lock:
            key = (provider, model)
            row = self._records.setdefault(key, {"requests": 0, "input_tokens": 0,
                                                 "output_tokens": 0})
            row["requests"] += 1
            row["input_tokens"] += input_tokens
            row["output_tokens"] += output_tokens
            total_model = row["input_tokens"] + row["output_tokens"]
            total_cost = self.total_cost()
            if self.max_tokens_per_model is not None and total_model > self.max_tokens_per_model:
                raise RuntimeError(f"token cap exceeded for {provider}:{model}")
            if self.max_total_usd is not None and total_cost > self.max_total_usd:
                raise RuntimeError("total cost cap exceeded")

    def total_cost(self) -> float:
        return sum(self.cost_table.cost(model, row["input_tokens"], row["output_tokens"])
                   for (_, model), row in self._records.items())

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for (provider, model), row in self._records.items():
            out[f"{provider}:{model}"] = {
                **row,
                "cost_usd": round(self.cost_table.cost(
                    model, row["input_tokens"], row["output_tokens"]), 6),
            }
        out["total_cost_usd"] = round(self.total_cost(), 6)
        return out


@dataclass
class Completion:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


async def _post_with_retry(url: str, *, headers: dict[str, str],
                           body: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(5):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("provider response must be a JSON object")
                return data
        except httpx.HTTPStatusError as exc:
            last = exc
            if exc.response.status_code not in (429, 500, 502, 503, 504):
                raise
            retry_after = exc.response.headers.get("retry-after")
            try:
                delay = float(retry_after) if retry_after else 0.5 * (2 ** attempt)
            except ValueError:
                delay = 0.5 * (2 ** attempt)
            await asyncio.sleep(min(delay, 30.0) + random.uniform(0, 0.25))
    assert last is not None
    raise last


class BaseProvider:
    name: str

    def __init__(self, api_key: str, quota: QuotaTracker):
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self.quota = quota

    async def complete(self, model: str, messages: list[dict[str, str]], *,
                       max_tokens: int = 512, temperature: float = 0.0) -> Completion:
        raise NotImplementedError


class OpenAICompatProvider(BaseProvider):
    def __init__(self, base_url: str, api_key: str, *, name: str,
                 quota: QuotaTracker):
        super().__init__(api_key, quota)
        parsed = urlparse(base_url)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in local_hosts):
            raise ValueError("base_url must use HTTPS (HTTP is allowed only for loopback)")
        if not parsed.hostname:
            raise ValueError("base_url must include a hostname")
        self.base_url = base_url.rstrip("/")
        self.name = name

    async def complete(self, model: str, messages: list[dict[str, str]], *,
                       max_tokens: int = 512, temperature: float = 0.0) -> Completion:
        data = await _post_with_retry(
            self.base_url + "/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            body={"model": model, "messages": messages, "max_tokens": max_tokens,
                  "temperature": temperature, "stream": False},
        )
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        incoming = int(usage.get("prompt_tokens", 0))
        outgoing = int(usage.get("completion_tokens", 0))
        await self.quota.record(self.name, model, incoming, outgoing)
        content = message.get("content") or ""
        if not isinstance(content, str):
            raise ValueError("provider returned non-text message content")
        return Completion(content, self.name, model, incoming, outgoing)


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    async def complete(self, model: str, messages: list[dict[str, str]], *,
                       max_tokens: int = 512, temperature: float = 0.0) -> Completion:
        system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        rest = [{"role": m["role"], "content": m["content"]}
                for m in messages if m.get("role") != "system"]
        body: dict[str, Any] = {"model": model, "messages": rest,
                                "max_tokens": max_tokens, "temperature": temperature}
        if system:
            body["system"] = system
        data = await _post_with_retry(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01"},
            body=body,
        )
        usage = data.get("usage") or {}
        incoming = int(usage.get("input_tokens", 0))
        outgoing = int(usage.get("output_tokens", 0))
        await self.quota.record(self.name, model, incoming, outgoing)
        text = "".join(block.get("text", "") for block in data.get("content", [])
                       if block.get("type") == "text")
        return Completion(text, self.name, model, incoming, outgoing)


class ProviderRegistry:
    def __init__(self, quota: QuotaTracker | None = None):
        self.quota = quota or QuotaTracker()
        self.providers: dict[str, BaseProvider] = {}

    def add(self, provider: BaseProvider) -> "ProviderRegistry":
        self.providers[provider.name] = provider
        return self

    def get(self, name: str) -> BaseProvider:
        try:
            return self.providers[name]
        except KeyError as exc:
            raise KeyError(f"provider {name!r} is not configured") from exc

    @classmethod
    def from_env(cls, quota: QuotaTracker | None = None) -> "ProviderRegistry":
        q = quota or QuotaTracker()
        registry = cls(q)
        envs = (
            ("openai", "OPENAI_API_KEY", "https://api.openai.com/v1"),
            ("deepseek", "DEEPSEEK_API_KEY", "https://api.deepseek.com/v1"),
            ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1"),
            ("together", "TOGETHER_API_KEY", "https://api.together.xyz/v1"),
        )
        for name, variable, url in envs:
            if key := os.getenv(variable):
                registry.add(OpenAICompatProvider(url, key, name=name, quota=q))
        if key := os.getenv("ANTHROPIC_API_KEY"):
            registry.add(AnthropicProvider(key, q))
        if base := os.getenv("OLLAMA_BASE_URL"):
            registry.add(OpenAICompatProvider(
                base, os.getenv("OLLAMA_API_KEY", "ollama"), name="ollama", quota=q
            ))
        return registry
