import { createFileRoute, Link } from "@tanstack/react-router";
import { Shield, Radar, Building2, Users, ArrowRight, Activity } from "lucide-react";
import { demoState } from "@/lib/demo-state";

export const Route = createFileRoute("/")({
  component: Landing,
});

function Landing() {
  const s = demoState;
  return (
    <div className="min-h-screen bg-hero text-foreground overflow-x-hidden">
      {/* Ambient grid + orbs */}
      <div className="pointer-events-none fixed inset-0 opacity-40 grid-bg" />
      <div
        className="pointer-events-none fixed -top-40 -right-40 w-[600px] h-[600px] rounded-full blur-3xl opacity-30 animate-float-slow"
        style={{ background: "var(--gradient-primary)" }}
      />
      <div
        className="pointer-events-none fixed -bottom-40 -left-40 w-[500px] h-[500px] rounded-full blur-3xl opacity-25"
        style={{ background: "var(--gradient-alert)" }}
      />

      <header className="relative z-10 flex items-center justify-between px-6 md:px-12 py-5">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-md flex items-center justify-center ring-cyan"
            style={{ background: "var(--gradient-primary)" }}
          >
            <Shield className="w-5 h-5 text-background" strokeWidth={2.5} />
          </div>
          <div>
            <div className="font-display font-semibold tracking-wide">URJA KAVACH</div>
            <div className="text-[9px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
              Energy Shield · India
            </div>
          </div>
        </div>
        <div className="hidden md:flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          ET AI Hackathon 2026 · System Nominal
        </div>
      </header>

      <main className="relative z-10 max-w-[1400px] mx-auto px-6 md:px-12 pt-12 md:pt-20 pb-24">
        {/* Hero */}
        <div className="grid lg:grid-cols-12 gap-10 items-center">
          <div className="lg:col-span-7">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-cyan/30 bg-cyan/5 text-[10px] font-mono uppercase tracking-[0.25em] text-cyan mb-6">
              <Activity className="w-3 h-3" />
              Four-agent AI cascade · Watch → Predict → Recommend → Advise
            </div>
            <h1 className="font-display text-5xl md:text-7xl font-semibold leading-[1.02] tracking-tight">
              India's <span className="text-gradient">energy shield</span>,<br />
              running in real time.
            </h1>
            <p className="mt-6 text-lg text-muted-foreground max-w-xl leading-relaxed">
              A single AI-driven cockpit that watches every crude corridor, predicts cascading
              impact on GDP, inflation, and power, recommends grade-eligible reroutes, and turns it
              all into calm, plain-language advisories for 1.4 billion citizens.
            </p>

            <div className="mt-10 grid sm:grid-cols-2 gap-4">
              <PortalCard
                to="/official"
                icon={<Building2 className="w-5 h-5" />}
                eyebrow="For officials"
                title="Enter Command Cockpit"
                sub="Live risk gauge · corridor map · what-if simulator · reroute approvals · audit trail"
                accent="var(--cyan)"
              />
              <PortalCard
                to="/public"
                icon={<Users className="w-5 h-5" />}
                eyebrow="For citizens"
                title="Public Assurance Board"
                sub="Fuel supply status · price outlook · reserve cover · plain-language advisories"
                accent="var(--alert-low)"
              />
            </div>

            <Link
              to="/mission"
              className="mt-4 inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-muted-foreground hover:text-cyan transition-colors"
            >
              <Activity className="w-3 h-3" />
              Or jump straight to Mission Control — inject a live signal{" "}
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>

          {/* Live status pod */}
          <div className="lg:col-span-5">
            <div className="panel-glow p-6 md:p-8 relative overflow-hidden">
              <div
                className="absolute inset-x-0 top-0 h-px"
                style={{ background: "var(--gradient-primary)" }}
              />
              <div className="flex items-center justify-between mb-6">
                <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
                  NATIONAL STATE · T-LIVE
                </div>
                <Radar className="w-4 h-4 text-cyan animate-pulse" />
              </div>
              <div className="flex items-baseline gap-3">
                <div
                  className="font-mono text-7xl font-semibold"
                  style={{ color: "var(--alert-high)" }}
                >
                  {s.national_score}
                </div>
                <div
                  className="text-sm font-mono uppercase tracking-widest"
                  style={{ color: "var(--alert-high)" }}
                >
                  Elevated
                </div>
              </div>
              <div className="mt-2 text-sm text-muted-foreground">
                Composite risk across 4 corridors, 5 refineries, and SPR draw.
              </div>

              <div className="mt-6 grid grid-cols-3 gap-3 text-center">
                <Stat label="Corridors watched" value="4" />
                <Stat label="Refineries" value="5" />
                <Stat label="Vessels tracked" value="127" />
              </div>

              <div className="mt-6 space-y-2">
                {s.corridors.slice(0, 3).map((c) => (
                  <div
                    key={c.id}
                    className="flex items-center justify-between px-3 py-2 rounded-md bg-surface-2/60 border border-border"
                  >
                    <div className="flex items-center gap-2 text-sm">
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{
                          background: `var(--alert-${c.band === "critical" ? "crit" : c.band})`,
                        }}
                      />
                      {c.name}
                    </div>
                    <div
                      className="font-mono text-sm"
                      style={{ color: `var(--alert-${c.band === "critical" ? "crit" : c.band})` }}
                    >
                      {c.score}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Agent cascade */}
        <div className="mt-24">
          <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground mb-6">
            The cascade
          </div>
          <div className="grid md:grid-cols-4 gap-4">
            {[
              {
                title: "WATCH",
                desc: "RAG + LLM ingests headlines, AIS tracks, dark-ship anomalies. Scores corridor risk with confidence bands.",
                tag: "Signals",
              },
              {
                title: "PREDICT",
                desc: "Domino model computes GDP delta, inflation, FX, power stress, and SPR days remaining.",
                tag: "Impact",
              },
              {
                title: "RECOMMEND",
                desc: "Grade-eligibility gate + true-cost ranking (crude + war-risk + detour). No wrong-oil reroutes.",
                tag: "Action",
              },
              {
                title: "ADVISE",
                desc: "Alarm-language-scored advisories for citizens. Officially approvable, always audited.",
                tag: "Voice",
              },
            ].map((a, i) => (
              <div key={a.title} className="panel p-5 relative">
                <div className="text-[10px] font-mono text-muted-foreground">STEP 0{i + 1}</div>
                <div className="mt-2 font-display text-xl font-semibold text-gradient">
                  {a.title}
                </div>
                <div className="mt-2 text-sm text-muted-foreground leading-relaxed">{a.desc}</div>
                <div className="mt-4 text-[10px] font-mono uppercase tracking-widest text-cyan">
                  {a.tag}
                </div>
                {i < 3 && (
                  <ArrowRight className="hidden md:block absolute -right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-cyan/40" />
                )}
              </div>
            ))}
          </div>
        </div>
      </main>

      <footer className="relative z-10 border-t border-border/60 py-6 px-6 md:px-12 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
        Urja Kavach v1.3 · Built on the frozen contract · ET AI Hackathon 2026
      </footer>
    </div>
  );
}

function PortalCard({
  to,
  icon,
  eyebrow,
  title,
  sub,
  accent,
}: {
  to: string;
  icon: React.ReactNode;
  eyebrow: string;
  title: string;
  sub: string;
  accent: string;
}) {
  return (
    <Link
      to={to}
      className="group panel p-5 hover:panel-glow transition-all block relative overflow-hidden"
    >
      <div
        className="absolute top-0 left-0 h-full w-1"
        style={{ background: accent, opacity: 0.7 }}
      />
      <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.25em] text-muted-foreground">
        <span style={{ color: accent }}>{icon}</span>
        {eyebrow}
      </div>
      <div className="mt-3 font-display text-lg font-semibold group-hover:text-cyan transition-colors">
        {title}
      </div>
      <div className="mt-2 text-xs text-muted-foreground leading-relaxed">{sub}</div>
      <div
        className="mt-4 flex items-center gap-1 text-[10px] font-mono uppercase tracking-widest"
        style={{ color: accent }}
      >
        Enter <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-1" />
      </div>
    </Link>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel p-3">
      <div className="font-mono text-2xl font-semibold text-gradient">{value}</div>
      <div className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground mt-1">
        {label}
      </div>
    </div>
  );
}
