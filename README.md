# Urja Kavach ("Energy Shield")

**An AI-driven resilience system for India's crude-oil supply chain — built for
the ET AI Hackathon 2026.**

A signal (a headline, a tanker going dark, a chokepoint closure) flows through
four cooperating agents — **Watch → Predict → Recommend → Advise** — that
score geopolitical risk, model economic fallout, rank executable procurement
reroutes, and simulate Strategic Petroleum Reserve drawdown. One shared
`RiskState` object drives two live portals — a restricted **Official Cockpit**
and a public **Citizen Board** — over a WebSocket, so a single injected signal
animates the whole system in one sweep.

---

## Where each judging criterion is addressed

| Criterion | Where to look |
|---|---|
| **Relevance to Problem Statement** | [The 30-second pitch](#the-30-second-pitch) |
| **Innovation & Creativity** | [Why this isn't a dashboard with a chatbot bolted on](#why-this-isnt-a-dashboard-with-a-chatbot-bolted-on) |
| **Technical Implementation** | [What's real (not a mockup)](#whats-real-not-a-mockup) · [The shared contract layer](#the-shared-contract-layer) · `python -m pytest` (323/323 pass) |
| **Business Viability** | [Business viability & path to deployment](#business-viability--path-to-deployment) |
| **Presentation & Clarity** | The demo video + [Live demo](#live-demo) links below |
| **Impact & Scalability** | [Business viability & path to deployment](#business-viability--path-to-deployment) |

---

## Live demo

| | |
|---|---|
| **Official Cockpit** | [urja-kawach-frontend-979294330096.us-central1.run.app/official](https://urja-kawach-frontend-979294330096.us-central1.run.app/official) |
| **Public Board** | [urja-kawach-frontend-979294330096.us-central1.run.app/public](https://urja-kawach-frontend-979294330096.us-central1.run.app/public) |
| **Mission Control** (inject a signal) | [urja-kawach-frontend-979294330096.us-central1.run.app/mission](https://urja-kawach-frontend-979294330096.us-central1.run.app/mission) |
| **Backend API** | [urja-kawach-api-979294330096.us-central1.run.app](https://urja-kawach-api-979294330096.us-central1.run.app) (interactive docs at `/docs`) |

Both services run on **Google Cloud Run**. To try the full demo: open the
live link, click **Get started**, register an account picking either role
(**Official** or **Citizen**), then — as an Official — go to **Mission
Control** and click **Inject signal** to watch the cascade run end to end on
both portals live.

---

## The 30-second pitch

India imports ~88% of its crude oil; 40–45% of it transits the Strait of
Hormuz. Strategic reserves cover only ~9.5 days, and economies without
automated rerouting take ~47 days longer to stabilise after a shock. Existing
planning tools can't model geopolitical scenarios in real time, evaluate
alternative corridors, or coordinate refiners, logistics, and reserves in one
place.

**Urja Kavach demonstrates the full loop**: a live headline enters → the risk
gauge spikes → economic dominoes recompute (GDP drag, price rise, refinery
run-rate, power-sector stress) → reroute options re-rank by real delivered
cost → the SPR drawdown plan updates → an official approves → the public
board shows a calm, plain-language advisory. Signal to decision in under a
minute, on stage — every number traceable back to a source.

- **Grounded** — RAG-backed signal scoring (Groq LLM + ChromaDB) and a
  supplier → corridor → refinery knowledge graph; every score links back to
  its retrieved sources.
- **Trustworthy** — explicit, adjustable assumptions typed as
  fact/estimate/internal, human-in-the-loop approval, and a full audit log
  including every slider override.
- **Scalable** — event-driven core; a new corridor/supplier/refinery is one
  config row, not a code change; agents are stateless.
- **Validated** — a backtest module replays a real historical crisis (the
  2023–24 Red Sea/Houthi shipping disruption) through the real Watch agent
  and measures its signal lead-time against the actual Brent price move.

---

## What's real (not a mockup)

Every one of the four agents is a real, tested implementation, not a stub
wired up for a demo:

| Agent | What it actually does |
|---|---|
| **Watch** | RAG retrieval (ChromaDB, local ONNX embeddings) grounds a Groq LLM (`llama-3.3-70b-versatile`, with an 8B fallback) scoring call; falls back to a deterministic offline stub on any failure — never a hard crash on stage. |
| **Predict** | A sourced, glass-box domino model: every coefficient is either a cited fact, a researched estimate, or an honestly-labeled internal constant — two of which were found to be measurably wrong during v1.3's sourcing pass and corrected, not just documented. |
| **Recommend** | Min-max cost/speed/compatibility scoring with a hard wrong-oil eligibility gate (a refinery genuinely can't run every crude grade) and real true-cost ranking (crude + war-risk insurance + detour cost). |
| **Advise** | A real Strategic Petroleum Reserve depletion simulation. |
| **Geo** *(data layer)* | A curated 16-tanker AIS replay + hand-authored corridor geometry, plus a real `IsolationForest` (scikit-learn) dark-ship anomaly detector — the project's one genuine unsupervised-ML component. |
| **Backtest** | Replays a real historical crisis chronologically through the real Watch agent with no future-information leakage, and measures signal lead-time against an illustrative Brent price timeline. |
| **Alarm + conservation copy** | A small TF-IDF + logistic-regression classifier for alarm-language tone, and LLM-generated, scenario-specific public-facing guidance. |

**323 backend tests pass**, covering the frozen contract plus every agent,
the API, auth, and the WebSocket push path.

---

## Why this isn't a dashboard with a chatbot bolted on

The easy version of this project is "ask an LLM to rate the headline 0–100
and show it on a gauge." We deliberately didn't build that, because it
doesn't survive contact with a real official who has to act on the number:

- **Confidence comes from retrieval agreement, never the LLM's self-report.**
  LLMs are well known to be poor at self-rating their own certainty. Watch's
  `confidence`/`band` are computed from how much the retrieved sources agree
  with each other — the LLM scores the risk, but it doesn't get to grade its
  own homework.
- **The anomaly detector's features were chosen by rejecting the obvious
  one.** The first design measured each tanker's distance from the shared
  corridor polyline. That confounds with each clean tanker's own seeded lane
  offset — verified empirically, not assumed — so it was rejected in favor of
  deviation from the tanker's *own* initial course, which isolates the
  actual anomaly instead of penalizing tankers for sailing their normal lane.
- **Assumptions are typed, not bare numbers.** Every coefficient behind the
  economic model (`Predict`) is tagged `fact`, `estimate`, or `internal` with
  a source and a range — so an official can see, and challenge, exactly
  which numbers are load-bearing research versus a judgment call, instead of
  trusting an opaque model output. Two of these coefficients were found to
  be measurably wrong during the v1.3 sourcing pass and were corrected —
  a real methodology check on the model, not just documentation.
- **A hard eligibility gate, not just a ranking.** `Recommend` doesn't just
  sort reroutes by cost — it enforces a wrong-oil gate first, because a
  refinery genuinely cannot process every crude grade. A plausible-looking
  cheap reroute that's physically infeasible is filtered out, not
  deprioritized.
- **Validated against a real crisis, not synthetic data.** `Backtest`
  replays the actual 2023–24 Red Sea/Houthi disruption chronologically
  through the real Watch agent with a hard `as_of` cutoff — no future
  headline can leak into a past score — and measures the agent's lead time
  against the real Brent price move. Most hackathon "AI risk scores" are
  never checked against a real historical outcome; this one is.

---

## Architecture

```
POST /signal {corridor, headline, severity}
  → Watch      real RAG + LLM corridor risk scoring
  → Predict    sourced glass-box economic domino model
  → Recommend  wrong-oil gate + true-cost reroute ranking
  → Advise     SPR reserve depletion simulation
  → Geo        AIS tankers + affected refineries + dark-ship flags
       ↓
  one shared RiskState, re-validated on every merge, pushed as a
  full snapshot over WebSocket to every connected client
       ↓
  Official Cockpit  ·  Public Board   (India Connect Portal)
```

- **`backend/schemas/contract.py`** is a frozen Pydantic v2 contract — the
  single source of truth for the shape of `RiskState`. See
  **[The shared contract layer](#the-shared-contract-layer)** below for the
  full spec.
- **`backend/cascade.py`** orchestrates the five-step pipeline above;
  **`backend/state_store.py`** merges each agent's validated output,
  re-validates the *entire* state (the project's "drift alarm"), and
  publishes a full snapshot — never a diff — to every WebSocket client.
- Agents never call each other directly — they only interact through an
  event bus (`backend/bus.py`), so a Redis Streams implementation can drop in
  later behind the same interface without touching agent code.
- **India Connect Portal** (Vite + TanStack Start, React 19) is the frontend
  — one app, two role-gated views (`/official`, `/public`), both subscribing
  to the same `useRiskState()` WebSocket hook so one injected signal animates
  every panel at once.

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy (SQLite locally / Postgres in prod), Pydantic v2 |
| Auth | JWT (HS256), roles `citizen` \| `official` |
| LLM | Groq (`llama-3.3-70b-versatile` primary, `llama-3.1-8b-instant` fallback) |
| RAG / vectors | ChromaDB + local ONNX MiniLM embeddings (no embeddings API) |
| Knowledge graph | NetworkX |
| Anomaly ML | scikit-learn `IsolationForest` |
| Alarm-language | TF-IDF + logistic regression |
| Frontend | Vite + TanStack Start, React 19, TypeScript, Tailwind v4, shadcn/ui, Recharts, Google Maps JS API |
| Deployment | Docker (backend + frontend images), Google Cloud Run, Cloud SQL/Postgres-compatible |

---

## Business viability & path to deployment

**Who adopts this.** The natural first users are exactly the people who
already own the two halves of this problem in India: **ISPRL** (which
operates the strategic petroleum reserves this system simulates drawdown
for) and **MoPNG-affiliated refiners** (IOCL/BPCL/HPCL-class operations
teams, who already run the reroute/compatibility calls `Recommend` makes
explicit). The Official Cockpit is built for exactly that operational
handoff — approve/audit is role-gated and logged today, not a future
feature.

**Why it's cheap to run, not just cheap to build.** The architecture was
chosen to keep marginal cost near zero between crises:
- **Serverless, stateless agents** — Cloud Run bills per request, not per
  idle hour; nothing runs (and nothing costs money) until a signal comes in.
- **Groq's free/low-cost tier** covers real LLM scoring at hackathon and
  early-pilot volume; the deterministic stub fallback means a rate limit or
  outage degrades gracefully instead of costing more or failing the demo.
- **Local ONNX embeddings, not an embeddings API** — RAG retrieval has no
  per-query external cost.

**Why it scales past one corridor.** Every expansion point in the system is
a config row, not a code change: a new corridor, supplier, or refinery is a
JSON entry in `backend/seed/*.json`, not a redeploy. The same event-driven
core (`EventBus` protocol, currently `InMemoryBus`) is designed to swap to
Redis Streams for multi-instance production load without touching a single
agent. That means the path from "Hormuz demo" to "every corridor India's
crude supply depends on" — and, longer-term, to other single-chokepoint-
dependent commodities like LNG or coal — is additive configuration, not a
rewrite.

**The quantified case for urgency.** Economies without automated rerouting
take ~47 days longer to stabilize after a supply shock (see
[the pitch](#the-30-second-pitch)). Shrinking that decision loop from weeks
to the under-a-minute, signal-to-recommendation loop this system demonstrates
is the entire value proposition — every day of faster rerouting is a day of
avoided price pass-through and reserve burn.

**What's next: automated ingestion.** Today, Watch scores whatever signal
arrives via `POST /signal` — retrieval is grounded in a small, committed
corpus (`backend/agents/rag.py`), and injection happens through Mission
Control, not a live feed. That's a deliberate choice for a deterministic,
offline-safe demo, but a production deployment's real trigger should be a
scheduled News API/RSS/GDELT poller calling that same `/signal` endpoint on
a timer. Because Watch, `cascade.py`, and the contract only ever see "a
signal arrived," this is a thin integration seam, not a redesign — swapping
the trigger source doesn't touch a single line of agent logic.

---

## Repository layout

```
Urja-Kawach/
├── backend/                  FastAPI app, agents, schemas, auth, DB
│   ├── schemas/contract.py   the frozen contract (see below)
│   ├── agents/               watch.py, predict.py, recommend.py, advise.py,
│   │                         geo.py, anomaly.py, backtest.py, alarm.py, conservation.py
│   ├── api/routes.py         REST + WebSocket routes
│   └── cascade.py            signal → Watch → Predict → Recommend → Advise → Geo
├── India Connect Portal/     the frontend (Vite + TanStack Start)
│   ├── src/routes/           official.tsx, public.tsx, mission.tsx, auth.tsx
│   ├── src/components/kavach/ map, gauge, header, role-gating
│   └── spec.md               frontend architecture + full phased build history
├── tests/                    323 backend tests
├── .claude/docs/             AI-build planning docs (PLAN.md, DEV_B_ROADMAP.md, AGENTS.md)
├── SETUP.md                  from-scratch local run guide
├── README-dev-a.md           backend API reference
├── PROJECT_GUIDE.md          architecture deep-dive + full PRD
├── SPEC.md                   phase-by-phase as-built spec log
├── docker-compose.yml        full local stack (Postgres + backend + frontend)
└── frontend's legacy Next.js build has been retired — India Connect Portal is the only frontend now.
```

---

## Quick start — run it locally

Two terminals, no external database required for local dev.

### 0. Prerequisites

- **Python 3.11+**
- **Node.js 20+**
- **Git**

### 1. Get the code

```bash
git clone https://github.com/Titli06/Urja-Kawach.git
cd Urja-Kawach
```

### 2. Terminal 1 — start the backend

```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows (PowerShell/CMD)

pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Up when you see `Uvicorn running on http://127.0.0.1:8000`. First launch
auto-creates the SQLite DB and seeds corridors/suppliers/refineries.
(Optional check: `http://localhost:8000/docs`.)

### 3. Terminal 2 — start the frontend

```bash
cd "India Connect Portal"
npm install
npm run dev
```

Up when you see `Local: http://localhost:8080`. Open it, register an
account (either role), and go — no extra config needed, it talks to the
backend on port 8000 automatically.

### Optional: enable the real Watch agent (RAG + LLM)

By default `USE_REAL_AGENTS=0`, so Watch uses its deterministic offline stub
— nothing else to set up. To try the real RAG+LLM path, copy `.env.example`
to `.env` and set:

```bash
USE_REAL_AGENTS=1
GROQ_API_KEY=<your key>          # free tier at console.groq.com
```

Any missing key, rate limit, or network error falls back to the same
deterministic stub automatically — the demo never hard-fails.

### Run the tests

```bash
python -m pytest        # 323 tests
```

---

## Running the whole stack with Docker

```bash
cp .env.example .env    # fill in POSTGRES_PASSWORD, JWT_SECRET at minimum
docker compose up --build
```

This spins up Postgres, the backend API, and the frontend in one command —
see `docker-compose.yml`'s own comments for the full breakdown of what's
configurable. Two things worth knowing before deploying beyond your own
machine:

- **The frontend's `VITE_*` variables are Docker *build* args, not runtime
  env** — Vite inlines them into the client bundle at `npm run build` time.
  Set `VITE_API_URL`/`VITE_WS_URL` in `.env` to your backend's real public
  address (not the `localhost:8000` default) before building, or a deployed
  frontend won't be able to reach the backend at all.
- **The Google Maps browser key** (`VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_BROWSER_KEY`)
  is the same kind of build arg — left unset, the map silently falls back to
  a static SVG instead of failing the build. Get one at
  [console.cloud.google.com/google/maps-apis](https://console.cloud.google.com/google/maps-apis)
  and **restrict it by HTTP referrer** to whatever domain actually serves the
  frontend.

---

## Documentation index

| Doc | Covers |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Orientation for a new contributor or AI coding agent — start here for architecture context |
| [PROJECT_GUIDE.md](PROJECT_GUIDE.md) | Architecture deep-dive, the full PRD (v1.0 baseline + v1.3 delta), historical status board |
| [.claude/docs/PLAN.md](.claude/docs/PLAN.md) | The live forward build plan — what's shipped vs. planned, phased |
| [SPEC.md](SPEC.md) | Phase-by-phase as-built spec log with every implementation decision and why |
| [README-dev-a.md](README-dev-a.md) | Backend API reference (endpoints, auth, design notes) |
| [.claude/docs/DEV_B_ROADMAP.md](.claude/docs/DEV_B_ROADMAP.md) | AI/ML implementation detail — LLM client, RAG shape, prompt design, knowledge graph |
| [India Connect Portal/spec.md](India%20Connect%20Portal/spec.md) | Frontend architecture and its full phased build history |
| [SETUP.md](SETUP.md) | From-scratch local run guide with troubleshooting |

---

## The shared contract layer

`backend/schemas/contract.py` is a **frozen** Pydantic v2 schema — the single
source of truth for the shape of `RiskState` and every agent's output
envelope. **Never edit it casually** — see the change protocol below.

> **Read this before you build anything that produces or consumes state.**
> If your code disagrees with this contract, your code is wrong — or the
> contract needs a version bump.

### Status

| | |
|---|---|
| Contract version | **v1.3 shape**, shipped — see [SPEC.md](SPEC.md) |
| Pydantic | v2 (`>=2.9,<3`) |
| Tests | 101 conformance tests (part of the repo's 323 total) |
| Contract module depends on | `pydantic` only — **no** LLM/DB/web libs, by design |

`contract.py` imports only `datetime`, `typing`, and `pydantic`. **Keep it
that way** — no DB, no LLM, no FastAPI imports, or you create circular-import
hell and break the "any component can depend on the contract" guarantee.
Always import models from `backend.schemas` (the re-export), not from
`contract.py` directly.

### Models

| Model | Maps to | Produced by |
|---|---|---|
| `CorridorRiskEntry` | value of `corridor_risk[<id>]` | **Watch** |
| `Impact` | `impact` block | **Predict** |
| `AssumptionEntry` | value of each `assumptions[<key>]` | **Predict** |
| `Assumptions` | `assumptions` block | **Predict** |
| `AssumptionOverride` | element of `assumption_overrides[]` | API (slider drag away from default) |
| `CostBreakdown` | `Reroute.cost_breakdown` | **Recommend** |
| `Reroute` | element of `reroutes[]` | **Recommend** |
| `Reserve` | `reserve` block | **Advise** |
| `Geo` | `geo` block | **Geo** + **Anomaly** (dark-ship ids) |
| `Validation` | `validation` block — always `None` on live state; `GET /backtest/{id}` computes real values but never merges them onto `RiskState` | never (see `GET /backtest/{id}`) |
| `RiskState` | whole top-level object | assembled/merged by `state_store.py` |
| `WatchAgentOutput` | `{corridor_risk}` | Watch (strict envelope) |
| `PredictAgentOutput` | `{impact, assumptions}` | Predict (strict envelope) |

### Full state example (steady state)

```json
{
  "scenario": "hormuz_partial_closure",
  "severity": 0.4,
  "corridor_risk": {
    "hormuz": { "score": 68, "confidence": "medium", "band": 10,
                "source_ids": ["news_412", "ais_88", "sanc_3"] }
  },
  "impact": { "supply_gap_pct": 40, "price_rise_pct": 12,
              "gdp_delta_pct": -0.36, "refinery_runrate_pct": 70,
              "power_stress_pct": 4.5 },
  "assumptions": {
    "supply_lost_pct":        { "value": 40,    "type": "fact",     "range": [35, 45],     "src": "brief: Hormuz transit share" },
    "buffer_days":             { "value": 9,     "type": "fact",     "range": [6, 9.5],     "src": "ISPRL SPR capacity vs. typical fill level" },
    "price_elasticity":        { "value": 3,     "type": "estimate", "range": [3, 10],      "src": "inverse of published short-run oil demand elasticity" },
    "power_oil_dependence":    { "value": 0.015, "type": "fact",     "range": [0.01, 0.02], "src": "oil-fired generation share is negligible in India's grid" },
    "gdp_oil_sensitivity":     { "value": 0.03,  "type": "estimate", "range": [0.02, 0.08], "src": "published $10-Brent-rise GDP-drag estimates" },
    "power_stress_multiplier": { "value": 7.5,   "type": "internal", "range": [5, 10],      "src": "no external reference — internal calibration constant" }
  },
  "reroutes": [ { "supplier": "ru_urals", "route": "suez_cape", "days": 22,
                  "cost": 74.1, "compatible": true, "rank": 1,
                  "refinery_id": "jamnagar", "grade_ok": true, "rank_eligible": true,
                  "reason": null,
                  "cost_breakdown": { "crude": 74.1, "war_risk_insurance": 1.48, "detour": 12.0 },
                  "true_cost": 87.58 } ],
  "reserve": { "days_cover": 9.5, "drawdown_per_day": 0.4, "survives_until_refill": true },
  "assumption_overrides": [],
  "geo": { "at_risk_tanker_ids": ["hormuz_01", "hormuz_02", "hormuz_03", "hormuz_04"],
           "dark_tanker_ids": ["hormuz_02", "hormuz_03", "hormuz_04"],
           "affected_refinery_ids": ["jamnagar", "paradip", "vadinar"] },
  "validation": null,
  "updated_at": "2026-01-15T09:22:00Z"
}
```

### Partial state example (Watch has run, Predict has not — a valid mid-cascade snapshot)

```json
{
  "scenario": "hormuz_partial_closure",
  "severity": 0.4,
  "corridor_risk": {
    "hormuz": { "score": 68, "confidence": "medium", "band": 10, "source_ids": ["news_412"] }
  },
  "impact": null,
  "assumptions": null,
  "reroutes": [],
  "reserve": null,
  "assumption_overrides": [],
  "geo": null,
  "validation": null,
  "updated_at": "2026-01-15T09:22:00Z"
}
```

### Locked design decisions (not negotiable without a version bump)

1. **`confidence` is `Literal["low","medium","high"]`** (full words). `"med"`
   is **rejected** at the contract surface — the Watch agent normalizes it
   to `"medium"` before it ever touches the state.
2. **All numeric fields are `float` except `Reroute.rank` (`int`).** Floats
   accept integers cleanly (`score`, `band`, `days`, etc. can be `68` or
   `68.5`). DB implication: use `numeric`/`double precision` columns, never
   `INTEGER`, or you silently truncate `68.5 → 68`.
3. **Agent-written blocks are optional on `RiskState`.** Required:
   `scenario`, `updated_at`, `corridor_risk`, `severity`. Optional: `impact`,
   `assumptions`, `reserve`, `geo`, `validation` (default `None`) and
   `reroutes`, `assumption_overrides` (default `[]`) — so a mid-cascade
   snapshot still validates. Each per-agent envelope (`WatchAgentOutput`,
   `PredictAgentOutput`) keeps its own fields required.
4. **The WebSocket always pushes a full `RiskState` snapshot, never a
   diff.** "Watch just ran" is simply a full object with `impact: null`.
5. **`corridor_risk` keys and `source_ids` are free-form strings** — no
   enum, no regex. Unknown ids are logged as warnings inside the agents,
   never rejected by the schema — this preserves "new corridor = one config
   row."
6. **Only `severity` (0..1) and `score` (0..100) are range-bounded in the
   schema.** Every other percentage is clamped inside the agents so a
   transient value never crashes the cascade on stage.
7. **The contract is closed: `extra="forbid"` on every model.** An unknown
   field (typo or un-announced change) raises loudly — that's the
   intentional drift alarm.

### Contract-change protocol

1. Propose the field/type/why.
2. Update `contract.py` **and** the API in the same change.
3. Make sure `pytest` still passes — the test suite locks the contract's
   shape and is the team's drift alarm for the whole project.

### Testing the contract

```bash
python -m pytest tests/test_contract.py    # 101 tests
```

Locks: the full example round-trips; required vs. optional fields;
`extra="forbid"`; enum/type/range validation; fractional numerics accepted;
`rank` integrity; the Watch-only partial-state case; and the
`AssumptionEntry`/`AssumptionOverride`/`CostBreakdown`/`Geo`/`Validation`
models.

---

*Urja Kavach · ET AI Hackathon 2026 · contract at v1.3 shape · 323/323 tests
passing.*
