// UI-only helpers shared across both real (live) and demo data: severity-tier
// banding and well-known corridor/refinery map coordinates. Contains no
// RiskState-shaped data of its own — see types/contract.ts for the real
// contract mirror and lib/demo-state.ts for the landing page's mock data.

export type Band = "low" | "medium" | "high" | "critical";

export const bandOf = (score: number): Band =>
  score >= 80 ? "critical" : score >= 60 ? "high" : score >= 35 ? "medium" : "low";

export const bandColor: Record<Band, string> = {
  low: "var(--alert-low)",
  medium: "var(--alert-med)",
  high: "var(--alert-high)",
  critical: "var(--alert-crit)",
};

export const bandLabel: Record<Band, string> = {
  low: "STABLE",
  medium: "WATCH",
  high: "ELEVATED",
  critical: "CRITICAL",
};

// India-shaped stylized map coords (percentage on a 100x100 viewport).
// The first block is the original demo id set (lib/demo-state.ts, predates
// the real seed data). The second block adds the *real* corridor/refinery
// ids (backend/seed/corridors.json, refineries.json) so IndiaMap.tsx can
// also render live data as RealWorldMap's offline fallback (India Connect
// Portal/spec.md Phase 7, decision #1) — both sets coexist since the
// landing page still uses the demo ids.
export const MAP_LOCATIONS = {
  hormuz: [12, 42] as [number, number],
  bab_el_mandeb: [24, 62] as [number, number],
  malacca: [88, 66] as [number, number],
  suez: [8, 26] as [number, number],
  mumbai: [42, 58] as [number, number],
  jamnagar: [36, 50] as [number, number],
  kochi: [48, 78] as [number, number],
  paradip: [66, 60] as [number, number],
  vizag: [62, 66] as [number, number],
  chennai: [58, 72] as [number, number],

  suez_cape: [8, 26] as [number, number],
  atlantic: [4, 54] as [number, number],
  vadinar: [34, 48] as [number, number],
};
