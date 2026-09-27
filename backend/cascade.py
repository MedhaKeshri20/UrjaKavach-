"""Cascade orchestration — the demo money-shot, wired by Dev A.

One injected signal flows Watch -> Predict -> Recommend -> Advise -> Geo, each
stage merging its validated block into the shared :class:`StateStore` (which
publishes a full snapshot after every merge, so the portals animate the whole
sweep live).

Watch (v1.3 Phase 4, RAG+LLM with an internal stub fallback), Predict (v1.3
Phase 3), Recommend, and Advise are all real agents now — Watch's real path
degrades to its own deterministic stub internally (see
backend/agents/watch.py) rather than cascade.py branching on it. Geo (v1.3
Phase 6) is the fifth, final step — the first thing that ever populates
RiskState.geo for real, reusing the same excluded-corridor set step 3 already
computed for Recommend (SPEC.md Phase 6 decision #7).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.agents.advise import simulate_reserve
from backend.agents.geo import build_geo
from backend.agents.predict import assumptions_from_severity, run_predict
from backend.agents.recommend import recommend
from backend.agents.watch import run_watch
from backend.schemas import RiskState
from backend.state_store import StateStore

# A corridor at/above this score is treated as disrupted and excluded from
# reroute candidates (that is what makes them *re*-routes).
AFFECTED_THRESHOLD = 50.0

SessionFactory = Callable[[], "contextmanager[Session]"]


def affected_corridors(state: RiskState, threshold: float = AFFECTED_THRESHOLD) -> set[str]:
    return {
        cid
        for cid, entry in state.corridor_risk.items()
        if entry.score >= threshold
    }


async def run_cascade(
    signal: dict,
    store: StateStore,
    session_factory: SessionFactory,
) -> RiskState:
    """Run the full pipeline for one signal and return the final state."""

    # 0) Label the scenario so the portals show what's unfolding.
    scenario = signal.get("scenario") or f"{signal.get('corridor', 'unknown')}_disruption"
    await store.set_scenario(scenario)

    # 1) Watch: score the affected corridor from the signal. (v1.3 Phase 4:
    # run_watch is the real RAG+LLM agent, falling back to the deterministic
    # stub internally — see backend/agents/watch.py.)
    await store.merge_watch(run_watch(signal))

    # 2) Predict: glass-box impact from severity-derived assumptions.
    assumptions = assumptions_from_severity(store.get().severity)
    predict_out = run_predict(assumptions)
    await store.merge_predict(predict_out)

    # 3) Recommend: rank alternatives, excluding disrupted corridors.
    excluded = affected_corridors(store.get()) or {signal.get("corridor")}
    excluded.discard(None)
    with session_factory() as session:
        scored = recommend(session, sort="balanced", exclude_corridors=excluded)
    reroutes = [opt.reroute for opt in scored]
    await store.merge_reroutes(reroutes)

    # 4) Advise: does the reserve last until the top *eligible* reroute lands?
    # (v1.3 Phase 2: the top row isn't guaranteed eligible in general — only
    # by score_options' own eligible-first sort — so check explicitly.)
    eligible_reroutes = [r for r in reroutes if r.rank_eligible]
    refill_days = eligible_reroutes[0].days if eligible_reroutes else 0.0
    reserve = simulate_reserve(
        buffer_days=assumptions.buffer_days.value,
        supply_gap_pct=predict_out.impact.supply_gap_pct,
        refill_days=refill_days,
    )
    await store.merge_reserve(reserve)

    # 5) Geo: at-risk tankers (static AIS tag) + affected refineries (Phase 5's
    # knowledge graph) for whichever corridors are currently excluded/elevated.
    # First real stamp of RiskState.geo — Phase 5 shipped affected_by() uncalled.
    with session_factory() as session:
        geo = build_geo(session, excluded)
    await store.merge_geo(geo)

    return store.get()
