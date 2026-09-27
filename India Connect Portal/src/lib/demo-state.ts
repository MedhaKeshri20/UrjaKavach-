// Hardcoded demo/marketing data — NOT the live RiskState contract.
//
// This file is intentionally named and typed apart from `types/contract.ts`
// (the real backend mirror) so the two can never be confused for one
// another again — see India Connect Portal/spec.md Phase 1 decision #6.
// `DemoState`'s shape does not match the real `RiskState` contract (it
// predates it, invented independently) and is not meant to; it exists only
// to render the marketing landing page (`/`) without a live backend.
//
// Deliberately named `demoState`, not `seedState` — nothing that reads this
// should be able to pretend it's live data.
//
// Every other page (`/official`, `/public`, `RealWorldMap`) still reads from
// this file today too, as a temporary carryover: Phase 1 only builds the
// real contract types and retires the old invented-shape-pretending-to-be-
// the-contract file (`kavach-data.ts`'s old `RiskState`) — it does not wire
// live data yet (that's Phase 3). Rewiring those pages off this file to a
// real `useRiskState()` hook is Phase 3's job, not done here.

import { MAP_LOCATIONS, type Band } from "@/lib/kavach-data";

export interface DemoCorridor {
  id: string;
  name: string;
  from: [number, number]; // [x%, y%] on the stylized map
  to: [number, number];
  score: number; // 0..100
  band: Band;
  confidence: number; // 0..1
  headlines: string[];
}

export interface DemoRefinery {
  id: string;
  name: string;
  city: string;
  pos: [number, number];
  capacity_kbd: number; // thousand barrels/day
  grade: "sour" | "sweet" | "mixed";
  stress_pct: number;
}

export interface DemoReroute {
  refinery_id: string;
  from_port: string;
  to_port: string;
  vessels: number;
  grade_ok: boolean;
  rank_eligible: boolean;
  reason: string;
  true_cost_usd_bbl: number;
  cost_breakdown: { crude: number; war_risk: number; detour: number };
  eta_days: number;
}

export interface DemoImpact {
  gdp_delta_pct: number;
  inflation_delta_pct: number;
  fx_delta_inr: number;
  power_stress_pct: number;
  spr_days_remaining: number;
}

export interface DemoAuditEntry {
  ts: string;
  actor: "watch" | "predict" | "recommend" | "advise" | "official";
  action: string;
  detail: string;
}

export interface DemoAdvisory {
  title: string;
  body: string;
  severity: Band;
  cta?: string;
}

export interface DemoState {
  updated_at: string;
  national_score: number;
  national_band: Band;
  corridors: DemoCorridor[];
  refineries: DemoRefinery[];
  reroutes: DemoReroute[];
  impact: DemoImpact;
  advisories: DemoAdvisory[];
  audit: DemoAuditEntry[];
  spr_series: { day: number; days_cover: number; baseline: number }[];
  dark_ship_events: { corridor_id: string; count: number; last_seen: string }[];
}

export const demoState: DemoState = {
  updated_at: new Date().toISOString(),
  national_score: 68,
  national_band: "high",
  corridors: [
    {
      id: "hormuz",
      name: "Strait of Hormuz",
      from: MAP_LOCATIONS.hormuz,
      to: MAP_LOCATIONS.jamnagar,
      score: 82,
      band: "critical",
      confidence: 0.86,
      headlines: [
        "Tanker seized off Bandar Abbas — Reuters",
        "US 5th Fleet raises alert to Bravo",
        "Insurance premiums up 34% w/w",
      ],
    },
    {
      id: "bab_el_mandeb",
      name: "Bab-el-Mandeb",
      from: MAP_LOCATIONS.bab_el_mandeb,
      to: MAP_LOCATIONS.kochi,
      score: 71,
      band: "high",
      confidence: 0.78,
      headlines: ["Houthi drone strike on VLCC — Bloomberg", "MSC re-routes fleet via Cape"],
    },
    {
      id: "malacca",
      name: "Strait of Malacca",
      from: MAP_LOCATIONS.malacca,
      to: MAP_LOCATIONS.chennai,
      score: 28,
      band: "low",
      confidence: 0.91,
      headlines: ["Traffic nominal", "PSA berth utilization 74%"],
    },
    {
      id: "suez",
      name: "Suez Canal",
      from: MAP_LOCATIONS.suez,
      to: MAP_LOCATIONS.mumbai,
      score: 44,
      band: "medium",
      confidence: 0.72,
      headlines: ["Delays 6–14 hrs southbound", "SCA transit fees stable"],
    },
  ],
  refineries: [
    {
      id: "jamnagar",
      name: "Reliance Jamnagar",
      city: "Jamnagar",
      pos: MAP_LOCATIONS.jamnagar,
      capacity_kbd: 1240,
      grade: "sour",
      stress_pct: 62,
    },
    {
      id: "mumbai",
      name: "BPCL Mumbai",
      city: "Mumbai",
      pos: MAP_LOCATIONS.mumbai,
      capacity_kbd: 240,
      grade: "sour",
      stress_pct: 55,
    },
    {
      id: "kochi",
      name: "BPCL Kochi",
      city: "Kochi",
      pos: MAP_LOCATIONS.kochi,
      capacity_kbd: 310,
      grade: "sour",
      stress_pct: 48,
    },
    {
      id: "paradip",
      name: "IOCL Paradip",
      city: "Paradip",
      pos: MAP_LOCATIONS.paradip,
      capacity_kbd: 300,
      grade: "sweet",
      stress_pct: 22,
    },
    {
      id: "vizag",
      name: "HPCL Visakh",
      city: "Visakhapatnam",
      pos: MAP_LOCATIONS.vizag,
      capacity_kbd: 166,
      grade: "mixed",
      stress_pct: 34,
    },
  ],
  reroutes: [
    {
      refinery_id: "jamnagar",
      from_port: "Ras Tanura",
      to_port: "Sikka (Jamnagar)",
      vessels: 4,
      grade_ok: true,
      rank_eligible: true,
      reason: "Arab Heavy → sour-config match",
      true_cost_usd_bbl: 4.82,
      cost_breakdown: { crude: 2.1, war_risk: 1.9, detour: 0.82 },
      eta_days: 11,
    },
    {
      refinery_id: "kochi",
      from_port: "Yanbu",
      to_port: "Kochi",
      vessels: 2,
      grade_ok: true,
      rank_eligible: true,
      reason: "Cape re-route, sour-compatible",
      true_cost_usd_bbl: 6.14,
      cost_breakdown: { crude: 2.4, war_risk: 2.3, detour: 1.44 },
      eta_days: 24,
    },
    {
      refinery_id: "paradip",
      from_port: "Basrah",
      to_port: "Paradip",
      vessels: 1,
      grade_ok: false,
      rank_eligible: false,
      reason: "Basrah Heavy blocked — Paradip is sweet-only",
      true_cost_usd_bbl: 0,
      cost_breakdown: { crude: 0, war_risk: 0, detour: 0 },
      eta_days: 0,
    },
  ],
  impact: {
    gdp_delta_pct: -0.42,
    inflation_delta_pct: 0.71,
    fx_delta_inr: 1.24,
    power_stress_pct: 18,
    spr_days_remaining: 9.4,
  },
  advisories: [
    {
      title: "Fuel supply remains stable",
      body: "India holds 9.4 days of strategic reserves plus 65 days of commercial stock. There is no shortage.",
      severity: "low",
      cta: "How reserves work",
    },
    {
      title: "Petrol/Diesel price outlook: steady this fortnight",
      body: "Government-monitored retail prices are unchanged. Any pass-through would be gradual.",
      severity: "low",
    },
    {
      title: "Elevated risk on Hormuz corridor",
      body: "Officials have activated re-routing to Jamnagar and Kochi refineries. No consumer impact expected.",
      severity: "high",
    },
  ],
  audit: [
    {
      ts: "T-00:00",
      actor: "official",
      action: "APPROVED",
      detail: "Reroute plan #A-2411 committed",
    },
    {
      ts: "T-00:12",
      actor: "advise",
      action: "Advisory drafted",
      detail: "3 public advisories, alarm score 0.14",
    },
    {
      ts: "T-00:34",
      actor: "recommend",
      action: "Ranked reroutes",
      detail: "2 eligible, 1 blocked (grade)",
    },
    {
      ts: "T-01:02",
      actor: "predict",
      action: "Impact computed",
      detail: "GDP −0.42%, power stress 18%",
    },
    {
      ts: "T-01:18",
      actor: "watch",
      action: "Signal ingested",
      detail: "Hormuz tanker seizure, conf 0.86",
    },
  ],
  spr_series: Array.from({ length: 30 }, (_, i) => ({
    day: i - 14,
    days_cover: 12 - Math.max(0, (i - 10) * 0.35) + Math.sin(i / 3) * 0.4,
    baseline: 12,
  })),
  dark_ship_events: [
    { corridor_id: "hormuz", count: 7, last_seen: "2h ago" },
    { corridor_id: "bab_el_mandeb", count: 3, last_seen: "6h ago" },
  ],
};
