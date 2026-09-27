"""Watch agent — grounded, cited corridor risk scoring (F1, F2, F8, F12).

Retrieve top-k relevant snippets (RAG, backend/agents/rag.py), score via an
LLM prompt built from them, and derive confidence/band from retrieval
agreement — never from the LLM's own self-report (SPEC.md Phase 4 decision
#6).

Graceful degradation is uniform (decision #9): an unrecognized corridor, an
empty retrieval, a disabled USE_REAL_AGENTS flag, a missing API key, or any
LLM call/parse failure (after trying both model tiers) all fall back to the
same place — run_watch_stub(signal) — one fallback path to reason about and
test, not several.

SPEC.md Phase 7 (F18): the dark-ship anomaly count for the signal's corridor
is folded into the prompt as one more grounded context line (never blended
into the score arithmetically — there is no composite-score slot to blend
into, SPEC.md Phase 4 decision #5) and into the LLM cache key.

SPEC.md Phase 8 (F14): an optional ``as_of`` cutoff enables backtest.py's
historical replay -- it caps retrieve() at snippets dated on/before it (no
future-info leak into a past headline's score) and suppresses the dark-ship
context line (the anomaly detector's AIS window is a fixed present-day
snapshot, meaningless attached to a years-old headline). ``None`` (the
default) is unchanged live-cascade behavior.

SPEC.md Phase 9 (F19): the alarm-language classifier's verdict is folded in
as one more context line, the same pattern as the dark-ship line -- except,
unlike the dark-ship line, it is never suppressed under ``as_of`` (decision
#7): tone classification is a pure function of the headline text being
replayed, with no present-day-snapshot dependency to make stale.
"""

from __future__ import annotations

import logging
from datetime import date

from backend.agents.alarm import is_alarming
from backend.agents.anomaly import dark_tanker_count
from backend.agents.llm import LLMUnavailable, complete_json
from backend.agents.rag import Snippet, retrieve
from backend.agents.stubs import _confidence_for, run_watch_stub
from backend.config import get_settings
from backend.schemas import CorridorRiskEntry, WatchAgentOutput

logger = logging.getLogger(__name__)

# Kept in sync with backend/seed/corridors.json BY CONVENTION, not a live
# query — run_watch() stays pure/DB-free, mirroring predict.py's and
# recommend.py's architecture notes (decision #13).
# tests/test_watch.py::test_known_corridors_matches_seed_config guards drift.
KNOWN_CORRIDORS = {"hormuz", "suez_cape", "atlantic", "malacca"}

_RETRIEVE_K = 5
_STALENESS_DAYS = 180

_PROMPT_TEMPLATE = """You are a corridor risk analyst. Score how much the \
following headline raises disruption risk for the "{corridor}" oil transit \
corridor, from 0 (no added risk) to 100 (severe, imminent disruption).

Headline: {headline}

Context from prior reporting on this corridor:
{context}
{dark_ship_line}{alarm_line}
Respond with a JSON object only: {{"score": <0-100 number>, "reason": \
"<one sentence>"}}"""


def _build_prompt(
    corridor: str,
    headline: str,
    snippets: list[Snippet],
    dark_count: int,
    alarming: bool,
) -> str:
    context = "\n".join(f"- ({s.date}, {s.source}) {s.text}" for s in snippets)
    dark_ship_line = (
        f"\n{dark_count} tanker(s) near this corridor are currently flagged by AIS "
        "anomaly detection as behaving suspiciously (transponder gap and/or "
        "off-course deviation) -- weigh this as one more grounded signal, not "
        "a deciding factor on its own.\n"
        if dark_count > 0
        else ""
    )
    alarm_line = (
        "\nThis headline's language was independently classified as alarming in "
        "tone by a separate tone classifier -- weigh this as one more grounded "
        "signal, not a deciding factor on its own.\n"
        if alarming
        else ""
    )
    return _PROMPT_TEMPLATE.format(
        corridor=corridor,
        headline=headline,
        context=context,
        dark_ship_line=dark_ship_line,
        alarm_line=alarm_line,
    )


def _band_from_retrieval(snippets: list[Snippet]) -> float:
    """Tighter band when several, date-consistent snippets were retrieved;
    wider when evidence is thin or stale (decision #6)."""

    band = max(4.0, min(20.0, 20.0 - 3.0 * len(snippets)))
    if len(snippets) < _RETRIEVE_K:
        band += 6.0  # thin evidence for this corridor
    dates = sorted(date.fromisoformat(s.date) for s in snippets)
    if dates and (dates[-1] - dates[0]).days > _STALENESS_DAYS:
        band += 4.0  # retrieved snippets span a stale/mixed-recency range
    return round(max(4.0, min(20.0, band)), 1)


def _score_with_llm(
    corridor: str,
    headline: str,
    snippets: list[Snippet],
    dark_count: int,
    alarming: bool,
    as_of: str | None,
) -> float:
    prompt = _build_prompt(corridor, headline, snippets, dark_count, alarming)
    cache_key = (
        f"{corridor}|{headline.strip().lower()}|"
        f"{','.join(sorted(s.id for s in snippets))}|dark={dark_count}|"
        f"alarm={alarming}|as_of={as_of or 'live'}"
    )
    settings = get_settings()

    last_exc: Exception | None = None
    for model in (settings.watch_model_primary, settings.watch_model_fallback):
        try:
            data = complete_json(prompt, cache_key=cache_key, model=model)
            return max(0.0, min(100.0, float(data["score"])))
        except (LLMUnavailable, KeyError, TypeError, ValueError) as exc:
            logger.warning("Watch: model %s failed (%s), trying next tier", model, exc)
            last_exc = exc
    raise LLMUnavailable(f"both model tiers failed: {last_exc}")


def run_watch(signal: dict, *, as_of: str | None = None) -> WatchAgentOutput:
    """Score the affected corridor from an injected signal — the real Watch
    agent. Falls back to run_watch_stub(signal) per decision #9's uniform
    fallback list: real-agents flag off, no API key, an unrecognized
    corridor, empty retrieval, or an LLM failure on both model tiers.

    ``as_of`` (SPEC.md Phase 8): historical-replay mode for backtest.py. When
    set: (a) retrieve() only sees snippets dated on/before it, and (b) the
    dark-ship anomaly context line is suppressed. ``None`` (default) is
    unchanged live-cascade behavior; cascade.py never passes as_of.

    SPEC.md Phase 9 (F19): the alarm-language classifier always runs
    (unaffected by ``as_of``) -- see module docstring.
    """

    settings = get_settings()
    corridor = signal["corridor"]

    if not settings.use_real_agents or not settings.groq_api_key:
        return run_watch_stub(signal)

    if corridor not in KNOWN_CORRIDORS:
        logger.warning("Watch: unknown corridor %r, falling back to stub", corridor)
        return run_watch_stub(signal)

    headline = str(signal.get("headline", ""))
    snippets = retrieve(corridor, headline, k=_RETRIEVE_K, as_of=as_of)
    if not snippets:
        logger.warning("Watch: no snippets retrieved for %r, falling back to stub", corridor)
        return run_watch_stub(signal)

    dark_count = 0 if as_of is not None else dark_tanker_count(corridor)
    alarming = is_alarming(headline)
    try:
        score = _score_with_llm(corridor, headline, snippets, dark_count, alarming, as_of)
    except LLMUnavailable as exc:
        logger.warning("Watch: LLM unavailable (%s), falling back to stub", exc)
        return run_watch_stub(signal)

    band = _band_from_retrieval(snippets)
    entry = CorridorRiskEntry(
        score=round(score, 1),
        confidence=_confidence_for(band),
        band=band,
        source_ids=[s.id for s in snippets],
    )
    return WatchAgentOutput(corridor_risk={corridor: entry})
