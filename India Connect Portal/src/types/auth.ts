// Mirrors backend/auth/schemas.py exactly — register/login return the JWT in
// the JSON body as `access_token` (no HttpOnly cookie support server-side),
// plus role/email and a dashboard hint. See lib/session.ts for how the token
// is then stored client-side.

export type Role = "citizen" | "official";

export interface TokenResponse {
  access_token: string;
  token_type: string; // "bearer"
  role: Role;
  email: string;
  dashboard: string; // "/official" | "/citizen"
}

export interface CurrentUser {
  id: number;
  email: string;
  role: Role;
}
