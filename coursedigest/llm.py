"""The one way the tool calls a model: the OpenAI SDK, pointed at Gemini's free tier by default.

LLM_PROVIDER=gemini (default, free tier, key GEMINI_API_KEY) or openai (paid, key OPENAI_API_KEY).
LLM_MODEL overrides the provider's model list. On Gemini every model has its own daily free quota, so the list is
every available Flash model (see free_models). Answers are cached by input hash, so re-runs are free.
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
BUSY_WAIT = 20.0
FLASH = re.compile(r"^(?:models/)?gemini-(?:(\d+(?:\.\d+)?)-)?flash(-lite)?(-latest)?$")
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


def free_models(ids: list[str]) -> list[str]:
    """Gemini text Flash models, best first: Flash before Flash-Lite, then the -latest alias, then newest version."""
    ranked = []
    for model_id in ids:
        match = FLASH.match(model_id)
        if match and (match.group(1) or match.group(3)):
            version = float(match.group(1)) if match.group(1) else 99.0
            ranked.append((match.group(2) is not None, -version, model_id.removeprefix("models/")))
    return [model_id for *_, model_id in sorted(ranked)]


def retry_seconds(error: Exception) -> float:
    match = RETRY_IN.search(str(error))
    return float(match.group(1) or match.group(2)) + 1 if match else 30.0


def is_daily_quota(error: Exception) -> bool:
    return "PerDay" in str(error)


def call_with_quota(models: list[str], call):
    """Run call(model) on the first model that answers.

    A busy (5xx) or per-minute-limited model passes the call to the next one; when every model is busy, wait and go
    round again. A model whose daily quota is spent is dropped for the rest of the run.
    """
    spent: set[str] = set()
    for _ in range(MAX_WAITS):
        wait = 0.0
        for model in models:
            if model in spent:
                continue
            try:
                return model, call(model)
            except openai.RateLimitError as exc:
                if is_daily_quota(exc):
                    log.warning("daily free-tier quota used up for %s", model)
                    spent.add(model)
                else:
                    wait = max(wait, retry_seconds(exc))
            except openai.NotFoundError:
                log.info("%s is not available to this key, skipped", model)
                spent.add(model)
            except (openai.InternalServerError, openai.APIConnectionError) as exc:
                log.info("%s busy (%s)", model, type(exc).__name__)
                wait = max(wait, BUSY_WAIT)
        if len(spent) == len(models):
            raise DailyQuota("daily free-tier quota used up for every model; run again tomorrow (finished items are kept)")
        log.info("all models busy or rate limited, waiting %.0fs", wait)
        time.sleep(wait)
    raise LLMError(f"models still busy after {MAX_WAITS} rounds: {', '.join(models)}")


class LLM:
    def __init__(self, client: openai.OpenAI | None = None, provider: str | None = None):
        self.provider, settings = provider_settings(provider)
        self.models = settings["models"]
        if client is None:
            key = os.environ.get(settings["key"])
            if not key:
                raise LLMError(f"{settings['key']} is not set in .env")
            client = openai.OpenAI(api_key=key, base_url=settings["base_url"], max_retries=1)
        self.client = client
        if self.provider == "gemini" and not os.environ.get("LLM_MODEL"):
            try:
                self.models = free_models([m.id for m in client.models.list()]) or self.models
            except openai.OpenAIError as exc:
                log.warning("could not list models (%s); using %s", exc, ", ".join(self.models))
        self.base_url = settings["base_url"]
        self.api_key_name = settings["key"]
        self.usage = {"input": 0, "output": 0, "calls": 0}
        self.answered: dict[str, int] = {}
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
            self.answered[model] = self.answered.get(model, 0) + 1
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

    def label(self) -> str:
        """The models that answered this run, most used first (the configured model when nothing was called)."""
        return ", ".join(sorted(self.answered, key=self.answered.get, reverse=True)) or self.model

    def summary(self) -> str:
        return (f"{self.usage['calls']} calls, {self.usage['input']:,} input / {self.usage['output']:,} output tokens "
                f"on {self.provider} ({self.label()})" + (" - free tier" if self.provider == "gemini" else ""))
