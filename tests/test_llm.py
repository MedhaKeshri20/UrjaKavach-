"""Tests for backend/agents/llm.py — the Groq client wrapper (SPEC.md Phase 4).

No live network call is ever made here (decision #14): the Groq client
itself is monkeypatched out, so these tests pass with no GROQ_API_KEY set
anywhere in the environment.
"""

from __future__ import annotations

import json

import pytest

from backend.agents import llm as llm_module
from backend.agents.llm import LLMUnavailable, _salvage_json, complete_json


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Every test gets its own cache dir and a real (non-empty) API key by
    default, so complete_json's "no key" short-circuit doesn't mask what a
    given test actually wants to exercise."""

    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / ".llm_cache"))
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = type("Message", (), {"content": content})()


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeGroqClient:
    """Records how many times it was constructed / called with what args."""

    instances: list["_FakeGroqClient"] = []

    def __init__(self, *, response: str | None = None, raises: Exception | None = None, **kwargs):
        self._response = response
        self._raises = raises
        self.calls: list[dict] = []
        _FakeGroqClient.instances.append(self)

        class _Completions:
            def create(inner_self, **create_kwargs):
                self.calls.append(create_kwargs)
                if self._raises is not None:
                    raise self._raises
                return _FakeResponse(self._response)

        self.chat = type("Chat", (), {"completions": _Completions()})()


def _install_fake_groq(monkeypatch, **kwargs) -> _FakeGroqClient:
    _FakeGroqClient.instances.clear()

    def _factory(*args, **client_kwargs):
        return _FakeGroqClient(**kwargs)

    monkeypatch.setattr(llm_module, "Groq", _factory)
    return _factory


# ---------------------------------------------------------------------------
# _salvage_json
# ---------------------------------------------------------------------------


def test_salvage_json_parses_strict_json():
    assert _salvage_json('{"score": 42}') == {"score": 42}


def test_salvage_json_recovers_json_embedded_in_prose():
    text = 'Sure, here is the answer:\n{"score": 55, "reason": "elevated tension"}\nHope that helps!'
    assert _salvage_json(text) == {"score": 55, "reason": "elevated tension"}


def test_salvage_json_raises_on_non_json_text():
    with pytest.raises(json.JSONDecodeError):
        _salvage_json("this is not json at all")


# ---------------------------------------------------------------------------
# complete_json — success + caching
# ---------------------------------------------------------------------------


def test_complete_json_returns_parsed_response(monkeypatch):
    _install_fake_groq(monkeypatch, response='{"score": 61, "reason": "ok"}')
    data = complete_json("some prompt", cache_key="k1", model="llama-3.3-70b-versatile")
    assert data == {"score": 61, "reason": "ok"}


def test_complete_json_caches_and_does_not_recall_model(monkeypatch):
    _install_fake_groq(monkeypatch, response='{"score": 61}')

    first = complete_json("prompt", cache_key="same-key", model="m")
    assert len(_FakeGroqClient.instances) == 1

    # Second call, same cache_key/model: must hit the cache file, not
    # construct a second client at all.
    second = complete_json("a totally different prompt text", cache_key="same-key", model="m")
    assert second == first
    assert len(_FakeGroqClient.instances) == 1


def test_complete_json_cache_key_isolates_different_models(monkeypatch):
    """Decision #11: cache key is prefixed with the model, so two tiers for
    the same logical input don't collide on one cache file."""

    _install_fake_groq(monkeypatch, response='{"score": 10}')
    complete_json("prompt", cache_key="shared", model="model-a")
    complete_json("prompt", cache_key="shared", model="model-b")
    assert len(_FakeGroqClient.instances) == 2


def test_complete_json_salvages_prose_wrapped_json(monkeypatch):
    _install_fake_groq(
        monkeypatch, response='Here you go: {"score": 30, "reason": "calm"} enjoy'
    )
    data = complete_json("prompt", cache_key="k2", model="m")
    assert data == {"score": 30, "reason": "calm"}


# ---------------------------------------------------------------------------
# complete_json — failure modes, all uniformly raising LLMUnavailable
# ---------------------------------------------------------------------------


def test_complete_json_raises_without_api_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    _install_fake_groq(monkeypatch, response='{"score": 1}')
    with pytest.raises(LLMUnavailable):
        complete_json("prompt", cache_key="k3", model="m")
    # No client should even be constructed — fail fast, no network attempt.
    assert len(_FakeGroqClient.instances) == 0


def test_complete_json_raises_on_client_exception(monkeypatch):
    _install_fake_groq(monkeypatch, raises=TimeoutError("timed out"))
    with pytest.raises(LLMUnavailable):
        complete_json("prompt", cache_key="k4", model="m")


def test_complete_json_raises_on_malformed_json_response(monkeypatch):
    _install_fake_groq(monkeypatch, response="not json and no braces either")
    with pytest.raises(LLMUnavailable):
        complete_json("prompt", cache_key="k5", model="m")


def test_complete_json_raises_on_non_object_json(monkeypatch):
    _install_fake_groq(monkeypatch, response="[1, 2, 3]")
    with pytest.raises(LLMUnavailable):
        complete_json("prompt", cache_key="k6", model="m")


def test_complete_json_raises_on_empty_content(monkeypatch):
    _install_fake_groq(monkeypatch, response=None)
    with pytest.raises(LLMUnavailable):
        complete_json("prompt", cache_key="k7", model="m")


def test_complete_json_failure_is_not_cached(monkeypatch):
    """A failed call must not poison the cache — retrying later (e.g. after
    a transient rate limit) should attempt the call again."""

    _install_fake_groq(monkeypatch, raises=RuntimeError("boom"))
    with pytest.raises(LLMUnavailable):
        complete_json("prompt", cache_key="k8", model="m")

    _install_fake_groq(monkeypatch, response='{"score": 5}')
    data = complete_json("prompt", cache_key="k8", model="m")
    assert data == {"score": 5}
