"""Dark-ship anomaly detector: _features()/dark_tanker_ids()/dark_tanker_count()
(F18, SPEC.md Segment 1, Phase 7). All cases run against the real committed
AIS replay set (backend/agents/data/ais_sample.json) -- no synthetic fixture
needed, since Phase 7 curated the dark-tanker cases directly into that file
(SPEC.md Phase 7 §3)."""

from backend.agents.ais import list_tankers
from backend.agents.anomaly import _anomalous_ids, _features, dark_tanker_count, dark_tanker_ids

_EXPECTED_DARK = {"hormuz_02", "hormuz_03", "hormuz_04"}


def _tanker(tanker_id: str) -> dict:
    return next(t for t in list_tankers() if t["id"] == tanker_id)


# --------------------------------------------------------------------------- #
# _features -- pins SPEC.md Phase 7 §4's exact measured table so a future
# edit to the synthetic tracks can't silently drift without a test noticing.
# --------------------------------------------------------------------------- #


def test_features_clean_tanker_is_all_zero_gap_heading_speedstd_deviation():
    assert _features(_tanker("hormuz_01")) == (3.0, 0.0, 0.0, 0.0)


def test_features_every_clean_tanker_matches_hormuz_01_exactly():
    """All 13 non-dark tankers fly a straight line at constant heading/speed
    -- their feature vectors must be exact ties (SPEC.md decision #4's whole
    point), not just similar."""

    clean_ids = {t["id"] for t in list_tankers()} - _EXPECTED_DARK - {"hormuz_01"}
    assert len(clean_ids) == 12
    for tid in clean_ids:
        assert _features(_tanker(tid)) == (3.0, 0.0, 0.0, 0.0), tid


def test_features_dark_tankers_match_spec_table():
    assert _features(_tanker("hormuz_02")) == (12.0, 95.0, 3.43, 85.5)
    assert _features(_tanker("hormuz_03")) == (12.0, 120.0, 3.79, 75.2)
    assert _features(_tanker("hormuz_04")) == (12.0, 80.0, 3.74, 78.3)


# --------------------------------------------------------------------------- #
# _anomalous_ids / dark_tanker_ids -- exact match, not "contains" (the whole
# point of SPEC.md §4's tuned contamination/random_state constants)
# --------------------------------------------------------------------------- #


def test_anomalous_ids_flags_exactly_the_three_dark_hormuz_tankers():
    assert _anomalous_ids() == frozenset(_EXPECTED_DARK)


def test_dark_tanker_ids_hormuz_elevated():
    assert dark_tanker_ids({"hormuz"}) == ["hormuz_02", "hormuz_03", "hormuz_04"]


def test_dark_tanker_ids_clean_corridors_return_nothing():
    assert dark_tanker_ids({"suez_cape"}) == []
    assert dark_tanker_ids({"atlantic"}) == []
    assert dark_tanker_ids({"malacca"}) == []


def test_dark_tanker_ids_empty_elevated_set():
    assert dark_tanker_ids(set()) == []


def test_dark_tanker_ids_unions_multiple_corridors():
    """Still just the 3 Hormuz ids -- unioning in a clean corridor adds
    nothing."""

    assert dark_tanker_ids({"hormuz", "malacca"}) == ["hormuz_02", "hormuz_03", "hormuz_04"]


def test_dark_tanker_ids_unrecognized_corridor_matches_nothing_no_raise():
    assert dark_tanker_ids({"not_a_real_corridor"}) == []


# --------------------------------------------------------------------------- #
# dark_tanker_count -- unfiltered-by-elevated helper for Watch's prompt
# --------------------------------------------------------------------------- #


def test_dark_tanker_count_hormuz_is_three():
    assert dark_tanker_count("hormuz") == 3


def test_dark_tanker_count_clean_corridor_is_zero():
    assert dark_tanker_count("suez_cape") == 0
    assert dark_tanker_count("atlantic") == 0
    assert dark_tanker_count("malacca") == 0


def test_dark_tanker_count_unrecognized_corridor_is_zero_no_raise():
    assert dark_tanker_count("not_a_real_corridor") == 0


# --------------------------------------------------------------------------- #
# Determinism (PLAN.md's own acceptance line: "stable across runs")
# --------------------------------------------------------------------------- #


def test_dark_tanker_ids_is_deterministic_across_calls():
    assert dark_tanker_ids({"hormuz"}) == dark_tanker_ids({"hormuz"})


def test_dark_tanker_count_is_deterministic_across_calls():
    assert dark_tanker_count("hormuz") == dark_tanker_count("hormuz")


def test_anomalous_ids_is_deterministic_across_calls():
    assert _anomalous_ids() == _anomalous_ids()
