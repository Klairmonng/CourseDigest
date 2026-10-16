"""The one way the tool calls a model: the OpenAI SDK, pointed at Gemini's free tier by default.

LLM_PROVIDER=gemini (default, free tier, key GEMINI_API_KEY) or openai (paid, key OPENAI_API_KEY).
LLM_MODEL overrides the provider's model list. Answers are cached by input hash, so re-runs are free.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import TypeVar

import openai
from pydantic import BaseModel

PROVIDERS = {
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "key": "GEMINI_API_KEY",
               "models": ["gemini-flash-latest", "gemini-flash-lite-latest"]},
    "openai": {"base_url": None, "key": "OPENAI_API_KEY", "models": ["gpt-4.1-mini"]},
}
MAX_WAITS = 8
RETRY_IN = re.compile(r"retry in ([\d.]+)s|retryDelay['\"]?: ?['\"](\d+)s", re.I)

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class DailyQuota(LLMError):
    pass


def cache_key(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:20]


def provider_settings(name: str | None = None) -> tuple[str, dict]:
    name = (name or os.environ.get("LLM_PROVIDER") or "gemini").lower()
    if name not in PROVIDERS:
        raise LLMError(f"unknown LLM_PROVIDER {name!r} (use: {', '.join(PROVIDERS)})")
    settings = dict(PROVIDERS[name])
    if os.environ.get("LLM_MODEL"):
        settings["models"] = [os.environ["LLM_MODEL"]]
    return name, settings


def retry_seconds(error: Exception) -> float:
    match = RETRY_IN.search(str(error))
    return float(match.group(1) or match.group(2)) + 1 if match else 30.0


def is_daily_quota(error: Exception) -> bool:
    return "PerDay" in str(error)


def call_with_quota(models: list[str], call):
    """Run call(model); wait out per-minute limits; move to the next model when a daily quota is spent."""
    for model in models:
        for _ in range(MAX_WAITS):
            try:
                return model, call(model)
            except openai.RateLimitError as exc:
                if is_daily_quota(exc):
                    log.warning("daily free-tier quota used up for %s", model)
                    break
                wait = retry_seconds(exc)
                log.info("rate limited on %s, waiting %.0fs", model, wait)
                time.sleep(wait)
        else:
            raise LLMError(f"still rate limited on {model} after {MAX_WAITS} waits")
    raise DailyQuota("daily free-tier quota used up for every model; run again tomorrow (finished items are kept)")


class LLM:
    def __init__(self, client: openai.OpenAI | None = None, provider: str | None = None):
        self.provider, settings = provider_settings(provider)
        self.models = settings["models"]
        if client is None:
            key = os.environ.get(settings["key"])
            if not key:
                raise LLMError(f"{settings['key']} is not set in .env")
            client = openai.OpenAI(api_key=key, base_url=settings["base_url"])
        self.client = client
        self.base_url = settings["base_url"]
        self.api_key_name = settings["key"]
        self.usage = {"input": 0, "output": 0, "calls": 0}
        self._lock = threading.Lock()

    @property
    def model(self) -> str:
        return self.models[0]

    def structured(self, system: str, user: str, output: type[T], cache_dir: Path, key: str) -> T:
        """Return `output` for this prompt, from cache when the same input was answered before."""
        path = cache_dir / f"{key}.json"
        if path.exists():
            return output.model_validate_json(path.read_text("utf-8"))
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        model, response = call_with_quota(self.models, lambda m: self.client.chat.completions.parse(
            model=m, messages=messages, response_format=output))
        with self._lock:
            self.usage["calls"] += 1
            if response.usage:
                self.usage["input"] += response.usage.prompt_tokens
                self.usage["output"] += response.usage.completion_tokens
        message = response.choices[0].message
        if getattr(message, "refusal", None):
            raise LLMError(f"{model} refused: {message.refusal}")
        if response.choices[0].finish_reason == "length":
            raise LLMError(f"{model} output was cut off")
        if message.parsed is None:
            raise LLMError(f"{model} returned no structured output")
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(message.parsed.model_dump_json(indent=2), "utf-8")
        return message.parsed

    def summary(self) -> str:
        return (f"{self.usage['calls']} calls, {self.usage['input']:,} input / {self.usage['output']:,} output tokens "
                f"on {self.provider} ({self.model})" + (" - free tier" if self.provider == "gemini" else ""))
