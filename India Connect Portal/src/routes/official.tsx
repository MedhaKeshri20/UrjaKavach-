import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  CheckCircle2,
  ShipWheel,
  Clock,
  Zap,
  TrendingDown,
  Fuel,
  Factory,
  ShieldAlert,
  Radio,
  Ban,
  WifiOff,
  History,
} from "lucide-react";
import { KavachHeader } from "@/components/kavach/KavachHeader";
import { RiskGauge } from "@/components/kavach/RiskGauge";
import { RealWorldMap } from "@/components/kavach/RealWorldMap";
import { bandColor, bandLabel, bandOf, type Band } from "@/lib/kavach-data";
import {
  ASSUMPTION_FIELD_ORDER,
  ASSUMPTION_LABELS,
  assumptionSliderRange,
  auditActionLabel,
  corridorLabel,
  describeAuditEntry,
  nationalBand,
  nationalScore,
  refineryLabel,
  supplierLabel,
} from "@/lib/live-derive";
import { useRiskState } from "@/hooks/useRiskState";
import { useReserveHistory } from "@/hooks/useReserveHistory";
import { useGeoState } from "@/hooks/useGeoState";
import {
  api,
  ApiError,
  type AuditEntry,
  type BacktestResponse,
  type ProvenanceItem,
  type ReroutesResponse,
} from "@/lib/api";
import type { Assumptions, AssumptionEntry, Impact, RiskState } from "@/types/contract";

// The one curated historical case Segment 1's backtest module ships
// (backend/seed/backtest/red_sea_2023.json) — see backend/agents/backtest.py.
const BACKTEST_CASE_ID = "red_sea_2023";

type BacktestPoint = { ts: string; score?: number; price?: number };

function mergeBacktestTimelines(bt: BacktestResponse): BacktestPoint[] {
  const byTs = new Map<string, BacktestPoint>();
  for (const p of bt.score_timeline) {
    byTs.set(p.ts, { ...(byTs.get(p.ts) ?? { ts: p.ts }), score: p.score });
  }
  for (const p of bt.price_timeline) {
    byTs.set(p.ts, { ...(byTs.get(p.ts) ?? { ts: p.ts }), price: p.price_usd_bbl });
  }
  return Array.from(byTs.values()).sort((a, b) => a.ts.localeCompare(b.ts));
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { month: "short", day: "numeric" });
}
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { RequireRole } from "@/components/kavach/RequireRole";

type ScoredReroute = ReroutesResponse["options"][number];
type SortMode = "balanced" | "cost" | "speed";

export const Route = createFileRoute("/official")({
  head: () => ({
    meta: [
      { title: "Official Cockpit — Urja Kavach" },
      {
        name: "description",
        content:
          "Live risk cockpit for India's crude supply chain. Corridors, refineries, reroutes, and one-click approvals.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: () => (
    <RequireRole role="official">
      <OfficialCockpit />
    </RequireRole>
  ),
});

function timeAgo(iso: string): string {
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function OfficialCockpit() {
  const { state, status } = useRiskState();
  const reserveHistory = useReserveHistory(state);
  const { geoConfig } = useGeoState();
  const [activeCorridor, setActiveCorridor] = useState<string>("hormuz");
  const [approving, setApproving] = useState(false);
  const [approved, setApproved] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);

  // Real reroute ranking (Phase 4) — GET /reroutes recomputes candidates from
  // live seed config + current corridor exclusions independently of the
  // WS-pushed RiskState.reroutes (always "balanced"), so the sort toggle and
  // per-signal exclusion updates both need their own fetch.
  const [sort, setSort] = useState<SortMode>("balanced");
  const [reroutesResp, setReroutesResp] = useState<ReroutesResponse | null>(null);
  const [reroutesError, setReroutesError] = useState<string | null>(null);
  const [selectedSupplier, setSelectedSupplier] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getReroutes(sort)
      .then((res) => {
        if (cancelled) return;
        setReroutesResp(res);
        setReroutesError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setReroutesError(err instanceof ApiError ? err.message : "Failed to load reroutes");
      });
    return () => {
      cancelled = true;
    };
  }, [sort, state?.updated_at]);

  const refreshAudit = () => {
    api
      .getAudit()
      .then(setAudit)
      .catch(() => {
        // official-only + auth-gated; a failure here (401/403/offline) just
        // leaves the panel empty rather than crashing the whole cockpit.
      });
  };
  useEffect(refreshAudit, []);

  const score = state ? nationalScore(state) : null;
  const band = state ? nationalBand(state) : null;
  const corridorEntry = state?.corridor_risk?.[activeCorridor];
  const reroutesOptions = reroutesResp?.options ?? [];
  const eligibleOptions = reroutesOptions.filter((r) => r.grade_ok && r.rank_eligible);
  const topEligible = eligibleOptions[0];

  useEffect(() => {
    setSelectedSupplier((current) =>
      eligibleOptions.some((r) => r.supplier === current)
        ? current
        : (topEligible?.supplier ?? null),
    );
    // Re-run only when a fresh /reroutes response lands, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reroutesResp]);

  const selected = reroutesOptions.find((r) => r.supplier === selectedSupplier) ?? topEligible;

  const onSelectReroute = (r: ScoredReroute) => {
    if (!r.grade_ok || !r.rank_eligible) return;
    setSelectedSupplier(r.supplier);
    setApproved(false);
    setApproveError(null);
  };

  const onApprove = async () => {
    if (!selected) return;
    setApproving(true);
    setApproveError(null);
    try {
      await api.approve(selected.supplier);
      setApproved(true);
      refreshAudit();
    } catch (err) {
      setApproveError(err instanceof ApiError ? err.message : "Approve failed");
    } finally {
      setApproving(false);
    }
  };

  return (
    <div className="min-h-screen bg-cockpit text-foreground">
      <KavachHeader mode="official" />

      {status === "offline" && (
        <div className="bg-destructive/10 border-b border-destructive/30 text-destructive text-[11px] font-mono uppercase tracking-widest px-4 py-2 flex items-center gap-2">
          <WifiOff className="w-3.5 h-3.5" />
          Backend offline —{" "}
          {state ? "showing last known state, reconnecting…" : "no live state received yet"}
        </div>
      )}

      <main className="max-w-[1600px] mx-auto px-4 md:px-6 py-6 space-y-6">
        {/* Top row: gauge + map */}
        <section className="grid grid-cols-12 gap-4">
          <div className="col-span-12 lg:col-span-4 panel-glow p-6 flex flex-col">
            <div className="flex items-center justify-between">
              <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
                National Risk
              </div>
              <StatusBadge status={status} />
            </div>
            <div className="flex-1 flex items-center justify-center py-4">
              {state && score !== null && band ? (
                <RiskGauge score={score} band={band} size={260} />
              ) : (
                <div className="text-center text-muted-foreground text-xs py-10">
                  No signal injected yet.
                  <br />
                  <a href="/mission" className="text-cyan hover:underline">
                    Open Mission Control →
                  </a>
                </div>
              )}
            </div>
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <MiniStat
                label="Corridors"
                value={state ? String(Object.keys(state.corridor_risk).length) : "—"}
                color="var(--cyan)"
              />
              <MiniStat
                label="Reserve"
                value={state?.reserve ? `${state.reserve.days_cover.toFixed(1)}d` : "—"}
                color="var(--foreground)"
              />
              <MiniStat
                label="Updated"
                value={state ? timeAgo(state.updated_at) : "—"}
                color="var(--foreground)"
              />
            </div>
          </div>

          <div className="col-span-12 lg:col-span-8">
            <div className="mb-2 flex items-center justify-between px-1">
              <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
                Theater · Corridors × Refineries × AIS
              </div>
              <div className="text-[10px] font-mono text-muted-foreground">
                Click corridor to inspect · real corridor geometry + AIS replay
              </div>
            </div>
            <RealWorldMap
              activeCorridor={activeCorridor}
              onSelectCorridor={setActiveCorridor}
              corridorRisk={state?.corridor_risk}
              geo={state?.geo}
              geoConfig={geoConfig}
            />
          </div>
        </section>

        {/* Middle row: corridor detail + impact + what-if */}
        <section className="grid grid-cols-12 gap-4">
          {/* Corridor detail */}
          <div className="col-span-12 lg:col-span-4 panel p-5">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
                  Corridor
                </div>
                <div className="font-display text-2xl font-semibold mt-1">
                  {corridorLabel(activeCorridor)}
                </div>
              </div>
              {corridorEntry && (
                <BandBadge band={bandOf(corridorEntry.score)} score={corridorEntry.score} />
              )}
            </div>
            {corridorEntry ? (
              <>
                <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                  <KV label="Confidence" value={corridorEntry.confidence.toUpperCase()} />
                  <KV
                    label="Dark ships (all corridors)"
                    value={String(state?.geo?.dark_tanker_ids.length ?? 0)}
                  />
                </div>
                <div className="mt-5 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                  Signal feed · click a source to see its provenance
                </div>
                <div className="mt-2">
                  <SignalFeed sourceIds={corridorEntry.source_ids} />
                </div>
              </>
            ) : (
              <div className="mt-6 text-xs text-muted-foreground italic">
                No live scoring yet for this corridor{state ? "" : " — inject a signal first"}.
              </div>
            )}
          </div>

          {/* Impact */}
          <div className="col-span-12 lg:col-span-4 panel p-5">
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
              Predicted Impact
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <ImpactTile
                icon={<TrendingDown className="w-4 h-4" />}
                label="GDP Δ"
                value={state?.impact ? `${state.impact.gdp_delta_pct.toFixed(2)}%` : "—"}
                color="var(--alert-high)"
              />
              <ImpactTile
                icon={<Fuel className="w-4 h-4" />}
                label="Price rise"
                value={state?.impact ? `+${state.impact.price_rise_pct.toFixed(2)}%` : "—"}
                color="var(--alert-med)"
              />
              <ImpactTile
                icon={<Zap className="w-4 h-4" />}
                label="Power stress"
                value={state?.impact ? `${state.impact.power_stress_pct.toFixed(1)}%` : "—"}
                color="var(--alert-high)"
              />
              <ImpactTile
                icon={<Factory className="w-4 h-4" />}
                label="Refinery run-rate"
                value={state?.impact ? `${state.impact.refinery_runrate_pct.toFixed(1)}%` : "—"}
                color="var(--cyan)"
              />
            </div>
            <div className="mt-5 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
              SPR days-of-cover · session-observed, not historical
            </div>
            <div className="h-24 mt-2">
              {reserveHistory.length > 1 ? (
                <ResponsiveContainer>
                  <AreaChart
                    data={reserveHistory}
                    margin={{ top: 4, left: -20, right: 4, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="sprFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="oklch(0.72 0.17 220)" stopOpacity={0.7} />
                        <stop offset="100%" stopColor="oklch(0.72 0.17 220)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="ts" hide />
                    <YAxis hide domain={["auto", "auto"]} />
                    <Tooltip
                      contentStyle={{
                        background: "var(--surface-2)",
                        border: "1px solid var(--border)",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="days_cover"
                      stroke="var(--cyan)"
                      strokeWidth={2}
                      fill="url(#sprFill)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-muted-foreground italic">
                  Collecting samples — inject a few signals to see a trend.
                </div>
              )}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Now:{" "}
              <span className="font-mono text-foreground">
                {state?.reserve ? `${state.reserve.days_cover.toFixed(1)} days` : "—"}
              </span>
            </div>
          </div>

          {/* What-if (Phase 5: real Assumptions, real /simulate + audit-logged overrides) */}
          <AssumptionsPanel state={state} onOverride={refreshAudit} />
        </section>

        {/* Bottom row: reroutes + audit */}
        <section className="grid grid-cols-12 gap-4">
          <div className="col-span-12 lg:col-span-8 panel p-5">
            <div className="flex items-center justify-between mb-4 gap-3">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
                  Recommended Reroutes
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  Grade-eligibility gate + true-cost ranking · click a card to select it
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1">
                  {(["balanced", "cost", "speed"] as const).map((s) => (
                    <button
                      key={s}
                      onClick={() => setSort(s)}
                      className="text-[9px] font-mono uppercase tracking-widest px-2 py-1 rounded border transition-colors"
                      style={{
                        borderColor: sort === s ? "var(--cyan)" : "var(--border)",
                        color: sort === s ? "var(--cyan)" : "var(--muted-foreground)",
                        background:
                          sort === s
                            ? "color-mix(in oklab, var(--cyan) 12%, transparent)"
                            : "transparent",
                      }}
                    >
                      {s}
                    </button>
                  ))}
                </div>
                <div className="text-right">
                  <Button
                    onClick={onApprove}
                    disabled={!selected || approving || approved}
                    className="font-mono uppercase tracking-widest text-xs"
                    style={{
                      background: approved ? "var(--alert-low)" : "var(--gradient-primary)",
                      color: "var(--background)",
                    }}
                  >
                    {approved ? (
                      <>
                        <CheckCircle2 className="w-4 h-4 mr-1.5" /> Approved
                      </>
                    ) : approving ? (
                      "Approving…"
                    ) : (
                      "Approve selected reroute"
                    )}
                  </Button>
                  {!selected && (
                    <div className="text-[10px] text-muted-foreground mt-1">
                      No eligible reroute yet
                    </div>
                  )}
                  {approveError && (
                    <div className="text-[10px] text-destructive mt-1">{approveError}</div>
                  )}
                </div>
              </div>
            </div>
            {reroutesOptions.length === 0 ? (
              <div className="text-xs text-muted-foreground italic py-6 text-center">
                {reroutesError ?? "No candidate suppliers configured."}
              </div>
            ) : (
              <div className="grid md:grid-cols-3 gap-3">
                {reroutesOptions.map((r) => (
                  <RerouteCard
                    key={`${r.supplier}-${r.route}-${r.refinery_id}`}
                    r={r}
                    isTop={r.supplier === topEligible?.supplier}
                    selected={r.supplier === selectedSupplier}
                    onSelect={() => onSelectReroute(r)}
                  />
                ))}
              </div>
            )}
          </div>

          <div className="col-span-12 lg:col-span-4 panel p-5">
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground mb-4">
              Cascade Audit · newest first
            </div>
            {audit.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">No audit entries yet.</div>
            ) : (
              <ol className="relative border-l border-border/70 space-y-4 pl-4">
                {audit.map((a) => (
                  <AuditRow key={a.id} entry={a} />
                ))}
              </ol>
            )}
          </div>
        </section>

        {/* Backtest — one curated historical case (Phase 8), never mutates RiskState */}
        <section className="grid grid-cols-12 gap-4">
          <div className="col-span-12">
            <BacktestPanel />
          </div>
        </section>
      </main>
    </div>
  );
}

function StatusBadge({ status }: { status: "connecting" | "live" | "offline" }) {
  if (status === "live") {
    return (
      <div className="flex items-center gap-1.5 text-[10px] font-mono text-emerald-400">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        LIVE
      </div>
    );
  }
  if (status === "connecting") {
    return (
      <div className="flex items-center gap-1.5 text-[10px] font-mono text-amber-400">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        CONNECTING
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1.5 text-[10px] font-mono text-destructive">
      <span className="w-1.5 h-1.5 rounded-full bg-destructive" />
      OFFLINE
    </div>
  );
}

function BandBadge({ band, score }: { band: Band; score: number }) {
  return (
    <div className="text-right">
      <div className="font-mono text-3xl font-semibold" style={{ color: bandColor[band] }}>
        {score}
      </div>
      <div
        className="text-[9px] font-mono uppercase tracking-widest"
        style={{ color: bandColor[band] }}
      >
        {bandLabel[band]}
      </div>
    </div>
  );
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel p-2.5">
      <div className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
      <div className="font-mono mt-0.5">{value}</div>
    </div>
  );
}

// Real click-through from a corridor score to its retrieved snippets
// (Phase 6). Lazily resolves each source id on first click via
// GET /provenance and caches the result (including "missing", for the
// offline stub's non-corpus ids) so re-clicking never refetches.
function SignalFeed({ sourceIds }: { sourceIds: string[] }) {
  const [entries, setEntries] = useState<Record<string, ProvenanceItem | "missing" | "loading">>(
    {},
  );

  const onClickId = (id: string) => {
    if (entries[id] !== undefined) return;
    setEntries((prev) => ({ ...prev, [id]: "loading" }));
    api
      .getProvenance([id])
      .then((res) => {
        const item = res.items.find((i) => i.id === id);
        setEntries((prev) => ({ ...prev, [id]: item ?? "missing" }));
      })
      .catch(() => setEntries((prev) => ({ ...prev, [id]: "missing" })));
  };

  if (sourceIds.length === 0) {
    return <div className="text-xs text-muted-foreground italic">No sources retrieved.</div>;
  }

  return (
    <div className="space-y-2">
      {sourceIds.map((id, i) => {
        const entry = entries[id];
        return (
          <div key={id} className="rounded-md bg-surface-2/60 border border-border overflow-hidden">
            <button
              onClick={() => onClickId(id)}
              className="w-full flex items-start gap-2 text-xs p-2 text-left hover:bg-surface-2 transition-colors"
            >
              <Radio className="w-3.5 h-3.5 mt-0.5 shrink-0 text-cyan" />
              <span className="text-foreground/90 flex-1">Source {i + 1}</span>
            </button>
            {entry === "loading" && (
              <div className="px-2 pb-2 text-[10px] text-muted-foreground italic">Loading…</div>
            )}
            {entry === "missing" && (
              <div className="px-2 pb-2 text-[10px] text-muted-foreground italic">
                No provenance on file for this id — not a retrieved corpus snippet.
              </div>
            )}
            {entry && entry !== "loading" && entry !== "missing" && (
              <div className="px-2 pb-2 space-y-1">
                <div className="text-xs text-foreground/90">{entry.headline}</div>
                <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">
                  {entry.source} · {entry.timestamp}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="panel p-2.5">
      <div className="font-mono text-lg" style={{ color }}>
        {value}
      </div>
      <div className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground mt-0.5">
        {label}
      </div>
    </div>
  );
}

function ImpactTile({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="panel p-3">
      <div className="flex items-center justify-between text-muted-foreground">
        <div className="text-[9px] font-mono uppercase tracking-widest">{label}</div>
        <span style={{ color }}>{icon}</span>
      </div>
      <div className="font-mono text-xl mt-1" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

function RerouteCard({
  r,
  isTop,
  selected,
  onSelect,
}: {
  r: ScoredReroute;
  isTop: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const blocked = !r.grade_ok || !r.rank_eligible;
  return (
    <div
      onClick={blocked ? undefined : onSelect}
      className={`relative panel p-4 overflow-hidden ${blocked ? "" : "cursor-pointer transition-shadow"}`}
      style={{
        borderColor: blocked
          ? "color-mix(in oklab, var(--alert-crit) 40%, var(--border))"
          : selected
            ? "var(--cyan)"
            : isTop
              ? "color-mix(in oklab, var(--cyan) 60%, var(--border))"
              : "color-mix(in oklab, var(--alert-low) 40%, var(--border))",
        boxShadow: selected && !blocked ? "0 0 0 1px var(--cyan)" : undefined,
      }}
    >
      {blocked && (
        <div
          className="absolute inset-x-0 top-0 h-0.5"
          style={{ background: "var(--alert-crit)" }}
        />
      )}
      {!blocked && (
        <div
          className="absolute inset-x-0 top-0 h-0.5"
          style={{ background: "var(--gradient-primary)" }}
        />
      )}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-muted-foreground">
          <ShipWheel className="w-3.5 h-3.5" />
          {refineryLabel(r.refinery_id)} · #{r.rank}
        </div>
        {blocked ? (
          <span
            className="text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 rounded"
            style={{
              background: "color-mix(in oklab, var(--alert-crit) 20%, transparent)",
              color: "var(--alert-crit)",
            }}
          >
            <Ban className="w-3 h-3 inline mr-1" /> BLOCKED
          </span>
        ) : (
          <span
            className="text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 rounded"
            style={{
              background: "color-mix(in oklab, var(--alert-low) 20%, transparent)",
              color: "var(--alert-low)",
            }}
          >
            {selected && <CheckCircle2 className="w-3 h-3 inline mr-1" />}
            {selected ? "SELECTED" : isTop ? "TOP ELIGIBLE" : "ELIGIBLE"}
          </span>
        )}
      </div>
      <div className="mt-3 flex items-center gap-2 text-sm">
        <span className="font-mono text-foreground">{supplierLabel(r.supplier)}</span>
        <span className="text-muted-foreground">via</span>
        <span className="font-mono text-cyan">{corridorLabel(r.route)}</span>
      </div>
      <div className="mt-1 text-xs text-muted-foreground flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <Clock className="w-3 h-3" /> Lead time {r.days}d
        </span>
        {!blocked && (
          <span className="font-mono text-[10px]">score {r.scores.total.toFixed(3)}</span>
        )}
      </div>
      {r.reason && <div className="mt-3 text-xs text-muted-foreground italic">{r.reason}</div>}
      {!blocked && (
        <div className="mt-3 pt-3 border-t border-border/60">
          <div className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground">
            True cost · $/bbl
          </div>
          <div className="font-mono text-2xl text-gradient mt-0.5">${r.true_cost.toFixed(2)}</div>
          <div className="mt-2 flex gap-1 text-[10px] font-mono">
            <CostBar label="crude" v={r.cost_breakdown.crude} total={r.true_cost} />
            <CostBar label="war" v={r.cost_breakdown.war_risk_insurance} total={r.true_cost} />
            <CostBar label="det." v={r.cost_breakdown.detour} total={r.true_cost} />
          </div>
        </div>
      )}
    </div>
  );
}

function CostBar({ label, v, total }: { label: string; v: number; total: number }) {
  const pct = total > 0 ? (v / total) * 100 : 0;
  return (
    <div className="flex-1">
      <div className="h-1.5 rounded-full bg-surface-3 overflow-hidden">
        <div
          className="h-full"
          style={{ width: `${pct}%`, background: "var(--gradient-primary)" }}
        />
      </div>
      <div className="mt-1 text-[9px] text-muted-foreground flex justify-between">
        <span>{label}</span>
        <span>${v.toFixed(2)}</span>
      </div>
    </div>
  );
}

const _AUDIT_COLORS: Record<string, string> = {
  approve_reroute: "var(--alert-low)",
  override_assumption: "var(--cyan)",
};

function AuditRow({ entry }: { entry: AuditEntry }) {
  const c = _AUDIT_COLORS[entry.action] ?? "var(--cyan)";
  return (
    <li className="relative">
      <span
        className="absolute -left-[21px] top-1 w-3 h-3 rounded-full border-2"
        style={{ borderColor: c, background: "var(--surface-1)" }}
      />
      <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest">
        <span className="text-muted-foreground">{new Date(entry.ts).toLocaleTimeString()}</span>
        <span style={{ color: c }}>{entry.actor}</span>
        <span className="text-foreground">· {auditActionLabel(entry.action)}</span>
      </div>
      <div className="text-xs text-muted-foreground mt-0.5">{describeAuditEntry(entry)}</div>
    </li>
  );
}

function AssumptionsPanel({
  state,
  onOverride,
}: {
  state: RiskState | null;
  onOverride: () => void;
}) {
  const [local, setLocal] = useState<Assumptions | null>(state?.assumptions ?? null);
  const [preview, setPreview] = useState<Impact | null>(state?.impact ?? null);
  const [simError, setSimError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setLocal(state?.assumptions ?? null);
    setPreview(state?.impact ?? null);
    // Resync only when a new cascade produces a new `assumptions` object
    // (Predict always updates impact + assumptions together); resetting on
    // every unrelated `state` change would clobber an in-progress drag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.assumptions]);

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    [],
  );

  const runSimulate = (assumptions: Assumptions) => {
    api
      .simulate(state?.scenario ?? "what_if", assumptions)
      .then((res) => {
        setPreview(res.impact);
        setSimError(null);
      })
      .catch((err) => setSimError(err instanceof ApiError ? err.message : "Simulate failed"));
  };

  const onDrag = (field: keyof Assumptions, value: number) => {
    if (!local) return;
    const next: Assumptions = { ...local, [field]: { ...local[field], value } };
    setLocal(next);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runSimulate(next), 300);
  };

  const onCommit = (field: keyof Assumptions, value: number) => {
    if (!local) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const next: Assumptions = { ...local, [field]: { ...local[field], value } };
    setLocal(next);
    runSimulate(next);
    api
      .overrideAssumption(next)
      .then(() => onOverride())
      .catch(() => {
        // Best-effort audit write; the slider's own state is unaffected by
        // a failed log (e.g. session expired mid-drag).
      });
  };

  return (
    <div className="col-span-12 lg:col-span-4 panel p-5">
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
          What-If Simulator
        </div>
        <ShieldAlert className="w-4 h-4 text-cyan" />
      </div>
      {!local ? (
        <div className="mt-6 text-xs text-muted-foreground italic">
          No assumptions yet — inject a signal from Mission Control first.
        </div>
      ) : (
        <>
          <div className="mt-4 space-y-4 max-h-[280px] overflow-y-auto pr-1">
            {ASSUMPTION_FIELD_ORDER.map((field) => (
              <AssumptionSliderRow
                key={field}
                field={field}
                entry={local[field]}
                onDrag={(v) => onDrag(field, v)}
                onCommit={(v) => onCommit(field, v)}
              />
            ))}
          </div>
          <div className="mt-4 pt-4 border-t border-border/60 grid grid-cols-2 gap-2">
            <ImpactTile
              icon={<Fuel className="w-4 h-4" />}
              label="Price rise (preview)"
              value={preview ? `+${preview.price_rise_pct.toFixed(2)}%` : "—"}
              color="var(--alert-med)"
            />
            <ImpactTile
              icon={<TrendingDown className="w-4 h-4" />}
              label="GDP Δ (preview)"
              value={preview ? `${preview.gdp_delta_pct.toFixed(2)}%` : "—"}
              color="var(--alert-high)"
            />
          </div>
          <div className="mt-3">
            <div className="flex items-center justify-between text-[9px] font-mono uppercase tracking-widest text-muted-foreground mb-1">
              <span className="flex items-center gap-1">
                <Zap className="w-3 h-3" /> Power stress (preview)
              </span>
              <span className="text-cyan">
                {preview ? `${preview.power_stress_pct.toFixed(1)}%` : "—"}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-surface-3 overflow-hidden">
              <div
                className="h-full"
                style={{
                  width: `${Math.min(100, preview?.power_stress_pct ?? 0)}%`,
                  background: "var(--gradient-primary)",
                }}
              />
            </div>
          </div>
          {simError && <div className="mt-2 text-[10px] text-destructive">{simError}</div>}
          <div className="mt-3 text-[10px] font-mono text-muted-foreground">
            Recomputes via the real Predict model on every drag. Releasing a slider logs an override
            to the audit trail immediately — it's snapshotted onto the approved reroute only when
            Approve is clicked.
          </div>
        </>
      )}
    </div>
  );
}

function AssumptionSliderRow({
  field,
  entry,
  onDrag,
  onCommit,
}: {
  field: keyof Assumptions;
  entry: AssumptionEntry;
  onDrag: (value: number) => void;
  onCommit: (value: number) => void;
}) {
  const meta = ASSUMPTION_LABELS[field];
  const { min, max, step } = assumptionSliderRange(entry);
  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1.5">
        <span className="text-muted-foreground flex items-center gap-1.5">
          {meta.label}
          <TypeTag type={entry.type} src={entry.src} />
        </span>
        <span className="font-mono text-cyan">
          {entry.value.toFixed(meta.decimals)}
          {meta.unit}
        </span>
      </div>
      <Slider
        min={min}
        max={max}
        step={step}
        value={[entry.value]}
        onValueChange={([v]) => onDrag(v)}
        onValueCommit={([v]) => onCommit(v)}
      />
    </div>
  );
}

function TypeTag({ type, src }: { type: AssumptionEntry["type"]; src: string }) {
  if (type === "fact") {
    return (
      <span
        className="text-[8px] font-mono uppercase tracking-widest px-1 py-px rounded"
        style={{
          background: "color-mix(in oklab, var(--alert-low) 20%, transparent)",
          color: "var(--alert-low)",
        }}
        title={src}
      >
        fact
      </span>
    );
  }
  if (type === "estimate") {
    return (
      <span
        className="text-[8px] font-mono uppercase tracking-widest px-1 py-px rounded cursor-help"
        style={{
          background: "color-mix(in oklab, var(--cyan) 20%, transparent)",
          color: "var(--cyan)",
        }}
        title={src}
      >
        estimate
      </span>
    );
  }
  return (
    <span
      className="text-[8px] font-mono uppercase tracking-widest px-1 py-px rounded"
      style={{
        background: "color-mix(in oklab, var(--muted-foreground) 20%, transparent)",
        color: "var(--muted-foreground)",
      }}
      title="Not sourced — internal calibration constant"
    >
      not sourced
    </span>
  );
}

function BacktestPanel() {
  const [data, setData] = useState<BacktestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getBacktest(BACKTEST_CASE_ID)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load backtest");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const merged = useMemo(() => (data ? mergeBacktestTimelines(data) : []), [data]);

  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
            <History className="w-3.5 h-3.5" />
            Backtest · Signal Lead Time
          </div>
          <div className="font-display text-lg font-semibold mt-1">
            {data ? data.label : "One illustrative historical case"}
          </div>
        </div>
        {data && (
          <div className="text-right">
            <div className="font-mono text-3xl font-semibold text-gradient">
              {Math.round(data.validation.signal_lead_hours)}h
            </div>
            <div className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground">
              ~{Math.round(data.validation.signal_lead_hours / 24)} days before Brent priced it in
            </div>
          </div>
        )}
      </div>

      {!data ? (
        <div className="h-64 mt-3 flex items-center justify-center text-xs text-muted-foreground italic">
          {error ?? "Loading backtest…"}
        </div>
      ) : (
        <>
          <div className="h-64 mt-4">
            <ResponsiveContainer>
              <ComposedChart data={merged} margin={{ top: 8, left: -10, right: 8, bottom: 0 }}>
                <XAxis
                  dataKey="ts"
                  tickFormatter={shortDate}
                  stroke="var(--muted-foreground)"
                  fontSize={10}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  yAxisId="score"
                  domain={[0, 100]}
                  stroke="var(--cyan)"
                  fontSize={10}
                  tickLine={false}
                  axisLine={false}
                  width={30}
                />
                <YAxis
                  yAxisId="price"
                  orientation="right"
                  domain={["auto", "auto"]}
                  stroke="var(--alert-med)"
                  fontSize={10}
                  tickLine={false}
                  axisLine={false}
                  width={40}
                />
                <Tooltip
                  labelFormatter={(v) => shortDate(String(v))}
                  contentStyle={{
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <ReferenceLine
                  yAxisId="score"
                  y={data.watch_alert_threshold}
                  stroke="var(--cyan)"
                  strokeOpacity={0.5}
                  strokeDasharray="4 4"
                />
                <ReferenceLine
                  yAxisId="price"
                  y={data.brent_spike_threshold_usd}
                  stroke="var(--alert-med)"
                  strokeOpacity={0.5}
                  strokeDasharray="4 4"
                />
                <Line
                  yAxisId="score"
                  type="monotone"
                  dataKey="score"
                  name="Watch score"
                  stroke="var(--cyan)"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                />
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="price"
                  name="Brent (illustrative)"
                  stroke="var(--alert-med)"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[10px] font-mono text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-0.5" style={{ background: "var(--cyan)" }} />
              Watch crossed {data.watch_alert_threshold}:{" "}
              {data.watch_crossed_at ? shortDate(data.watch_crossed_at) : "never"}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-0.5" style={{ background: "var(--alert-med)" }} />
              Brent crossed ${data.brent_spike_threshold_usd}:{" "}
              {data.brent_crossed_at ? shortDate(data.brent_crossed_at) : "never"}
            </span>
          </div>
          <div className="mt-3 text-[10px] font-mono text-muted-foreground italic">{data.note}</div>
        </>
      )}
    </div>
  );
}
