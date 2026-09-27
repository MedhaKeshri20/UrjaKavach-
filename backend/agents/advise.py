"""Advise agent (Dev A) — Strategic Petroleum Reserve drawdown support.

Glass-box, like Predict: every number is arithmetic over named inputs, no hidden
constants. The question it answers is "if we cover the supply gap out of the
reserve, does the reserve last until the replacement barrels arrive?"

Inputs
------
buffer_days      Days of full-consumption cover in the reserve (seed/assumption).
supply_gap_pct   Percent of daily supply lost (from Predict's Impact).
refill_days      Lead time of the chosen reroute — when replacement crude lands.

Model
-----
drawdown_per_day = supply_gap_pct / 100      # fraction of a day's cover used/day
days_cover       = buffer_days / drawdown_per_day   (∞-safe: 0 gap -> no draw)
survives         = days_cover >= refill_days
"""

from __future__ import annotations

from backend.schemas import Reserve


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def simulate_reserve(
    buffer_days: float,
    supply_gap_pct: float,
    refill_days: float,
) -> Reserve:
    """Run the depletion simulation and return a contract ``Reserve`` block.

    Percentages are clamped here (README decision #6) so a transient >100% gap
    never crashes the cascade on stage.
    """

    buffer_days = max(0.0, float(buffer_days))
    refill_days = max(0.0, float(refill_days))
    gap = _clamp(float(supply_gap_pct), 0.0, 100.0)

    drawdown_per_day = gap / 100.0
    if drawdown_per_day <= 0.0:
        # No gap => reserve is not being drawn; it "lasts" indefinitely.
        days_cover = buffer_days
        survives = True
    else:
        days_cover = buffer_days / drawdown_per_day
        survives = days_cover >= refill_days

    return Reserve(
        days_cover=round(days_cover, 2),
        drawdown_per_day=round(drawdown_per_day, 4),
        survives_until_refill=survives,
    )
