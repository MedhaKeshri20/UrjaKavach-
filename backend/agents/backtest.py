"""Backtest / validation module (F14) -- replays one curated historical shock
through the real Watch agent, chronologically, with a strict as_of cutoff so
no future snippet leaks into the past (SPEC.md Phase 8 decision #3), and
measures how long before a hand-curated, illustrative Brent price series
crossed a notable-move threshold Watch's own score crossed its alert
threshold first.

Framed explicitly, everywhere this surfaces, as one illustrative historical
case -- never a validated statistical accuracy claim (PRD's own honesty
guard, repeated in the API response's own "note" field).

Pure/DB-free, like anomaly.py -- no runtime failure mode to degrade from, so
a curated case that never crosses its own threshold is a bug to catch in
tests, not something this module papers over (decision #10).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Callable, TypeVar

from backend.agents.rag import load_corpus
from backend.agents.watch import run_watch
from backend.cascade import AFFECTED_THRESHOLD
from backend.schemas import Validation

_DATA_DIR = Path(__file__).parent / "data" / "backtest"
_BRENT_SPIKE_PCT = 5.0  # decision #8 -- % above the pre-crisis baseline mean

T = TypeVar("T")


class BacktestCaseNotFound(Exception):
    """No curated data file for this case id -- a real 404 (decision #15),
    distinct from _first_crossing's "curation bug" error below."""


@dataclass(frozen=True)
class ScorePoint:
    ts: str
    headline_id: str
    score: float
    source_ids: list[str]


@dataclass(frozen=True)
class PricePoint:
    ts: str
    price_usd_bbl: float


@dataclass(frozen=True)
class BacktestResult:
    validation: Validation
    corridor: str
    label: str
    watch_alert_threshold: float
    watch_crossed_at: str
    brent_spike_threshold_usd: float
    brent_crossed_at: str
    score_timeline: list[ScorePoint]
    price_timeline: list[PricePoint]


def _load_case(case_id: str) -> dict:
    path = _DATA_DIR / f"{case_id}.json"
    if not path.exists():
        raise BacktestCaseNotFound(f"no curated backtest case {case_id!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def _score_timeline(case: dict) -> list[ScorePoint]:
    """Replay each curated headline through the real Watch agent, in
    chronological order, with as_of pinned to that headline's own date
    (decision #3) -- never the live present, never a later headline's date.
    """

    corpus = {row["id"]: row for row in load_corpus()}
    points: list[ScorePoint] = []
    for h in case["headlines"]:
        row = corpus[h["source_id"]]
        as_of = h["ts"][:10]  # date part -- matches Snippet.date's "YYYY-MM-DD" format
        signal = {"corridor": case["corridor"], "headline": row["text"], "severity": 0.0}
        out = run_watch(signal, as_of=as_of)
        entry = out.corridor_risk[case["corridor"]]
        points.append(
            ScorePoint(
                ts=h["ts"],
                headline_id=h["source_id"],
                score=entry.score,
                source_ids=entry.source_ids,
            )
        )
    return points


def _price_timeline(case: dict) -> list[PricePoint]:
    return [PricePoint(ts=p["ts"], price_usd_bbl=p["price_usd_bbl"]) for p in case["brent_series"]]


def _baseline_mean(case: dict) -> float:
    start, end = case["brent_baseline_start"], case["brent_baseline_end"]
    baseline = [p["price_usd_bbl"] for p in case["brent_series"] if start <= p["ts"][:10] <= end]
    if not baseline:
        raise ValueError(f"backtest case {case['id']!r}: empty baseline window")
    return sum(baseline) / len(baseline)


def _first_crossing(points: list[T], value_fn: Callable[[T], float], threshold: float) -> T:
    for p in points:
        if value_fn(p) >= threshold:
            return p
    raise ValueError(
        "curated backtest data never crosses its own threshold -- fix the "
        "case data, don't silently degrade (SPEC.md Phase 8 decision #10)"
    )


@lru_cache(maxsize=8)
def run_backtest(case_id: str) -> BacktestResult:
    """Compute (and cache -- decision #16) the full backtest result for one
    curated case: Watch's real score timeline, the illustrative Brent price
    timeline, and the lead time between when each first crosses its own
    threshold."""

    case = _load_case(case_id)
    score_timeline = _score_timeline(case)
    price_timeline = _price_timeline(case)

    watch_point = _first_crossing(score_timeline, lambda p: p.score, AFFECTED_THRESHOLD)
    spike_threshold = round(_baseline_mean(case) * (1 + _BRENT_SPIKE_PCT / 100.0), 2)
    price_point = _first_crossing(price_timeline, lambda p: p.price_usd_bbl, spike_threshold)

    watch_dt = datetime.fromisoformat(watch_point.ts.replace("Z", "+00:00"))
    price_dt = datetime.fromisoformat(price_point.ts.replace("Z", "+00:00"))
    lead_hours = round((price_dt - watch_dt).total_seconds() / 3600.0, 1)

    return BacktestResult(
        validation=Validation(backtest_id=case_id, signal_lead_hours=lead_hours),
        corridor=case["corridor"],
        label=case["label"],
        watch_alert_threshold=AFFECTED_THRESHOLD,
        watch_crossed_at=watch_point.ts,
        brent_spike_threshold_usd=spike_threshold,
        brent_crossed_at=price_point.ts,
        score_timeline=score_timeline,
        price_timeline=price_timeline,
    )
