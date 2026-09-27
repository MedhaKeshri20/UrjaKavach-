"""Tests for backend/agents/conservation.py -- LLM-generated citizen
conservation copy (SPEC.md Segment 1, Phase 9, F7 slice).

No live network call is ever made here: backend.agents.conservation's own
`complete_json` name is monkeypatched out where the real-agent path is
exercised, mirroring test_watch.py's/test_llm.py's posture. The default
(USE_REAL_AGENTS=0) test-suite environment already exercises the static
fallback path with no monkeypatching at all.
"""

from __future__ import annotations

import pytest

from backend.agents import conservation as conservation_module
from backend.agents.conservation import _LEVELS_FALLBACK, generate_conservation_copy


def _forbid_llm_call(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("complete_json should not have been called")

    monkeypatch.setattr(conservation_module, "complete_json", _boom)


# ---------------------------------------------------------------------------
# decision #12 -- Normal skips the LLM entirely
# ---------------------------------------------------------------------------


def test_generate_conservation_copy_normal_skips_llm(monkeypatch):
    monkeypatch.setenv("USE_REAL_AGENTS", "1")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    _forbid_llm_call(monkeypatch)

    result = generate_conservation_copy("Normal", None)
    assert result == {
        "message": _LEVELS_FALLBACK["Normal"][0],
        "conservation_plan": _LEVELS_FALLBACK["Normal"][1],
    }


# ---------------------------------------------------------------------------
# Offline fallback (default test-suite env: USE_REAL_AGENTS=0)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["Elevated", "Shortage"])
def test_generate_conservation_copy_falls_back_without_real_agents(monkeypatch, level):
    monkeypatch.setenv("USE_REAL_AGENTS", "0")
    _forbid_llm_call(monkeypatch)

    result = generate_conservation_copy(level, "Strait of Hormuz")
    message, plan = _LEVELS_FALLBACK[level]
    assert result == {"message": message, "conservation_plan": list(plan)}


def test_generate_conservation_copy_falls_back_without_api_key(monkeypatch):
    monkeypatch.setenv("USE_REAL_AGENTS", "1")
    monkeypatch.setenv("GROQ_API_KEY", "")
    _forbid_llm_call(monkeypatch)

    result = generate_conservation_copy("Elevated", "Strait of Hormuz")
    message, plan = _LEVELS_FALLBACK["Elevated"]
    assert result == {"message": message, "conservation_plan": list(plan)}


# ---------------------------------------------------------------------------
# Real-agent path (LLM monkeypatched, not the real network)
# ---------------------------------------------------------------------------


def test_generate_conservation_copy_uses_llm_response_when_available(monkeypatch):
    monkeypatch.setenv("USE_REAL_AGENTS", "1")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setattr(
        conservation_module,
        "complete_json",
        lambda *a, **k: {"message": "Calm scenario-specific copy.", "conservation_plan": ["Tip one.", "Tip two."]},
    )

    result = generate_conservation_copy("Elevated", "Strait of Hormuz")
    assert result == {
        "message": "Calm scenario-specific copy.",
        "conservation_plan": ["Tip one.", "Tip two."],
    }


def test_generate_conservation_copy_cache_key_is_level_and_corridor(monkeypatch):
    monkeypatch.setenv("USE_REAL_AGENTS", "1")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")

    captured: dict = {}

    def _complete(prompt, *, cache_key, model):
        captured["cache_key"] = cache_key
        captured["prompt"] = prompt
        return {"message": "x", "conservation_plan": ["y"]}

    monkeypatch.setattr(conservation_module, "complete_json", _complete)

    generate_conservation_copy("Shortage", "Strait of Hormuz")
    assert captured["cache_key"] == "Shortage|Strait of Hormuz"
    assert "Strait of Hormuz" in captured["prompt"]
    assert "Shortage" in captured["prompt"]


def test_generate_conservation_copy_cache_key_handles_no_corridor(monkeypatch):
    monkeypatch.setenv("USE_REAL_AGENTS", "1")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")

    captured: dict = {}

    def _complete(prompt, *, cache_key, model):
        captured["cache_key"] = cache_key
        return {"message": "x", "conservation_plan": ["y"]}

    monkeypatch.setattr(conservation_module, "complete_json", _complete)

    generate_conservation_copy("Elevated", None)
    assert captured["cache_key"] == "Elevated|none"


# ---------------------------------------------------------------------------
# Malformed LLM payload -- must degrade, never propagate a bad response
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "", "conservation_plan": ["a tip"]},
        {"message": "fine", "conservation_plan": []},
        {"conservation_plan": ["a tip"]},  # missing "message"
        {"message": "fine"},  # missing "conservation_plan"
        {"message": "fine", "conservation_plan": "not a list, a string"},
    ],
)
def test_generate_conservation_copy_malformed_payload_falls_back(monkeypatch, payload):
    monkeypatch.setenv("USE_REAL_AGENTS", "1")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setattr(conservation_module, "complete_json", lambda *a, **k: payload)

    result = generate_conservation_copy("Elevated", "Strait of Hormuz")
    message, plan = _LEVELS_FALLBACK["Elevated"]
    assert result == {"message": message, "conservation_plan": list(plan)}


def test_generate_conservation_copy_llm_unavailable_falls_back(monkeypatch):
    from backend.agents.llm import LLMUnavailable

    monkeypatch.setenv("USE_REAL_AGENTS", "1")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")

    def _raise(*args, **kwargs):
        raise LLMUnavailable("boom")

    monkeypatch.setattr(conservation_module, "complete_json", _raise)

    result = generate_conservation_copy("Shortage", "Strait of Hormuz")
    message, plan = _LEVELS_FALLBACK["Shortage"]
    assert result == {"message": message, "conservation_plan": list(plan)}
