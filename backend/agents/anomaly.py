"""Dark-ship anomaly detector (F18) — the project's one real, learned-from-
data component. Unsupervised sklearn.ensemble.IsolationForest over per-vessel
AIS features (speed variability, heading-change rate, deviation from the
vessel's own initial course, transponder-gap length) — no labelled
"suspicious ship" dataset exists, so learning what normal looks like and
flagging deviations is the right tool, not a forced ML story
(PROJECT_GUIDE.md §10E).

Pure/DB-free, fed only by the static, committed AIS replay set (Phase 6, via
ais.py) -- like geo.py's at_risk_tanker_ids(), this has no network dependency
and nothing that can fail at runtime, so unlike Watch's LLM path there is no
offline-fallback branch here (SPEC.md Phase 7 decision #7).

ais.py (not geo.py) is the import source for list_tankers(): geo.py's
build_geo() calls into this module for dark_tanker_ids, so this module
importing from geo.py would be circular. See ais.py's own docstring.
"""

from __future__ import annotations

import math
from datetime import datetime
from functools import lru_cache

from sklearn.ensemble import IsolationForest

from backend.agents.ais import list_tankers

_KM_PER_DEG_LAT = 111.32

# Tuned against the curated AIS set (SPEC.md Phase 7 §4) so the three
# synthetic "went dark" Hormuz tankers cross the threshold and the other 13
# don't -- verified stable across a contamination/seed sweep, not a
# principled statistical derivation (n=16 is too small for one).
# random_state fixes the forest's split choices for byte-identical output
# across runs (PLAN.md §5's determinism rule).
_N_ESTIMATORS = 200
_CONTAMINATION = 0.19
_RANDOM_STATE = 42


def _project_km(lat: float, lon: float, ref_lat: float) -> tuple[float, float]:
    """Flat equirectangular projection, accurate to well under 1km at this
    scale -- the same 'illustrative, not surveyed' honesty Phase 6 already
    applied to the corridor GeoJSON itself."""

    x = lon * _KM_PER_DEG_LAT * math.cos(math.radians(ref_lat))
    y = lat * _KM_PER_DEG_LAT
    return x, y


def _heading_delta(a: float, b: float) -> float:
    """Smallest angle between two compass headings (handles the 350deg ->
    10deg wraparound as a 20deg change, not 340deg)."""

    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _features(tanker: dict) -> tuple[float, float, float, float]:
    """(max_gap_hours, max_heading_delta_deg, speed_std_knots,
    max_path_deviation_km) over one tanker's full committed track.

    max_path_deviation_km is self-referential (SPEC.md Phase 7 decision #3):
    each tanker is extrapolated from its own first observed leg's velocity,
    not compared against the shared corridor polyline -- the curated fleet
    deliberately seeds each clean tanker in its own parallel "lane" offset
    from that polyline, which would otherwise swamp the actual anomaly
    signal. Every value is rounded (decision #4) to collapse floating-point
    noise between genuinely-identical "clean straight line" tankers into
    exact ties, rather than 13 numerically-almost-equal-but-distinct rows.
    """

    track = tanker["track"]
    timestamps = [datetime.fromisoformat(p["ts"].replace("Z", "+00:00")) for p in track]

    gaps = [
        (timestamps[i + 1] - timestamps[i]).total_seconds() / 3600.0
        for i in range(len(timestamps) - 1)
    ]
    headings = [p["heading_deg"] for p in track]
    heading_deltas = [
        _heading_delta(headings[i], headings[i + 1]) for i in range(len(headings) - 1)
    ]
    speeds = [p["speed_knots"] for p in track]
    speed_mean = sum(speeds) / len(speeds)
    speed_std = math.sqrt(sum((s - speed_mean) ** 2 for s in speeds) / len(speeds))

    ref_lat = track[0]["lat"]
    projected = [_project_km(p["lat"], p["lon"], ref_lat) for p in track]
    x0, y0 = projected[0]
    x1, y1 = projected[1]
    dt0 = (timestamps[1] - timestamps[0]).total_seconds() / 3600.0
    vx, vy = (x1 - x0) / dt0, (y1 - y0) / dt0

    deviations = []
    for i in range(2, len(track)):
        elapsed_h = (timestamps[i] - timestamps[0]).total_seconds() / 3600.0
        pred_x, pred_y = x0 + vx * elapsed_h, y0 + vy * elapsed_h
        act_x, act_y = projected[i]
        deviations.append(math.hypot(act_x - pred_x, act_y - pred_y))

    return (
        round(max(gaps), 1),
        round(max(heading_deltas), 1),
        round(speed_std, 2),
        round(max(deviations), 1),
    )


@lru_cache(maxsize=1)
def _anomalous_ids() -> frozenset[str]:
    """Fit once over the whole committed fleet (16 samples) and cache -- the
    AIS data never changes at runtime, so this is a one-time cost per
    process, mirroring geo.py's list_tankers() lru_cache."""

    tankers = list_tankers()
    X = [_features(t) for t in tankers]
    model = IsolationForest(
        n_estimators=_N_ESTIMATORS,
        contamination=_CONTAMINATION,
        random_state=_RANDOM_STATE,
    )
    labels = model.fit_predict(X)  # -1 = anomaly, 1 = normal
    return frozenset(t["id"] for t, label in zip(tankers, labels) if label == -1)


def dark_tanker_ids(elevated_corridors: set[str]) -> list[str]:
    """Anomalous tankers within the currently-elevated/excluded corridor set
    -- filtered the same way geo.at_risk_tanker_ids() is (decision #8), so a
    signal's geo block only ever carries dark markers relevant to it."""

    by_corridor = {t["id"]: t["corridor_id"] for t in list_tankers()}
    return sorted(
        tid for tid in _anomalous_ids() if by_corridor.get(tid) in elevated_corridors
    )


def dark_tanker_count(corridor: str) -> int:
    """Anomalous tankers in one specific corridor, independent of any
    elevated-threshold concept -- Watch scores a signal's corridor directly
    and never computes an elevated set (decision #9). An unrecognized
    corridor returns 0 rather than raising, matching at_risk_tanker_ids()'s
    'no geometry to fail on' tolerance for bad input."""

    by_corridor = {t["id"]: t["corridor_id"] for t in list_tankers()}
    return sum(1 for tid in _anomalous_ids() if by_corridor.get(tid) == corridor)
