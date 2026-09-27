"""Tests for backend/agents/watch.py — the real Watch agent (SPEC.md Phase 4).

No live network call is ever made here (decision #14): backend.agents.watch's
own `complete_json` and `retrieve` names are monkeypatched out directly, so
these tests pass with no GROQ_API_KEY set and without touching the real RAG
corpus/Chroma store. A separate, small set of tests exercises the pure
fallback path against run_watch_stub directly.
"""

from __future__ import annotations

import json

import pytest

from backend.agents import watch as watch_module
from backend.agents.llm import LLMUnavailable
from backend.agents.rag import Snippet
from backend.agents.stubs import run_watch_stub
from backend.agents.watch import KNOWN_CORRIDORS, _band_from_retrieval, run_watch

_SEED_CORRIDORS_PATH = "backend/seed/corridors.json"


def _make_signal(**overrides) -> dict:
    signal = {
        "id": "sig_1",
        "corridor": "hormuz",
        "headline": "Tanker seized near the Strait of Hormuz",
        "severity": 0.4,
    }
    signal.update(overrides)
    return signal


def _snippet(id_: str, corridor: str = "hormuz", date: str = "2024-01-01") -> Snippet:
    return Snippet(id=id_, corridor=corridor, date=date, source="wire reporting", text="text")


@pytest.fixture(autouse=True)
def _real_agents_on(monkeypatch):
    """Most tests in this file want the real-agent path reachable; the
    flag/no-key fallback tests override this explicitly."""

    monkeypatch.setenv("USE_REAL_AGENTS", "1")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")


def _forbid_calls(monkeypatch):
    """Patch complete_json/retrieve to raise if invoked — used to prove a
    fallback path never attempts the real pipeline."""

    def _boom(*args, **kwargs):
        raise AssertionError("should not have been called")

    monkeypatch.setattr(watch_module, "complete_json", _boom)
    monkeypatch.setattr(watch_module, "retrieve", _boom)


# ---------------------------------------------------------------------------
# Corridor guardrail (decision #13)
# ---------------------------------------------------------------------------


def test_known_corridors_matches_seed_config():
    seed = json.loads(open(_SEED_CORRIDORS_PATH, encoding="utf-8").read())
    seed_ids = {row["id"] for row in seed}
    assert KNOWN_CORRIDORS == seed_ids, (
        "watch.KNOWN_CORRIDORS has drifted from backend/seed/corridors.json — "
        f"KNOWN_CORRIDORS={KNOWN_CORRIDORS!r} seed_ids={seed_ids!r}"
    )


# ---------------------------------------------------------------------------
# Uniform fallback triggers (decision #9)
# ---------------------------------------------------------------------------


def test_run_watch_falls_back_when_flag_off(monkeypatch):
    monkeypatch.setenv("USE_REAL_AGENTS", "0")
    _forbid_calls(monkeypatch)

    signal = _make_signal()
    result = run_watch(signal)
    expected = run_watch_stub(signal)
    assert result == expected


def test_run_watch_falls_back_when_no_api_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    _forbid_calls(monkeypatch)

    signal = _make_signal()
    assert run_watch(signal) == run_watch_stub(signal)


def test_run_watch_falls_back_on_unknown_corridor(monkeypatch):
    def _retrieve_should_not_be_called(*args, **kwargs):
        raise AssertionError("retrieve should not be called for an unknown corridor")

    monkeypatch.setattr(watch_module, "retrieve", _retrieve_should_not_be_called)

    signal = _make_signal(corridor="bosphorus")
    assert run_watch(signal) == run_watch_stub(signal)


def test_run_watch_falls_back_on_empty_retrieval(monkeypatch):
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: [])

    def _complete_should_not_be_called(*args, **kwargs):
        raise AssertionError("complete_json should not be called on empty retrieval")

    monkeypatch.setattr(watch_module, "complete_json", _complete_should_not_be_called)

    signal = _make_signal()
    assert run_watch(signal) == run_watch_stub(signal)


def test_run_watch_falls_back_after_both_tiers_fail(monkeypatch):
    snippets = [_snippet("news_hormuz_1"), _snippet("news_hormuz_2")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)
    monkeypatch.setattr(
        watch_module,
        "complete_json",
        lambda *a, **k: (_ for _ in ()).throw(LLMUnavailable("boom")),
    )

    signal = _make_signal()
    assert run_watch(signal) == run_watch_stub(signal)


# ---------------------------------------------------------------------------
# Real success path
# ---------------------------------------------------------------------------


def test_run_watch_uses_llm_score_when_available(monkeypatch):
    snippets = [_snippet("news_hormuz_1"), _snippet("news_hormuz_2"), _snippet("news_hormuz_3")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)
    monkeypatch.setattr(
        watch_module, "complete_json", lambda *a, **k: {"score": 72.4, "reason": "tense"}
    )

    signal = _make_signal()
    result = run_watch(signal)

    entry = result.corridor_risk["hormuz"]
    assert entry.score == 72.4
    # source_ids are exactly the retrieved snippets' ids (decision #10) —
    # never the raw signal id echoed back, never an LLM-selected subset.
    assert entry.source_ids == ["news_hormuz_1", "news_hormuz_2", "news_hormuz_3"]
    assert signal["id"] not in entry.source_ids


def test_run_watch_falls_through_model_tiers(monkeypatch):
    """Primary model fails, fallback model succeeds — no stub fallback."""

    snippets = [_snippet("s1"), _snippet("s2")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)

    calls: list[str] = []

    def _complete(prompt, *, cache_key, model):
        calls.append(model)
        if model == watch_module.get_settings().watch_model_primary:
            raise LLMUnavailable("rate limited")
        return {"score": 44.0, "reason": "ok"}

    monkeypatch.setattr(watch_module, "complete_json", _complete)

    signal = _make_signal()
    result = run_watch(signal)

    assert result.corridor_risk["hormuz"].score == 44.0
    assert len(calls) == 2


def test_run_watch_clamps_out_of_range_llm_score(monkeypatch):
    snippets = [_snippet("s1"), _snippet("s2"), _snippet("s3"), _snippet("s4"), _snippet("s5")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)
    monkeypatch.setattr(watch_module, "complete_json", lambda *a, **k: {"score": 999})

    result = run_watch(_make_signal())
    assert result.corridor_risk["hormuz"].score == 100.0


def test_run_watch_raises_no_uncaught_exception_on_bad_llm_payload(monkeypatch):
    """A response missing the "score" key must fall back cleanly, not crash
    the cascade."""

    snippets = [_snippet("s1"), _snippet("s2")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)
    monkeypatch.setattr(watch_module, "complete_json", lambda *a, **k: {"reason": "no score key"})

    signal = _make_signal()
    assert run_watch(signal) == run_watch_stub(signal)


# ---------------------------------------------------------------------------
# Confidence / band derivation (decision #6)
# ---------------------------------------------------------------------------


def test_confidence_never_from_llm_response(monkeypatch):
    """Even if the LLM response includes an extraneous confidence key, it's
    ignored — confidence/band are always derived from retrieval stats."""

    snippets = [_snippet(f"s{i}") for i in range(5)]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)
    monkeypatch.setattr(
        watch_module,
        "complete_json",
        lambda *a, **k: {"score": 50.0, "confidence": "high", "reason": "x"},
    )

    result = run_watch(_make_signal())
    entry = result.corridor_risk["hormuz"]
    assert entry.confidence == watch_module._confidence_for(
        _band_from_retrieval(snippets)
    )


def test_band_from_retrieval_widens_on_thin_evidence():
    full = [_snippet(f"s{i}") for i in range(5)]
    thin = [_snippet("s0")]
    assert _band_from_retrieval(thin) > _band_from_retrieval(full)


def test_band_from_retrieval_widens_on_stale_date_spread():
    consistent = [
        _snippet("a", date="2024-01-01"),
        _snippet("b", date="2024-01-15"),
        _snippet("c", date="2024-02-01"),
        _snippet("d", date="2024-02-10"),
        _snippet("e", date="2024-02-20"),
    ]
    stale_spread = [
        _snippet("a", date="2010-01-01"),
        _snippet("b", date="2015-01-01"),
        _snippet("c", date="2020-01-01"),
        _snippet("d", date="2023-01-01"),
        _snippet("e", date="2024-01-01"),
    ]
    assert _band_from_retrieval(stale_spread) > _band_from_retrieval(consistent)


def test_band_from_retrieval_stays_within_bounds():
    assert 4.0 <= _band_from_retrieval([]) <= 20.0
    assert 4.0 <= _band_from_retrieval([_snippet(f"s{i}") for i in range(20)]) <= 20.0


# ---------------------------------------------------------------------------
# Dark-ship anomaly context (SPEC.md Phase 7, F18)
# ---------------------------------------------------------------------------


def test_run_watch_prompt_includes_dark_ship_line_for_hormuz(monkeypatch):
    """Hormuz carries the curated 3-dark-tanker case (SPEC.md Phase 7 §3) --
    the prompt built for it must say so."""

    snippets = [_snippet("s1"), _snippet("s2")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)

    captured: dict = {}

    def _complete(prompt, *, cache_key, model):
        captured["prompt"] = prompt
        captured["cache_key"] = cache_key
        return {"score": 50.0, "reason": "ok"}

    monkeypatch.setattr(watch_module, "complete_json", _complete)

    run_watch(_make_signal(corridor="hormuz"))

    assert "3 tanker(s)" in captured["prompt"]
    assert "flagged by AIS anomaly detection" in captured["prompt"]
    assert "dark=3" in captured["cache_key"]


def test_run_watch_prompt_omits_dark_ship_line_for_clean_corridor(monkeypatch):
    """Malacca has zero flagged tankers -- no dark-ship line, no cache-key
    noise, and no snippets tagged 'malacca' exist in the real corpus, so
    retrieve() is monkeypatched here too."""

    snippets = [_snippet("s1", corridor="malacca"), _snippet("s2", corridor="malacca")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)

    captured: dict = {}

    def _complete(prompt, *, cache_key, model):
        captured["prompt"] = prompt
        captured["cache_key"] = cache_key
        return {"score": 50.0, "reason": "ok"}

    monkeypatch.setattr(watch_module, "complete_json", _complete)

    run_watch(_make_signal(corridor="malacca", headline="Routine transit near Malacca"))

    assert "flagged by AIS anomaly detection" not in captured["prompt"]
    assert "dark=0" in captured["cache_key"]


def test_run_watch_stub_dark_tanker_bump_matches_direct_stub_call(monkeypatch):
    """run_watch()'s stub-fallback path and a direct run_watch_stub() call
    must agree, dark-ship bump included (decision #9's uniform-fallback
    invariant, still true after Phase 7)."""

    monkeypatch.setenv("USE_REAL_AGENTS", "0")
    signal = _make_signal(corridor="hormuz", headline="Routine transit update")
    assert run_watch(signal) == run_watch_stub(signal)


# ---------------------------------------------------------------------------
# as_of cutoff / dark-ship suppression (SPEC.md Phase 8, F14)
# ---------------------------------------------------------------------------


def test_run_watch_as_of_passed_through_to_retrieve(monkeypatch):
    captured: dict = {}

    def _retrieve(corridor, headline, k, *, as_of=None, **kwargs):
        captured["as_of"] = as_of
        return [_snippet("s1"), _snippet("s2")]

    monkeypatch.setattr(watch_module, "retrieve", _retrieve)
    monkeypatch.setattr(
        watch_module, "complete_json", lambda *a, **k: {"score": 50.0, "reason": "ok"}
    )

    run_watch(_make_signal(), as_of="2023-12-01")
    assert captured["as_of"] == "2023-12-01"


def test_run_watch_as_of_suppresses_dark_ship_line_even_for_hormuz(monkeypatch):
    """hormuz normally carries the curated 3-dark-tanker case (SPEC.md Phase
    7 §3) -- but a historical replay (as_of set) must never mention it, since
    the anomaly detector's AIS data is a fixed present-day snapshot with no
    meaning attached to a years-old headline (SPEC.md Phase 8 decision #4)."""

    snippets = [_snippet("s1"), _snippet("s2")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)

    captured: dict = {}

    def _complete(prompt, *, cache_key, model):
        captured["prompt"] = prompt
        captured["cache_key"] = cache_key
        return {"score": 50.0, "reason": "ok"}

    monkeypatch.setattr(watch_module, "complete_json", _complete)

    run_watch(_make_signal(corridor="hormuz"), as_of="2019-06-01")

    assert "flagged by AIS anomaly detection" not in captured["prompt"]
    assert "dark=0" in captured["cache_key"]
    assert "as_of=2019-06-01" in captured["cache_key"]


def test_run_watch_no_as_of_still_includes_dark_ship_line_for_hormuz(monkeypatch):
    """Regression guard: as_of's suppression must not leak into the live
    (as_of=None) path -- hormuz's dark-ship line must still appear."""

    snippets = [_snippet("s1"), _snippet("s2")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)

    captured: dict = {}

    def _complete(prompt, *, cache_key, model):
        captured["prompt"] = prompt
        captured["cache_key"] = cache_key
        return {"score": 50.0, "reason": "ok"}

    monkeypatch.setattr(watch_module, "complete_json", _complete)

    run_watch(_make_signal(corridor="hormuz"))

    assert "flagged by AIS anomaly detection" in captured["prompt"]
    assert "dark=3" in captured["cache_key"]
    assert "as_of=live" in captured["cache_key"]


# ---------------------------------------------------------------------------
# Alarm-language classifier context (SPEC.md Phase 9, F19)
# ---------------------------------------------------------------------------

_ALARMING_HEADLINE = "Coast guard launches frantic search after vessel sends distress signal"
_CALM_HEADLINE = "Local council approves new bicycle lane along the riverside walking path"


def test_run_watch_prompt_includes_alarm_line_for_alarming_headline(monkeypatch):
    snippets = [_snippet("s1", corridor="malacca"), _snippet("s2", corridor="malacca")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)

    captured: dict = {}

    def _complete(prompt, *, cache_key, model):
        captured["prompt"] = prompt
        captured["cache_key"] = cache_key
        return {"score": 50.0, "reason": "ok"}

    monkeypatch.setattr(watch_module, "complete_json", _complete)

    run_watch(_make_signal(corridor="malacca", headline=_ALARMING_HEADLINE))

    assert "independently classified as alarming in tone" in captured["prompt"]
    assert "alarm=True" in captured["cache_key"]


def test_run_watch_prompt_omits_alarm_line_for_calm_headline(monkeypatch):
    snippets = [_snippet("s1", corridor="malacca"), _snippet("s2", corridor="malacca")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)

    captured: dict = {}

    def _complete(prompt, *, cache_key, model):
        captured["prompt"] = prompt
        captured["cache_key"] = cache_key
        return {"score": 50.0, "reason": "ok"}

    monkeypatch.setattr(watch_module, "complete_json", _complete)

    run_watch(_make_signal(corridor="malacca", headline=_CALM_HEADLINE))

    assert "independently classified as alarming in tone" not in captured["prompt"]
    assert "alarm=False" in captured["cache_key"]


def test_run_watch_alarm_line_not_suppressed_by_as_of(monkeypatch):
    """Contrast with the dark-ship line (SPEC.md Phase 8 decision #4): tone
    classification is a pure function of the replayed headline text, so it
    must still appear under as_of even though hormuz's dark-ship line is
    suppressed (SPEC.md Phase 9 decision #7)."""

    snippets = [_snippet("s1"), _snippet("s2")]
    monkeypatch.setattr(watch_module, "retrieve", lambda *a, **k: snippets)

    captured: dict = {}

    def _complete(prompt, *, cache_key, model):
        captured["prompt"] = prompt
        captured["cache_key"] = cache_key
        return {"score": 50.0, "reason": "ok"}

    monkeypatch.setattr(watch_module, "complete_json", _complete)

    run_watch(_make_signal(corridor="hormuz", headline=_ALARMING_HEADLINE), as_of="2019-06-01")

    assert "independently classified as alarming in tone" in captured["prompt"]
    assert "flagged by AIS anomaly detection" not in captured["prompt"]
    assert "alarm=True" in captured["cache_key"]
    assert "dark=0" in captured["cache_key"]
    assert "as_of=2019-06-01" in captured["cache_key"]


def test_run_watch_stub_alarm_bump_matches_direct_call(monkeypatch):
    """No escalation words, no dark tankers (malacca) in either headline --
    the entire score delta is attributable to the alarm-classifier bump
    (SPEC.md Phase 9 decision #6), mirroring the dark-tanker isolation test
    below."""

    monkeypatch.setenv("USE_REAL_AGENTS", "0")
    alarming_signal = {"corridor": "malacca", "headline": _ALARMING_HEADLINE, "severity": 0.4}
    calm_signal = {"corridor": "malacca", "headline": _CALM_HEADLINE, "severity": 0.4}

    alarming_score = run_watch(alarming_signal).corridor_risk["malacca"].score
    calm_score = run_watch(calm_signal).corridor_risk["malacca"].score

    from backend.agents.stubs import _ALARM_BUMP

    assert alarming_score - calm_score == pytest.approx(_ALARM_BUMP)
    # And run_watch's stub-fallback path agrees with a direct stub call.
    assert run_watch(alarming_signal) == run_watch_stub(alarming_signal)


def test_run_watch_stub_scores_higher_for_corridor_with_dark_tankers():
    """No escalation words in either headline -- the entire score delta is
    attributable to the dark-tanker bump (SPEC.md Phase 7 decision #12)."""

    hormuz_signal = {
        "corridor": "hormuz", "headline": "Routine transit update", "severity": 0.4,
    }
    clean_signal = {
        "corridor": "malacca", "headline": "Routine transit update", "severity": 0.4,
    }

    hormuz_score = run_watch_stub(hormuz_signal).corridor_risk["hormuz"].score
    clean_score = run_watch_stub(clean_signal).corridor_risk["malacca"].score

    from backend.agents.stubs import _DARK_TANKER_BUMP

    assert hormuz_score - clean_score == pytest.approx(3 * _DARK_TANKER_BUMP)
