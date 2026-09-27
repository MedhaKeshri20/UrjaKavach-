// Client-managed session. The backend returns the JWT in the login/register
// JSON body (not an HttpOnly cookie), so we store it in a cookie the client
// sets — that way the API client can read the token for the Authorization
// header. Note: this cookie is readable by JS (same exposure as
// localStorage) — a known, already-accepted trade-off in this codebase (see
// frontend/lib/session.ts, which made the same call: "fine for a hackathon
// demo, not for real secrets"). Carried forward explicitly here, not
// silently — see India Connect Portal/spec.md Phase 2, decision #2.
//
// Deliberately NOT reusing the old fake AuthProvider's localStorage
// (kavach.session.v1/kavach.users.v1) — no plaintext passwords are ever
// stored anywhere in this file; the only thing persisted is a real,
// backend-issued JWT.

import type { Role } from "@/types/auth";

export const SESSION_COOKIE = "uk_session";

export interface Session {
  token: string;
  role: Role;
  email: string;
}

export function saveSession(s: Session) {
  const value = encodeURIComponent(JSON.stringify(s));
  // 12h, path=/ so every route sees it. SameSite=Lax is fine for same-origin.
  document.cookie = `${SESSION_COOKIE}=${value}; path=/; max-age=${12 * 60 * 60}; SameSite=Lax`;
}

export function readSession(): Session | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((row) => row.startsWith(`${SESSION_COOKIE}=`));
  if (!match) return null;
  try {
    return JSON.parse(decodeURIComponent(match.split("=").slice(1).join("=")));
  } catch {
    return null;
  }
}

export function clearSession() {
  document.cookie = `${SESSION_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
}
