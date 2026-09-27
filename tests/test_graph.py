"""Knowledge graph agent: build_graph()/affected_by()/to_dict() (F10,
SPEC.md Segment 1, Phase 5). All cases run against today's real seed data --
no synthetic scenario needed (see SPEC.md Phase 5 §3's worked examples)."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agents.graph import AffectedAssets, affected_by, build_graph, to_dict
from backend.db import Base
from backend.models import Corridor, Refinery, Supplier
from backend.seed import seed_all


def _seeded_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    seed_all(session)
    return session


# --------------------------------------------------------------------------- #
# build_graph
# --------------------------------------------------------------------------- #


def test_build_graph_node_and_edge_counts():
    session = _seeded_session()
    n_corridors = session.query(Corridor).count()
    n_suppliers = session.query(Supplier).count()
    n_refineries = session.query(Refinery).count()

    g = build_graph(session)
    assert g.number_of_nodes() == n_corridors + n_suppliers + n_refineries

    for s in session.query(Supplier).all():
        ships_via = [
            (u, v) for u, v, d in g.out_edges(s.id, data=True)
            if d.get("relation") == "ships_via"
        ]
        assert len(ships_via) == 1
        assert ships_via[0][1] == s.corridor_id


def test_build_graph_rebuilds_cleanly():
    session = _seeded_session()
    g1 = build_graph(session)
    g2 = build_graph(session)
    assert g1.number_of_nodes() == g2.number_of_nodes()
    assert g1.number_of_edges() == g2.number_of_edges()


# --------------------------------------------------------------------------- #
# affected_by -- worked examples from SPEC.md Phase 5 §3
# --------------------------------------------------------------------------- #


def test_affected_by_hormuz_reaches_all_three_refineries():
    g = build_graph(_seeded_session())
    result = affected_by(g, {"hormuz"})
    assert result.suppliers == {"iq_basrah", "sa_arablight", "ae_murban"}
    assert result.refineries == {"jamnagar", "vadinar", "paradip"}


def test_affected_by_suez_cape_excludes_paradip():
    """The headline discriminating case: suez_cape's suppliers (Urals, Bonny
    Light) aren't in paradip's compatible_grades, so paradip must not show up
    as affected -- proving the query doesn't just trivially return
    "everything" every time."""

    g = build_graph(_seeded_session())
    result = affected_by(g, {"suez_cape"})
    assert result.suppliers == {"ru_urals", "ng_bonny"}
    assert result.refineries == {"jamnagar", "vadinar"}
    assert "paradip" not in result.refineries


def test_affected_by_atlantic_only_paradip():
    g = build_graph(_seeded_session())
    result = affected_by(g, {"atlantic"})
    assert result.suppliers == {"us_wti", "br_tupi"}
    assert result.refineries == {"paradip"}


def test_affected_by_known_corridor_with_no_suppliers_returns_empty():
    """malacca is a real, seeded corridor -- just one with zero suppliers
    routed through it today. That must return an empty result, not an
    error (contrast with the unknown-id case below)."""

    g = build_graph(_seeded_session())
    result = affected_by(g, {"malacca"})
    assert result == AffectedAssets(suppliers=set(), refineries=set())


def test_affected_by_unknown_corridor_raises():
    g = build_graph(_seeded_session())
    with pytest.raises(ValueError, match="not_a_real_corridor"):
        affected_by(g, {"not_a_real_corridor"})


def test_affected_by_unions_multiple_corridors():
    g = build_graph(_seeded_session())
    result = affected_by(g, {"suez_cape", "atlantic"})
    assert result.suppliers == {"ru_urals", "ng_bonny", "us_wti", "br_tupi"}
    assert result.refineries == {"jamnagar", "vadinar", "paradip"}


# --------------------------------------------------------------------------- #
# to_dict
# --------------------------------------------------------------------------- #


def test_to_dict_is_json_serializable():
    g = build_graph(_seeded_session())
    payload = to_dict(g)
    dumped = json.dumps(payload)
    reloaded = json.loads(dumped)

    node_ids = {n["id"] for n in reloaded["nodes"]}
    assert "hormuz" in node_ids
    assert "jamnagar" in node_ids

    edge = next(e for e in reloaded["edges"] if e["relation"] == "ships_via")
    assert set(edge) >= {"source", "target", "relation"}
