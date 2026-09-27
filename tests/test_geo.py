"""Geospatial agent: list_tankers()/at_risk_tanker_ids()/build_geo() (F11,
F13, SPEC.md Segment 1, Phase 6). Mirrors tests/test_graph.py's fixture
pattern -- all cases run against today's real seed data."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agents.geo import at_risk_tanker_ids, build_geo, list_tankers
from backend.db import Base
from backend.schemas import Geo
from backend.seed import seed_all


def _seeded_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    seed_all(session)
    return session


# --------------------------------------------------------------------------- #
# list_tankers
# --------------------------------------------------------------------------- #


def test_list_tankers_returns_16_records_across_four_corridors():
    tankers = list_tankers()
    assert len(tankers) == 16

    by_corridor: dict[str, int] = {}
    for t in tankers:
        by_corridor[t["corridor_id"]] = by_corridor.get(t["corridor_id"], 0) + 1
    assert by_corridor == {"hormuz": 4, "suez_cape": 4, "atlantic": 4, "malacca": 4}


def test_list_tankers_ids_are_unique():
    tankers = list_tankers()
    ids = [t["id"] for t in tankers]
    assert len(ids) == len(set(ids))


def test_list_tankers_each_track_has_8_points_with_required_fields():
    for t in list_tankers():
        track = t["track"]
        assert len(track) == 8
        for point in track:
            assert set(point) >= {"ts", "lat", "lon", "heading_deg", "speed_knots"}
            assert -90.0 <= point["lat"] <= 90.0
            assert -180.0 <= point["lon"] <= 180.0


def test_list_tankers_is_deterministic_across_calls():
    """Same process, same data -- two calls must be identical (no randomness,
    no live/network dependency, PLAN.md's determinism requirement)."""

    assert list_tankers() == list_tankers()


# --------------------------------------------------------------------------- #
# at_risk_tanker_ids -- static tag, no geometry (decision #3)
# --------------------------------------------------------------------------- #


def test_at_risk_tanker_ids_matches_static_tags():
    result = at_risk_tanker_ids({"hormuz"})
    assert result == ["hormuz_01", "hormuz_02", "hormuz_03", "hormuz_04"]


def test_at_risk_tanker_ids_unions_multiple_corridors():
    result = at_risk_tanker_ids({"hormuz", "malacca"})
    assert result == [
        "hormuz_01", "hormuz_02", "hormuz_03", "hormuz_04",
        "malacca_01", "malacca_02", "malacca_03", "malacca_04",
    ]


def test_at_risk_tanker_ids_empty_set_returns_nothing():
    assert at_risk_tanker_ids(set()) == []


def test_at_risk_tanker_ids_unrecognized_corridor_matches_nothing_no_raise():
    """No geometry to fail loud on (unlike affected_by()) -- an unrecognized
    corridor id simply matches zero tankers."""

    assert at_risk_tanker_ids({"not_a_real_corridor"}) == []


# --------------------------------------------------------------------------- #
# build_geo -- the Geo block cascade.py actually stamps onto RiskState
# --------------------------------------------------------------------------- #


def test_build_geo_hormuz_matches_worked_example():
    """SPEC.md Phase 6 §3.3's worked example: hormuz's four tankers at risk,
    all three refineries affected (mirrors SPEC.md Phase 5 §3's own
    affected_by({"hormuz"}) result). Since SPEC.md Phase 7, three of those
    four tankers are also the curated dark-ship case."""

    geo = build_geo(_seeded_session(), {"hormuz"})
    assert isinstance(geo, Geo)
    assert geo.at_risk_tanker_ids == ["hormuz_01", "hormuz_02", "hormuz_03", "hormuz_04"]
    assert geo.affected_refinery_ids == ["jamnagar", "paradip", "vadinar"]
    assert geo.dark_tanker_ids == ["hormuz_02", "hormuz_03", "hormuz_04"]


def test_build_geo_matches_graph_affected_by():
    from backend.agents.graph import affected_by, build_graph

    session = _seeded_session()
    geo = build_geo(session, {"suez_cape"})
    expected = sorted(affected_by(build_graph(session), {"suez_cape"}).refineries)
    assert geo.affected_refinery_ids == expected
    assert "paradip" not in geo.affected_refinery_ids


def test_build_geo_empty_elevated_set():
    geo = build_geo(_seeded_session(), set())
    assert geo.at_risk_tanker_ids == []
    assert geo.affected_refinery_ids == []
    assert geo.dark_tanker_ids == []


def test_build_geo_handles_unknown_corridor_without_raising():
    """affected_by() fails loud on an unrecognized corridor id (SPEC.md Phase
    5 decision #7); build_geo() must catch that rather than propagate it,
    since an unrecognized corridor can legitimately reach here from a
    POST /signal body the API deliberately never rejects (decision #8)."""

    geo = build_geo(_seeded_session(), {"not_a_real_corridor"})
    assert isinstance(geo, Geo)
    assert geo.affected_refinery_ids == []
    # at_risk still works normally -- no geometry to fail on for tankers
    assert geo.at_risk_tanker_ids == []
    assert geo.dark_tanker_ids == []


# --------------------------------------------------------------------------- #
# build_geo's dark_tanker_ids -- real values since SPEC.md Phase 7 (F18)
# --------------------------------------------------------------------------- #


def test_build_geo_dark_tanker_ids_filtered_by_elevated_corridors():
    """The curated dark-ship case lives entirely in Hormuz (SPEC.md Phase 7
    §3) -- a Hormuz-elevated cascade carries it, a clean corridor's does
    not, mirroring at_risk_tanker_ids' own elevated-corridor filtering."""

    assert build_geo(_seeded_session(), {"hormuz"}).dark_tanker_ids == [
        "hormuz_02", "hormuz_03", "hormuz_04",
    ]
    assert build_geo(_seeded_session(), {"suez_cape", "atlantic"}).dark_tanker_ids == []
    assert build_geo(_seeded_session(), {"malacca"}).dark_tanker_ids == []
    assert build_geo(_seeded_session(), set()).dark_tanker_ids == []
