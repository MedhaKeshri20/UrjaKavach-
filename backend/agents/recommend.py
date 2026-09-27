"""Recommend agent (Dev A) — rank alternative supplier+route options.

Transparent and defensible by construction (PRD §9 "trust hook"): every option
carries its component scores (price / speed / compat) next to the total, so the
UI can show *why* an option ranked where it did — never a bare number. The
component breakdown is exposed through :class:`ScoredOption`; the contract
``Reroute`` written into shared state stays clean (``extra="forbid"``), so the
provenance lives beside the row, not smuggled into it.

Scoring is min-max normalised across the *eligible* candidate set, so lower
true cost and fewer days score higher. A cost/speed toggle is just a
reweighting — same inputs, same math, different emphasis — which is exactly
the live toggle the demo flips.

**v1.3 (SPEC.md Segment 1, Phase 2 — F16/F17):** candidates fan out per
``(supplier x refinery)``; a crude grade the target refinery can't process is
a hard eligibility gate (``rank_eligible=False``, a named ``reason``, never
silently dropped), not a soft downweight. Ranking is on ``true_cost`` (crude +
war-risk insurance + detour), not crude price alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.models import Corridor, Refinery, Supplier
from backend.schemas import CostBreakdown, Reroute

# War-risk insurance + detour surcharge, USD/bbl per day of detour (F17).
# In the range widely reported for Red-Sea-crisis Cape-of-Good-Hope reroute
# freight-cost impact (~$1-3/bbl) — an estimate, same honesty tier as the
# seeded war_risk_pct/detour_days it's multiplied against (see SPEC.md
# Phase 2 decision #2).
DAILY_SHIP_COST: float = 1.20


@dataclass(frozen=True)
class Weights:
    price: float
    speed: float
    compat: float

    def normalised(self) -> "Weights":
        total = self.price + self.speed + self.compat
        if total <= 0:
            return Weights(1 / 3, 1 / 3, 1 / 3)
        return Weights(self.price / total, self.speed / total, self.compat / total)


# Cost/speed toggle presets. "balanced" is the default landing view.
WEIGHT_PRESETS: dict[str, Weights] = {
    "balanced": Weights(price=0.4, speed=0.4, compat=0.2),
    "cost": Weights(price=0.65, speed=0.15, compat=0.2),
    "speed": Weights(price=0.15, speed=0.65, compat=0.2),
}


@dataclass
class Candidate:
    """A raw procurement option before scoring: one (supplier, refinery) pair."""

    supplier: str
    route: str
    days: float
    cost: float
    compatible: bool  # system-wide soft flag (v1.0, unchanged): *any* refinery takes this grade?
    refinery_id: str
    grade_ok: bool  # F16 hard gate: does *this* refinery take this grade?
    war_risk_pct: float  # from Corridor, for true_cost
    detour_days: float  # from Corridor, for true_cost
    crude_grade: str  # only used to build `reason` when grade_ok is False
    refinery_name: str  # ditto


@dataclass
class ScoredOption:
    """A ranked option: the contract row plus its component-score breakdown."""

    reroute: Reroute
    price_score: float
    speed_score: float
    compat_score: float
    total: float

    def to_dict(self) -> dict:
        """API/audit view: the contract row + why it ranked there."""

        out = self.reroute.model_dump(mode="json")
        out["scores"] = {
            "price": round(self.price_score, 4),
            "speed": round(self.speed_score, 4),
            "compat": round(self.compat_score, 4),
            "total": round(self.total, 4),
        }
        return out


def _norm(value: float, lo: float, hi: float) -> float:
    """Min-max to 0..1 where *lower raw is better*. Degenerate range -> 1.0."""

    if hi <= lo:
        return 1.0
    return 1.0 - (value - lo) / (hi - lo)


def _true_cost(cost: float, war_risk_pct: float, detour_days: float) -> tuple[float, CostBreakdown]:
    """Crude + war-risk insurance + detour (F17), rounded to 2dp — USD-cents
    precision a procurement officer would actually read."""

    insurance = cost * war_risk_pct
    detour = detour_days * DAILY_SHIP_COST
    total = cost + insurance + detour
    return round(total, 2), CostBreakdown(
        crude=round(cost, 2),
        war_risk_insurance=round(insurance, 2),
        detour=round(detour, 2),
    )


def score_options(
    candidates: list[Candidate], weights: Weights
) -> list[ScoredOption]:
    """Score and rank candidates. Pure function — no DB, fully unit-testable.

    A candidate whose grade isn't compatible with its target refinery
    (``grade_ok=False``) is hard-gated: it still gets a row (with a
    ``reason``), but scores 0 and always ranks after every eligible option.
    Eligible options are ranked on ``true_cost`` (crude + war-risk insurance +
    detour), min-max normalised across the *eligible* set only, so a stray
    ineligible option's accidental cheapness never compresses the scale for
    the options that actually get ranked. Returns options sorted best-first
    with 1-based ``rank`` assigned in order.
    """

    if not candidates:
        return []

    weights = weights.normalised()

    priced = [(c, *_true_cost(c.cost, c.war_risk_pct, c.detour_days)) for c in candidates]
    eligible = [(c, tc, cb) for c, tc, cb in priced if c.grade_ok] or priced

    true_costs = [tc for _, tc, _ in eligible]
    days = [c.days for c, _, _ in eligible]
    min_cost, max_cost = min(true_costs), max(true_costs)
    min_days, max_days = min(days), max(days)

    scored: list[ScoredOption] = []
    for c, true_cost, breakdown in priced:
        price = _norm(true_cost, min_cost, max_cost)
        speed = _norm(c.days, min_days, max_days)
        compat = 1.0 if c.compatible else 0.3

        if c.grade_ok:
            total = weights.price * price + weights.speed * speed + weights.compat * compat
            reason = None
        else:
            total = 0.0
            reason = f"{c.crude_grade} not compatible with {c.refinery_name}"

        scored.append(
            ScoredOption(
                reroute=Reroute(
                    supplier=c.supplier,
                    route=c.route,
                    days=c.days,
                    cost=c.cost,  # UNCHANGED semantics: crude price only
                    compatible=c.compatible,
                    rank=1,  # placeholder; set after sort
                    refinery_id=c.refinery_id,
                    grade_ok=c.grade_ok,
                    rank_eligible=c.grade_ok,
                    reason=reason,
                    cost_breakdown=breakdown,
                    true_cost=true_cost,
                ),
                price_score=price,
                speed_score=speed,
                compat_score=compat,
                total=total,
            )
        )

    # Eligible options always rank first; within each group, best total first,
    # ties broken by cheaper true cost then faster.
    scored.sort(
        key=lambda s: (
            not s.reroute.rank_eligible,
            -s.total,
            s.reroute.true_cost,
            s.reroute.days,
        )
    )
    for i, opt in enumerate(scored, start=1):
        opt.reroute.rank = i
    return scored


def _all_grades(session: Session) -> set[str]:
    grades: set[str] = set()
    for r in session.query(Refinery).all():
        grades.update(r.compatible_grades or [])
    return grades


def build_candidates(
    session: Session, exclude_corridors: set[str] | None = None
) -> list[Candidate]:
    """Assemble candidates from seed config: one per (supplier x refinery).

    A supplier is *compatible* (system-wide, v1.0 soft flag) if at least one
    refinery can process its crude grade; ``grade_ok`` (F16) is per-row,
    checked against that specific refinery. ``exclude_corridors`` drops
    suppliers routing through a disrupted corridor, which is what turns
    "Hormuz is blocked" into a list of reroutes.
    """

    exclude_corridors = exclude_corridors or set()
    grades = _all_grades(session)
    corridors = {c.id: c for c in session.query(Corridor).all()}
    refineries = session.query(Refinery).all()

    candidates: list[Candidate] = []
    for s in session.query(Supplier).all():
        if s.corridor_id in exclude_corridors:
            continue
        corridor = corridors[s.corridor_id]
        for r in refineries:
            candidates.append(
                Candidate(
                    supplier=s.id,
                    route=s.corridor_id,
                    days=float(s.lead_days),
                    cost=float(s.base_price),
                    compatible=s.crude_grade in grades,
                    refinery_id=r.id,
                    grade_ok=s.crude_grade in (r.compatible_grades or []),
                    war_risk_pct=float(corridor.war_risk_pct),
                    detour_days=float(corridor.detour_days),
                    crude_grade=s.crude_grade,
                    refinery_name=r.name,
                )
            )
    return candidates


def recommend(
    session: Session,
    sort: str = "balanced",
    exclude_corridors: set[str] | None = None,
) -> list[ScoredOption]:
    """DB-backed entrypoint: build candidates, score with the chosen preset."""

    weights = WEIGHT_PRESETS.get(sort, WEIGHT_PRESETS["balanced"])
    candidates = build_candidates(session, exclude_corridors)
    return score_options(candidates, weights)
