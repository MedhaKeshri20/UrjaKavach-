"""Frozen JSON contract for the Urja Kavach shared risk-state.

This module is the *single source of truth* for the shape of data exchanged
between agents and portals. It is transcribed directly from Section 8 of the
PRD ("API contract & shared state") and MUST stay free of business logic so
that every agent (Watch, Predict, Recommend, Advise), the API layer, and the
frontends can depend on it without importing anything heavier.

**Contract version: v1.3 shape** (widened from v1.0 by SPEC.md's Phase 1 —
see PLAN.md Segment 1, Phase 1). This phase widens the shape only; several
new fields carry mechanical placeholder values until the phase that gives
them real meaning lands (noted per-field below and in SPEC.md).

Design decisions (all enforced, all documented):

* Pydantic **v2** models only.
* ``extra="forbid"`` on every model — the contract is closed. An unknown field
  is a bug (a typo or an un-announced contract change), so it must fail loudly
  rather than pass silently. This is how "do not invent fields" is enforced at
  runtime.
* All numeric fields are ``float`` except ``rank`` (an ordinal, always integer).
  Floats accept integer inputs cleanly, so this never rejects a valid value and
  it avoids mid-cascade validation errors when a slider or band produces a
  fractional number (e.g. ``buffer_days`` alongside a ``days_cover`` of 9.5).
* Only the two ranges the PRD states unambiguously are enforced in the schema:
  ``severity`` in ``0..1`` and corridor ``score`` in ``0..100``. All other
  percentages are left loose here and clamped *inside the agents* so a transient
  101% never throws mid-cascade. Physically-meaningful non-negativity is kept.
* Blocks are optional per their agent owner. ``scenario``, ``updated_at`` and
  ``corridor_risk`` are always present; ``impact``, ``assumptions``, ``reroutes``
  and ``reserve`` are written later in the Watch->Predict->Recommend->Advise
  cascade, so a mid-flight state (Watch has run, Predict has not) must validate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ``confidence`` is shown as the single value "medium" in Section 8. Section 10
# (not the contract source of truth) shows "low|med|high". We resolve to the
# full-word spelling anchored on Section 8. See ambiguity #1 in the report.
Confidence = Literal["low", "medium", "high"]

# Shared strict config applied to every contract model.
_STRICT = ConfigDict(extra="forbid")


class CorridorRiskEntry(BaseModel):
    """Risk assessment for a single corridor. Emitted by the **Watch** agent.

    This is the *value* type of the ``corridor_risk`` mapping (the key is the
    corridor id, e.g. ``"hormuz"``).
    """

    model_config = _STRICT

    score: float = Field(ge=0, le=100, description="Disruption risk score, 0..100.")
    confidence: Confidence = Field(description="Qualitative confidence label.")
    band: float = Field(ge=0, description="Uncertainty band around the score.")
    source_ids: list[str] = Field(
        description="Provenance: ids of the signals the score was derived from."
    )


class Impact(BaseModel):
    """Modelled economic impact of a scenario. Emitted by the **Predict** agent.

    ``gdp_delta_pct`` is expected to be negative in a disruption, so no lower
    bound is imposed on the impact fields.
    """

    model_config = _STRICT

    supply_gap_pct: float = Field(description="Percentage of supply lost.")
    price_rise_pct: float = Field(description="Percentage rise in fuel price.")
    gdp_delta_pct: float = Field(description="Change in GDP, percent (signed).")
    refinery_runrate_pct: float = Field(description="Refinery run-rate, percent.")
    power_stress_pct: float = Field(
        description=(
            "Power-sector stress, percent (F15). Required for shape consistency "
            "with every other Impact field; the real gap*dependence*multiplier "
            "computation lands in PLAN.md Phase 3 — until then agents emit 0.0."
        )
    )


class AssumptionEntry(BaseModel):
    """A single sourced, typed, slider-adjustable Predict input (F20).

    ``range`` is descriptive metadata only (drives the slider's min/max and
    the fact/estimate/internal honesty story) — it is **not** enforced by
    Pydantic. An official dragging a slider past the documented range mid-demo
    must not hard-crash the cascade; clamping (where needed) stays an agent
    concern, matching the contract's existing philosophy for other loose
    percentages (see module docstring).
    """

    model_config = _STRICT

    value: float = Field(description="The live (possibly overridden) value.")
    type: Literal["fact", "estimate", "internal"] = Field(
        description="Sourcing tier: measured fact, researched estimate, or an "
        "unsourced internal calibration constant."
    )
    range: tuple[float, float] = Field(
        description="Documented [lo, hi] bound — descriptive metadata, not validated."
    )
    src: str = Field(description="Citation or rationale for this value.")


class Assumptions(BaseModel):
    """Named, slider-adjustable inputs to the Predict model.

    Emitted by the **Predict** agent alongside :class:`Impact`. Every value is
    a live assumption exposed as a UI slider. As of the v1.3 shape (F20), each
    is a typed, sourced, ranged :class:`AssumptionEntry` rather than a bare
    float — a breaking change from v1.0, migrated in PLAN.md Phase 1.
    """

    model_config = _STRICT

    supply_lost_pct: AssumptionEntry = Field(description="Assumed supply lost, percent.")
    buffer_days: AssumptionEntry = Field(description="Assumed reserve buffer in days.")
    price_elasticity: AssumptionEntry = Field(description="Assumed price elasticity factor.")
    power_oil_dependence: AssumptionEntry = Field(
        description="Oil-fired share of power generation (F15 input)."
    )
    gdp_oil_sensitivity: AssumptionEntry = Field(
        description="GDP drag per unit price rise (F15 input)."
    )
    power_stress_multiplier: AssumptionEntry = Field(
        description="Internal calibration constant scaling power_stress_pct (F15 input)."
    )


class CostBreakdown(BaseModel):
    """Three-way route cost breakdown (F17): crude + war-risk insurance + detour."""

    model_config = _STRICT

    crude: float = Field(ge=0, description="Crude price component (USD/bbl).")
    war_risk_insurance: float = Field(ge=0, description="War-risk insurance surcharge (USD/bbl).")
    detour: float = Field(ge=0, description="Detour time/fuel surcharge (USD/bbl).")


class Reroute(BaseModel):
    """A single ranked procurement reroute option (Recommend agent output row)."""

    model_config = _STRICT

    supplier: str = Field(description="Supplier id, e.g. 'ru_urals'.")
    route: str = Field(description="Corridor/route id, e.g. 'suez_cape'.")
    days: float = Field(ge=0, description="Lead time in days.")
    cost: float = Field(
        ge=0, description="Crude price only per barrel (USD) — v1.0 semantics preserved."
    )
    compatible: bool = Field(
        description="v1.0 soft-downweight flag. Left unchanged; grade_ok is the F16 hard gate."
    )
    rank: int = Field(ge=1, description="1-based rank among options (ordinal).")
    refinery_id: str = Field(
        description=(
            "Which refinery this route/grade is evaluated against (F16). "
            "PLAN.md Phase 1 resolves this mechanically (first grade-compatible "
            "refinery, else a sentinel); Phase 2 fans candidates out per "
            "supplier x refinery so this becomes fully meaningful."
        )
    )
    grade_ok: bool = Field(
        description=(
            "F16 hard eligibility gate. Mirrors `compatible` until PLAN.md "
            "Phase 2 replaces the placeholder with the real per-refinery gate."
        )
    )
    rank_eligible: bool = Field(
        description="Whether this option may be ranked at all. Always True until Phase 2."
    )
    reason: Optional[str] = Field(
        default=None, description="Why an option is ineligible (F16). Set by Phase 2."
    )
    cost_breakdown: CostBreakdown = Field(
        description="Crude / war-risk insurance / detour breakdown (F17)."
    )
    true_cost: float = Field(
        ge=0,
        description=(
            "The F17 ranking field: crude + insurance + detour. Equals `cost` "
            "while Phase 1's surcharges are zero; Phase 2 makes them real."
        ),
    )


class Reserve(BaseModel):
    """Strategic reserve drawdown state (Advise agent output)."""

    model_config = _STRICT

    days_cover: float = Field(ge=0, description="Days of cover remaining.")
    drawdown_per_day: float = Field(description="Reserve drawn down per day.")
    survives_until_refill: bool = Field(
        description="Whether cover lasts until replenishment."
    )


class AssumptionOverride(BaseModel):
    """One audit-logged instance of an official dragging a slider off default (F20/F9).

    ``who`` is typed as a required identity string in Phase 1; whether it's a
    verified JWT subject or a demo placeholder is a Phase 3 decision (tied to
    whether `/simulate` becomes auth-gated — see PLAN.md's open decision #4).
    """

    model_config = _STRICT

    who: str = Field(description="Actor identity that made the override.")
    field: str = Field(description="Which Assumptions key was overridden, e.g. 'price_elasticity'.")
    from_default: float = Field(description="The value before the override.")
    to_value: float = Field(description="The value after the override.")
    ts: datetime = Field(description="ISO-8601 timestamp of the override.")


class Geo(BaseModel):
    """Geospatial block (F11/F13/F18): tanker + affected-asset ids.

    Stays ``None`` on RiskState until PLAN.md Phase 6 (at_risk/affected) and
    Phase 7 (dark_tanker_ids) populate it. All three fields are required
    *within* the model once it exists — Phase 6/7 must pass `[]` explicitly,
    mirroring CorridorRiskEntry's style rather than defaulting silently.
    """

    model_config = _STRICT

    at_risk_tanker_ids: list[str] = Field(
        description="Tankers inside an elevated-risk corridor's polygon."
    )
    dark_tanker_ids: list[str] = Field(
        description="Tankers flagged by the anomaly detector (F18)."
    )
    affected_refinery_ids: list[str] = Field(
        description="Refineries the knowledge graph resolves as affected (F10)."
    )


class Validation(BaseModel):
    """Backtest/validation block (F14). Stays ``None`` until PLAN.md Phase 8.

    Framed explicitly as one illustrative historical case, never a validated
    production accuracy metric — repeat that framing wherever this surfaces.
    """

    model_config = _STRICT

    backtest_id: str = Field(description="Which curated historical case this is.")
    signal_lead_hours: float = Field(
        description="Hours the Watch score crossed alert threshold before the real price move."
    )


class RiskState(BaseModel):
    """The complete shared risk-state object exchanged across the system.

    This is the top-level payload of ``GET /state`` and the ``state.updated``
    WebSocket event. It composes the per-agent blocks into one document.
    """

    model_config = _STRICT

    # Always present: the system always has a scenario, a timestamp, and a risk
    # reading from the Watch agent.
    scenario: str = Field(description="Scenario id, e.g. 'hormuz_partial_closure'.")
    updated_at: datetime = Field(description="ISO-8601 timestamp of last update.")
    corridor_risk: dict[str, CorridorRiskEntry] = Field(
        description="Per-corridor risk, keyed by corridor id (Watch agent)."
    )

    # severity is derived from the risk reading and always present.
    severity: float = Field(ge=0, le=1, description="Scenario severity, 0..1.")

    # Written later in the cascade by downstream agents; None/empty until then so
    # a mid-flight state (Watch done, Predict pending) still validates.
    impact: Optional[Impact] = Field(
        default=None, description="Modelled economic impact (Predict agent)."
    )
    assumptions: Optional[Assumptions] = Field(
        default=None, description="Adjustable model assumptions (Predict agent)."
    )
    reroutes: list[Reroute] = Field(
        default_factory=list, description="Ranked reroute options (Recommend agent)."
    )
    reserve: Optional[Reserve] = Field(
        default=None, description="Reserve drawdown state (Advise agent)."
    )
    assumption_overrides: list[AssumptionOverride] = Field(
        default_factory=list,
        description="Audit trail of slider drags away from default (F20/F9).",
    )
    geo: Optional[Geo] = Field(
        default=None, description="Geospatial block (F11/F13/F18). None until Phase 6/7."
    )
    validation: Optional[Validation] = Field(
        default=None, description="Backtest/validation block (F14). None until Phase 8."
    )


# --------------------------------------------------------------------------- #
# Per-agent output envelopes
#
# These compose the leaf models above into the exact block each agent is
# responsible for producing (per the task brief). They add no new fields; they
# only bundle existing contract pieces so an agent's public return value can be
# validated in one call.
# --------------------------------------------------------------------------- #


class WatchAgentOutput(BaseModel):
    """Output contract for the Watch agent: the ``corridor_risk`` block only."""

    model_config = _STRICT

    corridor_risk: dict[str, CorridorRiskEntry] = Field(
        description="Per-corridor risk, keyed by corridor id."
    )


class PredictAgentOutput(BaseModel):
    """Output contract for the Predict agent: ``impact`` + ``assumptions``."""

    model_config = _STRICT

    impact: Impact = Field(description="Modelled economic impact.")
    assumptions: Assumptions = Field(description="Adjustable model assumptions.")
