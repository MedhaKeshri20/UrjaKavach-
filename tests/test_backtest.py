"""Tests for backend/agents/backtest.py — the backtest/validation module
(SPEC.md Phase 8, F14). Runs with USE_REAL_AGENTS unset/off (this repo's
default), so run_watch() degrades internally to run_watch_stub() for every
replayed headline — fully deterministic, no GROQ_API_KEY required, and
pinned against the hand-verified worked example in SPEC.md Phase 8 §3.3.
"""

from __future__ import annotations

import pytest

from backend.agents import backtest as backtest_module
from backend.agents.backtest import (
    BacktestCaseNotFound,
    PricePoint,
    ScorePoint,
    _baseline_mean,
    _first_crossing,
    _load_case,
    run_backtest,
)
from backend.cascade import AFFECTED_THRESHOLD


@pytest.fixture(autouse=True)
def _clear_cache():
    """run_backtest is lru_cache'd (decision #16) -- clear between tests so
    monkeypatches in one test don't leak a cached result into another."""

    run_backtest.cache_clear()
    yield
    run_backtest.cache_clear()


# ---------------------------------------------------------------------------
# The worked example (SPEC.md Phase 8 §3.3) — hand-verified, deterministic
# ---------------------------------------------------------------------------


def test_run_backtest_stub_fallback_matches_worked_example():
    result = run_backtest("red_sea_2023")

    assert result.watch_crossed_at == "2023-12-03T00:00:00Z"
    assert result.brent_spike_threshold_usd == 84.5
    assert result.brent_crossed_at == "2024-02-02T00:00:00Z"
    assert result.validation.signal_lead_hours == 1464.0
    assert result.validation.backtest_id == "red_sea_2023"
    assert result.watch_alert_threshold == AFFECTED_THRESHOLD == 50.0
    assert result.corridor == "suez_cape"


def test_score_timeline_matches_hand_computed_stub_scores():
    """Pins SPEC.md Phase 8 §3.3's keyword-bump table so a future edit to the
    curated headline text or _ESCALATION_WORDS can't silently drift.

    Updated for SPEC.md Phase 9 (F19): every one of this case's 7 curated
    headlines classifies as "alarming" by the committed alarm-language
    corpus, so each score is +8.0 (_ALARM_BUMP) over its pre-Phase-9 value --
    verified not to shift `watch_crossed_at`/`signal_lead_hours`
    (test_run_backtest_stub_fallback_matches_worked_example below), since
    the uniform +8.0 shift doesn't change which headline first crosses
    AFFECTED_THRESHOLD=50.0."""

    result = run_backtest("red_sea_2023")
    scores = {p.headline_id: p.score for p in result.score_timeline}

    assert scores == {
        "news_suez_2023_houthi": 8.0,
        "news_suez_2023_dec_triple_attack": 64.0,
        "news_suez_2023_bp_pause": 38.0,
        "news_suez_2024_us_uk_strikes": 86.0,
        "news_suez_2024_reroute": 38.0,
        "sanc_suez_2024_insurance": 8.0,
        "news_suez_2024_strike": 56.0,
    }


def test_score_timeline_is_in_chronological_order():
    result = run_backtest("red_sea_2023")
    timestamps = [p.ts for p in result.score_timeline]
    assert timestamps == sorted(timestamps)


def test_price_timeline_matches_case_data():
    result = run_backtest("red_sea_2023")
    assert len(result.price_timeline) == 11
    assert result.price_timeline[0] == PricePoint(ts="2023-11-01T00:00:00Z", price_usd_bbl=80.40)
    assert result.price_timeline[-1] == PricePoint(ts="2024-03-06T00:00:00Z", price_usd_bbl=87.60)


def test_baseline_mean_and_spike_threshold_computed_correctly():
    case = _load_case("red_sea_2023")
    mean = _baseline_mean(case)
    assert mean == pytest.approx(80.475)
    assert round(mean * 1.05, 2) == 84.50


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_run_backtest_unknown_case_raises_not_found():
    with pytest.raises(BacktestCaseNotFound):
        run_backtest("not_a_real_case")


def test_first_crossing_raises_if_never_crossed():
    points = [ScorePoint(ts="2024-01-01T00:00:00Z", headline_id="x", score=10.0, source_ids=[])]
    with pytest.raises(ValueError):
        _first_crossing(points, lambda p: p.score, 50.0)


def test_first_crossing_returns_first_point_at_or_above_threshold():
    points = [
        ScorePoint(ts="2024-01-01T00:00:00Z", headline_id="a", score=10.0, source_ids=[]),
        ScorePoint(ts="2024-01-02T00:00:00Z", headline_id="b", score=55.0, source_ids=[]),
        ScorePoint(ts="2024-01-03T00:00:00Z", headline_id="c", score=90.0, source_ids=[]),
    ]
    assert _first_crossing(points, lambda p: p.score, 50.0).headline_id == "b"


# ---------------------------------------------------------------------------
# as_of threading and caching
# ---------------------------------------------------------------------------


def test_score_timeline_passes_each_headlines_own_date_as_of(monkeypatch):
    captured: list[str | None] = []

    def _fake_run_watch(signal, *, as_of=None):
        captured.append(as_of)
        from backend.agents.stubs import run_watch_stub

        return run_watch_stub(signal)

    monkeypatch.setattr(backtest_module, "run_watch", _fake_run_watch)

    result = run_backtest("red_sea_2023")
    case = _load_case("red_sea_2023")
    expected = [h["ts"][:10] for h in case["headlines"]]

    assert captured == expected
    # never None, never the live present, never a later headline's date
    assert all(as_of is not None for as_of in captured)
    assert len(result.score_timeline) == len(expected)


def test_run_backtest_is_cached(monkeypatch):
    calls = {"n": 0}
    from backend.agents.stubs import run_watch_stub

    def _fake_run_watch(signal, *, as_of=None):
        calls["n"] += 1
        return run_watch_stub(signal)

    monkeypatch.setattr(backtest_module, "run_watch", _fake_run_watch)

    run_backtest("red_sea_2023")
    run_backtest("red_sea_2023")

    assert calls["n"] == 7  # one Watch call per curated headline, not 14
