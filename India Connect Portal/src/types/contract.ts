// Hand-mirror of backend/schemas/contract.py — the frozen Urja Kavach
// RiskState contract. No codegen; this is a standing rule (PLAN.md Segment 2,
// Chunk A), not a one-time task. Whenever contract.py changes, update this
// file in the same change.
//
// Field names, optionality, and nesting match the Python source exactly.
// Numeric fields are `number` (Pydantic keeps them as `float` except
// `Reroute.rank`, which stays an ordinal `number` here too — TS has no
// separate int type). Every model in contract.py sets `extra="forbid"`; that
// is a runtime validation concern on the backend and has no direct TS
// equivalent, but it means an object with extra keys here is already wrong.

export type Confidence = "low" | "medium" | "high";

/** Value type of RiskState.corridor_risk, keyed by corridor id (e.g. "hormuz"). */
export interface CorridorRiskEntry {
  score: number; // 0..100
  confidence: Confidence;
  /** Uncertainty band around the score — a magnitude, not a severity tier. */
  band: number;
  /** Provenance: ids of the signals the score was derived from. */
  source_ids: string[];
}

/** Modelled economic impact of a scenario. Emitted by Predict. */
export interface Impact {
  supply_gap_pct: number;
  price_rise_pct: number;
  /** Signed — negative in a disruption. */
  gdp_delta_pct: number;
  refinery_runrate_pct: number;
  power_stress_pct: number;
}

/** A single sourced, typed, slider-adjustable Predict input (F20). */
export interface AssumptionEntry {
  /** The live (possibly overridden) value. */
  value: number;
  /** Sourcing tier: measured fact, researched estimate, or an unsourced internal constant. */
  type: "fact" | "estimate" | "internal";
  /** Documented [lo, hi] bound — descriptive metadata, not enforced. */
  range: [number, number];
  /** Citation or rationale for this value. */
  src: string;
}

/** Named, slider-adjustable inputs to the Predict model. Emitted by Predict. */
export interface Assumptions {
  supply_lost_pct: AssumptionEntry;
  buffer_days: AssumptionEntry;
  price_elasticity: AssumptionEntry;
  power_oil_dependence: AssumptionEntry;
  gdp_oil_sensitivity: AssumptionEntry;
  power_stress_multiplier: AssumptionEntry;
}

/** Three-way route cost breakdown (F17): crude + war-risk insurance + detour. */
export interface CostBreakdown {
  crude: number;
  war_risk_insurance: number;
  detour: number;
}

/** A single ranked procurement reroute option (Recommend agent output row). */
export interface Reroute {
  /** Supplier id, e.g. 'ru_urals'. */
  supplier: string;
  /** Corridor/route id, e.g. 'suez_cape'. */
  route: string;
  /** Lead time in days. */
  days: number;
  /** Crude price only per barrel (USD) — v1.0 semantics preserved. */
  cost: number;
  /** v1.0 soft-downweight flag. `grade_ok` is the F16 hard gate. */
  compatible: boolean;
  /** 1-based rank among options. */
  rank: number;
  /** Which refinery this route/grade is evaluated against (F16). */
  refinery_id: string;
  /** F16 hard eligibility gate. */
  grade_ok: boolean;
  /** Whether this option may be ranked at all. */
  rank_eligible: boolean;
  /** Why an option is ineligible (F16), if it is. */
  reason: string | null;
  cost_breakdown: CostBreakdown;
  /** The F17 ranking field: crude + insurance + detour. */
  true_cost: number;
}

/** Strategic reserve drawdown state (Advise agent output). */
export interface Reserve {
  days_cover: number;
  drawdown_per_day: number;
  survives_until_refill: boolean;
}

/** One audit-logged instance of an official dragging a slider off default (F20/F9). */
export interface AssumptionOverride {
  /** Actor identity that made the override (verified JWT subject — the user's email). */
  who: string;
  /** Which Assumptions key was overridden, e.g. 'price_elasticity'. */
  field: string;
  from_default: number;
  to_value: number;
  /** ISO-8601 timestamp. */
  ts: string;
}

/** Geospatial block (F11/F13/F18): tanker + affected-asset ids. */
export interface Geo {
  /** Tankers inside an elevated-risk corridor's polygon. */
  at_risk_tanker_ids: string[];
  /** Tankers flagged by the anomaly detector (F18). */
  dark_tanker_ids: string[];
  /** Refineries the knowledge graph resolves as affected (F10). */
  affected_refinery_ids: string[];
}

/**
 * Backtest/validation block (F14). Always `null` on live `RiskState` in this
 * codebase — `GET /backtest/{id}` is a standalone read that never writes to
 * shared state (see PLAN.md Segment 1, Phase 8).
 */
export interface Validation {
  backtest_id: string;
  signal_lead_hours: number;
}

/**
 * The complete shared risk-state object exchanged across the system. Top-level
 * payload of `GET /state` and the `state.updated` WebSocket event.
 */
export interface RiskState {
  /** Scenario id, e.g. 'hormuz_partial_closure'. */
  scenario: string;
  /** ISO-8601 timestamp of last update. */
  updated_at: string;
  /** Per-corridor risk, keyed by corridor id (Watch agent). */
  corridor_risk: Record<string, CorridorRiskEntry>;
  /** Scenario severity, 0..1. */
  severity: number;
  /** `null` until Predict has run in the current cascade. */
  impact: Impact | null;
  /** `null` until Predict has run in the current cascade. */
  assumptions: Assumptions | null;
  /** Ranked reroute options (Recommend agent). Empty until Recommend has run. */
  reroutes: Reroute[];
  /** `null` until Advise has run in the current cascade. */
  reserve: Reserve | null;
  /** Audit trail of slider drags away from default (F20/F9), snapshotted at Approve. */
  assumption_overrides: AssumptionOverride[];
  /** `null` until a signal has been injected (Phase 6/7 populate it). */
  geo: Geo | null;
  /** Always `null` in this codebase — see the Validation doc comment. */
  validation: Validation | null;
}

/** Output contract for the Watch agent: the `corridor_risk` block only. */
export interface WatchAgentOutput {
  corridor_risk: Record<string, CorridorRiskEntry>;
}

/** Output contract for the Predict agent: `impact` + `assumptions`. */
export interface PredictAgentOutput {
  impact: Impact;
  assumptions: Assumptions;
}
