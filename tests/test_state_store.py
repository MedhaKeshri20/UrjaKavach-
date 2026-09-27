"""StateStore: merge order, partial-state validity, UTC stamping, publish."""

import asyncio
from datetime import datetime, timezone

from backend.bus import TOPIC_STATE_UPDATED, InMemoryBus
from backend.schemas import (
    Assumptions,
    AssumptionEntry,
    AssumptionOverride,
    CorridorRiskEntry,
    CostBreakdown,
    Geo,
    Impact,
    PredictAgentOutput,
    Reserve,
    Reroute,
    RiskState,
    WatchAgentOutput,
)
from backend.state_store import StateStore, derive_severity


def _watch(score=68.0):
    return WatchAgentOutput(
        corridor_risk={
            "hormuz": CorridorRiskEntry(
                score=score, confidence="medium", band=10, source_ids=["news_1"]
            )
        }
    )


def _entry(value, type_="fact", lo=0.0, hi=100.0, src="test fixture"):
    return AssumptionEntry(value=value, type=type_, range=(lo, hi), src=src)


def _predict():
    return PredictAgentOutput(
        impact=Impact(
            supply_gap_pct=40, price_rise_pct=12, gdp_delta_pct=-0.8,
            refinery_runrate_pct=70, power_stress_pct=0.6,
        ),
        assumptions=Assumptions(
            supply_lost_pct=_entry(40),
            buffer_days=_entry(9),
            price_elasticity=_entry(3, "estimate"),
            power_oil_dependence=_entry(0.015),
            gdp_oil_sensitivity=_entry(0.03, "estimate"),
            power_stress_multiplier=_entry(7.5, "internal"),
        ),
    )


def test_initial_state_is_valid_and_quiet():
    store = StateStore(bus=InMemoryBus())
    state = store.get()
    assert isinstance(state, RiskState)
    assert state.impact is None and state.reroutes == [] and state.reserve is None
    assert state.geo is None
    assert state.severity == 0.0


def test_derive_severity_uses_worst_corridor():
    cr = {
        "a": CorridorRiskEntry(score=30, confidence="low", band=5, source_ids=[]),
        "b": CorridorRiskEntry(score=90, confidence="high", band=5, source_ids=[]),
    }
    assert derive_severity(cr) == 0.9
    assert derive_severity({}) == 0.0


def test_merge_sequence_and_partial_validity():
    store = StateStore(bus=InMemoryBus())

    asyncio.run(store.merge_watch(_watch(80)))
    mid = store.get()
    # Watch has run, Predict has not -> a legal mid-cascade snapshot.
    assert mid.corridor_risk["hormuz"].score == 80
    assert mid.severity == 0.8
    assert mid.impact is None

    asyncio.run(store.merge_predict(_predict()))
    assert store.get().impact.supply_gap_pct == 40

    asyncio.run(
        store.merge_reroutes(
            [
                Reroute(
                    supplier="ru_urals", route="suez_cape", days=22, cost=74.1,
                    compatible=True, rank=1, refinery_id="jamnagar", grade_ok=True,
                    rank_eligible=True, reason=None,
                    cost_breakdown=CostBreakdown(crude=74.1, war_risk_insurance=0.0, detour=0.0),
                    true_cost=74.1,
                )
            ]
        )
    )
    assert store.get().reroutes[0].rank == 1

    asyncio.run(
        store.merge_reserve(
            Reserve(days_cover=9.5, drawdown_per_day=0.4, survives_until_refill=True)
        )
    )
    assert store.get().reserve.days_cover == 9.5

    assert store.get().geo is None  # unpopulated until merge_geo runs
    asyncio.run(
        store.merge_geo(
            Geo(
                at_risk_tanker_ids=["hormuz_01"],
                dark_tanker_ids=[],
                affected_refinery_ids=["jamnagar"],
            )
        )
    )
    assert store.get().geo.at_risk_tanker_ids == ["hormuz_01"]


def test_updated_at_is_tz_aware_utc_and_bumps():
    store = StateStore(bus=InMemoryBus())
    before = store.get().updated_at
    asyncio.run(store.merge_watch(_watch()))
    after = store.get().updated_at
    assert after.tzinfo is not None
    assert after.utcoffset() == timezone.utc.utcoffset(None)
    assert after >= before


def test_merge_publishes_full_snapshot():
    bus = InMemoryBus()
    received = []
    bus.subscribe(TOPIC_STATE_UPDATED, lambda payload: received.append(payload))
    store = StateStore(bus=bus)

    asyncio.run(store.merge_watch(_watch()))
    assert received, "a state.updated snapshot should have been published"
    snap = received[-1]
    # full snapshot, JSON-ready, every top-level key present (even if null)
    for key in ("scenario", "severity", "corridor_risk", "impact", "reroutes", "reserve", "updated_at"):
        assert key in snap
    assert isinstance(snap["updated_at"], str)  # datetime serialised to ISO


def test_merge_geo_publishes_full_snapshot():
    """v1.3 (SPEC.md Segment 1, Phase 6): merge_geo is the first thing that
    ever stamps RiskState.geo -- its own publish must carry it through."""

    bus = InMemoryBus()
    received = []
    bus.subscribe(TOPIC_STATE_UPDATED, lambda payload: received.append(payload))
    store = StateStore(bus=bus)

    asyncio.run(
        store.merge_geo(
            Geo(at_risk_tanker_ids=[], dark_tanker_ids=[], affected_refinery_ids=["jamnagar"])
        )
    )
    assert received
    assert received[-1]["geo"]["affected_refinery_ids"] == ["jamnagar"]


# --------------------------------------------------------------------------- #
# v1.3 (SPEC.md Segment 1, Phase 3): pending assumption overrides (F20/F9) --
# stamped onto RiskState only at Approve time, never on the exploratory commit.
# --------------------------------------------------------------------------- #


def _override(field="price_elasticity", from_default=3.0, to_value=6.0, who="officer@gov.in"):
    return AssumptionOverride(
        who=who, field=field, from_default=from_default, to_value=to_value,
        ts=datetime.now(timezone.utc),
    )


def test_pending_overrides_starts_empty():
    store = StateStore(bus=InMemoryBus())
    assert store.pending_overrides == []


def test_upsert_pending_override_is_visible_before_any_merge():
    store = StateStore(bus=InMemoryBus())
    store.upsert_pending_override(_override())
    assert len(store.pending_overrides) == 1
    # not stamped onto RiskState until an explicit merge
    assert store.get().assumption_overrides == []


def test_upsert_pending_override_dedups_by_field_latest_wins():
    store = StateStore(bus=InMemoryBus())
    store.upsert_pending_override(_override(to_value=6.0))
    store.upsert_pending_override(_override(to_value=8.0))
    pending = store.pending_overrides
    assert len(pending) == 1
    assert pending[0].to_value == 8.0


def test_clear_pending_override_removes_a_field():
    store = StateStore(bus=InMemoryBus())
    store.upsert_pending_override(_override(field="price_elasticity"))
    store.upsert_pending_override(_override(field="buffer_days", from_default=9.0, to_value=5.0))
    store.clear_pending_override("price_elasticity")
    fields = {o.field for o in store.pending_overrides}
    assert fields == {"buffer_days"}


def test_clear_pending_override_on_missing_field_is_a_noop():
    store = StateStore(bus=InMemoryBus())
    store.clear_pending_override("no_such_field")
    assert store.pending_overrides == []


def test_merge_assumption_overrides_snapshots_then_clears_pending():
    store = StateStore(bus=InMemoryBus())
    store.upsert_pending_override(_override())

    state = asyncio.run(store.merge_assumption_overrides())
    assert len(state.assumption_overrides) == 1
    assert state.assumption_overrides[0].field == "price_elasticity"
    # pending is cleared once snapshotted
    assert store.pending_overrides == []
    # a second snapshot with nothing pending resets the field to empty
    state2 = asyncio.run(store.merge_assumption_overrides())
    assert state2.assumption_overrides == []


def test_merge_assumption_overrides_publishes_a_snapshot():
    bus = InMemoryBus()
    received = []
    bus.subscribe(TOPIC_STATE_UPDATED, lambda payload: received.append(payload))
    store = StateStore(bus=bus)

    store.upsert_pending_override(_override())
    asyncio.run(store.merge_assumption_overrides())
    assert received
    assert len(received[-1]["assumption_overrides"]) == 1


def test_set_scenario_clears_pending_overrides():
    store = StateStore(bus=InMemoryBus())
    store.upsert_pending_override(_override())
    asyncio.run(store.set_scenario("new_scenario"))
    assert store.pending_overrides == []
