"""ORM models — the six tables from PRD Section 7.

Column-type discipline (README locked decision #2): every numeric field is
``Float``/``Numeric``, never ``Integer``, so a contract value like ``68.5`` or
``9.5`` is never silently truncated. ``rank`` lives inside the JSON
``ranked_options`` blob (a serialized ``Reroute``), so it keeps its int-ness
there. Timestamps are ``DateTime(timezone=True)`` — the tz-aware UTC the
contract's ``updated_at`` requires (README consistency rule).

Config tables (corridors/suppliers/refineries) are seeded from JSON; state and
log tables are written by the agents and the API. JSON columns store
``model.model_dump(mode="json")`` output, never hand-built dicts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy import JSON as SA_JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


def utcnow() -> datetime:
    """Timezone-aware UTC now (contract requires tz-aware ``updated_at``)."""

    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Config tables (seeded from backend/seed/*.json) — "new corridor = one row".
# --------------------------------------------------------------------------- #


class Corridor(Base):
    __tablename__ = "corridors"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    chokepoint: Mapped[str] = mapped_column(String, nullable=False)
    base_volume_pct: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="normal")
    # v1.3 (SPEC.md Phase 1): F17 route-cost inputs + F11 map polyline path.
    war_risk_pct: Mapped[float] = mapped_column(Float, nullable=False)
    detour_days: Mapped[float] = mapped_column(Float, nullable=False)
    geojson_path: Mapped[str] = mapped_column(String, nullable=False)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    country: Mapped[str] = mapped_column(String, nullable=False)
    crude_grade: Mapped[str] = mapped_column(String, nullable=False)
    base_price: Mapped[float] = mapped_column(Float, nullable=False)
    lead_days: Mapped[float] = mapped_column(Float, nullable=False)
    corridor_id: Mapped[str] = mapped_column(
        ForeignKey("corridors.id"), nullable=False
    )


class Refinery(Base):
    __tablename__ = "refineries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    capacity_bpd: Mapped[float] = mapped_column(Float, nullable=False)
    # list[str] of grades this refinery can process — stored as a JSON array so
    # it is portable across SQLite and Postgres.
    compatible_grades: Mapped[list] = mapped_column(SA_JSON, nullable=False)
    buffer_days: Mapped[float] = mapped_column(Float, nullable=False)
    # v1.3 (SPEC.md Phase 1): F11 map coordinates.
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)


# --------------------------------------------------------------------------- #
# State + log tables (written by agents / API).
# --------------------------------------------------------------------------- #


class RiskStateRow(Base):
    """Per-corridor Watch reading (PRD §7 ``risk_state``). One row per corridor
    per update; the API assembles the live ``RiskState`` object from these plus
    the latest recommendation. Kept append-friendly for the audit/replay story.
    """

    __tablename__ = "risk_state"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    corridor_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String, nullable=False)
    band: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # provenance signal ids — JSON array of strings.
    source_ids: Mapped[list] = mapped_column(SA_JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Recommendation(Base):
    """A snapshot of Predict+Recommend output (PRD §7 ``recommendations``).

    ``ranked_options`` and ``assumptions`` hold serialized contract models
    (``[Reroute...]`` and ``Assumptions``), not hand-built dicts.
    """

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scenario: Mapped[str] = mapped_column(String, nullable=False)
    ranked_options: Mapped[list] = mapped_column(SA_JSON, nullable=False, default=list)
    assumptions: Mapped[dict | None] = mapped_column(SA_JSON, nullable=True)
    impact: Mapped[dict | None] = mapped_column(SA_JSON, nullable=True)
    reserve: Mapped[dict | None] = mapped_column(SA_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AuditLog(Base):
    """Append-only log of every recommendation and approval (PRD §7, F9).

    ``payload`` is a serialized model dump — replayable end to end.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(SA_JSON, nullable=False, default=dict)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
