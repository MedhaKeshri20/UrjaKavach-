"""Predict agent — the sourced, slider-adjustable v1.3 domino model (F3/F15/F20).

    ┌─────────────────────────────────────────────────────────────────┐
    │  Predict is no longer a stub. Watch (backend/agents/stubs.py)   │
    │  is the only remaining one.                                     │
    └─────────────────────────────────────────────────────────────────┘

Every input is a named, typed AssumptionEntry (fact | estimate | internal), so
the arithmetic below is exactly what a slider drag recomputes — no hidden
coefficients. Pure function: no DB, no mutation, fully unit-testable (mirrors
backend/agents/recommend.py's architecture note).

v1.3 (SPEC.md Phase 3): replaces the v1.0 stub's hardcoded `0.066` gdp-drag
coefficient with the sourced, slider-adjustable `gdp_oil_sensitivity`, and
computes `power_stress_pct` for real instead of a `0.0` placeholder.
"""

from __future__ import annotations

from backend.schemas import Assumptions, AssumptionEntry, Impact, PredictAgentOutput

# Percentage bounds the formulas can't guarantee on their own once a slider
# (or a raw API call) pushes an input past its documented `range` metadata —
# `AssumptionEntry.range` is descriptive only, never enforced (SPEC.md Phase 1
# decision #6). Clamping here, not in the schema, matches the contract's
# existing philosophy (module docstring, backend/schemas/contract.py).
_PRICE_RISE_BOUNDS = (0.0, 100.0)
_GDP_DELTA_BOUNDS = (-50.0, 0.0)
_POWER_STRESS_BOUNDS = (0.0, 100.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def assumptions_from_severity(
    severity: float, buffer_days: float = 9.0, price_elasticity: float = 3.0
) -> Assumptions:
    """Default Predict inputs derived from severity (each is a live slider).

    Relocated from stubs.py unchanged (SPEC.md Phase 1's mechanical patch
    already gave every key its typed/sourced shape) — Predict just isn't a
    stub anymore, so its input-defaulting function lives with it.
    """

    supply_lost = round(_clamp(severity * 100, 0.0, 100.0), 1)
    return Assumptions(
        supply_lost_pct=AssumptionEntry(
            value=supply_lost, type="fact", range=(35.0, 45.0),
            src="brief: Hormuz transit share",
        ),
        buffer_days=AssumptionEntry(
            value=float(buffer_days), type="fact", range=(6.0, 9.5),
            src="ISPRL SPR capacity vs. typical fill level",
        ),
        price_elasticity=AssumptionEntry(
            value=float(price_elasticity), type="estimate", range=(3.0, 10.0),
            src="inverse of published short-run oil demand elasticity",
        ),
        power_oil_dependence=AssumptionEntry(
            value=0.015, type="fact", range=(0.01, 0.02),
            src="oil-fired generation share is negligible in India's grid",
        ),
        gdp_oil_sensitivity=AssumptionEntry(
            value=0.03, type="estimate", range=(0.02, 0.08),
            src="published $10-Brent-rise GDP-drag estimates",
        ),
        power_stress_multiplier=AssumptionEntry(
            value=7.5, type="internal", range=(5.0, 10.0),
            src="no external reference — internal calibration constant",
        ),
    )


def run_predict(assumptions: Assumptions) -> PredictAgentOutput:
    """Glass-box domino model (PRD §10A, corrected v1.3 coefficients).

    gap          = supply_lost_pct
    price_rise   = (gap / 10) * price_elasticity
    gdp_delta    = -(price_rise * gdp_oil_sensitivity)   # was hardcoded 0.066
    power_stress = gap * power_oil_dependence * power_stress_multiplier
    run_rate     = 100 - gap * 0.75

    Replaces run_predict_stub: same signature, same shape out
    (PredictAgentOutput is unchanged), real power_stress_pct, and the
    sourced gdp_oil_sensitivity coefficient instead of the v1.0 magic number.
    """

    gap = _clamp(assumptions.supply_lost_pct.value, 0.0, 100.0)
    price_rise = _clamp(
        (gap / 10.0) * assumptions.price_elasticity.value, *_PRICE_RISE_BOUNDS
    )
    gdp_delta = _clamp(
        -(price_rise * assumptions.gdp_oil_sensitivity.value), *_GDP_DELTA_BOUNDS
    )
    power_stress = _clamp(
        gap
        * assumptions.power_oil_dependence.value
        * assumptions.power_stress_multiplier.value,
        *_POWER_STRESS_BOUNDS,
    )
    run_rate = _clamp(100.0 - gap * 0.75, 0.0, 100.0)

    impact = Impact(
        supply_gap_pct=round(gap, 1),
        price_rise_pct=round(price_rise, 2),
        gdp_delta_pct=round(gdp_delta, 3),
        refinery_runrate_pct=round(run_rate, 1),
        power_stress_pct=round(power_stress, 3),
    )
    return PredictAgentOutput(impact=impact, assumptions=assumptions)
