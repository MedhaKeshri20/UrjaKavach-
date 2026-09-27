// Real JWT auth against the backend (backend/auth/routes.py). Replaces the
// old fake, client-only AuthProvider that stored plaintext passwords in
// localStorage — see India Connect Portal/spec.md Phase 2. No password ever
// touches this file; only a backend-issued token does (via lib/session.ts).

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { clearSession, readSession, saveSession } from "@/lib/session";
import type { Role } from "@/types/auth";

export type { Role };

export interface KavachUser {
  email: string;
  role: Role;
}

interface AuthCtx {
  user: KavachUser | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<KavachUser>;
  register: (email: string, password: string, role: Role) => Promise<KavachUser>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<KavachUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const session = readSession();
    if (!session) {
      setReady(true);
      return;
    }
    // Trust the cookie optimistically so the UI isn't blank while verifying,
    // but confirm server-side the token is still valid (spec.md Phase 2: a
    // stale/expired/revoked token must not silently look "logged in" — on a
    // real 401 we clear it, rather than trusting a client-only claim).
    setUser({ email: session.email, role: session.role });
    api
      .me()
      .then((me) => {
        if (cancelled) return;
        setUser({ email: me.email, role: me.role });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          clearSession();
          setUser(null);
        }
        // Any other failure (offline/network blip) — keep the optimistic
        // session rather than punishing the user for a transient backend
        // outage; RequireRole still gates real actions server-side anyway.
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login: AuthCtx["login"] = async (email, password) => {
    const tok = await api.login(email, password);
    const u: KavachUser = { email: tok.email, role: tok.role };
    saveSession({ token: tok.access_token, ...u });
    setUser(u);
    return u;
  };

  const register: AuthCtx["register"] = async (email, password, role) => {
    const tok = await api.register(email, password, role);
    const u: KavachUser = { email: tok.email, role: tok.role };
    saveSession({ token: tok.access_token, ...u });
    setUser(u);
    return u;
  };

  const logout = () => {
    clearSession();
    setUser(null);
  };

  return <Ctx.Provider value={{ user, ready, login, register, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth must be used inside AuthProvider");
  return c;
}
