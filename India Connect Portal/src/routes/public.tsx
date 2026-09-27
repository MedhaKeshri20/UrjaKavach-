import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { Info, Megaphone, ShieldCheck, Sparkles, WifiOff } from "lucide-react";
import { KavachHeader } from "@/components/kavach/KavachHeader";
import { bandColor } from "@/lib/kavach-data";
import { corridorLabel } from "@/lib/live-derive";
import { useRiskState } from "@/hooks/useRiskState";
import { useReserveHistory } from "@/hooks/useReserveHistory";
import { api, ApiError, type PublicStatus } from "@/lib/api";
import { RequireRole } from "@/components/kavach/RequireRole";

type StatusTone = "low" | "medium" | "high";

// backend/api/routes.py's `_level_for` — the only three values `status` can
// take. Mapped here to the same "low/medium/high" tone vocabulary the rest
// of the app already uses (bandColor), not a fourth invented scale.
const STATUS_TONE: Record<string, StatusTone> = {
  Normal: "low",
  Elevated: "medium",
  Shortage: "high",
};

const STATUS_LABEL: Record<string, string> = {
  Normal: "SUPPLY STABLE",
  Elevated: "SUPPLY UNDER WATCH",
  Shortage: "SUPPLY DISRUPTED",
};

function describePublicAction(entry: PublicStatus["action_feed"][number]): string {
  if (entry.action === "approve_reroute") {
    return entry.route
      ? `Officials approved an alternate supply route via ${corridorLabel(entry.route)}.`
      : "Officials approved an alternate supply route.";
  }
  return "Officials updated the response plan.";
}

export const Route = createFileRoute("/public")({
  head: () => ({
    meta: [
      { title: "Public Assurance Board — Urja Kavach" },
      {
        name: "description",
        content:
          "India's fuel supply status in plain language. Reserves, prices, and advisories from official sources.",
      },
      { property: "og:title", content: "India Fuel Supply · Public Board" },
      {
        property: "og:description",
        content: "Fuel supply is stable. See reserves, prices, and current advisories.",
      },
    ],
  }),
  component: () => (
    <RequireRole role="citizen">
      <PublicBoard />
    </RequireRole>
  ),
});

function PublicBoard() {
  const { state, status } = useRiskState();
  const reserveHistory = useReserveHistory(state);
  const [publicStatus, setPublicStatus] = useState<PublicStatus | null>(null);
  const [publicStatusError, setPublicStatusError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .publicStatus()
      .then((res) => {
        if (cancelled) return;
        setPublicStatus(res);
        setPublicStatusError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setPublicStatusError(err instanceof ApiError ? err.message : "Failed to load status");
      });
    return () => {
      cancelled = true;
    };
    // Re-fetch whenever a new cascade completes so the badge/copy/action
    // feed track the latest signal, not just the WS-pushed RiskState fields.
  }, [state?.updated_at]);

  const tone: StatusTone | null = publicStatus ? STATUS_TONE[publicStatus.status] : null;
  const daysCover = state?.reserve?.days_cover ?? null;

  return (
    <div className="min-h-screen bg-cockpit text-foreground">
      <KavachHeader mode="public" />

      {status === "offline" && (
        <div className="bg-destructive/10 border-b border-destructive/30 text-destructive text-[11px] font-mono uppercase tracking-widest px-4 py-2 flex items-center gap-2">
          <WifiOff className="w-3.5 h-3.5" />
          Backend offline —{" "}
          {state ? "showing last known state, reconnecting…" : "no live state received yet"}
        </div>
      )}

      <main className="max-w-[1200px] mx-auto px-4 md:px-6 py-8 space-y-8">
        {/* Reassurance hero */}
        <section className="panel-glow p-6 md:p-10 relative overflow-hidden">
          <div
            className="absolute inset-x-0 top-0 h-px"
            style={{ background: "var(--gradient-primary)" }}
          />
          <div
            className="absolute -right-24 -top-24 w-96 h-96 rounded-full blur-3xl opacity-30"
            style={{ background: "var(--gradient-primary)" }}
          />
          <div className="relative grid md:grid-cols-2 gap-8 items-center">
            <div>
              <div
                className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-[10px] font-mono uppercase tracking-widest"
                style={{
                  background: tone
                    ? `color-mix(in oklab, ${bandColor[tone]} 15%, transparent)`
                    : "color-mix(in oklab, var(--muted-foreground) 15%, transparent)",
                  color: tone ? bandColor[tone] : "var(--muted-foreground)",
                }}
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                {publicStatus ? STATUS_LABEL[publicStatus.status] : "CHECKING STATUS…"}
              </div>
              <h1 className="mt-4 font-display text-4xl md:text-5xl font-semibold leading-tight tracking-tight">
                India&apos;s fuel supply, <br />
                <span className="text-gradient">explained simply.</span>
              </h1>
              <p className="mt-4 text-base text-muted-foreground leading-relaxed max-w-md">
                {publicStatus?.message ??
                  (publicStatusError
                    ? "Status is temporarily unavailable — please check back shortly."
                    : "Checking current status…")}
              </p>
              <div className="mt-6 flex flex-wrap gap-2 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                <span className="px-2.5 py-1 rounded border border-border">
                  Updated{" "}
                  {publicStatus
                    ? new Date(publicStatus.updated_at).toLocaleTimeString("en-IN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "—"}{" "}
                  IST
                </span>
                <span className="px-2.5 py-1 rounded border border-border">
                  Source: MoPNG · PPAC
                </span>
              </div>
            </div>

            {/* Reserves visual */}
            <div className="panel p-6">
              <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                Strategic reserve · days of cover
              </div>
              <div className="flex items-baseline gap-3 mt-2">
                <div className="font-mono text-6xl font-semibold text-gradient">
                  {daysCover !== null ? daysCover.toFixed(1) : "—"}
                </div>
                <div className="text-sm text-muted-foreground">days</div>
              </div>
              <div className="mt-4 space-y-3">
                {daysCover !== null && (
                  <Bar
                    label="Strategic Petroleum Reserve"
                    value={daysCover}
                    max={30}
                    color="var(--cyan)"
                  />
                )}
                <Bar
                  label="Commercial refinery stock (illustrative)"
                  value={65}
                  max={90}
                  color="var(--alert-low)"
                />
              </div>
              <div className="mt-4 text-xs text-muted-foreground flex items-start gap-2">
                <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                India refines much more crude than it consumes daily. Even under stress, disruptions
                take weeks to reach the pump.
              </div>
            </div>
          </div>
        </section>

        {/* Conservation guidance — real, from GET /public/status's conservation_plan */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
              What you can do
            </div>
          </div>
          {publicStatus ? (
            <div className="grid md:grid-cols-3 gap-4">
              {publicStatus.conservation_plan.map((tip, i) => (
                <PublicCard key={i} icon={<Sparkles />} headline={tip} tone={tone ?? "low"} />
              ))}
            </div>
          ) : (
            <div className="panel p-5 text-xs text-muted-foreground italic">
              {publicStatusError ?? "Loading guidance…"}
            </div>
          )}
        </section>

        {/* Recent official actions — real, from GET /public/status's action_feed
            (last 5 audit-derived rows), phrased in plain language for a public
            audience rather than exposing raw action/actor names. */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
              Recent official actions
            </div>
          </div>
          {publicStatus && publicStatus.action_feed.length > 0 ? (
            <div className="space-y-3">
              {publicStatus.action_feed.map((entry, i) => (
                <div key={i} className="panel p-4 flex items-center gap-3">
                  <Megaphone className="w-4 h-4 shrink-0 text-cyan" />
                  <div className="flex-1 text-sm text-foreground/90">
                    {describePublicAction(entry)}
                  </div>
                  <div className="text-[10px] font-mono text-muted-foreground shrink-0">
                    {new Date(entry.ts).toLocaleTimeString("en-IN", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="panel p-5 text-xs text-muted-foreground italic">
              {publicStatus ? "No official actions logged yet." : (publicStatusError ?? "Loading…")}
            </div>
          )}
        </section>

        {/* Reserve trend chart — real, session-observed only */}
        <section className="panel p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
                Reserve trend
              </div>
              <div className="font-display text-xl font-semibold mt-1">
                Strategic days-of-cover, this session
              </div>
            </div>
          </div>
          <div className="h-56">
            {reserveHistory.length > 1 ? (
              <ResponsiveContainer>
                <AreaChart
                  data={reserveHistory}
                  margin={{ top: 10, left: -10, right: 10, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="pubFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.72 0.17 220)" stopOpacity={0.6} />
                      <stop offset="100%" stopColor="oklch(0.72 0.17 220)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="ts"
                    stroke="var(--muted-foreground)"
                    fontSize={10}
                    tickLine={false}
                    axisLine={false}
                    hide
                  />
                  <YAxis
                    stroke="var(--muted-foreground)"
                    fontSize={10}
                    tickLine={false}
                    axisLine={false}
                    domain={["auto", "auto"]}
                  />
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
                    fill="url(#pubFill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground italic">
                No trend yet this session — reserve data appears after the first signal is
                processed.
              </div>
            )}
          </div>
        </section>

        <p className="text-center text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground pt-4">
          If you have a question, ask a helpline — not a rumor. · MoPNG helpline · 1906
        </p>
      </main>
    </div>
  );
}

function Bar({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono" style={{ color }}>
          {value.toFixed(1)} days
        </span>
      </div>
      <div className="h-2 rounded-full bg-surface-3 overflow-hidden relative">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: color, boxShadow: `0 0 12px ${color}` }}
        />
        <div
          className="absolute inset-0 animate-sweep w-1/4"
          style={{
            background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent)",
          }}
        />
      </div>
    </div>
  );
}

function PublicCard({
  icon,
  headline,
  tone,
}: {
  icon: React.ReactNode;
  headline: string;
  tone: StatusTone;
}) {
  const color = bandColor[tone];
  return (
    <div className="panel p-5 relative overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-0.5" style={{ background: color }} />
      <div className="flex items-center gap-3">
        <span style={{ color }}>{icon}</span>
        <div className="text-sm font-medium leading-relaxed">{headline}</div>
      </div>
    </div>
  );
}
