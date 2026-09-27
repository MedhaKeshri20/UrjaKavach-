"""Contract conformance tests for the shared risk-state schema.

These tests lock the JSON contract defined in Section 8 of the PRD, widened to
the v1.3 shape by SPEC.md's Phase 1. They verify:

* the canonical example (now v1.3-shaped) validates against the models;
* per-agent output blocks (Watch -> corridor_risk, Predict -> impact/assumptions)
  conform to the schema;
* invalid payloads raise ``ValidationError``;
* required fields are enforced;
* unknown ("invented") fields are rejected;
* nested models validate recursively;
* documented numeric ranges and enums are honoured;
* the new v1.3 models (AssumptionEntry, AssumptionOverride, CostBreakdown,
  Geo, Validation) hold to the same conventions as the v1.0 models.

There is no business logic to exercise yet, so the "public function returning
agent output" requirement is expressed by validating representative agent
outputs through the ``WatchAgentOutput`` / ``PredictAgentOutput`` envelopes plus
a small local producer that stands in for a future agent's return value.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from backend.schemas.contract import (
    AssumptionEntry,
    AssumptionOverride,
    Assumptions,
    CorridorRiskEntry,
    CostBreakdown,
    Geo,
    Impact,
    PredictAgentOutput,
    Reroute,
    Reserve,
    RiskState,
    Validation,
    WatchAgentOutput,
)


# --------------------------------------------------------------------------- #
# Fixtures — the canonical example, now widened to the v1.3 shape.
# --------------------------------------------------------------------------- #


def _assumption_entry(value: float, type_: str, lo: float, hi: float, src: str) -> dict:
    return {"value": value, "type": type_, "range": [lo, hi], "src": src}


def _assumptions_dict() -> dict[str, Any]:
    """A fully-populated, contract-valid typed Assumptions dict (all 6 keys)."""
    return {
        "supply_lost_pct": _assumption_entry(40, "fact", 35, 45, "brief: Hormuz transit share"),
        "buffer_days": _assumption_entry(9, "fact", 6, 9.5, "ISPRL SPR capacity vs. typical fill level"),
        "price_elasticity": _assumption_entry(
            3, "estimate", 3, 10, "inverse of published short-run oil demand elasticity"
        ),
        "power_oil_dependence": _assumption_entry(
            0.015, "fact", 0.01, 0.02, "oil-fired generation share is negligible in India's grid"
        ),
        "gdp_oil_sensitivity": _assumption_entry(
            0.03, "estimate", 0.02, 0.08, "published $10-Brent-rise GDP-drag estimates"
        ),
        "power_stress_multiplier": _assumption_entry(
            7.5, "internal", 5, 10, "no external reference — internal calibration constant"
        ),
    }


def _reroute_dict(**overrides: Any) -> dict[str, Any]:
    """A contract-valid Reroute dict; override individual fields per test."""
    base = {
        "supplier": "ru_urals",
        "route": "suez_cape",
        "days": 22,
        "cost": 74.1,
        "compatible": True,
        "rank": 1,
        "refinery_id": "jamnagar",
        "grade_ok": True,
        "rank_eligible": True,
        "reason": None,
        "cost_breakdown": {"crude": 74.1, "war_risk_insurance": 0.0, "detour": 0.0},
        "true_cost": 74.1,
    }
    base.update(overrides)
    return base


def _section8_example() -> dict[str, Any]:
    """Return a fresh copy of the shared risk-state example, v1.3-shaped."""
    return {
        "scenario": "hormuz_partial_closure",
        "severity": 0.4,
        "corridor_risk": {
            "hormuz": {
                "score": 68,
                "confidence": "medium",
                "band": 10,
                "source_ids": ["news_412", "ais_88", "sanc_3"],
            }
        },
        "impact": {
            "supply_gap_pct": 40,
            "price_rise_pct": 12,
            "gdp_delta_pct": -0.8,
            "refinery_runrate_pct": 70,
            "power_stress_pct": 0.6,
        },
        "assumptions": _assumptions_dict(),
        "reroutes": [_reroute_dict()],
        "reserve": {
            "days_cover": 9.5,
            "drawdown_per_day": 0.4,
            "survives_until_refill": True,
        },
        "assumption_overrides": [],
        "geo": None,
        "validation": None,
        "updated_at": "2026-01-15T09:22:00Z",
    }


@pytest.fixture
def example() -> dict[str, Any]:
    return _section8_example()


# --------------------------------------------------------------------------- #
# Stand-in "agent" producers — represent a future agent's public return value.
# The contract requirement: whatever an agent returns must validate.
# --------------------------------------------------------------------------- #


def produce_watch_output() -> WatchAgentOutput:
    """Simulate the Watch agent's public return value."""
    return WatchAgentOutput.model_validate(
        {"corridor_risk": _section8_example()["corridor_risk"]}
    )


def produce_predict_output() -> PredictAgentOutput:
    """Simulate the Predict agent's public return value."""
    src = _section8_example()
    return PredictAgentOutput.model_validate(
        {"impact": src["impact"], "assumptions": src["assumptions"]}
    )


# --------------------------------------------------------------------------- #
# Happy path.
# --------------------------------------------------------------------------- #


def test_full_state_validates(example: dict[str, Any]) -> None:
    state = RiskState.model_validate(example)
    assert state.scenario == "hormuz_partial_closure"
    assert state.severity == 0.4
    assert state.corridor_risk["hormuz"].score == 68
    assert state.reroutes[0].rank == 1
    assert state.reserve.survives_until_refill is True
    assert isinstance(state.updated_at, datetime)
    # v1.3 additions on a fully-populated state
    assert state.impact.power_stress_pct == 0.6
    assert state.assumptions.power_stress_multiplier.value == 7.5
    assert state.reroutes[0].true_cost == state.reroutes[0].cost
    assert state.assumption_overrides == []
    assert state.geo is None
    assert state.validation is None


def test_updated_at_parses_to_aware_datetime(example: dict[str, Any]) -> None:
    state = RiskState.model_validate(example)
    assert state.updated_at == datetime(2026, 1, 15, 9, 22, 0, tzinfo=timezone.utc)


def test_roundtrip_is_stable(example: dict[str, Any]) -> None:
    """A validated state re-validates identically (contract is idempotent)."""
    first = RiskState.model_validate(example)
    second = RiskState.model_validate(first.model_dump())
    assert first == second


def test_watch_agent_output_conforms() -> None:
    out = produce_watch_output()
    assert isinstance(out, WatchAgentOutput)
    assert out.corridor_risk["hormuz"].confidence == "medium"


def test_predict_agent_output_conforms() -> None:
    out = produce_predict_output()
    assert isinstance(out, PredictAgentOutput)
    assert out.impact.gdp_delta_pct == -0.8
    assert out.assumptions.price_elasticity.value == 3
    assert out.assumptions.price_elasticity.type == "estimate"


# --------------------------------------------------------------------------- #
# Required-field enforcement.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "missing",
    ["scenario", "severity", "corridor_risk", "updated_at"],
)
def test_missing_required_top_level_field_raises(
    example: dict[str, Any], missing: str
) -> None:
    payload = copy.deepcopy(example)
    del payload[missing]
    with pytest.raises(ValidationError):
        RiskState.model_validate(payload)


@pytest.mark.parametrize(
    "optional",
    ["impact", "assumptions", "reroutes", "reserve", "assumption_overrides", "geo", "validation"],
)
def test_missing_optional_block_is_allowed(
    example: dict[str, Any], optional: str
) -> None:
    """Agent-written blocks may be absent mid-cascade and default cleanly."""
    payload = copy.deepcopy(example)
    del payload[optional]
    state = RiskState.model_validate(payload)
    # Empty list for the two list-shaped blocks, None for every object block.
    if optional in ("reroutes", "assumption_overrides"):
        assert getattr(state, optional) == []
    else:
        assert getattr(state, optional) is None


def test_watch_only_partial_state_validates() -> None:
    """Gate-2 case: Watch has written corridor_risk, Predict has not run yet."""
    partial = {
        "scenario": "hormuz_partial_closure",
        "severity": 0.4,
        "corridor_risk": {
            "hormuz": {
                "score": 68,
                "confidence": "medium",
                "band": 10,
                "source_ids": ["news_412"],
            }
        },
        "updated_at": "2026-01-15T09:22:00Z",
    }
    state = RiskState.model_validate(partial)
    assert state.impact is None
    assert state.assumptions is None
    assert state.reserve is None
    assert state.reroutes == []
    assert state.assumption_overrides == []
    assert state.geo is None
    assert state.validation is None


@pytest.mark.parametrize("missing", ["score", "confidence", "band", "source_ids"])
def test_corridor_entry_missing_field_raises(missing: str) -> None:
    entry = {
        "score": 68,
        "confidence": "medium",
        "band": 10,
        "source_ids": ["news_412"],
    }
    del entry[missing]
    with pytest.raises(ValidationError):
        CorridorRiskEntry.model_validate(entry)


@pytest.mark.parametrize(
    "missing",
    ["supply_gap_pct", "price_rise_pct", "gdp_delta_pct", "refinery_runrate_pct", "power_stress_pct"],
)
def test_impact_missing_field_raises(missing: str) -> None:
    impact = {
        "supply_gap_pct": 40,
        "price_rise_pct": 12,
        "gdp_delta_pct": -0.8,
        "refinery_runrate_pct": 70,
        "power_stress_pct": 0.6,
    }
    del impact[missing]
    with pytest.raises(ValidationError):
        Impact.model_validate(impact)


@pytest.mark.parametrize(
    "missing",
    [
        "supply_lost_pct",
        "buffer_days",
        "price_elasticity",
        "power_oil_dependence",
        "gdp_oil_sensitivity",
        "power_stress_multiplier",
    ],
)
def test_assumptions_missing_field_raises(missing: str) -> None:
    assumptions = _assumptions_dict()
    del assumptions[missing]
    with pytest.raises(ValidationError):
        Assumptions.model_validate(assumptions)


@pytest.mark.parametrize(
    "missing", ["supplier", "route", "days", "cost", "compatible", "rank",
                "refinery_id", "grade_ok", "rank_eligible", "cost_breakdown", "true_cost"],
)
def test_reroute_missing_field_raises(missing: str) -> None:
    reroute = _reroute_dict()
    del reroute[missing]
    with pytest.raises(ValidationError):
        Reroute.model_validate(reroute)


def test_reroute_reason_defaults_to_none() -> None:
    reroute = _reroute_dict()
    del reroute["reason"]
    r = Reroute.model_validate(reroute)
    assert r.reason is None


# --------------------------------------------------------------------------- #
# Closed contract — no invented fields.
# --------------------------------------------------------------------------- #


def test_extra_top_level_field_forbidden(example: dict[str, Any]) -> None:
    payload = copy.deepcopy(example)
    payload["totally_new_field"] = 123
    with pytest.raises(ValidationError):
        RiskState.model_validate(payload)


def test_extra_nested_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        CorridorRiskEntry.model_validate(
            {
                "score": 68,
                "confidence": "medium",
                "band": 10,
                "source_ids": ["news_412"],
                "reason": "one sentence",  # present in Section 10, NOT in Section 8
            }
        )


def test_extra_field_forbidden_on_reroute() -> None:
    reroute = _reroute_dict(bogus_field="nope")
    with pytest.raises(ValidationError):
        Reroute.model_validate(reroute)


# --------------------------------------------------------------------------- #
# Type / enum / range validation.
# --------------------------------------------------------------------------- #


def test_bad_confidence_enum_raises() -> None:
    with pytest.raises(ValidationError):
        CorridorRiskEntry.model_validate(
            {
                "score": 68,
                "confidence": "med",  # Section 10 spelling — rejected by contract
                "band": 10,
                "source_ids": ["news_412"],
            }
        )


def test_wrong_type_for_score_raises() -> None:
    with pytest.raises(ValidationError):
        CorridorRiskEntry.model_validate(
            {
                "score": "high",
                "confidence": "medium",
                "band": 10,
                "source_ids": ["news_412"],
            }
        )


@pytest.mark.parametrize("bad_score", [-1, 101, 150])
def test_score_out_of_range_raises(bad_score: int) -> None:
    with pytest.raises(ValidationError):
        CorridorRiskEntry.model_validate(
            {
                "score": bad_score,
                "confidence": "medium",
                "band": 10,
                "source_ids": ["news_412"],
            }
        )


@pytest.mark.parametrize("bad_severity", [-0.1, 1.1, 2.0])
def test_severity_out_of_range_raises(
    example: dict[str, Any], bad_severity: float
) -> None:
    payload = copy.deepcopy(example)
    payload["severity"] = bad_severity
    with pytest.raises(ValidationError):
        RiskState.model_validate(payload)


def test_source_ids_must_be_list_of_str() -> None:
    with pytest.raises(ValidationError):
        CorridorRiskEntry.model_validate(
            {
                "score": 68,
                "confidence": "medium",
                "band": 10,
                "source_ids": "news_412",  # a bare string, not a list
            }
        )


def test_reroute_rank_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Reroute.model_validate(_reroute_dict(rank=0))  # 1-based


def test_numerics_accept_fractional_values() -> None:
    """All numerics except rank are float, so mid-cascade fractionals don't throw."""
    entry = CorridorRiskEntry.model_validate(
        {
            "score": 68.5,
            "confidence": "medium",
            "band": 10.5,
            "source_ids": ["news_412"],
        }
    )
    assert entry.score == 68.5
    assert entry.band == 10.5

    reroute = Reroute.model_validate(_reroute_dict(days=22.5))
    assert reroute.days == 22.5


def test_rank_rejects_non_integer() -> None:
    """rank is the only genuinely-ordinal field; fractional rank is invalid."""
    with pytest.raises(ValidationError):
        Reroute.model_validate(_reroute_dict(rank=1.5))


def test_reserve_valid() -> None:
    reserve = Reserve.model_validate(
        {"days_cover": 9.5, "drawdown_per_day": 0.4, "survives_until_refill": True}
    )
    assert reserve.days_cover == 9.5


# --------------------------------------------------------------------------- #
# AssumptionEntry / typed Assumptions (F20) — new in v1.3.
# --------------------------------------------------------------------------- #


def test_assumption_entry_valid() -> None:
    entry = AssumptionEntry.model_validate(
        _assumption_entry(40, "fact", 35, 45, "brief: Hormuz transit share")
    )
    assert entry.value == 40
    assert entry.type == "fact"
    assert entry.range == (35.0, 45.0)


def test_assumption_entry_range_is_metadata_not_validated() -> None:
    """Decision #6: range is descriptive only — an out-of-range value is legal."""
    entry = AssumptionEntry.model_validate(
        _assumption_entry(999, "estimate", 3, 10, "deliberately out of range")
    )
    assert entry.value == 999  # not clamped or rejected by the schema itself


@pytest.mark.parametrize("bad_type", ["med", "guess", "FACT", ""])
def test_assumption_entry_rejects_bad_type_enum(bad_type: str) -> None:
    with pytest.raises(ValidationError):
        AssumptionEntry.model_validate(_assumption_entry(40, bad_type, 35, 45, "src"))


@pytest.mark.parametrize("missing", ["value", "type", "range", "src"])
def test_assumption_entry_missing_field_raises(missing: str) -> None:
    entry = _assumption_entry(40, "fact", 35, 45, "src")
    del entry[missing]
    with pytest.raises(ValidationError):
        AssumptionEntry.model_validate(entry)


def test_assumption_entry_extra_field_forbidden() -> None:
    entry = _assumption_entry(40, "fact", 35, 45, "src")
    entry["bogus"] = 1
    with pytest.raises(ValidationError):
        AssumptionEntry.model_validate(entry)


def test_assumption_entry_range_must_have_exactly_two_elements() -> None:
    entry = _assumption_entry(40, "fact", 35, 45, "src")
    entry["range"] = [1, 2, 3]
    with pytest.raises(ValidationError):
        AssumptionEntry.model_validate(entry)


# --------------------------------------------------------------------------- #
# AssumptionOverride (F9/F20) — new in v1.3.
# --------------------------------------------------------------------------- #


def _override_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        "who": "officer@gov.in",
        "field": "price_elasticity",
        "from_default": 3.0,
        "to_value": 5.0,
        "ts": "2026-01-15T09:22:00Z",
    }
    base.update(overrides)
    return base


def test_assumption_override_valid() -> None:
    override = AssumptionOverride.model_validate(_override_dict())
    assert override.who == "officer@gov.in"
    assert override.from_default == 3.0
    assert override.to_value == 5.0
    assert isinstance(override.ts, datetime)


@pytest.mark.parametrize("missing", ["who", "field", "from_default", "to_value", "ts"])
def test_assumption_override_missing_field_raises(missing: str) -> None:
    override = _override_dict()
    del override[missing]
    with pytest.raises(ValidationError):
        AssumptionOverride.model_validate(override)


def test_assumption_override_extra_field_forbidden() -> None:
    override = _override_dict(bogus=1)
    with pytest.raises(ValidationError):
        AssumptionOverride.model_validate(override)


def test_risk_state_carries_assumption_overrides(example: dict[str, Any]) -> None:
    payload = copy.deepcopy(example)
    payload["assumption_overrides"] = [_override_dict()]
    state = RiskState.model_validate(payload)
    assert len(state.assumption_overrides) == 1
    assert state.assumption_overrides[0].field == "price_elasticity"


# --------------------------------------------------------------------------- #
# CostBreakdown (F17) — new in v1.3.
# --------------------------------------------------------------------------- #


def test_cost_breakdown_valid() -> None:
    cb = CostBreakdown.model_validate(
        {"crude": 71.0, "war_risk_insurance": 2.4, "detour": 0.7}
    )
    assert cb.crude == 71.0


@pytest.mark.parametrize("field", ["crude", "war_risk_insurance", "detour"])
def test_cost_breakdown_rejects_negative(field: str) -> None:
    payload = {"crude": 71.0, "war_risk_insurance": 2.4, "detour": 0.7}
    payload[field] = -1.0
    with pytest.raises(ValidationError):
        CostBreakdown.model_validate(payload)


def test_cost_breakdown_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        CostBreakdown.model_validate(
            {"crude": 71.0, "war_risk_insurance": 2.4, "detour": 0.7, "bogus": 1}
        )


# --------------------------------------------------------------------------- #
# Geo (F11/F13/F18) and Validation (F14) — new in v1.3, optional RiskState blocks.
# --------------------------------------------------------------------------- #


def test_geo_valid_and_can_be_empty() -> None:
    geo = Geo.model_validate(
        {"at_risk_tanker_ids": [], "dark_tanker_ids": [], "affected_refinery_ids": []}
    )
    assert geo.at_risk_tanker_ids == []


@pytest.mark.parametrize(
    "missing", ["at_risk_tanker_ids", "dark_tanker_ids", "affected_refinery_ids"]
)
def test_geo_missing_field_raises(missing: str) -> None:
    geo = {"at_risk_tanker_ids": [], "dark_tanker_ids": [], "affected_refinery_ids": []}
    del geo[missing]
    with pytest.raises(ValidationError):
        Geo.model_validate(geo)


def test_geo_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        Geo.model_validate(
            {
                "at_risk_tanker_ids": [],
                "dark_tanker_ids": [],
                "affected_refinery_ids": [],
                "bogus": 1,
            }
        )


def test_risk_state_geo_present_and_populated(example: dict[str, Any]) -> None:
    payload = copy.deepcopy(example)
    payload["geo"] = {
        "at_risk_tanker_ids": ["ais_88", "ais_91"],
        "dark_tanker_ids": ["ais_77"],
        "affected_refinery_ids": ["in_jamnagar"],
    }
    state = RiskState.model_validate(payload)
    assert state.geo.dark_tanker_ids == ["ais_77"]


def test_validation_valid() -> None:
    v = Validation.model_validate({"backtest_id": "2025_iran_spike", "signal_lead_hours": 34})
    assert v.signal_lead_hours == 34


@pytest.mark.parametrize("missing", ["backtest_id", "signal_lead_hours"])
def test_validation_missing_field_raises(missing: str) -> None:
    payload = {"backtest_id": "2025_iran_spike", "signal_lead_hours": 34}
    del payload[missing]
    with pytest.raises(ValidationError):
        Validation.model_validate(payload)


def test_validation_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        Validation.model_validate(
            {"backtest_id": "2025_iran_spike", "signal_lead_hours": 34, "bogus": 1}
        )


def test_risk_state_validation_present_and_populated(example: dict[str, Any]) -> None:
    payload = copy.deepcopy(example)
    payload["validation"] = {"backtest_id": "2025_iran_spike", "signal_lead_hours": 34}
    state = RiskState.model_validate(payload)
    assert state.validation.signal_lead_hours == 34


# --------------------------------------------------------------------------- #
# Nested / recursive validation.
# --------------------------------------------------------------------------- #


def test_nested_corridor_entry_error_propagates(example: dict[str, Any]) -> None:
    payload = copy.deepcopy(example)
    payload["corridor_risk"]["hormuz"]["confidence"] = "not_a_level"
    with pytest.raises(ValidationError):
        RiskState.model_validate(payload)


def test_nested_reroute_error_propagates(example: dict[str, Any]) -> None:
    payload = copy.deepcopy(example)
    payload["reroutes"][0]["days"] = -5
    with pytest.raises(ValidationError):
        RiskState.model_validate(payload)


def test_nested_assumption_entry_error_propagates(example: dict[str, Any]) -> None:
    payload = copy.deepcopy(example)
    payload["assumptions"]["price_elasticity"]["type"] = "not_a_tier"
    with pytest.raises(ValidationError):
        RiskState.model_validate(payload)


def test_nested_cost_breakdown_error_propagates(example: dict[str, Any]) -> None:
    payload = copy.deepcopy(example)
    payload["reroutes"][0]["cost_breakdown"]["war_risk_insurance"] = -1
    with pytest.raises(ValidationError):
        RiskState.model_validate(payload)


def test_multiple_corridors_supported(example: dict[str, Any]) -> None:
    """corridor_risk is an open mapping keyed by corridor id."""
    payload = copy.deepcopy(example)
    payload["corridor_risk"]["suez_cape"] = {
        "score": 30,
        "confidence": "low",
        "band": 5,
        "source_ids": ["news_9"],
    }
    state = RiskState.model_validate(payload)
    assert set(state.corridor_risk) == {"hormuz", "suez_cape"}
