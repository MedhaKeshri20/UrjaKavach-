// REST client. Talks directly to the FastAPI backend (CORS is wildcard-open
// by default on the backend — see backend/config.py's `cors_origins`), or via
// the Vite dev proxy at /api/* when VITE_API_URL is unset (see
// vite.config.ts). Attaches the Bearer token from the session cookie for
// protected calls.

import { readSession } from "@/lib/session";
import type { CurrentUser, Role, TokenResponse } from "@/types/auth";
import type { Assumptions, Impact, Reroute, RiskState } from "@/types/contract";

const BASE = import.meta.env.VITE_API_URL || "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const session = readSession();
  if (session?.token) headers.set("Authorization", `Bearer ${session.token}`);

  const res = await fetch(`${BASE}${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = Array.isArray(body.detail)
        ? body.detail.map((d: { msg: string }) => d.msg).join(", ")
        : (body.detail ?? detail);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, String(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface AuditEntry {
  id: number;
  actor: string;
  action: string;
  payload: Record<string, unknown>;
  ts: string;
}

export interface ReroutesResponse {
  sort: "balanced" | "cost" | "speed";
  excluded_corridors: string[];
  options: (Reroute & {
    scores: { price: number; speed: number; compat: number; total: number };
  })[];
}

export interface PublicStatus {
  status: string;
  message: string;
  conservation_plan: string[];
  action_feed: { action: string; supplier: string | null; route: string | null; ts: string }[];
  updated_at: string;
}

export interface TankerTrackPoint {
  ts: string;
  lat: number;
  lon: number;
  heading_deg: number;
  speed_knots: number;
}

export interface Tanker {
  id: string;
  corridor_id: string;
  track: TankerTrackPoint[];
}

export interface CorridorGeometry {
  type: string;
  coordinates: [number, number][]; // [lon, lat] per GeoJSON convention
}

export interface GeoStateResponse {
  geo: RiskState["geo"];
  corridors: {
    id: string;
    name: string;
    chokepoint: string;
    war_risk_pct: number;
    detour_days: number;
    geojson_path: string;
    // null if the committed GeoJSON file was missing/malformed — the map
    // just skips that corridor's polyline rather than fabricating one.
    geometry: CorridorGeometry | null;
  }[];
  refineries: { id: string; name: string; capacity_bpd: number; lat: number; lon: number }[];
  tankers: Tanker[];
}

export interface ProvenanceItem {
  id: string;
  headline: string;
  source: string;
  timestamp: string;
}

export interface ProvenanceResponse {
  items: ProvenanceItem[];
  // ids that don't resolve to a real corpus entry (e.g. the offline stub's
  // source_ids, which are just the injected signal's own id) — never
  // fabricated, always reported honestly.
  missing: string[];
}

export interface BacktestResponse {
  validation: { backtest_id: string; signal_lead_hours: number };
  corridor: string;
  label: string;
  watch_alert_threshold: number;
  watch_crossed_at: string | null;
  brent_spike_threshold_usd: number;
  brent_crossed_at: string | null;
  // Field names verified against a live GET /backtest/red_sea_2023 response,
  // not guessed from the contract — score_timeline entries also carry
  // headline_id/source_ids, and the price field is price_usd_bbl, not price.
  score_timeline: { ts: string; headline_id: string; score: number; source_ids: string[] }[];
  price_timeline: { ts: string; price_usd_bbl: number }[];
  note: string;
}

export const api = {
  // risk state / cascade
  getState: () => request<RiskState>("/state"),
  injectSignal: (body: {
    corridor: string;
    headline: string;
    severity?: number;
    scenario?: string;
    id?: string;
    source_ids?: string[];
  }) => request<RiskState>("/signal", { method: "POST", body: JSON.stringify(body) }),
  simulate: (scenario: string, assumptions: Assumptions) =>
    request<{ scenario: string; impact: Impact; assumptions: Assumptions }>("/simulate", {
      method: "POST",
      body: JSON.stringify({ scenario, assumptions }),
    }),
  overrideAssumption: (assumptions: Assumptions) =>
    request<{ ok: boolean; overrides_logged: string[]; pending: unknown[] }>(
      "/assumptions/override",
      { method: "POST", body: JSON.stringify({ assumptions }) },
    ),
  getReroutes: (sort: "balanced" | "cost" | "speed" = "balanced") =>
    request<ReroutesResponse>(`/reroutes?sort=${sort}`),
  approve: (supplier: string, note?: string) =>
    request<{
      ok: boolean;
      audit_id: number;
      actor: string;
      action: string;
      payload: unknown;
      ts: string;
    }>("/approve", { method: "POST", body: JSON.stringify({ supplier, note }) }),
  getAudit: (limit = 50) => request<AuditEntry[]>(`/audit?limit=${limit}`),
  publicStatus: () => request<PublicStatus>("/public/status"),
  getGeoState: () => request<GeoStateResponse>("/geo/state"),
  getBacktest: (id: string) => request<BacktestResponse>(`/backtest/${id}`),
  getProvenance: (ids: string[]) =>
    request<ProvenanceResponse>(`/provenance?ids=${ids.map(encodeURIComponent).join(",")}`),

  // auth
  register: (email: string, password: string, role: Role) =>
    request<TokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, role }),
    }),
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<CurrentUser>("/auth/me"),
};
