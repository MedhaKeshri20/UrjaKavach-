"""Alarm-language tone classifier (F19, SPEC.md Segment 1, Phase 9).

is_alarming() is a pure, network-free function over the committed corpus
(backend/agents/data/alarm_corpus.json) -- these tests need no monkeypatching
and no GROQ_API_KEY, mirroring test_anomaly.py's posture for the other real
ML component in this codebase.
"""

import json
from pathlib import Path

from backend.agents.alarm import _CORPUS_PATH, _classifier, is_alarming

_CANONICAL_DEMO_HEADLINE = "Missile strike closes Strait of Hormuz shipping lane"


def test_is_alarming_true_for_canonical_demo_headline():
    """Pins SPEC.md Phase 9 §3.1's worked example -- the exact headline
    frontend/components/mission/launch-simulation.tsx injects for the one-
    button Mission Control demo must classify as alarming."""

    assert is_alarming(_CANONICAL_DEMO_HEADLINE) is True


def test_is_alarming_false_for_routine_headline():
    assert is_alarming("Shipping companies report steady, on-schedule deliveries this quarter") is False


def test_is_alarming_true_for_seizure_headline():
    assert is_alarming("Iran seizes tanker in the Strait of Hormuz amid rising tensions") is True


def test_is_alarming_returns_bool_not_numpy_type():
    result = is_alarming(_CANONICAL_DEMO_HEADLINE)
    assert isinstance(result, bool)


def test_classifier_is_deterministic_across_calls():
    """lru_cache means _classifier() returns the same fitted pipeline object
    every call; is_alarming() on the same text agrees with itself."""

    first = _classifier()
    second = _classifier()
    assert first is second
    assert is_alarming(_CANONICAL_DEMO_HEADLINE) == is_alarming(_CANONICAL_DEMO_HEADLINE)


def test_corpus_label_balance():
    """Regression guard: a future careless edit to the committed corpus
    can't silently skew it to all-one-class without a test noticing."""

    corpus = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
    assert len(corpus) >= 50
    alarming_frac = sum(row["label"] for row in corpus) / len(corpus)
    assert 0.3 <= alarming_frac <= 0.7


def test_corpus_path_resolves_to_committed_file():
    assert _CORPUS_PATH == Path(__file__).resolve().parent.parent / "backend" / "agents" / "data" / "alarm_corpus.json"
    assert _CORPUS_PATH.exists()
