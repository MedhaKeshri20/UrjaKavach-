"""Thin Groq LLM client wrapper — the only place backend/agents/*.py talks to
an external LLM API. Every call is cached to disk by input hash so the same
prompt always returns the same JSON, on stage and in CI (PRD §10/§17).

SPEC.md Phase 4 decision #1: provider is Groq (free tier), not Anthropic or
Gemini. Decision #12: no retries within a model tier — one attempt, then the
caller (watch.py) moves to the next tier or the offline stub.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from groq import Groq

from backend.config import get_settings

_CALL_TIMEOUT_SECONDS = 8.0


class LLMUnavailable(Exception):
    """Any failure to get a usable JSON response — network error, timeout,
    non-2xx, rate limit, or a response that isn't (recoverably) JSON.
    Callers (watch.py) catch this and move to the next fallback tier."""


def _cache_path(cache_key: str) -> Path:
    cache_dir = Path(get_settings().llm_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.json"


def _salvage_json(text: str) -> dict:
    """Decision #19: strict parse first, then a one-shot salvage of the
    substring between the first '{' and the last '}' (a smaller/free-tier
    model doesn't always uniformly honor JSON-only instructions)."""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise
        return json.loads(text[start : end + 1])


def complete_json(prompt: str, *, cache_key: str, model: str) -> dict:
    """Call the LLM, expecting a JSON object back. Cached by ``cache_key``
    (a stable, normalized key the caller builds — see watch.py, not the raw
    prompt). Raises :class:`LLMUnavailable` on any failure; never returns a
    partial result."""

    path = _cache_path(f"{model}:{cache_key}")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    settings = get_settings()
    if not settings.groq_api_key:
        raise LLMUnavailable("no GROQ_API_KEY configured")

    client = Groq(
        api_key=settings.groq_api_key,
        timeout=_CALL_TIMEOUT_SECONDS,
        max_retries=0,  # decision #12 — one attempt per tier, no SDK retries
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("empty completion content")
        data = _salvage_json(content)
    except Exception as exc:  # network, timeout, rate limit, bad JSON — uniform
        raise LLMUnavailable(str(exc)) from exc

    if not isinstance(data, dict):
        raise LLMUnavailable(f"expected a JSON object, got {type(data).__name__}")

    path.write_text(json.dumps(data), encoding="utf-8")
    return data
