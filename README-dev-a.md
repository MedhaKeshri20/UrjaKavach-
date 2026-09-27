# Urja Kavach — Dev A (Backend / Integration)

> **Status: ✅ DONE for PRD v1.0 scope — feature-complete, tested & bug-checked.**
> All **91 tests pass** (43 contract + 48 backend, incl. `/audit`). Verified
> end-to-end on localhost (`uvicorn`): every endpoint + the full signal→cascade
> flow works, and the frontend is wired to all of it (originally the Next.js
> `frontend/` app, since replaced by India Connect Portal — see below).
> A security pass found and fixed two issues (long-password 500 via bcrypt's
> 72-byte limit; wildcard-CORS combined with credentials). **Before deploying,
> set a real `JWT_SECRET`** — see [Auth](#auth-jwt) and the Security notes in
> [PROJECT_GUIDE.md](PROJECT_GUIDE.md#security-notes).
>
> **PRD v1.3 work landed since this doc's v1.0 sign-off** (see [SPEC.md](SPEC.md)):
> the contract/DB widening (Phase 1), Recommend's wrong-oil gate + real route
> cost (Phase 2), Predict's real power-stress computation + assumption-
> override audit via the new `POST /assumptions/override` endpoint (Phase 3),
> and Watch's real RAG+LLM scoring agent (Phase 4 — Groq + ChromaDB, falling
> back to the deterministic stub on any failure), the knowledge graph
> (Phase 5 — `backend/agents/graph.py`, self-contained, no API change), and
> the geospatial data layer (Phase 6 — `backend/agents/geo.py`, a curated
> AIS replay set + hand-authored corridor GeoJSON, wired into `cascade.py`'s
> new fifth step and the new `GET /geo/state` endpoint), and the dark-ship
> anomaly detector (Phase 7 — `backend/agents/anomaly.py`, an `IsolationForest`
> over AIS features; the AIS source itself is now config-driven via
> `Settings.ais_data_path`/`AIS_DATA_PATH`, defaulting to the committed replay
> set), and the backtest/validation module (Phase 8 —
> `backend/agents/backtest.py` replays a curated Red Sea/Houthi case through
> the real Watch agent; `GET /backtest/{id}` is a fully standalone read that
> never mutates `RiskState`), and the alarm-language classifier + LLM
> conservation copy (Phase 9 — `backend/agents/alarm.py`, a TF-IDF+LogReg
> classifier over a committed general-tone corpus, feeding Watch's prompt
> and offline stub as one more context line/bump; `backend/agents/
> conservation.py` replaces `GET /public/status`'s static tips with
> LLM-generated, scenario-specific copy behind the same response shape).
> **319 tests pass** now (up from 91).

This is the **Dev A** slice from PRD Section 9: the API gateway, event bus,
database + config seeding, the **Recommend** and **Advise** agents, the
approve/audit flow, JWT auth, and the deployment scaffolding. It builds strictly
on top of Dev B's frozen contract (`backend/schemas/`) — see the main
[README](README.md) and never edit `contract.py`.

Predict is now the real v1.3 model (`backend/agents/predict.py`, PLAN.md
Phase 3), and Watch is now the real RAG+LLM agent too
(`backend/agents/watch.py`, PLAN.md Phase 4), with the deterministic stub
(`backend/agents/stubs.py`) kept as its internal offline fallback — every
agent in the cascade is real now.

## Run it

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.app:app --reload                  # http://localhost:8000
```

Startup creates the tables and seeds `backend/seed/*.json`. Interactive API docs
at `http://localhost:8000/docs`.

Or the whole stack in one command:

```bash
docker compose up          # api (+ postgres + redis for the prod-parity path)
```

## The cascade (demo money-shot)

```bash
# inject a headline -> Watch -> Predict -> Recommend -> Advise, live
curl -X POST localhost:8000/signal -H 'content-type: application/json' \
  -d '{"corridor":"hormuz","headline":"Tanker seized near Hormuz","severity":0.4,
       "id":"news_412","source_ids":["news_412","ais_88"]}'

curl localhost:8000/state                 # full RiskState, all blocks populated
curl 'localhost:8000/reroutes?sort=speed' # ranked options + score breakdown
curl localhost:8000/public/status         # simplified citizen view
```

## Endpoints (PRD §8)

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | Liveness probe |
| GET  | `/state` | Current shared `RiskState` |
| POST | `/signal` | Inject a signal → runs the cascade |
| POST | `/simulate` | What-if: strict `Assumptions` → `Impact` (pure, no mutation) |
| POST | `/assumptions/override` | **Auth required** — log a slider commit that diverges from default → `audit_log` (F20, v1.3 Phase 3) |
| GET  | `/reroutes?sort=cost\|speed\|balanced` | Ranked options + component scores |
| GET  | `/geo/state` | Live `geo` block + corridor/refinery config + AIS tanker tracks (F11/F13, v1.3 Phase 6) |
| POST | `/approve` | **Official-only** — approve a reroute → writes `audit_log` |
| GET  | `/audit?limit=` | **Official-only** — replayable audit log, most recent first (F9) |
| GET  | `/public/status` | Citizen status band + conservation plan + action feed |
| WS   | `/ws/state` | Full-snapshot push on every state change |

> `/audit` was added to feed the Next.js official cockpit's live audit-trail
> panel. Like `/approve`, it's gated to the `official` role.
>
> **Planned (PRD v1.3, not yet built):** `GET /backtest/{id}`
> (historical score-vs-Brent replay — [PLAN.md](.claude/docs/PLAN.md) Phase 8).

## Auth (JWT)

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Create an account with a role, returns a token |
| POST | `/auth/login` | Verify credentials, returns a token |
| GET  | `/auth/me` | Current user (requires Bearer token) |

Register takes a **role** — `"citizen"` or `"official"` (the frontend renders
this as a dropdown; it matches `type UserRole = "citizen" | "official"`). Both
register and login return `{access_token, role, dashboard}`, so the portal can
route straight to the matching dashboard on signup/login. Officials get a token
that unlocks official-only actions like `/approve`; the audit trail records the
approver from the token, not a client-supplied name.

```bash
# register an official, capture the token, approve as them
TOKEN=$(curl -s -X POST localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"email":"officer@gov.in","password":"secret123","role":"official"}' | jq -r .access_token)
curl -X POST localhost:8000/approve -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"supplier":"ru_urals"}'
```

Passwords are bcrypt-hashed; tokens are HS256 JWTs. Config lives in `.env`
(`JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRY_MINUTES`) — see `.env.example`.
Set a real random `JWT_SECRET` in production.

## Design notes

- **State store** (`backend/state_store.py`) merges each validated agent block,
  **re-validates the whole `RiskState`** (the drift alarm), stamps tz-aware UTC
  `updated_at`, persists, and publishes a **full snapshot** on `state.updated`.
- **Event bus** (`backend/bus.py`) is in-memory now, Redis Streams later —
  same interface. Agents publish/subscribe, never call each other.
- **DB** (`backend/models.py`) is SQLite by default, Postgres via `DATABASE_URL`.
  All numeric columns are `Float` (never `INTEGER`) per the contract's rule #2.
- **Config-driven scale**: a new corridor/supplier/refinery is one row in
  `backend/seed/*.json`, no code change.

## Tests

```bash
python -m pytest        # 319 tests: contract (101) + agent/store/API/auth/audit/watch/rag/llm/graph/geo/anomaly/ais/backtest/alarm/conservation
```

## Frontend

**India Connect Portal** (`../India Connect Portal`) consumes every endpoint
above — run the backend first, then `cd "India Connect Portal" && npm run dev`.
See [../India Connect Portal/spec.md](../India%20Connect%20Portal/spec.md) and
[../PROJECT_GUIDE.md](../PROJECT_GUIDE.md).
