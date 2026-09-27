# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Urja Kavach ("Energy Shield") — an AI-driven resilience system for India's crude-oil
supply chain, built for the ET AI Hackathon 2026. A signal (e.g. a headline) flows
through four agents — **Watch → Predict → Recommend → Advise** — each merging a
validated block into one shared `RiskState` object, which is pushed live to the
**India Connect Portal** frontend (official cockpit + public citizen board) over
a WebSocket.

### Branch state & the plan (read first)

`main` is the **single integrated branch** — the historical `swosti_kavach`
merge (Dev A's backend + Dev C/D's original Next.js frontend onto Dev B's
frozen contract) is already done (`git diff main swosti_kavach` is empty).
Everything described in the Architecture section below is present on `main`
today: the frozen contract, the full cascade, real Recommend/Advise/Predict/
Watch agents, the full REST/WS API + JWT auth, and the India Connect Portal
frontend. **323 backend tests pass.**

The original Next.js `frontend/` (Dev C/D's PRD v1.0 build) has been removed
from the repo. **`India Connect Portal/`** (Vite + TanStack Start) replaced it
as of `PLAN.md` Segment 2's stack switch, has landed the full v1.3 Segment 2
scope (Chunks A–I), and is the only frontend here now. See `India Connect
Portal/spec.md` for the full phased build history behind it.

The product spec has since moved to **v1.3**, which adds ten features
(geospatial/AIS layer, a historical backtest, power-sector stress, a wrong-oil
eligibility gate + real route cost, a dark-ship anomaly detector, an
alarm-language score, and a fact/estimate/internal assumption-sourcing
framework) that touch the contract, the DB, every agent, and the frontend.

**[PLAN.md](.claude/docs/PLAN.md) Segment 1, Phases 1–9 have landed** (see
**[SPEC.md](SPEC.md)** for the exact specs and decisions):
- **Phase 1** — contract + DB widened to the v1.3 shape.
- **Phase 2** — Recommend's wrong-oil hard gate (`grade_ok`/`rank_eligible`) and
  real `true_cost` (crude + war-risk insurance + detour) ranking, replacing
  Phase 1's mechanical placeholders.
- **Phase 3** — Predict is now a real agent (`backend/agents/predict.py`,
  replacing the stub): `power_stress_pct` is genuinely computed, `gdp_delta_pct`
  uses the corrected `gdp_oil_sensitivity` coefficient (not the old hardcoded
  `0.066`), and assumption-slider overrides are audited via a new
  `POST /assumptions/override` endpoint, snapshotted onto
  `RiskState.assumption_overrides` only at Approve time.
- **Phase 4** — Watch is now a real agent (`backend/agents/watch.py`): RAG
  retrieval (ChromaDB, local embeddings) grounds a Groq LLM scoring call
  (`llama-3.3-70b-versatile` primary, `llama-3.1-8b-instant` fallback),
  falling back to the deterministic stub on any of: `USE_REAL_AGENTS` off
  (the default), no `GROQ_API_KEY`, an unrecognized corridor, empty
  retrieval, or an LLM failure on both model tiers. `confidence`/`band` come
  from retrieval agreement, never the LLM's self-report.
- **Phase 5** — `backend/agents/graph.py`: a NetworkX supplier→corridor→
  refinery model, answering "if hormuz closes, what's affected?" via
  `affected_by()`. Deliberately a self-contained library only — it doesn't
  touch `RiskState`, `cascade.py`, or the API yet; Phase 6 is what actually
  calls it to populate `geo.affected_refinery_ids`.
- **Phase 6** — the geospatial data layer: a curated, deterministic 16-tanker
  AIS replay set (`backend/agents/data/ais_sample.json`, 8-point tracks per
  tanker) and hand-authored corridor GeoJSON polylines
  (`backend/seed/geo/*.geojson`), both wired together by the new
  `backend/agents/geo.py`'s `build_geo()` (reusing Phase 5's `affected_by()`
  for the refinery half). `cascade.py` gained a fifth step that calls it, so
  **`RiskState.geo` is genuinely populated for the first time** (`None` until
  a signal is injected, matching `impact`/`reserve`'s existing pattern). New
  `GET /geo/state` bundles the live `geo` block with corridor/refinery config
  and the raw tanker tracks — the one endpoint Segment 2's map needs.
- **Phase 7** — the dark-ship anomaly detector: `backend/agents/anomaly.py`
  fits a `sklearn.ensemble.IsolationForest` (fixed `random_state`, fit once
  and cached) over four per-vessel features derived from Phase 6's AIS
  replay set — transponder-gap length, heading-change rate, speed
  variability, and deviation from the tanker's own initial course (not a
  distance to the shared corridor polyline — that confounds with each
  clean tanker's seeded "lane" offset, verified empirically before being
  rejected). Three of Hormuz's four curated tankers are a synthetic "went
  dark" case; `geo.dark_tanker_ids` is now genuinely populated (filtered by
  the signal's elevated corridors, like `at_risk_tanker_ids`), and the
  corridor-scoped dark-tanker count reaches both Watch's real LLM prompt
  and its offline stub fallback as one more grounded signal — never blended
  into the score arithmetically. The AIS source itself is config-driven
  (`Settings.ais_data_path` / `AIS_DATA_PATH`, defaulting to the committed
  replay set) — the one seam a live feed would plug into without touching
  `geo.py`/`anomaly.py`, proven by `tests/test_ais.py`.
- **Phase 8** — the backtest/validation module: `backend/agents/backtest.py`
  replays one curated historical case (the Red Sea/Houthi shipping crisis,
  Nov 2023 – Mar 2024, on `suez_cape`) through the real `run_watch()`
  chronologically, with a new `as_of` cutoff threaded through
  `retrieve()`/`run_watch()` so no snippet dated after the headline being
  scored ever leaks in (defaults to `None` everywhere in the live cascade —
  zero behavior change there). `GET /backtest/{id}` returns Watch's score
  timeline, an illustrative (hand-curated, explicitly labeled) Brent price
  timeline, and the lead time between when each first crosses its own
  threshold. It's a fully standalone, side-effect-free read — it never
  writes to `RiskState.validation` or triggers a WS push, unlike every
  cascade-adjacent endpoint elsewhere in the API. `validation` therefore
  stays permanently `None` on `RiskState` in this codebase; the backtest
  result lives only in the `GET /backtest/{id}` response.
- **Phase 9** — the two cheapest, lowest-priority v1.3 additions.
  `backend/agents/alarm.py`: a TF-IDF + logistic-regression classifier over a
  small, hand-curated, committed corpus of **general** alarming-vs-calm
  language (67 rows — not oil-crisis outcomes, though it does include a
  generic conflict/security vocabulary sub-group, added after the first
  disaster-only draft measurably failed to discriminate on real oil-corridor
  headlines). Its binary verdict reaches Watch's real prompt as one more
  context line (mirroring Phase 7's dark-ship line — never blended into any
  score) and the offline stub as a matching `+8.0` bump; unlike the
  dark-ship line, it is **not** suppressed under `as_of`, since tone
  classification has no present-day-snapshot dependency. Separately,
  `GET /public/status` now calls `backend/agents/conservation.py`'s
  `generate_conservation_copy()` for LLM-generated, scenario-specific
  `message`/`conservation_plan` content (cached by `level|corridor_name`,
  falling back to the original static copy with no API key) — `status`
  itself stays a rule-based severity threshold, never LLM-decided.

No features remain in the v1.3 scope Segment 1 owns — every agent/data-layer
phase is real code, 323/323 tests green. **Phase 10** (determinism/cut-over)
is also **✅ landed**: a live `GROQ_API_KEY` became available, real
`.llm_cache/` entries for the canonical demo scenario + the backtest replay
are committed, and the full cascade was verified end-to-end against the real
agent path (see PLAN.md's Phase 10 section for the full breakdown, including
a real test-suite hermeticity bug found and fixed along the way). Segment 2
(frontend/integration) is also done — see `India Connect Portal/spec.md`
Phases 0–10, all landed.

**[PLAN.md](.claude/docs/PLAN.md) is the forward-looking build plan for that gap** — read it
before picking up any new feature work. It splits the remaining work into two
segments (AI + Backend; Frontend + Integration) and phases the backend/AI
segment into vertical slices, each touching schema + DB + agent logic together.

[PROJECT_GUIDE.md](PROJECT_GUIDE.md) holds the architecture deep-dive, the full
PRD (v1.0 baseline + v1.3 delta), and the historical per-developer status board
for what already shipped. [README.md](README.md) is the main project README —
pitch, live demo links, quick start, and the contract layer in depth — and
[README-dev-a.md](README-dev-a.md) documents the backend API;
[SETUP.md](SETUP.md) is the from-scratch local run guide;
[DEV_B_ROADMAP.md](.claude/docs/DEV_B_ROADMAP.md) holds AI-implementation detail (LLM client,
RAG, prompt design) supporting PLAN.md's Watch/Predict/knowledge-graph phases.

## Commands

### Backend (Python 3.11, from repo root)

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.app:app --reload                   # http://localhost:8000, docs at /docs
python -m pytest                                    # full suite
python -m pytest tests/test_contract.py             # one file
python -m pytest tests/test_contract.py::test_name  # one test
python -m pytest -k "watch"                          # by keyword
```

No `.env` is required for local dev (SQLite + in-memory bus + a dev-only JWT
secret are the defaults — see `.env.example`). The DB auto-creates and seeds
`backend/seed/*.json` on startup (idempotent, safe to re-run).

### Frontend (Node 20+, from `India Connect Portal/`)

```bash
cd "India Connect Portal"
npm install
npm run dev      # Vite dev server, http://localhost:8080 — start the backend first
npm run build    # production build (client + SSR + nitro node-server bundle)
npm run preview  # serve the production build
npm run lint
```

The frontend proxies `/api/*` to the backend via `vite.config.ts`'s dev-only
proxy (no CORS needed); the WebSocket connects directly to
`ws://localhost:8000/ws/state`. Point at a non-default backend with
`BACKEND_URL` (see `India Connect Portal/.env.example`).

### Whole stack

```bash
docker compose up   # backend image + Postgres + Redis (prod-parity path)
```
Local dev normally doesn't need Docker — SQLite + in-memory bus require zero setup.

## Architecture

### The contract is law

`backend/schemas/contract.py` is a **frozen** Pydantic v2 schema — the single
source of truth for the shape of `RiskState` and every agent's output envelope.
**Never edit it casually.** It imports only `datetime`, `typing`, and `pydantic` —
no DB/LLM/FastAPI imports, so any component can depend on it without circular
imports. Always import models from `backend.schemas` (the re-export), not from
`contract.py` directly.

Locked rules baked into the schema (see [README.md](README.md) for the full
rationale on each):
- `confidence` is `Literal["low","medium","high"]` — full words only; an agent
  that produces `"med"` must normalize it before it touches the state.
- All numeric fields are `float` except `Reroute.rank` (`int`).
- Agent-written blocks (`impact`, `assumptions`, `reserve`, `reroutes`, `geo`,
  `validation`, `assumption_overrides`) are optional/default-empty on
  `RiskState` so a mid-cascade snapshot validates — but each per-agent
  envelope (`WatchAgentOutput`, `PredictAgentOutput`) keeps its own fields
  required. `Assumptions` (v1.3) is now typed: each value is an
  `AssumptionEntry` (`{value, type: fact|estimate|internal, range, src}`), not
  a bare float — see [SPEC.md](SPEC.md).
- The WebSocket always pushes a **full `RiskState` snapshot**, never a diff.
- Every model has `extra="forbid"` — an unannounced field raises loudly. This is
  the intentional drift alarm; if you need a new field, update the contract and
  the mock `/state` together, don't route around it.

Contract-change protocol (from PROJECT_GUIDE.md): propose the field/type/why,
update `contract.py` and the API in the same change, and make sure `pytest`
still passes — the test suite locks the contract's shape.

### The cascade

```
POST /signal {corridor, headline, severity, id, source_ids}
  -> Watch     score corridor risk                  -> merge_watch()
  -> Predict   glass-box domino model from severity  -> merge_predict()
  -> Recommend rank supplier+route options           -> merge_reroutes()
  -> Advise    reserve depletion simulation          -> merge_reserve()
  -> Geo       at-risk tankers + affected refineries -> merge_geo()
```
Implemented in `backend/cascade.py`, orchestrated by `backend/state_store.py`
(`StateStore`). Every merge re-validates the *entire* `RiskState` from a fresh
dump (the drift alarm), stamps a tz-aware UTC `updated_at`, persists, and
publishes a full snapshot on the `state.updated` topic — which
`ConnectionManager` (in `backend/app.py`) broadcasts to every connected
WebSocket client. This is why one injected signal animates the whole frontend
in one sweep.

Agents never call each other directly — they only interact through
`backend/bus.py` (`InMemoryBus`, an in-memory pub/sub behind the `EventBus`
protocol; a Redis Streams implementation can drop in later behind the same
interface without touching agent code).

**Watch** (`backend/agents/watch.py`, real RAG+LLM scoring — Groq + ChromaDB,
falling back internally to the deterministic `backend/agents/stubs.py` logic
on any failure), **Predict** (`backend/agents/predict.py`, the sourced v1.3
glass-box domino model), **Recommend** (`backend/agents/recommend.py`,
min-max cost/speed/compatibility scoring with the real wrong-oil gate +
true-cost ranking), and **Advise** (`backend/agents/advise.py`, reserve
depletion sim) are all real, non-stub agents now — every agent in the
cascade emits its final v1.3 envelope. `backend/agents/stubs.py` still
exists as Watch's offline fallback, not dead code. A fifth cascade step,
**Geo** (`backend/agents/geo.py`, `build_geo()`), stamps `RiskState.geo`
for the first time (F11/F13) — it's a data-layer step, not one of the
PRD's four core agents, so it isn't part of the Watch→Predict→Recommend→
Advise pitch above, but every signal now populates it too, including real
`dark_tanker_ids` from `backend/agents/anomaly.py`'s `IsolationForest`
(F18) since Phase 7. Since Phase 9, Watch's prompt (and its offline stub)
also fold in `backend/agents/alarm.py`'s binary alarm-language verdict —
never a `RiskState` field, purely a prompt-context line/stub bump.

### Backend layout

```
backend/
├── schemas/contract.py   frozen contract (see above)
├── config.py              env-driven Settings (SQLite/Postgres, in-mem/Redis bus, JWT)
├── db.py, models.py       SQLAlchemy engine/session + the 6 PRD tables + users
├── seed.py, seed/*.json   idempotent config seeding — a new corridor/supplier/
│                          refinery is one JSON row, not a code change
├── bus.py                 EventBus protocol + InMemoryBus pub/sub
├── state_store.py         StateStore: merge -> re-validate -> persist -> publish
├── cascade.py             signal -> Watch -> Predict -> Recommend -> Advise -> Geo
├── agents/
│   ├── predict.py         real: sourced v1.3 glass-box domino model (F3/F15/F20)
│   ├── recommend.py       real: min-max scoring, exposes component scores
│   ├── advise.py          real: SPR reserve depletion simulation
│   ├── watch.py            real: RAG (rag.py) + Groq LLM scoring (llm.py)
│   ├── graph.py           real: NetworkX supplier/corridor/refinery model + affected_by() (F10)
│   ├── ais.py             AIS replay loading only (list_tankers()) -- split out to
│   │                      avoid a geo.py <-> anomaly.py circular import; source is
│   │                      config-driven (Settings.ais_data_path / AIS_DATA_PATH)
│   ├── geo.py             real: Geo block (build_geo(), F11/F13/F18)
│   ├── anomaly.py         real: IsolationForest dark-ship detector (F18)
│   ├── backtest.py        real: historical replay + lead-time measurement (F14)
│   ├── alarm.py           real: TF-IDF+LogReg alarm-language classifier (F19)
│   ├── conservation.py    real: LLM conservation copy for /public/status (F7 slice)
│   └── stubs.py           Watch's deterministic offline-fallback stand-in
├── api/routes.py, app.py  create_app() factory; REST + WS routes; CORS
├── auth/                  User model, register/login schemas, JWT issuing
└── middleware/auth.py     get_current_user / require_role("official") deps
```

Numeric DB columns are always `Float`, never `INTEGER` — truncating e.g.
`68.5 -> 68` would silently violate the contract. `create_app()` builds an
isolated app so tests can run against a throwaway DB; `app = create_app()` at
the bottom of `app.py` is the ASGI entrypoint (`uvicorn backend.app:app`).

Auth: JWT (HS256, `pyjwt`), roles are `"citizen"` | `"official"`. `/approve`
and `/audit` are official-only via `Depends(require_role("official"))`. The
audit trail always records the approver from the verified token, never a
client-supplied name.

### API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/state` | current `RiskState` |
| POST | `/signal` | inject a signal, runs the full cascade |
| POST | `/simulate` | pure what-if: `Assumptions` -> `Impact`, no mutation |
| POST | `/assumptions/override` | auth required, any role: log a slider commit diverging from default -> `audit_log` |
| GET | `/reroutes?sort=cost\|speed\|balanced` | ranked options + score breakdown |
| GET | `/geo/state` | live `geo` block + corridor/refinery config + AIS tanker tracks (F11/F13) |
| GET | `/backtest/{id}` | one curated historical case: Watch score timeline + illustrative Brent timeline + lead time (F14); never mutates `RiskState` |
| POST | `/approve` | official-only, writes `audit_log` |
| GET | `/audit?limit=` | official-only, replayable log |
| GET | `/public/status` | citizen-facing simplified status; `message`/`conservation_plan` are LLM-generated when available (F7 slice), `status` stays rule-based |
| WS | `/ws/state` | full-snapshot push on every state change |
| POST | `/auth/register`, `/auth/login`, GET `/auth/me` | JWT auth |

### Frontend layout (`India Connect Portal/`, Vite + TanStack Start, React 19, Tailwind v4, shadcn/ui)

```
India Connect Portal/
├── src/
│   ├── routes/                 TanStack Start file-based routes (see routes/README.md)
│   │   ├── index.tsx           marketing landing
│   │   ├── auth.tsx            login/register
│   │   ├── mission.tsx         Mission Control — one-button cascade demo entry
│   │   ├── official.tsx        the cockpit: gauge, map, simulator, reroutes, audit
│   │   ├── public.tsx          calm public status board (read-only)
│   │   └── __root.tsx          app shell, wraps every route
│   ├── components/kavach/      domain components (map, header, gauge, RequireRole)
│   ├── components/ui/          shadcn/ui primitives
│   ├── hooks/useRiskState.ts   subscribes to WS /ws/state, drives every panel
│   ├── lib/api.ts              REST client, attaches Bearer token
│   ├── lib/session.ts          client-side session cookie set after login/register
│   ├── lib/auth.tsx            auth context/provider
│   ├── types/contract.ts       TypeScript mirror of backend/schemas/contract.py
│   ├── router.tsx, routeTree.gen.ts   TanStack Router setup (routeTree.gen.ts is generated — don't hand-edit)
│   └── server.ts, start.ts     SSR entry points
└── vite.config.ts              dev proxy /api/* -> backend; node-server nitro preset for Docker builds
```

There's no Next-style middleware here — `RequireRole`
(`src/components/kavach/RequireRole.tsx`) role-gates client-side instead:
`official.tsx` wraps its content in `<RequireRole role="official">`,
`public.tsx` in `<RequireRole role="citizen">`; a signed-in user with the
wrong role is redirected to their own dashboard, not just blocked.

One signal, one sweep: `useRiskState()` is the single subscription point: a
`POST /signal` triggers a `state.updated` WS push, and every panel across every
page re-renders from that one hook. When adding a new panel, read from this
hook rather than making a parallel fetch.

`types/contract.ts` must be kept in sync by hand with
`backend/schemas/contract.py` — there's no codegen; if you change the Python
contract, update this file too.

See `India Connect Portal/spec.md` for the full phased build history and
`.claude/docs/india-connect-portal/AGENTS.md` for its Lovable.dev connector
notes and secrets-handling rules.

## Testing

`tests/` covers both the frozen contract (`test_contract.py`, 101 tests: full
round-trip, required/optional fields, `extra="forbid"`, range/enum validation,
plus v1.3's `AssumptionEntry`/`AssumptionOverride`/`CostBreakdown`/`Geo`/
`Validation` models) and the backend (`test_advise.py`, `test_api.py`,
`test_auth.py`, `test_predict.py`, `test_recommend.py`, `test_state_store.py`,
`test_watch.py`, `test_rag.py`, `test_llm.py`, `test_graph.py`, `test_geo.py`,
`test_anomaly.py`, `test_ais.py`, `test_backtest.py`, `test_alarm.py`,
`test_conservation.py` — **323 tests total**).
`tests/conftest.py` puts the repo root on `sys.path` so `pytest` runs from
anywhere without an editable install, and holds an autouse fixture
(`_isolate_real_agents_flag`) that forces `USE_REAL_AGENTS=0`/
`GROQ_API_KEY=""` for every test by default — added in Segment 1 Phase 10
after a developer's real local `.env` was found to silently flip
`test_api.py`/`test_auth.py`/`test_backtest.py` onto the real LLM path and
break their pinned assertions (they never overrode these two fields
themselves, unlike `test_watch.py`'s own file-local `_real_agents_on`
fixture, which still correctly re-enables the real-agent path for the tests
that specifically want it — monkeypatch is last-write-wins, so the
file-local override still applies after the suite-wide default). Whenever a
mock or real `/state` response changes, assert it still validates against
`RiskState` — that's the team's drift alarm for the whole contract. Watch's
real-agent tests never make a live network call — `backend.agents.llm`'s
Groq client and `backend.agents.rag`'s retrieval are monkeypatched/isolated
per test — and now, genuinely (not just by accident of an unset ambient
env), no `GROQ_API_KEY` is ever required for `pytest` to pass, regardless of
what the developer's own local `.env` has configured.

There is no frontend test suite currently; verify UI changes in
`India Connect Portal/` by running `npm run dev` against a running backend
and exercising the flow in-browser (`npm run build` for a production/typecheck
pass).
