"""Shared risk-state store — Dev A's merge/assemble/serve responsibility.

One process-wide :class:`RiskState` is the single object both portals render.
Each agent hands Dev A a *validated block* (an envelope) and the store merges it
into the running state, then:

  1. re-validates the whole ``RiskState`` (the drift alarm — an illegal merge
     fails loudly right here, exactly as the contract's ``extra="forbid"`` and
     README intend),
  2. stamps a fresh tz-aware UTC ``updated_at``,
  3. persists the durable rows (risk_state / recommendations),
  4. publishes a *full snapshot* on ``state.updated`` — never a diff, so the
     frontend's one-shape ``useRiskState()`` contract holds (README decision #4).

The merged object stays valid even while later blocks are still ``None`` — a
mid-cascade snapshot (Watch done, Predict pending) is a legal ``RiskState``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from backend.bus import TOPIC_STATE_UPDATED, InMemoryBus
from backend.models import Recommendation, RiskStateRow, utcnow
from backend.schemas import (
    AssumptionOverride,
    Geo,
    PredictAgentOutput,
    Reroute,
    Reserve,
    RiskState,
    WatchAgentOutput,
)

SessionFactory = Callable[[], "contextmanager[Session]"]


def derive_severity(corridor_risk: dict) -> float:
    """Severity (0..1) = worst corridor score / 100. Empty -> 0."""

    if not corridor_risk:
        return 0.0
    worst = max(entry.score for entry in corridor_risk.values())
    return max(0.0, min(1.0, worst / 100.0))


def _initial_state() -> RiskState:
    """A valid, quiet steady-state to serve before any signal arrives."""

    return RiskState(
        scenario="steady_state",
        updated_at=utcnow(),
        corridor_risk={},
        severity=0.0,
    )


class StateStore:
    def __init__(
        self,
        bus: InMemoryBus | None = None,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self._bus = bus or InMemoryBus()
        # None => skip DB persistence (used by pure-logic tests).
        self._session_factory = session_factory
        self._state = _initial_state()
        self._lock = asyncio.Lock()
        # v1.3 (SPEC.md Phase 3, F20/F9): assumption-slider overrides still
        # diverging from default, not yet stamped onto RiskState. Transient,
        # in-memory only — the durable record is audit_log (backend/api/routes.py).
        self._pending_overrides: dict[str, AssumptionOverride] = {}

    # -- reads ------------------------------------------------------------- #

    def get(self) -> RiskState:
        return self._state

    def snapshot(self) -> dict:
        """JSON-ready full snapshot (datetime -> ISO string)."""

        return self._state.model_dump(mode="json")

    # -- session helper ---------------------------------------------------- #

    @contextmanager
    def _session(self) -> Iterator[Session | None]:
        if self._session_factory is None:
            yield None
            return
        with self._session_factory() as session:  # type: ignore[union-attr]
            yield session

    # -- merges ------------------------------------------------------------ #

    async def set_scenario(self, scenario: str) -> RiskState:
        # A new scenario starts clean — a prior what-if session's unapproved
        # overrides must not bleed into an unrelated signal (SPEC.md Phase 3).
        self.reset_pending_overrides()
        return await self._commit(self._state.model_copy(update={"scenario": scenario}))

    async def merge_watch(self, out: WatchAgentOutput) -> RiskState:
        corridor_risk = {**self._state.corridor_risk, **out.corridor_risk}
        severity = derive_severity(corridor_risk)
        with self._session() as session:
            if session is not None:
                for cid, entry in out.corridor_risk.items():
                    session.add(
                        RiskStateRow(
                            corridor_id=cid,
                            score=entry.score,
                            confidence=entry.confidence,
                            band=entry.band,
                            source_ids=list(entry.source_ids),
                        )
                    )
        return await self._commit(
            self._state.model_copy(
                update={"corridor_risk": corridor_risk, "severity": severity}
            )
        )

    async def merge_predict(self, out: PredictAgentOutput) -> RiskState:
        return await self._commit(
            self._state.model_copy(
                update={"impact": out.impact, "assumptions": out.assumptions}
            )
        )

    async def merge_reroutes(self, reroutes: list[Reroute]) -> RiskState:
        new = self._state.model_copy(update={"reroutes": list(reroutes)})
        with self._session() as session:
            if session is not None:
                session.add(
                    Recommendation(
                        scenario=new.scenario,
                        ranked_options=[r.model_dump(mode="json") for r in reroutes],
                        assumptions=(
                            new.assumptions.model_dump(mode="json")
                            if new.assumptions
                            else None
                        ),
                        impact=(
                            new.impact.model_dump(mode="json") if new.impact else None
                        ),
                        reserve=(
                            new.reserve.model_dump(mode="json") if new.reserve else None
                        ),
                    )
                )
        return await self._commit(new)

    async def merge_reserve(self, reserve: Reserve) -> RiskState:
        return await self._commit(self._state.model_copy(update={"reserve": reserve}))

    async def merge_geo(self, geo: Geo) -> RiskState:
        """Stamp the geospatial block onto RiskState (F11/F13, SPEC.md
        Phase 6) — the first cascade step to ever populate `geo` for real."""

        return await self._commit(self._state.model_copy(update={"geo": geo}))

    # -- assumption overrides (F20/F9, SPEC.md Phase 3) --------------------- #

    @property
    def pending_overrides(self) -> list[AssumptionOverride]:
        """Overrides currently diverging from default, not yet stamped onto
        RiskState — cleared by merge_assumption_overrides() or a new scenario."""

        return list(self._pending_overrides.values())

    def upsert_pending_override(self, entry: AssumptionOverride) -> None:
        self._pending_overrides[entry.field] = entry  # latest wins per field

    def clear_pending_override(self, field: str) -> None:
        self._pending_overrides.pop(field, None)

    def reset_pending_overrides(self) -> None:
        self._pending_overrides.clear()

    async def merge_assumption_overrides(self) -> RiskState:
        """Snapshot pending overrides onto RiskState — Approve-time only.

        Exploratory override commits (POST /assumptions/override) only ever
        write to audit_log; this is the sole path that touches the live,
        WS-broadcast RiskState.assumption_overrides field, so it always
        reflects exactly what's tied to the most recent approval (including
        resetting to `[]` when nothing is pending).
        """

        new_state = await self._commit(
            self._state.model_copy(
                update={"assumption_overrides": self.pending_overrides}
            )
        )
        self.reset_pending_overrides()
        return new_state

    # -- internals --------------------------------------------------------- #

    async def _commit(self, new_state: RiskState) -> RiskState:
        # Re-validate the whole object from a dump: this is the drift alarm.
        data = new_state.model_dump()
        data["updated_at"] = utcnow()
        validated = RiskState.model_validate(data)
        self._state = validated
        await self._bus.publish(TOPIC_STATE_UPDATED, self.snapshot())
        return validated
