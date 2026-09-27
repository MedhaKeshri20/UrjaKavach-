// Small, honest UI-derivation helpers for real (live) RiskState data — kept
// separate from lib/kavach-data.ts's generic band helpers and from
// lib/demo-state.ts's mock data. Nothing here invents numbers; every
// function is a pure presentation transform of a real contract value.

import { bandOf, type Band } from "@/lib/kavach-data";
import type { Assumptions, AssumptionEntry, RiskState } from "@/types/contract";
import type { AuditEntry } from "@/lib/api";

// No "national risk" field exists on the real contract — only `severity`
// (0..1) and per-corridor scores. Derived client-side per spec.md §2
// decision #3, not invented independently of real data.
export function nationalScore(state: RiskState): number {
  return Math.round(state.severity * 100);
}

export function nationalBand(state: RiskState): Band {
  return bandOf(nationalScore(state));
}

// Corridor id -> display name. A presentation lookup, not risk data — real
// ids/scores/confidence always come from `state.corridor_risk` directly.
// Matches backend/seed/corridors.json exactly (hormuz/suez_cape/atlantic/
// malacca) — note these differ from lib/demo-state.ts's mock ids
// (bab_el_mandeb/suez), which predate the real seed data.
export const CORRIDOR_LABELS: Record<string, string> = {
  hormuz: "Strait of Hormuz",
  suez_cape: "Suez / Cape of Good Hope",
  atlantic: "Atlantic Basin",
  malacca: "Strait of Malacca",
};

export function corridorLabel(id: string): string {
  return CORRIDOR_LABELS[id] ?? id;
}

// The contract's own `CorridorRiskEntry.band` is an uncertainty magnitude,
// not a severity tier (see types/contract.ts) — this derives a display tier
// from `score` the same way the rest of the UI already does everywhere else.
export function corridorTier(score: number): Band {
  return bandOf(score);
}

// Supplier id -> display name (country + crude grade). A presentation
// lookup only, matching backend/seed/suppliers.json exactly — real ids
// always come from Reroute.supplier directly.
export const SUPPLIER_LABELS: Record<string, string> = {
  iq_basrah: "Iraq — Basrah Medium",
  sa_arablight: "Saudi Arabia — Arab Light",
  ae_murban: "UAE — Murban",
  ru_urals: "Russia — Urals",
  ng_bonny: "Nigeria — Bonny Light",
  us_wti: "USA — WTI",
  br_tupi: "Brazil — Lula",
};

export function supplierLabel(id: string): string {
  return SUPPLIER_LABELS[id] ?? id;
}

// Refinery id -> display name. Matches backend/seed/refineries.json's own
// `name` field exactly (Reroute.refinery_id carries only the id, not the
// name, so this mirrors CORRIDOR_LABELS' pattern rather than re-fetching).
export const REFINERY_LABELS: Record<string, string> = {
  jamnagar: "Jamnagar (RIL)",
  vadinar: "Vadinar (Nayara)",
  paradip: "Paradip (IOCL)",
};

export function refineryLabel(id: string): string {
  return REFINERY_LABELS[id] ?? id;
}

// audit_log's `action` values (backend/api/routes.py) -> plain-language
// labels for the cockpit's audit trail.
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  approve_reroute: "Approved reroute",
  override_assumption: "Adjusted assumption",
};

export function auditActionLabel(action: string): string {
  return AUDIT_ACTION_LABELS[action] ?? action;
}

// One-line, honest summary of a real audit_log row for the audit trail
// panel. Covers the actions this app currently triggers/reads
// (approve_reroute, override_assumption) with a generic fallback for
// anything else — never fabricates detail that isn't in the payload.
export function describeAuditEntry(entry: AuditEntry): string {
  const p = entry.payload ?? {};
  if (entry.action === "approve_reroute") {
    const supplier = typeof p.supplier === "string" ? supplierLabel(p.supplier) : "?";
    const route = typeof p.route === "string" ? corridorLabel(p.route) : "?";
    return `${supplier} via ${route}`;
  }
  if (entry.action === "override_assumption") {
    const field = typeof p.field === "string" ? p.field : null;
    const label = field ? (ASSUMPTION_LABELS[field as keyof Assumptions]?.label ?? field) : "?";
    return `${label}: ${p.from_default ?? "?"} → ${p.to_value ?? "?"}`;
  }
  const summary = JSON.stringify(p);
  return summary.length > 120 ? `${summary.slice(0, 120)}…` : summary;
}

// Display metadata for the six Assumptions fields (F20 slider UX). Purely
// presentational — values/types/ranges/sources always come from the live
// AssumptionEntry itself, never invented here.
export const ASSUMPTION_LABELS: Record<
  keyof Assumptions,
  { label: string; unit: string; decimals: number }
> = {
  supply_lost_pct: { label: "Supply lost", unit: "%", decimals: 1 },
  buffer_days: { label: "SPR buffer", unit: "d", decimals: 1 },
  price_elasticity: { label: "Price elasticity", unit: "x", decimals: 2 },
  power_oil_dependence: { label: "Power-oil dependence", unit: "", decimals: 3 },
  gdp_oil_sensitivity: { label: "GDP-oil sensitivity", unit: "", decimals: 3 },
  power_stress_multiplier: { label: "Power-stress multiplier", unit: "x", decimals: 1 },
};

export const ASSUMPTION_FIELD_ORDER: (keyof Assumptions)[] = [
  "supply_lost_pct",
  "buffer_days",
  "price_elasticity",
  "power_oil_dependence",
  "gdp_oil_sensitivity",
  "power_stress_multiplier",
];

// `AssumptionEntry.range` is the documented, sourced bound (spec.md Phase 5
// decision #6's "fact type" narrow slider). `estimate`/`internal` types get a
// wider slider so an official can explore past the documented estimate — one
// range-width of padding on each side — while `fact` stays locked as close to
// `range` as possible. `range` is a fixed citation (e.g. "typical Hormuz
// transit share, 35-45%"), but the live `value` is severity-scaled and can
// legitimately fall outside it (a severity=1.0 signal pushes
// `supply_lost_pct` to 100, verified against a live backend) — always
// widening to include the current value avoids Radix silently clamping the
// displayed thumb away from the real live state.
export function assumptionSliderRange(entry: AssumptionEntry): {
  min: number;
  max: number;
  step: number;
} {
  const [lo, hi] = entry.range;
  const span = hi - lo || 1;
  const narrow = entry.type === "fact";
  const min = Math.min(entry.value, narrow ? lo : Math.max(0, lo - span));
  const max = Math.max(entry.value, narrow ? hi : hi + span);
  const step = (max - min) / 200 || 0.01;
  return { min, max, step };
}
