"""REST + WebSocket endpoints (PRD Section 8).

Every response that represents shared state is a validated contract model, so
the mock and the real API are provably the same shape — the drift alarm the
README asks Dev A to run. Request bodies are validated at the boundary too:
``/simulate`` carries a strict :class:`Assumptions` (all six typed fields required).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.agents.backtest import BacktestCaseNotFound, run_backtest
from backend.agents.conservation import generate_conservation_copy
from backend.agents.geo import list_tankers
from backend.agents.predict import assumptions_from_severity, run_predict
from backend.agents.rag import load_corpus
from backend.agents.recommend import recommend
from backend.cascade import affected_corridors, run_cascade
from backend.auth.models import User
from backend.config import REPO_ROOT
from backend.db import get_session
from backend.middleware.auth import get_current_user, require_role
from backend.models import AuditLog, Corridor, Refinery
from backend.schemas import Assumptions, AssumptionOverride, Impact, RiskState

# Float-compare tolerance when deciding whether a submitted assumption value
# diverges from its severity-derived default (SPEC.md Phase 3).
_OVERRIDE_EPSILON = 1e-9

log = logging.getLogger("urja.api")
router = APIRouter()


# --------------------------------------------------------------------------- #
# Request / response models (API surface — not part of the frozen contract).
# --------------------------------------------------------------------------- #


class SignalRequest(BaseModel):
    """The demo 'headline drop' that triggers the cascade."""

    model_config = ConfigDict(extra="forbid")

    corridor: str = Field(description="Corridor id the signal hits, e.g. 'hormuz'.")
    headline: str = Field(description="Free-text headline scored by Watch.")
    scenario: Optional[str] = Field(default=None, description="Scenario label override.")
    severity: Optional[float] = Field(default=None, ge=0, le=1)
    id: Optional[str] = Field(default=None, description="Signal id for provenance.")
    source_ids: Optional[list[str]] = Field(default=None)


class SimulateRequest(BaseModel):
    """What-if body: a scenario label + a *strict* Assumptions block."""

    model_config = ConfigDict(extra="forbid")

    scenario: str
    assumptions: Assumptions  # all six typed fields required, extra forbidden


class SimulateResponse(BaseModel):
    scenario: str
    impact: Impact
    assumptions: Assumptions


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier: str = Field(description="Supplier id of the reroute being approved.")
    note: Optional[str] = Field(default=None)


class AssumptionOverrideRequest(BaseModel):
    """Body for POST /assumptions/override — a full Assumptions snapshot,
    diffed field-by-field against the severity-derived default (F20/F9)."""

    model_config = ConfigDict(extra="forbid")

    assumptions: Assumptions


# --------------------------------------------------------------------------- #
# Dependencies — pull the app-wide singletons off app.state.
# --------------------------------------------------------------------------- #


def get_store(request: Request):
    return request.app.state.store


def get_session_factory(request: Request):
    return request.app.state.session_factory


def get_manager(request: Request):
    return request.app.state.manager


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/state", response_model=RiskState)
def get_state(store=Depends(get_store)) -> RiskState:
    """Current shared risk-state. Both portals hydrate from this."""

    return store.get()


@router.post("/signal", response_model=RiskState)
async def post_signal(
    body: SignalRequest,
    store=Depends(get_store),
    session_factory=Depends(get_session_factory),
    session: Session = Depends(get_session),
) -> RiskState:
    """Inject a signal and run the full cascade; return the final state."""

    # Soft-validate the corridor against seed config (README rule #5): warn,
    # never reject — an unknown corridor must not break the "new corridor = one
    # config row" story.
    if session.get(Corridor, body.corridor) is None:
        log.warning("signal for unknown corridor id: %s", body.corridor)

    signal = body.model_dump(exclude_none=True)
    return await run_cascade(signal, store, session_factory)


@router.post("/simulate", response_model=SimulateResponse)
def post_simulate(body: SimulateRequest) -> SimulateResponse:
    """Pure what-if: recompute Impact from adjusted assumptions. No mutation."""

    out = run_predict(body.assumptions)
    return SimulateResponse(
        scenario=body.scenario, impact=out.impact, assumptions=out.assumptions
    )


@router.post("/assumptions/override")
def post_assumption_override(
    body: AssumptionOverrideRequest,
    store=Depends(get_store),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Log a slider *commit* that diverges from the severity-derived default.

    Exploratory only (SPEC.md Phase 3 decision #5): writes one audit_log row
    per divergent field and updates the store's pending-override set. Never
    touches RiskState.assumption_overrides or triggers a WS push directly —
    POST /approve is what snapshots the pending set onto shared state.
    """

    defaults = assumptions_from_severity(store.get().severity)
    now = datetime.now(timezone.utc)
    logged: list[str] = []

    for field in Assumptions.model_fields:
        submitted = getattr(body.assumptions, field).value
        default = getattr(defaults, field).value
        if abs(submitted - default) <= _OVERRIDE_EPSILON:
            store.clear_pending_override(field)
            continue

        entry = AssumptionOverride(
            who=user.email,
            field=field,
            from_default=default,
            to_value=submitted,
            ts=now,
        )
        store.upsert_pending_override(entry)
        session.add(
            AuditLog(
                actor=user.email,
                action="override_assumption",
                payload=entry.model_dump(mode="json"),
            )
        )
        logged.append(field)

    if logged:
        session.commit()

    return {
        "ok": True,
        "overrides_logged": logged,
        "pending": [o.model_dump(mode="json") for o in store.pending_overrides],
    }


@router.get("/reroutes")
def get_reroutes(
    sort: str = "balanced",
    store=Depends(get_store),
    session: Session = Depends(get_session),
) -> dict:
    """Ranked procurement options with per-option score breakdown.

    ``sort`` is the cost/speed toggle: ``balanced`` | ``cost`` | ``speed``.
    """

    if sort not in {"balanced", "cost", "speed"}:
        raise HTTPException(status_code=400, detail="sort must be balanced|cost|speed")
    excluded = affected_corridors(store.get())
    scored = recommend(session, sort=sort, exclude_corridors=excluded)
    return {
        "sort": sort,
        "excluded_corridors": sorted(excluded),
        "options": [opt.to_dict() for opt in scored],
    }


def _load_geojson_geometry(geojson_path: str) -> Optional[dict]:
    """Parse a corridor's committed GeoJSON file into its raw `geometry`
    (India Connect Portal/spec.md Phase 7) -- `geojson_path` on the `Corridor`
    row is a repo-relative path string, not a URL, so the frontend can't fetch
    it directly; embedding the parsed geometry here keeps `/geo/state` the
    single one-stop read instead of standing up a separate static-file mount.
    Missing/malformed files degrade to `None` (map falls back to no polyline
    for that corridor) rather than 500ing the whole endpoint.
    """

    try:
        raw = json.loads((REPO_ROOT / geojson_path).read_text(encoding="utf-8"))
        return raw["features"][0]["geometry"]
    except (OSError, KeyError, IndexError, json.JSONDecodeError):
        log.warning("geo/state: could not load geometry from %s", geojson_path)
        return None


@router.get("/geo/state")
def get_geo_state(
    store=Depends(get_store),
    session: Session = Depends(get_session),
) -> dict:
    """The geospatial layer's one-stop read (F11/F13, SPEC.md Phase 6):
    current Geo block (None until a signal's been injected — same pattern as
    impact/reserve), corridor/refinery config (map data with no other HTTP
    consumer today), and the curated AIS tanker-track replay set.
    """

    state = store.get()
    corridors = session.query(Corridor).all()
    refineries = session.query(Refinery).all()
    return {
        "geo": state.geo.model_dump(mode="json") if state.geo else None,
        "corridors": [
            {
                "id": c.id,
                "name": c.name,
                "chokepoint": c.chokepoint,
                "war_risk_pct": c.war_risk_pct,
                "detour_days": c.detour_days,
                "geojson_path": c.geojson_path,
                "geometry": _load_geojson_geometry(c.geojson_path),
            }
            for c in corridors
        ],
        "refineries": [
            {
                "id": r.id,
                "name": r.name,
                "capacity_bpd": r.capacity_bpd,
                "lat": r.lat,
                "lon": r.lon,
            }
            for r in refineries
        ],
        "tankers": list_tankers(),
    }


@router.get("/provenance")
def get_provenance(ids: str) -> dict:
    """Resolve Watch's `corridor_risk[id].source_ids` to real, citable
    snippets (F2/F12) -- the popover lookup PLAN.md's Phase 4 section
    explicitly deferred to "Segment 2, Chunk D" without pinning a shape.
    ``ids`` is a comma-separated list (matching this file's plain
    query-param style elsewhere, e.g. ``sort``); only ids present in the
    committed RAG corpus resolve -- the offline stub's source_ids (the
    injected signal's own id, e.g. 'sig_unknown') are not real corpus
    entries and legitimately come back as `missing`, never fabricated.
    """

    requested = [i for i in ids.split(",") if i]
    corpus = {row["id"]: row for row in load_corpus()}
    items = []
    missing = []
    for source_id in requested:
        row = corpus.get(source_id)
        if row is None:
            missing.append(source_id)
            continue
        items.append(
            {
                "id": row["id"],
                "headline": row["text"],
                "source": row["source"],
                "timestamp": row["date"],
            }
        )
    return {"items": items, "missing": missing}


@router.get("/backtest/{backtest_id}")
def get_backtest(backtest_id: str) -> dict:
    """One curated historical case (F14, SPEC.md Phase 8): Watch's real score
    timeline vs. an illustrative Brent price timeline, and the lead time
    between them. Never touches RiskState (decision #5) -- a side-effect-free
    read, unlike every cascade-adjacent endpoint elsewhere in this file.
    Framed explicitly as one illustrative case, never a validated accuracy
    metric (PRD's honesty guard) -- see the response's own "note" field.
    """

    try:
        result = run_backtest(backtest_id)
    except BacktestCaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "validation": result.validation.model_dump(mode="json"),
        "corridor": result.corridor,
        "label": result.label,
        "watch_alert_threshold": result.watch_alert_threshold,
        "watch_crossed_at": result.watch_crossed_at,
        "brent_spike_threshold_usd": result.brent_spike_threshold_usd,
        "brent_crossed_at": result.brent_crossed_at,
        "score_timeline": [asdict(p) for p in result.score_timeline],
        "price_timeline": [asdict(p) for p in result.price_timeline],
        "note": (
            "Illustrative single historical case; Brent series is "
            "hand-curated/approximate, not audited market data. Not a "
            "validated statistical accuracy claim."
        ),
    }


@router.post("/approve")
async def post_approve(
    body: ApproveRequest,
    store=Depends(get_store),
    session: Session = Depends(get_session),
    user: User = Depends(require_role("official")),
) -> dict:
    """Official approves a reroute -> append an immutable audit_log row.

    Official-only: the actor is taken from the authenticated user's token, so
    the audit trail records who really approved (not a client-supplied name).
    """

    match = next(
        (r for r in store.get().reroutes if r.supplier == body.supplier), None
    )
    if match is None:
        raise HTTPException(
            status_code=404, detail=f"no ranked reroute for supplier '{body.supplier}'"
        )

    payload = match.model_dump(mode="json")
    if body.note:
        payload["note"] = body.note
    pending = store.pending_overrides
    payload["assumption_overrides"] = [o.model_dump(mode="json") for o in pending]

    entry = AuditLog(actor=user.email, action="approve_reroute", payload=payload)
    session.add(entry)
    session.commit()
    session.refresh(entry)

    # Snapshot whatever's pending (possibly none) onto shared state — always,
    # so a later approve with nothing new pending resets it to `[]` rather
    # than leaving a prior approval's overrides stale (SPEC.md Phase 3 #7).
    await store.merge_assumption_overrides()

    return {
        "ok": True,
        "audit_id": entry.id,
        "actor": entry.actor,
        "action": entry.action,
        "payload": entry.payload,
        "ts": entry.ts.isoformat(),
    }


@router.get("/audit")
def get_audit(
    limit: int = 50,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("official")),
) -> list[dict]:
    """Official-only: the replayable audit log, most recent first (F9)."""

    limit = max(1, min(limit, 200))
    rows = (
        session.query(AuditLog).order_by(AuditLog.ts.desc()).limit(limit).all()
    )
    return [
        {
            "id": r.id,
            "actor": r.actor,
            "action": r.action,
            "payload": r.payload,
            "ts": r.ts.isoformat(),
        }
        for r in rows
    ]


# -- Public (citizen) portal: filtered, read-only, no raw numbers ----------- #

# SPEC.md Phase 9: message/conservation_plan content moved to
# backend/agents/conservation.py's _LEVELS_FALLBACK (now LLM-generated when
# available); this table keeps only the severity->status-name thresholds.
_LEVELS = [
    (0.34, "Normal"),
    (0.67, "Elevated"),
    (1.01, "Shortage"),
]


def _level_for(severity: float) -> str:
    for ceiling, name in _LEVELS:
        if severity < ceiling:
            return name
    return _LEVELS[-1][1]


@router.get("/public/status")
def public_status(
    store=Depends(get_store),
    session: Session = Depends(get_session),
) -> dict:
    """Simplified citizen view: status band, plain guidance, action feed.

    ``message``/``conservation_plan`` are LLM-generated, scenario-specific
    copy (SPEC.md Phase 9, F7 slice) when USE_REAL_AGENTS+GROQ_API_KEY are
    set, falling back to static copy otherwise -- ``status`` itself stays a
    rule-based threshold on severity, never LLM-decided.
    """

    state = store.get()
    level = _level_for(state.severity)

    worst_corridor_id = (
        max(state.corridor_risk, key=lambda cid: state.corridor_risk[cid].score)
        if state.corridor_risk
        else None
    )
    corridor_name = None
    if worst_corridor_id:
        corridor = session.query(Corridor).filter_by(id=worst_corridor_id).first()
        corridor_name = corridor.name if corridor else worst_corridor_id

    copy = generate_conservation_copy(level, corridor_name)

    recent = (
        session.query(AuditLog)
        .order_by(AuditLog.ts.desc())
        .limit(5)
        .all()
    )
    action_feed = [
        {
            "action": a.action,
            "supplier": a.payload.get("supplier"),
            "route": a.payload.get("route"),
            "ts": a.ts.isoformat(),
        }
        for a in recent
    ]

    return {
        "status": level,
        "message": copy["message"],
        "conservation_plan": copy["conservation_plan"],
        "action_feed": action_feed,
        "updated_at": state.updated_at.isoformat(),
    }


# -- WebSocket: push full snapshots on every state change ------------------- #


@router.websocket("/ws/state")
async def ws_state(websocket: WebSocket) -> None:
    manager = websocket.app.state.manager
    store = websocket.app.state.store
    await manager.connect(websocket)
    try:
        # Hydrate immediately with the current full snapshot.
        await websocket.send_json(store.snapshot())
        while True:
            # We don't expect client messages; this keeps the socket open and
            # detects disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:  # pragma: no cover - defensive
        manager.disconnect(websocket)
