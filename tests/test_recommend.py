"""Recommend agent: scoring math, rank integrity, cost/speed re-ranking, the
wrong-oil hard gate, and true-cost ranking (SPEC.md Segment 1, Phase 2)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agents.recommend import (
    Candidate,
    DAILY_SHIP_COST,
    WEIGHT_PRESETS,
    Weights,
    build_candidates,
    score_options,
)
from backend.db import Base
from backend.models import Refinery, Supplier
from backend.schemas import Reroute
from backend.seed import seed_all


def _candidates():
    return [
        Candidate(
            "cheap_slow", "r1", days=30, cost=70.0, compatible=True, refinery_id="jamnagar",
            grade_ok=True, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="Urals", refinery_name="Jamnagar (RIL)",
        ),
        Candidate(
            "dear_fast", "r2", days=8, cost=90.0, compatible=True, refinery_id="vadinar",
            grade_ok=True, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="Urals", refinery_name="Vadinar (Nayara)",
        ),
        Candidate(
            "mid", "r3", days=18, cost=80.0, compatible=True, refinery_id="paradip",
            grade_ok=True, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="Arab Light", refinery_name="Paradip (IOCL)",
        ),
        Candidate(
            "incompatible", "r4", days=12, cost=75.0, compatible=False, refinery_id="jamnagar",
            grade_ok=False, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="Heavy Sour", refinery_name="Jamnagar (RIL)",
        ),
    ]


def test_ranks_are_dense_and_one_based():
    scored = score_options(_candidates(), WEIGHT_PRESETS["balanced"])
    ranks = [o.reroute.rank for o in scored]
    assert ranks == [1, 2, 3, 4]
    # every emitted row is a valid contract Reroute
    for o in scored:
        assert isinstance(o.reroute, Reroute)


def test_empty_candidates_returns_empty():
    assert score_options([], WEIGHT_PRESETS["balanced"]) == []


def test_cost_preset_prefers_cheapest():
    scored = score_options(_candidates(), WEIGHT_PRESETS["cost"])
    assert scored[0].reroute.supplier == "cheap_slow"


def test_speed_preset_prefers_fastest():
    scored = score_options(_candidates(), WEIGHT_PRESETS["speed"])
    assert scored[0].reroute.supplier == "dear_fast"


def test_component_scores_exposed_in_dict():
    scored = score_options(_candidates(), WEIGHT_PRESETS["balanced"])
    d = scored[0].to_dict()
    assert set(d["scores"]) == {"price", "speed", "compat", "total"}
    # never a bare number: the breakdown rides alongside the row
    assert "supplier" in d and "rank" in d


def test_weights_normalise():
    w = Weights(2, 2, 0).normalised()
    assert abs(w.price + w.speed + w.compat - 1.0) < 1e-9


def test_single_candidate_degenerate_range():
    scored = score_options(
        [
            Candidate(
                "solo", "r", days=10, cost=80.0, compatible=True, refinery_id="jamnagar",
                grade_ok=True, war_risk_pct=0.0, detour_days=0.0,
                crude_grade="Urals", refinery_name="Jamnagar (RIL)",
            )
        ],
        WEIGHT_PRESETS["balanced"],
    )
    assert len(scored) == 1
    assert scored[0].reroute.rank == 1
    # degenerate min==max normalises to best (1.0), not a divide-by-zero
    assert scored[0].price_score == 1.0
    assert scored[0].speed_score == 1.0


# --------------------------------------------------------------------------- #
# v1.3 (SPEC.md Segment 1, Phase 2): the real wrong-oil hard gate (F16) and
# true-cost ranking (F17), replacing Phase 1's mechanical placeholders.
# --------------------------------------------------------------------------- #


def test_incompatible_is_hard_gated_but_still_present():
    scored = score_options(_candidates(), WEIGHT_PRESETS["balanced"])
    incompat = next(o for o in scored if o.reroute.supplier == "incompatible")
    assert incompat.reroute.grade_ok is False
    assert incompat.reroute.rank_eligible is False
    assert incompat.reroute.reason == "Heavy Sour not compatible with Jamnagar (RIL)"
    assert incompat.total == 0.0
    # never dropped -- still a ranked row, last among the four
    assert incompat.reroute.rank == 4


def test_ineligible_always_ranks_after_eligible_on_every_preset():
    """An ineligible candidate that's cheapest/fastest on paper must never
    outrank an eligible one, regardless of the sort preset."""

    candidates = [
        Candidate(
            "eligible_pricier", "r1", days=20, cost=90.0, compatible=True, refinery_id="jamnagar",
            grade_ok=True, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="Urals", refinery_name="Jamnagar (RIL)",
        ),
        Candidate(
            "ineligible_cheapest", "r2", days=5, cost=10.0, compatible=False, refinery_id="paradip",
            grade_ok=False, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="Heavy Sour", refinery_name="Paradip (IOCL)",
        ),
    ]
    for preset in WEIGHT_PRESETS.values():
        scored = score_options(candidates, preset)
        assert scored[0].reroute.supplier == "eligible_pricier"
        assert scored[0].reroute.rank_eligible is True
        assert scored[1].reroute.rank_eligible is False


def test_true_cost_can_flip_the_cheapest_crude_out_of_first_place():
    """SPEC.md Phase 2 worked example, with small synthetic numbers: a
    cheap-crude option through a high-war-risk, long-detour corridor loses to
    a pricier-crude option with a direct, low-risk route."""

    candidates = [
        Candidate(
            "cheap_but_risky", "suez_cape", days=20, cost=70.0, compatible=True,
            refinery_id="jamnagar", grade_ok=True, war_risk_pct=0.05, detour_days=10.0,
            crude_grade="Urals", refinery_name="Jamnagar (RIL)",
        ),
        Candidate(
            "pricier_but_direct", "atlantic", days=20, cost=80.0, compatible=True,
            refinery_id="jamnagar", grade_ok=True, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="WTI", refinery_name="Jamnagar (RIL)",
        ),
    ]
    scored = score_options(candidates, WEIGHT_PRESETS["cost"])
    # raw cost says cheap_but_risky wins; true_cost flips it
    assert candidates[0].cost < candidates[1].cost
    assert scored[0].reroute.supplier == "pricier_but_direct"
    assert scored[0].reroute.true_cost < scored[1].reroute.true_cost


def test_cost_breakdown_and_true_cost_are_rounded_and_additive():
    scored = score_options(
        [
            Candidate(
                "x", "suez_cape", days=10, cost=74.1, compatible=True, refinery_id="jamnagar",
                grade_ok=True, war_risk_pct=0.02, detour_days=10.0,
                crude_grade="Urals", refinery_name="Jamnagar (RIL)",
            )
        ],
        WEIGHT_PRESETS["balanced"],
    )
    r = scored[0].reroute
    assert r.cost_breakdown.crude == 74.1
    assert r.cost_breakdown.war_risk_insurance == round(74.1 * 0.02, 2)
    assert r.cost_breakdown.detour == round(10.0 * DAILY_SHIP_COST, 2)
    assert r.true_cost == round(
        r.cost_breakdown.crude + r.cost_breakdown.war_risk_insurance + r.cost_breakdown.detour, 2
    )


def test_normalization_uses_eligible_candidates_only():
    """An extreme ineligible candidate must not compress the price/speed
    scale for the eligible candidates that actually get ranked."""

    baseline = [
        Candidate(
            "a", "r1", days=10, cost=70.0, compatible=True, refinery_id="jamnagar",
            grade_ok=True, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="Urals", refinery_name="Jamnagar (RIL)",
        ),
        Candidate(
            "b", "r2", days=20, cost=90.0, compatible=True, refinery_id="vadinar",
            grade_ok=True, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="Urals", refinery_name="Vadinar (Nayara)",
        ),
    ]
    scored_baseline = score_options(baseline, WEIGHT_PRESETS["balanced"])

    with_extreme = baseline + [
        Candidate(
            "extreme_ineligible", "r3", days=1, cost=1.0, compatible=False, refinery_id="paradip",
            grade_ok=False, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="Heavy Sour", refinery_name="Paradip (IOCL)",
        ),
    ]
    scored_with_extreme = score_options(with_extreme, WEIGHT_PRESETS["balanced"])

    a_base = next(o for o in scored_baseline if o.reroute.supplier == "a")
    a_extreme = next(o for o in scored_with_extreme if o.reroute.supplier == "a")
    assert a_base.price_score == a_extreme.price_score
    assert a_base.speed_score == a_extreme.speed_score


def test_all_ineligible_falls_back_to_normalising_over_everyone():
    """Degenerate case: zero eligible candidates must not crash on an empty
    min/max — falls back to normalising across the full (ineligible) set."""

    candidates = [
        Candidate(
            "only_one", "r1", days=10, cost=70.0, compatible=False, refinery_id="jamnagar",
            grade_ok=False, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="Heavy Sour", refinery_name="Jamnagar (RIL)",
        ),
        Candidate(
            "only_two", "r2", days=20, cost=90.0, compatible=False, refinery_id="vadinar",
            grade_ok=False, war_risk_pct=0.0, detour_days=0.0,
            crude_grade="Heavy Sour", refinery_name="Vadinar (Nayara)",
        ),
    ]
    scored = score_options(candidates, WEIGHT_PRESETS["balanced"])
    assert len(scored) == 2
    assert all(o.total == 0.0 for o in scored)
    assert all(o.reroute.rank_eligible is False for o in scored)
    assert [o.reroute.rank for o in scored] == [1, 2]


# --------------------------------------------------------------------------- #
# build_candidates: DB-backed (supplier x refinery) fan-out.
# --------------------------------------------------------------------------- #


def _seeded_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    seed_all(session)
    return session


def test_build_candidates_fans_out_per_supplier_times_refinery():
    session = _seeded_session()
    n_suppliers = session.query(Supplier).count()
    n_refineries = session.query(Refinery).count()

    candidates = build_candidates(session, exclude_corridors=set())
    assert len(candidates) == n_suppliers * n_refineries


def test_build_candidates_excludes_disrupted_corridor_before_fan_out():
    session = _seeded_session()
    n_refineries = session.query(Refinery).count()
    n_hormuz_suppliers = session.query(Supplier).filter_by(corridor_id="hormuz").count()
    n_total_suppliers = session.query(Supplier).count()

    candidates = build_candidates(session, exclude_corridors={"hormuz"})
    assert len(candidates) == (n_total_suppliers - n_hormuz_suppliers) * n_refineries
    assert all(c.route != "hormuz" for c in candidates)


def test_build_candidates_grade_ok_is_per_refinery_not_per_supplier():
    """Today's seed data: Urals is accepted by jamnagar+vadinar, not paradip
    -- so ru_urals must appear eligible twice and ineligible once."""

    session = _seeded_session()
    candidates = [c for c in build_candidates(session, exclude_corridors={"hormuz"}) if c.supplier == "ru_urals"]
    assert len(candidates) == 3
    by_refinery = {c.refinery_id: c.grade_ok for c in candidates}
    assert by_refinery == {"jamnagar": True, "vadinar": True, "paradip": False}
