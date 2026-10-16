"""The one way the tool calls Claude: structured output, refusal fallback, cached by input hash."""
from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5-5"
# USD per million tokens: input, cache write (5 min), cache read, output (claude-api skill, 2026-10-06)
PRICE_PER_MTOK = {"claude-opus-5-5": (4.00, 5.00, 0.20, 20.00)}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class ClaudeError(RuntimeError):
    pass


def cache_key(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:20]


class Claude:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.usage = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
        self._lock = threading.Lock()

    def structured(self, system: str, user: str | list, output: type[T], cache_dir: Path,
                   key: str, effort: str = "medium", max_tokens: int = 16000) -> T:
        """Return `output` for this prompt, from cache when the same input was answered before."""
        path = cache_dir / f"{key}.json"
        if path.exists():
            return output.model_validate_json(path.read_text("utf-8"))
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=output,
            output_config={"effort": effort},
            thinking={"type": "adaptive"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        with self._lock:
            u = response.usage
            self.usage["input"] += u.input_tokens
            self.usage["cache_write"] += u.cache_creation_input_tokens or 0
            self.usage["cache_read"] += u.cache_read_input_tokens or 0
            self.usage["output"] += u.output_tokens
        if response.stop_reason == "refusal":
            raise ClaudeError(f"refused ({getattr(response.stop_details, 'category', None)})")
        if response.stop_reason == "max_tokens":
            raise ClaudeError("output cut off at max_tokens")
        parsed = response.parsed_output
        if parsed is None:
            raise ClaudeError("no structured output in response")
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(parsed.model_dump_json(indent=2), "utf-8")
        return parsed

    def cost_usd(self) -> float:
        prices = PRICE_PER_MTOK.get(self.model, (0.0, 0.0, 0.0, 0.0))
        counts = (self.usage["input"], self.usage["cache_write"], self.usage["cache_read"], self.usage["output"])
        return sum(c * p for c, p in zip(counts, prices)) / 1_000_000
