import { createFileRoute, Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import {
  Shield,
  Building2,
  Users,
  Loader2,
  AlertCircle,
  ArrowRight,
  ShieldCheck,
  Lock,
  Mail,
} from "lucide-react";
import { useAuth, type Role } from "@/lib/auth";

type Search = { role?: Role; mode?: "login" | "register"; redirect?: string };

export const Route = createFileRoute("/auth")({
  validateSearch: (s: Record<string, unknown>): Search => ({
    role: s.role === "official" || s.role === "citizen" ? s.role : undefined,
    mode: s.mode === "register" ? "register" : "login",
    redirect: typeof s.redirect === "string" ? s.redirect : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Sign in · Urja Kavach" },
      {
        name: "description",
        content: "Verified access for officials and citizens of India's energy shield.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AuthPage,
});

function AuthPage() {
  const search = useSearch({ from: "/auth" }) as Search;
  const navigate = useNavigate();
  const { login, register } = useAuth();

  const [role, setRole] = useState<Role>(search.role ?? "citizen");
  const [mode, setMode] = useState<"login" | "register">(search.mode ?? "login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // form state — kept to exactly what the backend accepts (backend/auth/schemas.py's
  // RegisterRequest/LoginRequest are extra="forbid": email + password + role only).
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const roleTheme =
    role === "official"
      ? {
          color: "var(--cyan)",
          label: "Official Cockpit",
          icon: <Building2 className="w-5 h-5" />,
          subtitle: "Command cockpit · every action audit-logged",
        }
      : {
          color: "var(--alert-low)",
          label: "Public Board",
          icon: <Users className="w-5 h-5" />,
          subtitle: "Plain-language advisories · open to every citizen",
        };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user =
        mode === "login" ? await login(email, password) : await register(email, password, role);
      const target = search.redirect || (user.role === "official" ? "/official" : "/public");
      navigate({ to: target as "/official" | "/public" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-hero grid-bg text-foreground flex flex-col">
      <div
        className="pointer-events-none fixed -top-40 -right-40 w-[600px] h-[600px] rounded-full blur-3xl opacity-25 animate-float-slow"
        style={{ background: "var(--gradient-primary)" }}
      />
      <div
        className="pointer-events-none fixed -bottom-40 -left-40 w-[500px] h-[500px] rounded-full blur-3xl opacity-20"
        style={{ background: "var(--gradient-alert)" }}
      />

      <header className="relative z-10 px-6 md:px-12 py-5 flex items-center justify-between">
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
              Energy Shield · India
            </div>
          </div>
        </Link>
        <Link
          to="/"
          className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground hover:text-cyan"
        >
          ← Back to overview
        </Link>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center px-4 py-8">
        <div className="w-full max-w-5xl grid lg:grid-cols-5 gap-8">
          {/* Left: role differentiation */}
          <aside className="lg:col-span-2 space-y-4">
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-muted-foreground">
              Choose your access
            </div>
            <h1 className="font-display text-3xl md:text-4xl font-semibold leading-tight">
              Two doors,
              <br />
              <span className="text-gradient">one shield.</span>
            </h1>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Urja Kavach serves two audiences. Pick the door that matches you — each unlocks a
              different view of India's energy resilience.
            </p>

            <div className="space-y-3 pt-2">
              <RoleTile
                active={role === "official"}
                onClick={() => setRole("official")}
                icon={<Building2 className="w-5 h-5" />}
                title="I'm an Official"
                subtitle="MoPNG, MEA, PSU refiner, or defence liaison"
                bullets={[
                  "Role is self-declared at sign-up, no domain gate",
                  "Live cockpit + what-if simulator",
                  "Approve reroutes · every action audit-logged",
                ]}
                accent="var(--cyan)"
              />
              <RoleTile
                active={role === "citizen"}
                onClick={() => setRole("citizen")}
                icon={<Users className="w-5 h-5" />}
                title="I'm a Citizen"
                subtitle="Any resident of India — no verification needed"
                bullets={[
                  "Plain-language advisories",
                  "Fuel supply · price outlook",
                  "Reserve days-of-cover",
                ]}
                accent="var(--alert-low)"
              />
            </div>
          </aside>

          {/* Right: form */}
          <section className="lg:col-span-3 panel-glow p-6 md:p-8 relative overflow-hidden">
            <div
              className="absolute inset-x-0 top-0 h-px"
              style={{ background: "var(--gradient-primary)" }}
            />
            <div className="flex items-center gap-3 mb-1">
              <div
                className="w-9 h-9 rounded-md flex items-center justify-center"
                style={{
                  background: `color-mix(in oklab, ${roleTheme.color} 15%, transparent)`,
                  color: roleTheme.color,
                }}
              >
                {roleTheme.icon}
              </div>
              <div>
                <div className="font-display text-lg font-semibold">{roleTheme.label}</div>
                <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                  {roleTheme.subtitle}
                </div>
              </div>
            </div>

            {/* Mode tabs */}
            <div className="mt-6 inline-flex p-1 rounded-md border border-border bg-surface-2/60 text-xs font-mono uppercase tracking-widest">
              <button
                type="button"
                onClick={() => setMode("login")}
                className={`px-4 py-1.5 rounded ${mode === "login" ? "bg-surface-3 text-foreground" : "text-muted-foreground"}`}
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => setMode("register")}
                className={`px-4 py-1.5 rounded ${mode === "register" ? "bg-surface-3 text-foreground" : "text-muted-foreground"}`}
              >
                Register
              </button>
            </div>

            <form onSubmit={onSubmit} className="mt-6 space-y-4">
              <Field label="Email" icon={<Mail className="w-4 h-4" />}>
                <input
                  required
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={role === "official" ? "officer@example.gov.in" : "you@example.com"}
                  className="w-full bg-transparent outline-none text-sm placeholder:text-muted-foreground/60"
                />
              </Field>

              <Field label="Password" icon={<Lock className="w-4 h-4" />}>
                <input
                  required
                  type="password"
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Minimum 6 characters"
                  className="w-full bg-transparent outline-none text-sm placeholder:text-muted-foreground/60"
                />
              </Field>

              {mode === "register" && (
                <div className="flex items-start gap-2 text-[11px] text-muted-foreground p-3 rounded-md border border-cyan/25 bg-cyan/5">
                  <ShieldCheck className="w-3.5 h-3.5 mt-0.5 shrink-0 text-cyan" />
                  <span>
                    The <span className="font-mono text-cyan">{role}</span> role is self-declared at
                    sign-up — there is no email domain check. What keeps this honest: every
                    official-only action (approving a reroute, overriding an assumption) is written
                    to a permanent audit log against your account, not a client-supplied name.
                  </span>
                </div>
              )}

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
                disabled={loading}
                className="w-full mt-2 flex items-center justify-center gap-2 py-3 rounded-md font-mono uppercase tracking-widest text-xs text-background disabled:opacity-60 transition-opacity"
                style={{ background: "var(--gradient-primary)", boxShadow: "var(--shadow-glow)" }}
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <ArrowRight className="w-4 h-4" />
                )}
                {mode === "login" ? "Enter platform" : `Create ${role} account`}
              </button>

              <div className="text-center text-[11px] text-muted-foreground pt-1">
                {mode === "login" ? (
                  <>
                    New here?{" "}
                    <button
                      type="button"
                      onClick={() => setMode("register")}
                      className="text-cyan hover:underline"
                    >
                      Create an account
                    </button>
                  </>
                ) : (
                  <>
                    Already registered?{" "}
                    <button
                      type="button"
                      onClick={() => setMode("login")}
                      className="text-cyan hover:underline"
                    >
                      Sign in
                    </button>
                  </>
                )}
              </div>
            </form>
          </section>
        </div>
      </main>

      <footer className="relative z-10 py-4 text-center text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
        Backend-verified sign-in · JWT session kept in this browser only
      </footer>
    </div>
  );
}

function RoleTile({
  active,
  onClick,
  icon,
  title,
  subtitle,
  bullets,
  accent,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  bullets: string[];
  accent: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full text-left panel p-4 transition-all relative overflow-hidden ${active ? "panel-glow" : "hover:border-cyan/40"}`}
      style={active ? { borderColor: accent } : undefined}
    >
      <div
        className="absolute left-0 top-0 h-full w-1"
        style={{ background: accent, opacity: active ? 1 : 0.4 }}
      />
      <div className="flex items-center gap-3">
        <div
          className="w-9 h-9 rounded-md flex items-center justify-center"
          style={{ background: `color-mix(in oklab, ${accent} 15%, transparent)`, color: accent }}
        >
          {icon}
        </div>
        <div>
          <div className="font-display text-sm font-semibold">{title}</div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
            {subtitle}
          </div>
        </div>
      </div>
      <ul className="mt-3 space-y-1 text-[11px] text-muted-foreground">
        {bullets.map((b) => (
          <li key={b} className="flex items-center gap-2">
            <span className="w-1 h-1 rounded-full" style={{ background: accent }} />
            {b}
          </li>
        ))}
      </ul>
    </button>
  );
}

function Field({
  label,
  icon,
  children,
}: {
  label: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-1.5">
        {label}
      </div>
      <div className="flex items-center gap-2 px-3 py-2.5 rounded-md border border-border bg-surface-2/60 focus-within:border-cyan/60 focus-within:ring-1 focus-within:ring-cyan/40 transition-colors">
        <span className="text-muted-foreground">{icon}</span>
        {children}
      </div>
    </label>
  );
}
