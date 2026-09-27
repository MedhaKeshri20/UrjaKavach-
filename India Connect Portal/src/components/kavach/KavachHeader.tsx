import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { LogOut, Shield, UserCircle2 } from "lucide-react";
import { useAuth, type Role } from "@/lib/auth";

export function KavachHeader({ mode }: { mode: "official" | "public" }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const otherHref = mode === "official" ? "/public" : "/official";
  const otherLabel = mode === "official" ? "Public Board" : "Official Cockpit";
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = () => {
    logout();
    // Pre-existing bug fixed here: `mode` is "official"|"public" (which page
    // we're on), not a Role ("official"|"citizen") — they collided by
    // coincidence on "official" but "public" was never a valid Role.
    const roleForAuth: Role = mode === "official" ? "official" : "citizen";
    navigate({ to: "/auth", search: { mode: "login", role: roleForAuth } });
  };

  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-md">
      <div className="max-w-[1600px] mx-auto flex items-center justify-between px-6 py-3">
        <Link to="/" className="flex items-center gap-3 group">
          <div
            className="relative w-9 h-9 rounded-md flex items-center justify-center ring-cyan"
            style={{ background: "var(--gradient-primary)" }}
          >
            <Shield className="w-5 h-5 text-background" strokeWidth={2.5} />
          </div>
          <div className="leading-tight">
            <div className="font-display font-semibold text-sm tracking-wide">URJA KAVACH</div>
            <div className="text-[9px] font-mono uppercase tracking-[0.25em] text-muted-foreground">
              Energy Shield · India
            </div>
          </div>
        </Link>

        <nav className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest">
          <div className="hidden md:flex items-center gap-1 mr-3 text-muted-foreground">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span>
              Live ·{" "}
              {new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })} IST
            </span>
          </div>
          <Link
            to={otherHref}
            className="px-3 py-1.5 rounded-md border border-border hover:border-cyan hover:text-cyan transition-colors"
          >
            {otherLabel} →
          </Link>
          <span
            className="hidden sm:inline-block ml-2 px-2 py-1 rounded-md text-[10px]"
            style={{
              background:
                pathname === "/official"
                  ? "color-mix(in oklab, var(--cyan) 15%, transparent)"
                  : "var(--surface-2)",
              color: pathname === "/official" ? "var(--cyan)" : "var(--muted-foreground)",
            }}
          >
            {mode === "official" ? "CLASSIFIED · OFFICIAL USE" : "PUBLIC ADVISORY"}
          </span>

          {user && (
            <div className="flex items-center gap-2 ml-2 pl-3 border-l border-border">
              <div className="hidden md:flex items-center gap-2 px-2 py-1 rounded-md bg-surface-2/60 border border-border">
                <UserCircle2
                  className="w-4 h-4"
                  style={{ color: mode === "official" ? "var(--cyan)" : "var(--alert-low)" }}
                />
                <div className="leading-tight normal-case tracking-normal">
                  <div className="text-[11px] font-sans font-medium text-foreground">
                    {user.email}
                  </div>
                  <div className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground">
                    {user.role === "official" ? "Official" : "Citizen"}
                  </div>
                </div>
              </div>
              <button
                onClick={onLogout}
                title="Sign out"
                className="flex items-center gap-1 px-2 py-1.5 rounded-md border border-border hover:border-destructive hover:text-destructive transition-colors"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Exit</span>
              </button>
            </div>
          )}
        </nav>
      </div>
    </header>
  );
}
