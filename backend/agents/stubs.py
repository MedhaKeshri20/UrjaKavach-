"""Deterministic Watch stub.

    ┌─────────────────────────────────────────────────────────────────┐
    │  v1.3 (SPEC.md Phase 4): Watch now has a real RAG+LLM agent in    │
    │  backend/agents/watch.py (`run_watch`). This stub is no longer   │
    │  dead code — it's the offline fallback `run_watch` degrades to   │
    │  whenever USE_REAL_AGENTS is off, no GROQ_API_KEY is set, the     │
    │  corridor is unrecognized, retrieval comes up empty, or the LLM   │
    │  fails on both model tiers. It still emits the exact contract     │
    │  envelope (WatchAgentOutput) the real agent emits.                │
    └─────────────────────────────────────────────────────────────────┘

Everything here is pure arithmetic on the injected signal (plus, since v1.3
Phase 7, one real -- but network-free, always-available -- dependency: the
dark-ship anomaly detector) so the same headline always yields the same
score — the determinism the demo relies on (PRD §10).

v1.3 (SPEC.md Phase 3): Predict is no longer a stub — `assumptions_from_severity`
and `run_predict` (formerly `run_predict_stub`) moved to `backend/agents/predict.py`.

v1.3 (SPEC.md Phase 7): dark-tanker anomaly context also reaches this offline
path (decision #12) — unlike the LLM/RAG path, anomaly detection has no
network dependency, so there's no reason the demo's fully-offline fallback
shouldn't also visibly react to a corridor's dark tankers.

v1.3 (SPEC.md Phase 9): the alarm-language classifier (F19) is likewise
network-free and always available, so it gets a matching arithmetic bump
here (decision #5) alongside the dark-tanker bump.
"""

from __future__ import annotations

from backend.agents.alarm import is_alarming
from backend.agents.anomaly import dark_tanker_count
from backend.schemas import CorridorRiskEntry, Confidence, WatchAgentOutput

# Words that nudge a headline's risk up, for demo determinism without an LLM.
_ESCALATION_WORDS = {
    "seized": 25,
    "attack": 30,
    "strike": 22,
    "closure": 28,
    "closed": 28,
    "blockade": 30,
    "mine": 20,
    "missile": 26,
    "sanction": 15,
    "explosion": 24,
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _confidence_for(band: float) -> Confidence:
    """Tighter band => higher confidence. Full-word spelling per contract."""

    if band <= 8:
        return "high"
    if band <= 16:
        return "medium"
    return "low"


# Per flagged tanker in the signal's corridor -- same rough scale as
# _ESCALATION_WORDS (15-30), deliberately smaller since a dark-ship signal
# corroborates a headline, it isn't a headline-level escalation word itself
# (SPEC.md Phase 7 decision #12).
_DARK_TANKER_BUMP = 10.0

# Flat, one-time bump when the alarm-language classifier flags the headline
# as alarming -- smaller than both _ESCALATION_WORDS (15-30, a direct oil-risk
# signal) and _DARK_TANKER_BUMP (10.0, a physical AIS corroboration), since
# tone classification is the most indirect of the three stub inputs
# (SPEC.md Phase 9 decision #6). Flat, not probability-scaled, to match the
# classifier's binary output (decision #3).
_ALARM_BUMP = 8.0


def run_watch_stub(signal: dict) -> WatchAgentOutput:
    """Score the affected corridor from an injected signal.

    ``signal`` shape: ``{id, corridor, headline, severity?, source_ids?}``.
    """

    corridor = signal["corridor"]
    severity = float(signal.get("severity", 0.4))
    raw_headline = str(signal.get("headline", ""))
    headline = raw_headline.lower()

    bump = sum(w for kw, w in _ESCALATION_WORDS.items() if kw in headline)
    dark_bump = _DARK_TANKER_BUMP * dark_tanker_count(corridor)
    alarm_bump = _ALARM_BUMP if is_alarming(raw_headline) else 0.0
    score = _clamp(severity * 100 + bump + dark_bump + alarm_bump, 0.0, 100.0)
    # Wider band when the signal is thin (few provenance ids).
    source_ids = list(signal.get("source_ids") or [signal.get("id", "sig_unknown")])
    band = _clamp(20 - 3 * len(source_ids), 4.0, 20.0)

    entry = CorridorRiskEntry(
        score=round(score, 1),
        confidence=_confidence_for(band),
        band=round(band, 1),
        source_ids=source_ids,
    )
    return WatchAgentOutput(corridor_risk={corridor: entry})
