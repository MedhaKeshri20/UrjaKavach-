# SPEC — India Connect Portal becomes the Urja Kavach frontend

> **Status: decision record + build plan.** Supersedes the gap-analysis-only
> version of this file. The user has decided: this folder (Vite + TanStack
> Start, Lovable-originated) **replaces `frontend/` (Next.js) as the real
> Urja Kavach frontend** — not a prototype to mine for ideas. What's already
> built here is kept; everything below is what changes or gets added so it's
> genuinely wired to the backend, safe to ship, and feature-complete against
> PLAN.md Segment 2. **No implementation has started yet** — this is the plan
> to implement against. [PLAN.md](../.claude/docs/PLAN.md) §3 has been updated to point
> here (see its own note at the top of the Segment 2 section).

---

## 0 · Requirements this plan is built against (user directive)

1. India Connect Portal is **the** Urja Kavach frontend going forward.
2. Keep what's already built; extend it, don't restart it.
3. Frontend ↔ backend ↔ AI must be **actually wired** — no more silent mock
   data standing in for live state.
4. **No leakage, safety and trust maintained** — no committed secrets, real
   auth (not fake/plaintext), and the UI must never pass off fabricated data
   as live without saying so.
5. Every missing UI feature from the Segment 2 chunk table gets built.
6. PLAN.md Segment 2 gets updated to reflect this stack decision.

---

## 1 · Non-negotiables (apply to every phase below)

These come directly from requirement 4 and are treated as acceptance gates,
not suggestions:

- **No secret ever committed.** `.env` must be gitignored before this folder
  is ever `git add`ed (today it is not — `.gitignore` only excludes
  `*.local`). A committed `.env.example` with placeholder values replaces it.
- **The originally-committed Google Maps browser key was already
  compromised** — it was read and echoed back in the audit that produced
  this spec (this conversation's tool output), so it had to be treated as
  leaked regardless of git history. **Resolved in Phase 0**: it turned out
  to be Lovable's own connector-provisioned key, not one the user owned, so
  rotating it wasn't possible directly — instead the user created a
  fresh, self-owned Google Cloud key (HTTP-referrer + API restricted) and
  swapped it into local `.env` by hand (never pasted through chat, to avoid
  repeating the leak). Verified rendering clean on `/official`.
- **No plaintext passwords, anywhere, ever.** The current `AuthProvider`
  storing `{password}` objects in `localStorage` is removed outright, not
  patched — see Phase 2.
- **RBAC is enforced server-side, never trusted client-side.** `RequireRole`
  is fine as a UX nicety (fast redirect), but every official-only action
  (`/approve`, `/audit`) must rely on the backend's `require_role("official")`
  check, and the client must handle a `403` gracefully, not assume its own
  role check was sufficient.
- **Never silently substitute fake data for live data.** If the WebSocket is
  down or a fetch fails, the UI may fall back to a last-known-good snapshot
  or a clearly labeled offline/demo state — it must never render fabricated
  numbers with the same visual treatment as real ones. This is stricter than
  what `frontend/`'s `useRiskState()` does today (its `fallbackState` mock
  renders with no "this is not live" indicator) — the new build closes that
  gap rather than copying it.
- **The audit trail must reflect only what actually happened.** No frontend
  component may invent an audit row (see §3, mock `audit[]` issue) — every
  row rendered must come from `GET /audit` or a `POST /approve` /
  `POST /assumptions/override` response.

---

## 2 · Architecture decisions (resolves the prior open questions)

| # | Question | Decision | Why |
|---|---|---|---|
| 1 | Map provider | **Keep Google Maps** (`RealWorldMap.tsx`) as primary, per requirement 2. Add `IndiaMap.tsx` back in as an **explicit, labeled offline fallback** when the Maps key is missing/fails to load (it already renders an error state today — wire the existing stylized SVG map into that branch instead of a bare error message) | Keeps what's built; turns dead code into a real graceful-degradation path, matching the backend's own "never hard-fail the demo" philosophy (Watch's LLM→stub fallback, CLAUDE.md) |
| 2 | Auth storage shape | **Mirror `frontend/lib/session.ts` exactly**: JWT from `/auth/login`/`/auth/register` stored in a JS-readable cookie (`uk_session` equivalent), attached as `Authorization: Bearer` on every API call. This is a known, already-documented trade-off in this codebase ("fine for a hackathon demo, not for real secrets") — carried forward explicitly, not silently | Matches the backend's actual issuance shape (JWT in JSON body, no HttpOnly cookie support server-side); reusing a proven pattern beats inventing a new one |
| 3 | `national_score` / `national_band` | **Derive client-side, don't add a backend field.** `national_score = Math.round(severity * 100)`, `national_band` via the existing `bandOf()` thresholds applied to that score | `severity` (0–1) is always present on `RiskState`; no contract change needed, and the mock's own 68/"high" example is consistent with this formula at the seeded severity |
| 4 | `alarm_language_score` (mock field) | **Drop it from the UI entirely.** Per CLAUDE.md, Phase 9 intentionally never exposes this as a `RiskState`/API field — it's folded into Watch's prompt only. Displaying an invented number here would violate non-negotiable "never pass off fabricated data as real" | Respects an explicit upstream design decision instead of working around it |
| 5 | `spr_series` (30-day history mock) | **No fabricated history.** Backend has no days-of-cover time-series endpoint. Replace the chart with a **client-side rolling buffer**: append `reserve.days_cover` each time a new `RiskState` snapshot arrives over WS, explicitly labeled "session-observed, not historical" until a real backend history endpoint exists (flagged as a possible future Segment 1 addition, out of this plan's scope) | Real data only, honestly scoped, no invented 30-day trend line |
| 6 | `kavach-data.ts`'s `RiskState` type | **Rebuild, don't patch.** Replace it with a true `types/contract.ts`, a field-for-field mirror of `backend/schemas/contract.py` (same rule `frontend/types/contract.ts` already follows, and the same "no codegen, keep in sync by hand" standing rule from PLAN.md §3) | Drift already went too far to reconcile field-by-field (§ old spec's contract-drift table); a clean mirror is the only way to actually stay in sync going forward |

---

## 3 · What's kept as-is (no rework needed)

- Route structure (`/`, `/auth`, `/official`, `/public`) and file-based
  TanStack Router conventions.
- `KavachHeader`, `RiskGauge`, `RequireRole` (redirect *logic* stays; the
  identity layer underneath changes — Phase 2).
- The design system (`styles.css` tokens, shadcn/ui components already
  installed).
- `RealWorldMap.tsx`'s Google Maps integration pattern (polylines, markers,
  info-windows) — the geometry source changes (Phase 7), not the rendering
  approach.
- The reroute-card visual pattern in `official.tsx` (`grade_ok`/
  `rank_eligible` → BLOCKED/ELIGIBLE badge, cost-breakdown bars) — this is
  already a good F16/F17 UI; it just needs real data (Phase 4).
- The combined login/register page UX in `auth.tsx` (role toggle, agency/
  officer-ID fields, `.gov.in` hint copy) — kept as the UI shell; the
  `useAuth()` implementation underneath is replaced (Phase 2).

---

## 4 · Phased build plan

Mirrors PLAN.md/SPEC.md's phase style: goal, changes, acceptance criteria,
dependencies. Phases 0–3 are the baseline-wiring gate — nothing in Phases
4–10 can be genuinely "wired" (requirement 3) until these land.

### Phase 0 — Security cleanup *(blocking, do first)*

> **STATUS: ✅ landed.** `.gitignore` now excludes `.env`/`.env.local`/
> `.env.*.local` (verified via `git check-ignore -v` — nothing in this
> folder was ever tracked by git, so there was no history to scrub);
> `.env.example` is committed with placeholders only; `AGENTS.md` documents
> the secrets rule. The leaked key turned out to be Lovable's own connector
> key (`VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_BROWSER_KEY`), not one the user
> owned in Google Cloud — resolved by creating a fresh, user-owned key
> (own GCP project + billing, HTTP-referrer + API restricted to Maps
> JavaScript API) and swapping it into local `.env` directly in the editor
> (never pasted through chat, to avoid repeating the original leak vector).
> Verified working: `npm install` + `npm run dev` (Vite v8, port 8080) — no
> `bun` binary was available in this environment despite `bun.lock`/
> `bunfig.toml` being present, so **npm is the working package manager here
> in practice**; the scripts (`vite dev`/`vite build`/etc.) are plain Vite
> commands with nothing bun-specific, so this is a safe substitution, not a
> workaround — worth remembering for anyone else setting this up without
> Bun installed. `/official`'s map renders clean (tiles, corridor
> polylines, refinery markers) with the new key.

**Goal:** stop the folder from being unsafe to commit.

- Add `.env`, `.env.local`, `.env.*.local` to `.gitignore`.
- Replace `.env` with a committed `.env.example` (placeholder values only),
  matching `frontend/.env.example`'s existing convention.
- Document in this folder's README/AGENTS.md that a real
  `VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_BROWSER_KEY` must be supplied via the
  deploy environment, never committed.
- ~~**User action (not a code change):** rotate the already-leaked Google
  Maps key and restrict it by HTTP referrer before deploying.~~ **Done** —
  see the STATUS note above: a fresh, self-owned key replaced the
  Lovable-connector one.

**Acceptance:** `git status` shows `.env` untracked/ignored; a fresh clone
has no working Maps key until one is supplied out-of-band; no secret appears
in any commit this work produces. **All met.**

**Depends on:** nothing.

---

### Phase 1 — Real contract sync (Chunk A)

> **STATUS: ✅ landed**, with one deliberate scope adjustment and one
> pre-existing bug newly surfaced.
>
> **Scope adjustment:** the acceptance line below ("nothing outside the
> landing page still imports the old `seedState`") assumed Phase 3 (live WS
> wiring) lands close behind. Implementing Phase 1 in isolation, rewiring
> `/official`/`/public`/`RealWorldMap` to a live hook that doesn't exist yet
> would have broken the app. Instead: `demo-state.ts` (renamed `DemoState`/
> `demoState`, not `RiskState`/`seedState`, per decision #6) is temporarily
> still read by every page that isn't rewired to live data yet — the actual
> goal of this phase (retiring the invented shape that was drifting from and
> colliding with the real contract) is met; the literal "landing page only"
> reader restriction is Phase 3's job, not this one's. Documented here so
> it isn't mistaken for a missed acceptance criterion.
>
> **New file:** `src/types/contract.ts` — exact field-for-field mirror of
> `backend/schemas/contract.py` (`RiskState`, `CorridorRiskEntry`, `Impact`,
> `AssumptionEntry`, `Assumptions`, `CostBreakdown`, `Reroute`, `Reserve`,
> `AssumptionOverride`, `Geo`, `Validation`, plus the two agent output
> envelopes). Not consumed by anything yet — that starts in Phase 2/3.
>
> **Verified:** `npx tsc --noEmit` passes against it with zero errors;
> `npm run build` (client + SSR + nitro/Cloudflare bundle) succeeds cleanly;
> dev server HMR reloaded every touched file with no runtime errors.
>
> **Pre-existing bug found, not fixed here (out of Phase 1 scope):**
> `KavachHeader.tsx`'s logout call passes `role: mode` where `mode` is
> `"official"|"public"` but `lib/auth.tsx`'s `Role` type is
> `"official"|"citizen"` — a `tsc` error that predates this session (confirmed
> by running `tsc`/`eslint` against `KavachHeader.tsx` untouched). Belongs to
> Phase 2 (real auth), where `Role`/session plumbing is being rebuilt anyway.
>
> **Also found:** a `vite build` OOM on this machine's nitro/Cloudflare
> bundling step, traced to host-level memory pressure (~383 MB free of
> 7.24 GB total at the time — confirmed via `Get-CimInstance
> Win32_OperatingSystem`), not a code defect — a clean retry with the dev
> server stopped succeeded. Worth knowing if a build ever fails on this
> machine again: check free memory before assuming a regression.

**Goal:** `types/contract.ts`, a genuine hand-mirror of
`backend/schemas/contract.py`, replacing `kavach-data.ts`'s invented types.

- New `src/types/contract.ts`: `RiskState`, `CorridorRiskEntry`, `Impact`,
  `AssumptionEntry`, `Assumptions`, `CostBreakdown`, `Reroute`, `Reserve`,
  `AssumptionOverride`, `Geo`, `Validation` — same field names, same
  optionality, as the Python source.
- `kavach-data.ts` is trimmed to **UI-only derived helpers**
  (`bandOf`, `bandColor`, `bandLabel`, `MAP_LOCATIONS`) — its `RiskState`/
  `Corridor`/`Reroute`/etc. types and `seedState` are deleted, not kept
  alongside the real ones (two competing shapes is worse than one).
- A small, explicitly-labeled **demo dataset** (e.g. `src/lib/demo-state.ts`)
  replaces `seedState` for the one legitimate remaining use case: rendering
  the marketing landing page (`/`) without requiring a live backend. It must
  be visually/structurally distinguishable from the real thing if it ever
  leaks into an authenticated page (it shouldn't, post Phase 3).

**Acceptance:** `types/contract.ts` round-trips a real `GET /state` response
with no type errors; nothing outside the landing page still imports the old
`seedState`.

**Depends on:** Phase 0 (unrelated but sequenced first for safety).

---

### Phase 2 — Real auth (JWT, not localStorage)

> **STATUS: ✅ landed.** `src/types/auth.ts`, `src/lib/session.ts`,
> `src/lib/api.ts`, and a rewritten `src/lib/auth.tsx` all shipped as
> planned. Two adjustments found while implementing, neither in this
> section's original scope:
>
> - **Registration form fields dropped, not just the domain hint.**
>   `backend/auth/schemas.py`'s `RegisterRequest` is `extra="forbid"` with
>   exactly `{email, password, role}` — the old fake form's `name`/`agency`/
>   `officerId`/`state` fields would have made every real registration
>   fail with a 422. Removed them from `routes/auth.tsx` entirely rather
>   than silently dropping them client-side before the request (which
>   would've kept dead, decorative form fields around). `KavachHeader.tsx`'s
>   user chip now shows `email` + role instead of a fabricated `name`/
>   `agency` the backend never stored.
> - **The ".gov.in domain gate" claim was never real.** Checked
>   `backend/auth/routes.py`/`schemas.py` directly — there is no
>   server-side email-domain check at all; role is entirely self-declared
>   at registration. The old copy ("Official access requires a verified
>   .gov.in... email") was describing a policy that doesn't exist —
>   corrected to state the truth: role is self-declared, and what actually
>   keeps it honest is that every official-only action is written to a
>   permanent, server-side audit log against the real authenticated
>   identity (`user.email` from the verified JWT, never a client-supplied
>   name — confirmed in `backend/api/routes.py`'s `post_approve`).
>
> **Verified against a live backend** (not just typechecked): registered
> both an official and a citizen account via `POST /auth/register`,
> confirmed `GET /auth/me` round-trips correctly, confirmed
> `GET /audit` returns 401 with no token and 403 for a citizen token
> (role-gating genuinely enforced server-side, not just hidden client-side).

**Goal:** replace the fake `AuthProvider` with one that talks to
`/auth/register`, `/auth/login`, `/auth/me`.

- New `src/lib/session.ts` (cookie read/write, mirrors
  `frontend/lib/session.ts` per decision #2 in §2).
- New `src/lib/api.ts` REST client: attaches `Authorization: Bearer` from
  the session cookie, throws a typed `ApiError` on non-2xx, mirrors
  `frontend/lib/api.ts`'s method list (`getState`, `injectSignal`,
  `simulate`, `getReroutes`, `approve`, `publicStatus`, `getAudit`,
  `register`, `login`, `me`) plus the v1.3 additions Phase 4–8 need
  (`getGeoState`, `getBacktest`, `overrideAssumption`).
- `AuthProvider`/`useAuth()` rewritten: `login`/`register` call the real
  endpoints, persist the returned token+role via `session.ts`, `logout`
  clears the cookie. The `.gov.in`/PSU email check becomes purely a UX hint
  (the backend is the real gate) — remove the client-side hard block so a
  legitimate account isn't refused by a stale regex.
- `RequireRole` calls `GET /auth/me` (or reads the session cookie) instead
  of the fake context; on a `401`, clears the session and redirects to
  `/auth` instead of silently treating the user as logged out.

**Acceptance:** creating an official account actually calls
`POST /auth/register`, appears in the backend's user table, and a
subsequent official-only call (`/approve`) succeeds with that token and
fails with a clear error for a citizen token; no password ever touches
`localStorage`.

**Depends on:** Phase 1 (needs `types/contract.ts`'s auth-adjacent types,
or a small `types/auth.ts` alongside it, mirroring `frontend/types/auth.ts`).

---

### Phase 3 — Live state + signal injection (the missing baseline)

> **STATUS: ✅ landed**, with scope pulled forward from Phase 4 (documented,
> not silent) and a few honest simplifications where the real contract
> didn't map cleanly onto the old mock UI.
>
> **Shipped:** `src/hooks/useRiskState.ts` (WS + REST hydrate, `connecting|
> live|offline` status, **no demo-state fallback at all** — `state` stays
> `null` until a real snapshot arrives, satisfying §1's non-negotiable more
> strictly than `frontend/`'s own version, which does fall back to a mock);
> `src/hooks/useReserveHistory.ts` (session-observed rolling buffer per §2
> decision #5, explicitly not presented as history); `src/lib/live-derive.ts`
> (`nationalScore`/`nationalBand` per decision #3, a real `CORRIDOR_LABELS`
> map matching `backend/seed/corridors.json`'s actual ids, `describeAuditEntry`);
> a new `/mission` route (corridor select + headline input + severity slider
> → `POST /signal`, linked from the landing page); `official.tsx` and
> `public.tsx` fully rewired off the hook; a Vite dev proxy + `BACKEND_URL`/
> `VITE_API_URL`/`VITE_WS_URL` in `.env.example`.
>
> **Pulled forward from Phase 4, not deferred — because leaving it undone
> would have meant visibly broken (blank/`undefined`) reroute cards, which
> §1's "nothing rendered wrong" bar doesn't allow:**
> - `RerouteCard` now takes the real `Reroute` type and reads real field
>   names (`true_cost`, `cost_breakdown.war_risk_insurance`, `supplier`/
>   `route` instead of invented `from_port`/`to_port`/`vessels`) — verified
>   against a live cascade response, not guessed from the contract alone.
> - **Approve is wired for real**, narrower than Phase 4's eventual scope:
>   the button approves the top-ranked eligible reroute (`rank_eligible &&
>   grade_ok`, first by `rank` — confirmed live that the backend already
>   sorts this way) via a real `POST /approve` call, and the audit panel
>   reads real `GET /audit` rows through `describeAuditEntry`. What's left
>   for Phase 4 specifically: the `sort=balanced|cost|speed` toggle against
>   `GET /reroutes`, and letting the official choose *which* reroute to
>   approve instead of always the top one.
>
> **Known, deliberate rough edges — not bugs, flagged for the phase that
> owns fixing them:**
> - The map (`RealWorldMap`) still renders demo corridor geometry (Phase 7's
>   job). Demo corridor ids (`bab_el_mandeb`, `suez`) don't exist in the real
>   seed data (`suez_cape`, `atlantic` instead) — clicking those two markers
>   shows an honest "no live scoring yet for this corridor" instead of
>   crashing, rather than pretending to have real data for them.
> - The What-If panel is kept as an explicitly-labeled **local preview**
>   (old client-only math, old demo corridor weights), visually decoupled
>   from the real gauge above it so the two can't be confused. Real
>   `Assumptions`-typed sliders wired to `POST /simulate` are Phase 5.
> - `/public`'s advisories list is still the old sample copy, now labeled
>   "Sample copy · real LLM-generated advisories land in Phase 9" rather
>   than presented as live.
> - Corridor "Signal feed" now shows real `source_ids` (ids only, no
>   fabricated headline text) — full provenance text is Phase 6.
>
> **Verified against a live backend end-to-end**, not just typechecked:
> `POST /signal` (Hormuz) → confirmed `corridor_risk`/`impact`/`reroutes`/
> `reserve`/`geo` all matched `types/contract.ts` exactly field-for-field;
> confirmed the real top-ranked eligible reroute (`ru_urals` via
> `suez_cape`, rank 1) is what the UI's Approve button would pick; called
> `POST /approve` for real and confirmed the resulting row via `GET /audit`;
> confirmed `GET /public/status` and the Vite dev proxy both work end to
> end. `npx tsc --noEmit`, `npm run build` (client+SSR+nitro), and a fresh
> `npm run dev` all clean; SSR-rendered `/`, `/mission`, `/official`,
> `/public` all returned `200` with zero server-side errors logged while
> hitting the live backend through the proxy.

**Goal:** the "one signal, one sweep" standing rule, and the demo entry
point that doesn't exist anywhere in this folder yet.

- New `src/hooks/useRiskState.ts`: WS subscription to `/ws/state`, REST
  hydrate-first via `GET /state`, auto-reconnect, exposes connection status
  (`connecting|live|offline`) — same architecture as
  `frontend/hooks/useRiskState.ts`, **plus** the non-negotiable from §1: when
  `offline`, the UI shows a visible "last known state — reconnecting" badge
  rather than quietly rendering `demo-state.ts` with no indicator.
- Every page (`/official`, `/public`) switches from reading `seedState` to
  reading this hook. The landing page (`/`) may keep `demo-state.ts` since it
  needs no auth and isn't a "live" surface.
- **New: a signal-injection entry point** (the missing Mission Control
  equivalent). Simplest version: a form on `/official` (or a new
  `/mission` route, matching `frontend/`'s naming) — corridor select +
  headline text input → `POST /signal` → the WS push animates every panel.
  This is the single most important missing feature: without it there is no
  way to demo the cascade at all in this folder today.
- Vite dev proxy (`vite.config.ts` → `server.proxy: { "/api": "http://localhost:8000" }`)
  so REST calls are same-origin in dev, matching `frontend/`'s CORS-free
  rewrite approach; `VITE_WS_URL`/`VITE_API_URL` env overrides for
  non-default backend hosts, matching `frontend/.env.example`'s
  `BACKEND_URL` pattern.

**Acceptance:** loading `/official` with the backend running shows real
seed-config data (not `seedState`'s numbers); injecting a signal visibly
updates the gauge, corridor panel, and reroutes without a page reload;
killing the backend flips the UI into a labeled offline state instead of
reverting to invented numbers.

**Depends on:** Phases 1–2.

---

### Phase 4 — Reroute cards v2, wired (Chunk B)

> **STATUS: ✅ landed.** `official.tsx` now fetches `GET /reroutes?sort=...`
> directly (a new `sort` toggle — Balanced/Cost/Speed buttons above the
> reroute grid — refetches on change, and again whenever `state.updated_at`
> ticks so exclusions stay current after a new signal). Field names were
> already reconciled in Phase 3 (pulled forward); this phase's actual
> remaining scope was the sort toggle and reroute selection.
>
> **Selection, not just the top pick:** clicking any non-blocked
> `RerouteCard` sets it as the selected option (badge switches to
> "SELECTED"); "Approve selected reroute" calls `POST /approve` with
> whichever supplier is selected, defaulting to the top eligible option when
> nothing's been clicked yet. Selection auto-resets to top-eligible if the
> previously selected supplier drops out of the eligible set on a refetch.
>
> **One backend quirk surfaced, not fixed here (out of frontend scope):**
> `POST /approve` matches by `supplier` only (`backend/api/routes.py`'s
> `post_approve`), not `(supplier, refinery_id)`, so if the same supplier
> appears twice (two eligible refineries), clicking either card selects the
> same underlying supplier id and the backend always approves whichever of
> that supplier's rows ranks first in `store.get().reroutes` — verified live
> against the running backend, not a frontend bug to route around.
>
> **Verified against a live backend**, not just typechecked: `GET
> /reroutes?sort=cost` after injecting a Hormuz signal correctly excluded
> `hormuz` and re-ranked by `true_cost`; a `POST /approve` call for a
> selected supplier produced a real row confirmed via `GET /audit`.
> `npx tsc --noEmit`, `eslint`, and `npm run build` all clean.

**Goal:** keep the existing `RerouteCard` visual pattern, feed it real data.

- `RerouteCard` reads from `GET /reroutes?sort=...` via the new API client,
  not `seedState.reroutes`.
- Field-name reconciliation per the old drift table: `true_cost_usd_bbl` →
  `true_cost`, `cost_breakdown.war_risk` → `cost_breakdown.war_risk_insurance`,
  `from_port`/`to_port` (invented) → real `supplier`/`route`/`refinery_id`
  (the UI can still resolve a human-readable port/refinery label from seed
  config via `GET /geo/state`'s `refineries[]`, but the identifiers driving
  logic must be the real ones).
- Sort toggle (`balanced|cost|speed`) wired to the same query param.
- "Approve Plan" button calls `POST /approve` with the selected supplier;
  success appends the real audit row (from the response), not a fabricated
  local one.

**Acceptance:** a `rank_eligible=false` option renders BLOCKED with its real
`reason` string from the backend; approving actually creates a row visible
via `GET /audit`.

**Depends on:** Phase 3.

---

### Phase 5 — Assumption slider UX (Chunk C)

> **STATUS: ✅ landed.** The old client-only-math "What-If Simulator ·
> Preview" panel (two generic sliders, invented corridor weights) is fully
> replaced by a new `AssumptionsPanel` in `official.tsx`, reading all six
> `Assumptions` fields live from `state.assumptions` (never invented
> defaults). Ships in the same grid slot as the old preview panel.
>
> - Per-field slider range (`lib/live-derive.ts`'s new
>   `assumptionSliderRange()`): `fact` type locks `min`/`max` as close as
>   possible to the entry's documented `range`; `estimate`/`internal` pad one
>   range-width on each side ("wide") so an official can explore past the
>   sourced estimate. **Bug found and fixed before landing**: `range` is a
>   fixed citation (`supply_lost_pct`'s is "typical Hormuz transit share,
>   35–45%"), but the live `value` is severity-scaled and can legitimately
>   sit outside it — confirmed live against a running backend (a
>   severity=1.0 Hormuz signal drives `supply_lost_pct.value` to `100`, well
>   past its own `[35, 45]` range). A naive "lock to `range`" slider would
>   have silently clamped the visible thumb to `45` via Radix's own
>   value-clamping while the real state stayed `100` — `assumptionSliderRange`
>   now always widens `min`/`max` to include the current `value`.
> - Type tag next to each label: `fact` (green), `estimate` (cyan, `title`
>   attribute shows `src` on hover — no `TooltipProvider` was wired app-wide,
>   so this uses the native HTML tooltip rather than pulling in Radix's), and
>   `internal` (grey, "not sourced" — no citation, matching
>   `power_stress_multiplier`'s real shape).
> - Dragging debounces a real `POST /simulate` call (300ms) using the live
>   `scenario` label; releasing (Radix Slider's `onValueCommit`) fires an
>   immediate final `/simulate` plus `POST /assumptions/override`, then
>   triggers the same `refreshAudit()` the reroute panel already uses so the
>   new `override_assumption` row appears without a manual refresh — UI copy
>   states explicitly that it's logged immediately but only snapshotted onto
>   an approval at Approve time, matching the backend's real behavior
>   (`post_assumption_override`'s docstring).
> - Power-stress bar (previously entirely absent from `official.tsx`) is a
>   labeled 0–100% bar under the preview tiles, sourced from `/simulate`'s
>   returned `Impact.power_stress_pct`.
> - If `state.assumptions` is `null` (no signal injected yet), the panel
>   shows an honest "inject a signal first" message instead of rendering
>   empty/undefined sliders — same fallback pattern already used by the
>   corridor-detail and reroute panels elsewhere on this page.
>
> **Verified against a live backend**, not just typechecked: registered a
> real official account, confirmed `POST /simulate` recomputes `price_rise_pct`/
> `gdp_delta_pct` correctly for an adjusted `price_elasticity`, confirmed
> `POST /assumptions/override` both returns `overrides_logged` and produces a
> real `GET /audit` row, and confirmed a subsequent `POST /approve` embeds
> that pending override in its `assumption_overrides` payload. `npx tsc
> --noEmit`, `eslint`, and `npm run build` all clean.
>
> **Not yet verified in-browser** (no browser-automation/screenshot tool was
> available in this environment): the slider drag/debounce/commit interaction
> itself, and the hover tooltip, were exercised via direct backend calls with
> the same request bodies the UI sends, not by physically dragging a slider
> in a running browser. Recommend a manual click-through before demo day.

**Goal:** replace the two generic, client-only-math sliders with the real
six-field `Assumptions` model, typed by sourcing tier.

- One slider row per `Assumptions` field (`supply_lost_pct`, `buffer_days`,
  `price_elasticity`, `power_oil_dependence`, `gdp_oil_sensitivity`,
  `power_stress_multiplier`), each reading its current `{value, type, range,
  src}` from live state.
- `type: "fact"` → narrow slider locked to `range`; `type: "estimate"` →
  wide slider + a hover tooltip showing `src`; the one `"internal"` constant
  (`power_stress_multiplier`) gets an explicit "not sourced" tag instead of
  a citation.
- Recompute calls real `POST /simulate` (debounced on drag), not invented
  client arithmetic.
- On slider **release** (commit, not every debounce tick), call
  `POST /assumptions/override`; a divergent field shows up in the audit
  panel on next `GET /audit` refresh, per the backend's actual "logged
  immediately, snapshotted onto `RiskState.assumption_overrides` only at
  Approve" behavior — the UI copy should say exactly that, not imply
  overrides are already committed before Approve.
- Add the missing **power-stress bar** to the what-if panel (`Impact.
  power_stress_pct`) — currently absent from `official.tsx` entirely.

**Acceptance:** dragging `price_elasticity` and releasing produces one new
`audit_log` row (visible via `GET /audit`) without needing to click Approve;
`Impact.power_stress_pct` moves visibly when `power_oil_dependence` changes.

**Depends on:** Phase 3.

---

### Phase 6 — Provenance popovers v2 (Chunk D)

> **STATUS: ✅ landed.** The provenance lookup shape this section flagged as
> unconfirmed (§7) turned out not to exist at all — grepped the backend and
> confirmed CLAUDE.md's "deferred to Segment 2, Chunk D" note meant exactly
> that: no endpoint. Added one: `GET /provenance?ids=a,b,c` (comma-separated,
> matching this codebase's existing plain-query-param style, e.g.
> `/reroutes?sort=`), resolving ids against the same committed
> `watch_corpus.json` `backend/agents/rag.py` already embeds for retrieval —
> `{items: [{id, headline, source, timestamp}], missing: [ids]}`. Backend
> change, not just frontend: `backend/api/routes.py` gained the route,
> `tests/test_api.py` gained 3 new tests, full suite still 100% green
> (323/323, up from 319).
>
> **Honesty preserved on the common path, not just the happy path**: the
> *offline stub* (this repo's default — `USE_REAL_AGENTS=0`) sets
> `source_ids` to the injected signal's own id (e.g. `sig_unknown`), not a
> real corpus id — confirmed live against a running backend before writing
> any UI code. `/provenance` reports these as `missing`, never fabricated,
> and the corridor panel's new `SignalFeed` component renders that
> explicitly ("No provenance on file for this id — not a retrieved corpus
> snippet") rather than a blank or broken-looking row.
>
> **UI**: the corridor detail panel's source-id list is now a `SignalFeed`
> component (`official.tsx`) — each id is a button; clicking it lazily
> fetches (once, cached per id) and expands to show the real headline/
> source/timestamp inline, rather than eagerly fetching everything up
> front.
>
> **Verified against a live backend** (through the real Vite dev proxy, not
> just typechecked): `GET /api/provenance?ids=news_hormuz_2019_seizure`
> round-tripped the real corpus headline/source/date. `npx tsc --noEmit`,
> `eslint`, and `npm run build` all clean.

**Goal:** real click-through from a corridor score to its retrieved
snippets.

- Corridor detail panel's "Signal feed" list becomes clickable per headline,
  showing `{headline, source, timestamp}` from `corridor_risk[id].
  source_ids` — needs whatever provenance lookup shape Segment 1 Phase 4
  exposes (CLAUDE.md notes this was "explicitly deferred to Segment 2,
  Chunk D" — confirm the exact endpoint/shape with the backend before
  building this phase; flagged as a dependency to verify, not assumed here).

**Acceptance:** clicking a headline shows its real source id and timestamp,
not a static string.

**Depends on:** Phase 3, and confirming the provenance lookup shape (see
above).

---

### Phase 7 — Geospatial map v2 (Chunks E + F)

> **STATUS: ✅ landed**, with one backend gap found and closed first, plus
> one deliberate scope note.
>
> **Backend gap found before any frontend code was written**: `Corridor.
> geojson_path` (e.g. `"backend/seed/geo/hormuz.geojson"`) is a
> repo-relative filesystem path, not a URL — the browser can't fetch it. No
> static-file mount existed either. Rather than stand one up (a new surface
> to secure/maintain), `GET /geo/state` now embeds each corridor's parsed
> `geometry` (`{type, coordinates}`, read via `backend.config.REPO_ROOT` so
> it resolves regardless of cwd) directly in its existing per-corridor
> object — keeps `/geo/state` the one-stop read its own docstring already
> promises. Degrades to `geometry: null` (map just skips that corridor's
> line) on a missing/malformed file rather than 500ing. New test
> (`test_geo_state_corridors_expose_parsed_geometry`) pins the real Hormuz
> coordinates; full suite unaffected (existing geo tests check individual
> fields, not whole-object equality, so the added field is non-breaking).
>
> **`RealWorldMap.tsx` fully rewired off live data**: new `useGeoState()`
> hook (`src/hooks/`) fetches `/geo/state` once for the static-ish config
> (corridor geometry, refinery lat/lon, the 16-tanker AIS replay set);
> per-signal state (`dark_tanker_ids`/`affected_refinery_ids`) is read
> directly from the WS-pushed `state.geo` rather than re-fetched, since the
> backend already guarantees the two agree
> (`test_geo_state_matches_live_state_geo`). Corridor polylines now draw
> from real `geometry.coordinates`, colored by live `corridor_risk` (a
> corridor with no live score yet renders a distinct muted grey, never
> defaulted to "low/stable" green — a real-data honesty fix that also
> applies to the primary Google Maps view, not just the fallback). Tanker
> markers step through their real 8-point track on a 2s interval (no
> physics sim, per this section's own suggestion); dark tankers get a
> visually distinct pulsing marker; affected refineries pulse too — both
> driven by one shared interval that repositions/re-icons existing marker
> objects in place (`.setIcon()`/`.setPosition()`) rather than recreating
> the whole overlay set on every tick.
>
> **`IndiaMap.tsx` wired in as the offline fallback** (decision #1):
> replaces the old bare "Map unavailable" text. `IndiaMap` had no other
> caller, so its internal `CHOKEPOINTS` array (previously the stale demo ids
> `bab_el_mandeb`/`suez`) was updated to the real corridor ids rather than
> built around them — a small adapter (`toIndiaMapData()`) maps live
> corridor/refinery config into `IndiaMap`'s existing `DemoCorridor`/
> `DemoRefinery` prop shape, reusing `MAP_LOCATIONS` (extended with real ids
> — `suez_cape`, `atlantic`, `vadinar` — alongside the original demo set,
> which the landing page still needs).
>
> **Scope note**: no `@types/google.maps` package is installed (the API
> loads dynamically via `<script>`, never `import`ed) — rather than the
> file's pre-existing pattern of typing every map/marker/polyline handle as
> `any` (already present before this phase, just never linted until this
> rewrite touched the file), added a small local interface shim
> (`GMapsNamespace`/`GMarker`/`GPolyline`/`GInfoWindow`) so only one `any`
> remains in the whole file — the literal `window.google` boundary itself,
> commented and eslint-disabled at that single line, narrowed to a real type
> immediately after.
>
> **Verified against a live backend** (through the real Vite dev proxy):
> injecting a live Hormuz signal and re-fetching `/api/geo/state` confirmed
> `geo.dark_tanker_ids` (`hormuz_02/03/04`) and `geo.affected_refinery_ids`
> (`jamnagar`/`paradip`/`vadinar`) match this section's own acceptance
> criteria exactly, and that every tanker record has the full 8-point
> `{ts, lat, lon, heading_deg, speed_knots}` track the animation reads.
> `npx tsc --noEmit`, `eslint`, and `npm run build` all clean.
>
> **Not yet verified in-browser** (no browser-automation/screenshot tool was
> available in this environment): the actual map rendering, tanker
> animation smoothness, and pulse-marker visuals were confirmed correct at
> the data layer (props reaching the component match real backend output
> exactly) but not visually confirmed in a running browser with a real
> Google Maps key. Recommend a manual look before demo day.

**Goal:** `RealWorldMap` driven by `/geo/state`, not hand-authored waypoints.

- Corridor polylines read `geojson_path` per corridor from `GET /geo/state`
  instead of the hardcoded `ROUTE_PATHS` object; still band-colored by live
  `corridor_risk[id].score`.
- New tanker layer: render each tracked vessel from `/geo/state`'s
  `tankers[]` replay data; animate along its 8-point track (simplest
  version: step through points on an interval, not a physics simulation).
- `dark_tanker_ids` render as a visually distinct pulsing/warning marker
  style, separate from normal tanker markers — the single "real ML" beat
  PRD §18 calls out, currently entirely absent from this folder.
- When a scenario resolves `geo.affected_refinery_ids`, pulse those refinery
  markers (currently `RealWorldMap` renders refineries statically with no
  connection to `geo` at all).
- `IndiaMap.tsx` wired in as the offline fallback per decision #1 (§2),
  replacing the current bare "Map unavailable" error text.

**Acceptance:** injecting a Hormuz signal (Phase 3's new entry point) visibly
marks the tankers Segment 1's curated replay set flags as dark, and pulses
Jamnagar/Vadinar/Paradip per `affected_by({"hormuz"})`'s known result.

**Depends on:** Phase 3.

---

### Phase 8 — Backtest chart (Chunk G)

> **STATUS: ✅ landed.** New `BacktestPanel` component in `official.tsx`,
> full-width row at the bottom of the cockpit, fetching
> `GET /backtest/red_sea_2023` once on mount (a static historical case, not
> tied to live cascade state — no `state.updated_at` refetch dependency,
> unlike the reroute/geo panels).
>
> **Bug found before writing any chart code, not guessed**: the `api.ts`
> `BacktestResponse` type was hand-authored ahead of this phase and didn't
> match the real endpoint — `score_timeline` entries actually carry
> `headline_id`/`score`/`source_ids` (not a bare `{ts, score}`), and price
> points are keyed `price_usd_bbl`, not `price`. Caught by curling the live
> endpoint before writing the component, fixed in `api.ts` first.
>
> **Chart**: a Recharts `ComposedChart` with dual Y-axes (`score` 0–100 on
> the left in cyan, Brent USD/bbl on the right in amber) — the two series
> don't share every timestamp (`price_timeline` has 4 earlier baseline
> points `score_timeline` doesn't), so both timelines are merged into one
> client-side array keyed by `ts` (`mergeBacktestTimelines()`) purely for
> the chart's x-axis, not a data transformation of any kind — every plotted
> point is a real value from the response. Dashed `ReferenceLine`s mark each
> series' own crossing threshold (`watch_alert_threshold` /
> `brent_spike_threshold_usd`); the lead-time callout shows both hours and
> days. The endpoint's own `note` field ("Illustrative single historical
> case… not a validated statistical accuracy claim") is rendered verbatim
> under the chart, per this section's own instruction not to drop it.
>
> **Verified against a live backend** (through the real Vite dev proxy):
> `GET /api/backtest/red_sea_2023` returned the real 7-point score timeline
> and 11-point price timeline, `signal_lead_hours: 1464.0`, matching
> CLAUDE.md's own pinned worked example. `npx tsc --noEmit`, `eslint`, and
> `npm run build` all clean.

**Goal:** a new panel, currently absent entirely.

- New panel on `/official`: Watch-score-vs-Brent overlay chart (Recharts,
  matching the existing chart style already used for the SPR area chart) +
  a lead-time callout number, from `GET /backtest/{id}`.
- UI copy must repeat the backend's own honesty framing verbatim-in-spirit:
  "one illustrative historical case," never presented as a validated
  accuracy metric (the endpoint's own `note` field should be surfaced, not
  dropped).

**Acceptance:** the panel renders the Red Sea/Houthi case's real score and
price timelines with the correct `signal_lead_hours` callout.

**Depends on:** Phase 3.

---

### Phase 9 — Public portal copy (Chunk H)

> **STATUS: ✅ landed**, with one scope expansion beyond this section's
> literal wording — found while implementing, not part of the original ask.
>
> **The status badge fix went deeper than the badge**: this section only
> named the STABLE/WATCH badge as needing to switch off the endpoint's real
> `status`, but the page's hero `<h1>` was a hardcoded, unconditional
> claim — "India has fuel. **There is no shortage.**" — regardless of live
> severity. Once `status` can genuinely reach `"Shortage"`, that headline
> would have been actively false, not just stale sample copy. Fixed by
> replacing the static headline body with `publicStatus.message` itself
> (the real, level-appropriate, LLM-or-fallback copy) rather than
> maintaining a second, locally-authored three-tier headline set that could
> drift from the endpoint's own wording — more literally "sourced entirely
> from the one endpoint" than the section's own text asked for.
>
> **Conservation plan**: the old static 3-card "Petrol prices / Shipping
> routes / Electricity" grid (fixed copy, never tied to any live signal) is
> replaced by cards generated from `conservation_plan[]` (2–4 real tips per
> the backend's own prompt spec), tone-colored by the live `status`.
>
> **Action feed**: new "Recent official actions" section renders
> `action_feed[]` (last 5 audit rows) — this UI element didn't exist at all
> before (only an unused `.animate-ticker` CSS keyframe was ever defined,
> never wired to anything); built as a plain vertical list rather than a
> scrolling marquee, since a 0–5-item feed looks broken as an infinite loop.
> Phrased in plain language for a public audience (`describePublicAction()`)
> rather than exposing raw action/actor names — an `override_assumption` row
> reads as "Officials updated the response plan," never technical jargon.
>
> **Verified against a live backend** (through the real Vite dev proxy):
> `GET /api/public/status` returned real `status`/`message`/
> `conservation_plan`/`action_feed` (including a live `override_assumption`
> row correctly falling through to the generic phrasing, and a real
> `approve_reroute` row rendering its actual route). `npx tsc --noEmit`,
> `eslint`, and `npm run build` all clean.

**Goal:** `/public` reads `GET /public/status`'s real shape instead of
`seedState.advisories`.

- Replace the static `advisories[]` block with `message` +
  `conservation_plan[]` from `GET /public/status`.
- Replace the fabricated `action_feed`-less ticker with the endpoint's real
  `action_feed[]` (last 5 audit-derived actions).
- `status` badge (STABLE/WATCH/etc.) driven by the endpoint's `status`
  field, not a locally recomputed `overallStable` boolean.

**Acceptance:** `/public` shows different copy after a signal changes the
severity level, sourced entirely from the one endpoint — no local advisory
authoring left in the component.

**Depends on:** Phase 3.

---

### Phase 10 — Demo rehearsal + `frontend/` deprecation (Chunk I)

> **STATUS: ✅ landed**, with the rehearsal run at the API layer rather than
> a literal browser click-through (no browser-automation/screenshot tool was
> available in this environment — flagged honestly, not silently skipped).
>
> **A GROQ_API_KEY became available in this session** (the user configured
> `USE_REAL_AGENTS=1` + a real key in `.env`), which changed what "rehearse
> the demo" could actually mean: this run exercised the **real** Watch
> LLM+RAG path throughout, not the deterministic stub — the first time this
> whole project's real-agent path has been demo-rehearsed end to end (see
> the Segment 1 Phase 10 section of `PLAN.md` for the paired backend work
> this unblocked, done first so the rehearsal below wasn't just exercising
> the stub again).
>
> **All 9 PRD §18 beats verified live, twice**, through the real Vite dev
> proxy against the running backend:
> 1. (static — no data dependency)
> 2. `GET /backtest/red_sea_2023` — real score/price timelines,
>    `signal_lead_hours` present (see the Segment 1 Phase 10 note on why
>    this number changed from the previously-pinned stub value)
> 3. `POST /signal` (Hormuz, the canonical Mission Control default headline)
>    — real LLM score (98.0) with a genuine natural-language `reason`,
>    served instantly from the now-committed LLM cache
> 4. `GET /geo/state` — real `dark_tanker_ids`/`affected_refinery_ids`
>    matching the documented worked example
> 5. `GET /state` — real `impact`/`assumptions` from Predict
> 6. `GET /reroutes?sort=cost` — a real `rank_eligible=false` option present
>    with its real `reason` string, ranking flips once insurance/detour are
>    added
> 7. `GET /provenance?ids=...` — real headline/source/timestamp for the
>    real Watch-retrieved `source_ids` (not `sig_unknown`, since the real
>    agent path was active); `POST /approve` → confirmed via `GET /audit`
> 8. `GET /public/status` — landed on real `status: "Shortage"` at the
>    severity this rehearsal reached, and the message correctly reflected
>    it rather than the old hardcoded "there is no shortage" claim (Phase 9
>    fix paid off here, not hypothetically)
> 9. (static — no data dependency)
>
> No panel's data source was stale or fabricated at any point checked.
>
> **`frontend/` marked legacy**: `frontend/README.md` now leads with an
> explicit "⚠️ LEGACY / SUPERSEDED" notice pointing at this folder, per
> decision — not deleted or archived (a separate, explicit destructive
> action left for the user, exactly as this section already said).
>
> **Folder rename**: still not done, still flagged as a follow-up, not
> resolved here — unchanged from this section's original text.

**Goal:** close the loop — run PRD §18's script end-to-end, then formally
retire the Next.js app.

- Run the full 9-beat demo script against this folder + a live backend,
  twice, fixing anything that doesn't animate correctly off a real cascade.
- Mark `frontend/` (Next.js) as **legacy/superseded** in its own README —
  do not delete it in this pass. Deleting or archiving the old app is a
  separate, explicit action for the user to confirm once this folder has
  reached parity (it's a destructive repo change, out of scope for a spec
  document to just do).
- Rename this folder / its `package.json` `name` field away from the
  generic `tanstack_start_ts` default and the space-containing directory
  name, if the user wants a cleaner path for CI/deploy tooling — flagged as
  a follow-up decision, not resolved here.

**Acceptance:** two clean end-to-end runs of the full cascade demo on real
(non-stub, if `GROQ_API_KEY` is available) or stub agents, no panel showing
stale/fabricated data at any point.

**Depends on:** Phases 0–9.

---

## 5 · Missing UI features — consolidated build list

Everything below is currently absent from this folder and is now in scope
per requirement 5 (cross-referenced to the phase that adds it):

- Signal-injection entry point / Mission-Control equivalent (Phase 3)
- Live-state offline/reconnecting indicator (Phase 3)
- Power-stress bar on the what-if panel (Phase 5)
- Fact/estimate/internal slider tiering + source tooltips (Phase 5)
- Assumption-override → audit-trail visibility (Phase 5)
- Clickable provenance popovers on corridor headlines (Phase 6)
- AIS tanker animation layer (Phase 7)
- Dark-ship pulsing warning markers (Phase 7)
- Affected-refinery pulse-on-trigger (Phase 7)
- Offline map fallback (wiring `IndiaMap.tsx` in, Phase 7)
- Backtest score-vs-Brent chart + lead-time callout (Phase 8)
- Real `GET /public/status` copy + action feed (Phase 9)

---

## 6 · Explicitly deferred (not in this plan's scope)

- A real backend days-of-cover **history** endpoint (§2 decision #5) —
  would need a Segment 1 change; the frontend works around its absence
  honestly instead.
- Exposing `alarm_language_score` as an API field — an intentional upstream
  design decision (CLAUDE.md), not something this frontend plan should route
  around.
- Deleting/archiving `frontend/` (Phase 10 only marks it legacy).
- Renaming this folder or its package name (flagged, not decided).
- A frontend automated test suite — carried over as a known gap from
  `frontend/` too (CLAUDE.md), not newly introduced or newly resolved here.

---

## 7 · Confirm before Phase 6

One open dependency, not blocking Phases 0–5: verify the exact provenance
lookup shape Segment 1 Phase 4 exposes for Watch's retrieved snippets (id →
`{headline, source, timestamp}`) before building Phase 6 — CLAUDE.md notes
this was deferred to "Segment 2, Chunk D" without pinning the endpoint. If
it doesn't exist yet, Phase 6 needs a small Segment 1 addition first.
