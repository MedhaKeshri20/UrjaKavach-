import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Shield, Zap, Loader2, AlertCircle, Radar } from "lucide-react";
import { useRiskState } from "@/hooks/useRiskState";
import { api, ApiError } from "@/lib/api";
import { bandColor } from "@/lib/kavach-data";
import { CORRIDOR_LABELS, corridorLabel, nationalBand, nationalScore } from "@/lib/live-derive";

export const Route = createFileRoute("/mission")({
  head: () => ({
    meta: [
      { title: "Mission Control — Urja Kavach" },
      {
        name: "description",
        content:
          "Inject a live signal and watch the Watch → Predict → Recommend → Advise cascade run end to end.",
      },
    ],
  }),
  component: MissionControl,
});

const CORRIDOR_IDS = Object.keys(CORRIDOR_LABELS);

function MissionControl() {
  const { state, status } = useRiskState();
  const navigate = useNavigate();
  const [corridor, setCorridor] = useState(CORRIDOR_IDS[0]);
  const [headline, setHeadline] = useState("Missile strike closes Strait of Hormuz shipping lane");
  const [severity, setSeverity] = useState(0.6);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const launch = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLaunching(true);
    try {
      await api.injectSignal({ corridor, headline, severity, id: `sig_${Date.now()}` });
      navigate({ to: "/official" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Launch failed — is the backend running?");
      setLaunching(false);
    }
  };

  const statusLabel =
    status === "live"
      ? "Backend live"
      : status === "connecting"
        ? "Connecting…"
        : "Backend offline";
  const statusDot =
    status === "live"
      ? "bg-emerald-400 animate-pulse"
      : status === "connecting"
        ? "bg-amber-400 animate-pulse"
        : "bg-red-500";

  return (
    <div className="min-h-screen bg-hero grid-bg text-foreground">
      <header className="px-6 md:px-12 py-5 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-md flex items-center justify-center ring-cyan"
            style={{ background: "var(--gradient-primary)" }}
          >
            <Shield className="w-5 h-5 text-background" strokeWidth={2.5} />
          </div>
          <div>
            <div className="font-display font-semibold text-sm tracking-wide">URJA KAVACH</div>
            <div className="text-[9px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
              Mission Control
            </div>
          </div>
        </Link>
        <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
          <span className={`w-1.5 h-1.5 rounded-full ${statusDot}`} />
          {statusLabel}
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-10">
        <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-cyan mb-3">
          Command center
        </div>
        <h1 className="font-display text-4xl font-semibold mb-2">Inject a live signal</h1>
        <p className="text-muted-foreground mb-8">
          This triggers the real Watch → Predict → Recommend → Advise cascade on the backend and
          pushes the result to every connected panel over the WebSocket — no page reload.
        </p>

        {state && (
          <div className="panel p-5 mb-8 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                Current national risk
              </div>
              <div
                className="font-mono text-3xl mt-1"
                style={{ color: bandColor[nationalBand(state)] }}
              >
                {nationalScore(state)}
              </div>
            </div>
            <Radar className="w-6 h-6 text-cyan" />
          </div>
        )}

        <form onSubmit={launch} className="panel-glow p-6 space-y-5">
          <div>
            <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2 block">
              Corridor
            </label>
            <select
              value={corridor}
              onChange={(e) => setCorridor(e.target.value)}
              className="w-full bg-surface-2/60 border border-border rounded-md px-3 py-2.5 text-sm"
            >
              {CORRIDOR_IDS.map((id) => (
                <option key={id} value={id} className="bg-surface-2">
                  {corridorLabel(id)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2 block">
              Headline
            </label>
            <input
              required
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              className="w-full bg-surface-2/60 border border-border rounded-md px-3 py-2.5 text-sm outline-none focus:border-cyan/60"
            />
          </div>

          <div>
            <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2 flex items-center justify-between">
              <span>Severity</span>
              <span className="text-cyan">{severity.toFixed(2)}</span>
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={severity}
              onChange={(e) => setSeverity(Number(e.target.value))}
              className="w-full"
            />
          </div>

          {error && (
            <div
              className="flex items-start gap-2 text-xs p-3 rounded-md border"
              style={{
                borderColor: "color-mix(in oklab, var(--alert-crit) 40%, transparent)",
                background: "color-mix(in oklab, var(--alert-crit) 8%, transparent)",
                color: "var(--alert-crit)",
              }}
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={launching}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-md font-mono uppercase tracking-widest text-xs text-background disabled:opacity-60 transition-opacity"
            style={{ background: "var(--gradient-primary)", boxShadow: "var(--shadow-glow)" }}
          >
            {launching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            {launching ? "Launching cascade…" : "Inject signal"}
          </button>
        </form>

        <div className="mt-6 flex gap-4 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
          <Link to="/official" className="hover:text-cyan">
            → Official cockpit
          </Link>
          <Link to="/public" className="hover:text-cyan">
            → Public board
          </Link>
        </div>
      </main>
    </div>
  );
}
