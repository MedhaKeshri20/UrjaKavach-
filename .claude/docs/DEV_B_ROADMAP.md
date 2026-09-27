# AI/ML implementation appendix (Watch · Predict · Knowledge Graph · Provenance · Conservation copy)

> **What this file is:** implementation-level detail (LLM client design, RAG
> shape, prompt rubric, formula chains, KG query shape) supporting the AI/ML
> phases of Segment 1 in **[PLAN.md](PLAN.md)** — that file owns phase
> sequencing, dependencies, and status; this file is the "how" for the phases
> that need more than a paragraph. Read PLAN.md first.
>
> **Scope covered here:** PLAN.md Phase 3 (Predict), Phase 4 (Watch + RAG +
> provenance + confidence), Phase 5 (knowledge graph), Phase 9 (conservation
> copy), Phase 10 (determinism/cut-over). PLAN.md's own phase sections already
> carry sufficient detail for Phase 1 (contract v2), Phase 2 (Recommend depth —
> Dev-A-adjacent), Phase 6 (geospatial/AIS data), Phase 7 (dark-ship anomaly
> detector), and Phase 8 (backtest) — this file doesn't duplicate those.
>
> **The golden rule:** the contract in [`backend/schemas/contract.py`](../../backend/schemas/contract.py)
> is law. Everything you build emits the **exact same envelopes** the stubs emit
> today (`WatchAgentOutput`, `PredictAgentOutput`), widened per PLAN.md Phase 1.
> If you keep the signatures, the cascade, the API, and the whole frontend keep
> working. **Never edit `contract.py`** without the contract-change protocol
> (see [README.md](../../README.md)).

---

## Where this fits today

`main` is the single integrated branch — the historical `swosti_kavach` merge is
done, and `backend/agents/stubs.py`, `backend/agents/predict.py`,
`backend/agents/watch.py`, `backend/agents/rag.py`, `backend/agents/llm.py`,
`backend/agents/graph.py`, `backend/cascade.py`, `backend/agents/recommend.py`,
`backend/agents/advise.py`, `backend/agents/ais.py`, `backend/agents/geo.py`,
`backend/agents/anomaly.py`, `backend/agents/backtest.py`,
`backend/agents/alarm.py`, `backend/agents/conservation.py`, the seed JSON,
and the whole frontend all exist on `main` right now. **319 tests pass**
(Phase 3/Predict, Phase 4/Watch, Phase 4-below/Knowledge-graph, PLAN.md Phase
6/geospatial data layer, PLAN.md Phase 7/dark-ship anomaly detector, PLAN.md
Phase 8/backtest, and PLAN.md Phase 9/alarm-language+conservation-copy have
all already landed — see [SPEC.md](../../SPEC.md)).
The line/anchor references below point at those files as they exist today.

---

## Where you plug in (memorise these three seams)

Everything Dev B ships swaps in behind code that already runs. The seams:

| Seam | File / symbol | Called by | You replace |
|---|---|---|---|
| ~~**Watch**~~ | ✅ **already real** — `run_watch(signal: dict) -> WatchAgentOutput` now lives in [`backend/agents/watch.py`](../../backend/agents/watch.py) (PLAN.md Phase 4, landed — see [SPEC.md](../../SPEC.md)), called from `backend/cascade.py`; `run_watch_stub` remains as its internal offline fallback | nothing left to replace |
| ~~**Predict**~~ | ✅ **already real** — `run_predict(assumptions: Assumptions) -> PredictAgentOutput` now lives in [`backend/agents/predict.py`](../../backend/agents/predict.py) (PLAN.md Phase 3, landed — see [SPEC.md](../../SPEC.md)), called from `backend/cascade.py` and `POST /simulate` in `backend/api/routes.py` | nothing left to replace |
| ~~**Predict inputs**~~ | ✅ **already real** — `assumptions_from_severity(severity, ...) -> Assumptions` also lives in `backend/agents/predict.py` now | nothing left to replace |
| ~~**Conservation copy**~~ | ✅ **already real** — `generate_conservation_copy(level, corridor_name)` now lives in [`backend/agents/conservation.py`](../../backend/agents/conservation.py) (PLAN.md Phase 9, landed — see [SPEC.md](../../SPEC.md)), called from `GET /public/status` in `backend/api/routes.py`; the old `_TIPS`/`_LEVELS` dicts' content moved into `conservation.py`'s `_LEVELS_FALLBACK` as the offline fallback | nothing left to replace |
| ~~**Knowledge graph**~~ | ✅ **already real** — `build_graph(session)`/`affected_by(graph, corridor_ids)` now live in [`backend/agents/graph.py`](../../backend/agents/graph.py) (PLAN.md Phase 5, landed — see [SPEC.md](../../SPEC.md)) | `backend/agents/geo.py`'s `build_geo()` (PLAN.md Phase 6, landed — see [SPEC.md](../../SPEC.md)), which wires it into `geo.affected_refinery_ids` for real | nothing left to replace |

> All four agent files live in `backend/agents/`. Keep the **stubs importable**
> until the real agent passes tests, then flip `cascade.py`/`routes.py` to the
> real function behind a `USE_REAL_AGENTS` flag (PLAN.md Phase 4), so the demo
> always has a deterministic fallback (PRD §17: LLM flakiness is a High risk).

**Determinism is non-negotiable (PRD §10, §17):** cache every LLM/embedding call
keyed by its input. On stage the same headline must always produce the same score.

---

## Status & phase mapping

**Status lives in [PLAN.md](PLAN.md) — Segment 1's phase table is the source of
truth.** This file's phase numbers below are implementation chapters, not a
separate status tracker; they map onto PLAN.md like this:

| This file | PLAN.md Segment 1 phase | Covers |
|---|---|---|
| Phase 0 (below) | — (done, historical) | Frozen contract + 43 tests |
| Phase 1 (below) | Phase 1 (partial — AI scaffolding only; contract/DB widening is PLAN.md's, not here) | LLM client, cache, config |
| Phase 2 (below) | **Phase 4 — ✅ landed** | Watch: RAG + LLM scoring (F1, F2) — see [SPEC.md](../../SPEC.md) for the as-built spec, which resolved several things this chapter left open (LLM provider is Groq not Anthropic/Gemini, embeddings are local not an API, confidence is retrieval-based not LLM-self-reported) |
| Phase 3 (below) | **Phase 3 — ✅ landed** | Predict: glass-box model (F3) + the v1.3 additions (power stress F15, assumption sourcing F20) — see [SPEC.md](../../SPEC.md) for the as-built spec, which resolved several things this chapter left open (override-endpoint shape, clamping bounds) |
| Phase 4 (below) | **Phase 5 — ✅ landed** | Knowledge graph (F10) — see [SPEC.md](../../SPEC.md) for the as-built spec, which resolved several things this chapter left open (self-contained library, no `cascade.py` wiring this phase; chokepoint collapses into the corridor node; `affected_by()` takes a set of corridor ids and raises on an unknown one) |
| Phase 5 (below) | **Phase 4** | Provenance + confidence bands (F8, F12) |
| Phase 6 (below) | **Phase 9 — ✅ landed** | LLM conservation copy (F7 slice) — see [SPEC.md](../../SPEC.md) for the as-built spec (single model tier, cached by `level\|corridor_name`, `status` stays rule-based) |
| Phase 7 (below) | **Phase 10** | Determinism, demo dataset, tests, cut-over |

Update PLAN.md's phase table when a phase lands — not this file.

---

## Phase 0 — Contract (DONE ✅)

**Delivered:** [`backend/schemas/contract.py`](../../backend/schemas/contract.py) — the frozen
Pydantic v2 contract — plus 43 conformance tests in `tests/test_contract.py`.

The models you will produce:

```python
from backend.schemas import (
    WatchAgentOutput,   # {corridor_risk: {<id>: CorridorRiskEntry}}
    CorridorRiskEntry,  # {score 0..100, confidence, band>=0, source_ids[]}
    PredictAgentOutput, # {impact, assumptions}  — both required
    Impact, Assumptions,
    Confidence,         # Literal["low","medium","high"]  — FULL WORDS
)
```

Locked rules that bite Dev B specifically:
- `confidence` must be `"low" | "medium" | "high"`. An LLM emitting `"med"` must
  be **normalized inside the Watch agent** before it hits the state.
- `score` is bounded `0..100`, `severity` `0..100→0..1` upstream; every other
  percentage is **clamped inside your agent** (the schema won't catch a 101%).
- `source_ids` are free-form strings — real provenance ids you retrieved.
- `extra="forbid"` everywhere: you cannot smuggle extra fields (e.g. a `reason`)
  into a contract model. Carry side-channel data (like the LLM's one-line reason)
  outside the contract object, the way Recommend does with `ScoredOption`.

**Acceptance:** `python -m pytest tests/test_contract.py` → 43 pass. (Already true.)

---

## Phase 1 — AI environment & scaffolding

> **STATUS: ✅ LANDED** (folded into PLAN.md Phase 4's implementation — see
> [SPEC.md](../../SPEC.md)). The provider decision landed as **Groq**, not
> Anthropic; `backend/agents/watch.py`/`rag.py` were built real from the
> start rather than scaffolded empty first (chunk 4 below didn't apply as
> written — there was no intermediate empty-skeleton step). `graph.py`
> (PLAN.md Phase 5) is still genuinely net-new, not scaffolded here.

**Goal:** stand up the AI toolchain without touching agent logic yet, so every
later phase has a client, a cache, and config to lean on.

**Chunks**
1. **Dependencies.** Add to `requirements.txt` (kept out until now on purpose):
   an LLM SDK, `chromadb` (vector store; FAISS is the fallback), `networkx`
   (this file's Phase 4). Pin versions. **Confirm the LLM provider first** — see
   PLAN.md §6 open decision 1: PRD v1.3's tech-stack table names Gemini 3.5
   Flash/Haiku 4.5, this repo's existing conventions lean Anthropic
   (`claude-sonnet-5`/`claude-haiku-4-5`). Don't build two clients.
2. **LLM client wrapper** — new `backend/agents/llm.py`:
   - Thin wrapper over whichever SDK is confirmed above.
   - A `complete_json(prompt, *, cache_key) -> dict` helper that **caches by input
     hash** to disk (e.g. a JSON file under `backend/agents/.llm_cache/`) so demos
     are deterministic and offline-replayable.
   - An **offline fallback**: if the API key is unset or a call fails, fall back
     to the deterministic stub logic. The demo must never hard-fail.
3. **Config.** Extend [`backend/config.py`](../../backend/config.py) `Settings` with
   the provider's API key, `llm_model`, `vector_store_path`, and a
   `use_real_agents` flag (env `USE_REAL_AGENTS=0/1`). Add the keys to
   `.env.example`.
4. **Package skeleton.** Create `backend/agents/watch.py`, `graph.py`, `rag.py`
   as empty modules with the target signatures, importing the stub as the
   fallback. (`predict.py` already exists for real — Phase 3 landed, see
   [SPEC.md](../../SPEC.md) — nothing to scaffold there.)

**Files:** `requirements.txt`, `.env.example`, `backend/config.py`,
`backend/agents/{llm,rag,watch,graph}.py` (new).

**Acceptance:** `pip install -r requirements.txt` succeeds; `from backend.agents.llm
import complete_json` works; with no API key, `complete_json` raises
`LLMUnavailable` (callers fall back to the stub — see SPEC.md Phase 4
decision #9 on why "return the fallback value" became "raise and let the
caller fall back," a cleaner separation of concerns); the existing 232 tests
still pass.

**Depends on:** nothing on the merge front (already done — see "Where this fits
today" above); do confirm the contract-widening in PLAN.md Phase 1 is at least
underway, since Phase 2/3 below consume its typed `Assumptions` shape.

---

## Phase 2 — Watch agent (RAG + LLM scoring) — F1, F2

> **STATUS: ✅ LANDED.** Implemented per [SPEC.md](../../SPEC.md)'s Phase 4
> section, which resolved this chapter's open questions: LLM provider is
> **Groq** (`llama-3.3-70b-versatile`/`llama-3.1-8b-instant`), not the
> Anthropic this chapter assumed; `confidence` is never asked of the LLM at
> all (derived purely from retrieval agreement — chunk 2's
> `"confidence":"low|med|high"` in the LLM's JSON response was dropped from
> the actual prompt); `source_ids` are every retrieved snippet's id, not an
> LLM-selected subset. **223 backend tests pass** (up from 188).

**Goal:** replace the keyword-bump stub with grounded, cited corridor risk scores.

**Chunks**
1. **RAG store** (`backend/agents/rag.py`) — F2:
   - Embed a curated set of headlines/sanctions snippets into ChromaDB with
     metadata `{source_id, date, corridor}`. **Pre-embed the demo set at startup**
     (persisted volume) so RAG works on a cold start (PRD §16).
   - `retrieve(corridor, k) -> list[Snippet]` returning top-k with their
     `source_id`s (these become the contract's `source_ids`).
2. **LLM scoring** (`backend/agents/watch.py`) — F1:
   - Build the scoring prompt from retrieved snippets; the LLM returns JSON only:
     `{"score":0-100, "confidence":"low|med|high", "source_ids":[...], "reason":"…"}`.
   - **Normalize** `"med" → "medium"`, **clamp** `score` to `0..100`.
   - Combine the LLM signal with the price/AIS bump into a composite score +
     confidence band (band drives F12).
3. **Emit the envelope** — keep the exact signature:
   ```python
   def run_watch(signal: dict) -> WatchAgentOutput: ...
   ```
   Soft-check the corridor id against seed config and **log a warning** on an
   unknown id (README rule #5) — never reject.
4. **Cut over:** point [`backend/cascade.py`](../../backend/cascade.py) at `run_watch`
   when `use_real_agents` is on; keep `run_watch_stub` as the fallback.

**Files:** `backend/agents/rag.py`, `backend/agents/watch.py`, `backend/cascade.py`;
demo snippets under `backend/seed/` or a new `backend/agents/data/`.

**Acceptance:**
- `run_watch(signal)` returns a valid `WatchAgentOutput` (validate it in a test).
- The same headline always yields the same score (cache hit).
- `source_ids` are real retrieved ids, not the signal id echoed back.
- Full cascade still runs; `/state` validates against `RiskState`.

**Depends on:** Phase 1.

---

## Phase 3 — Predict agent (glass-box domino model) — F3, F15, F20 *(≈ PLAN.md Phase 3)*

> **STATUS: ✅ LANDED.** Implemented per [SPEC.md](../../SPEC.md)'s Phase 3 section,
> which resolved this chapter's open override-logging question (a dedicated
> `POST /assumptions/override`, not a flag on `/simulate`) plus the pending-
> overrides-snapshotted-at-Approve-time mechanics this chapter didn't detail.
> The chunks below describe the design intent; SPEC.md is the as-built spec.

**Goal:** replace the arithmetic stub with the transparent, slider-driven **v1.3**
model — same math philosophy as v1.0, but every coefficient now typed
(fact/estimate/internal), sourced, ranged, and power-sector stress added.
**Do not use the v1.0 constant `0.066` for `gdp_delta`** — PRD v1.3 corrected it
to `0.03` after checking it against published GDP-drag estimates (see PRD §10A
in [PROJECT_GUIDE.md](../../PROJECT_GUIDE.md) for the full sourcing table); building
against the old constant would ship a knowingly-wrong number.

**Chunks**
1. **The formula chain** (`backend/agents/predict.py`): keep every assumption a
   **named, typed, sourced variable** (PRD §10A):
   ```
   gap          = supply_lost_pct                                        # FACT · 35-45%
   price_rise   = (gap / 10) * price_elasticity                          # ESTIMATE · 3-10
   gdp_delta    = -(price_rise * gdp_oil_sensitivity)                    # ESTIMATE · 0.02-0.08 (corrected from 0.066)
   power_stress = gap * power_oil_dependence * power_stress_multiplier
                  # power_oil_dependence: FACT · 0.01-0.02 (corrected from 0.05)
                  # power_stress_multiplier: INTERNAL, unsourced, labeled as such · 5-10
   run_rate     = clamp(100 - gap * 0.75)
   ```
   Each `Assumptions` field becomes `{value, type, range, src}` per the Phase 1
   contract widening (PLAN.md Phase 1 — this phase depends on it, don't start
   the formula chain before the typed shape exists). **Clamp all percentages**
   before returning (schema won't).
2. **Emit the envelope** — keep the exact signature so `/simulate` keeps working:
   ```python
   def run_predict(assumptions: Assumptions) -> PredictAgentOutput: ...
   ```
   Because [`POST /simulate`](../../backend/api/routes.py) calls this **directly**, the
   what-if simulator on the official portal is wired the moment you swap it in.
3. **Assumption defaults:** upgrade `assumptions_from_severity(...)` so cascade
   defaults come from real scenario data rather than a flat severity map, using
   the typed/sourced shape.
4. **Override audit (F9 extension):** whenever a value differs from its
   default, write an `AssumptionOverride` row (who, field, from-default,
   to-value, when) to `audit_log` — see PLAN.md Phase 3's open decision on
   whether this hangs off `POST /simulate` or a dedicated endpoint.
5. **(Optional) reasoning chain for the UI:** return the per-step arithmetic as a
   side-channel (NOT inside `Impact`/`Assumptions` — `extra="forbid"`). Mirror
   Recommend's `ScoredOption.to_dict()` pattern if the frontend wants to render it.

**Files:** `backend/agents/predict.py` (new — `run_predict` +
`assumptions_from_severity`, relocated from `stubs.py`), `backend/cascade.py`,
`backend/api/routes.py` (import swap + the new `POST /assumptions/override`),
`backend/state_store.py` (pending-override tracking).

**Acceptance:**
- `run_predict(assumptions)` returns a valid `PredictAgentOutput` with
  `power_stress_pct` populated and every assumption typed/sourced.
- `POST /simulate` with adjusted assumptions returns the recomputed `Impact`.
- Pure function, no mutation, fully unit-testable (mirror `tests/test_recommend.py`).

**Depends on:** PLAN.md Phase 1 (contract widening). Independent of this file's
Phase 2/Watch — can be done in parallel.

---

## Phase 4 — Knowledge graph — F10

> **STATUS: ✅ LANDED.** Implemented per [SPEC.md](../../SPEC.md)'s Phase 5
> section, which resolved several things this chapter left implicit:
> `graph.py` ships as a **self-contained library only** — no `cascade.py`
> wiring in this phase (chunk 2's "sharpen `affected_corridors()`" idea was
> explicitly deferred to PLAN.md Phase 6, since `RiskState.geo` couldn't be
> partially populated without Phase 6's AIS data anyway — **Phase 6 has since
> landed and does exactly this wiring**, see [SPEC.md](../../SPEC.md)); "chokepoint" is
> **not** a separate node from "corridor" (today's seed data is 1:1, so it's
> just an attribute on the corridor node); `affected_by()` takes a **set** of
> corridor ids (not one) and returns a structured `AffectedAssets(suppliers,
> refineries)`, not a flat `set[node]`; an unknown corridor id **raises**
> rather than returning an empty result; and "rebuild at startup" means
> "build fresh, uncached, on every call" (no literal FastAPI startup hook —
> there is no cache to invalidate). Chunk 3's `to_dict()` export shipped, but
> nothing reads it yet (no new endpoint this phase). **232 backend tests
> pass** (up from 223).

**Goal:** a NetworkX model of the supply network for affected-asset queries and
better reroute exclusion.

**Chunks**
1. **Build the graph** (`backend/agents/graph.py`) from seed config
   (`backend/seed/{corridors,suppliers,refineries}.json`): nodes = suppliers,
   routes/corridors, chokepoints, refineries; edges = "ships via", "feeds".
   Rebuild at startup so a new config row extends the graph with no code change.
2. **Query** `affected_by(chokepoint) -> set[node]` — everything reachable through
   a blocked chokepoint. This can sharpen `affected_corridors()` in
   [`cascade.py`](../../backend/cascade.py) (today a simple score threshold).
3. **Visualisation export** (photographs well for the deck): a `to_dict()` /
   graph-export the frontend map or a static diagram can render.

**Files:** `backend/agents/graph.py`; optional wiring in `backend/cascade.py`.

**Acceptance:** "if hormuz closes, what's affected?" returns the correct supplier/
refinery set from seed data; graph rebuilds cleanly on startup; unit-tested.

**Depends on:** Phase 1. Independent of Phases 2–3.

---

## Phase 5 — Provenance + confidence bands — F8, F12

> **STATUS: 🟡 PARTIALLY LANDED** alongside PLAN.md Phase 4 (see
> [SPEC.md](../../SPEC.md)). Chunk 2 (confidence bands) is done — `band`/
> `confidence` are derived from retrieval agreement in
> `backend/agents/watch.py`. Chunk 1's provenance-lookup endpoint is
> explicitly deferred to Segment 2, Chunk D, so its response shape gets
> designed against the real popover UI rather than guessed now;
> `source_ids` themselves are already real retrieved ids.

**Goal:** make every number traceable and every score carry uncertainty — the
trust centrepiece of the whole pitch.

**Chunks**
1. **Provenance:** ensure `source_ids` on every `CorridorRiskEntry` point to real
   retrieved signals (from Phase 2), and that the ids resolve to displayable
   snippets. Expose a lookup (id → {headline, source, timestamp}) the official
   portal's provenance popover can call. Coordinate the shape with Dev C.
2. **Confidence bands (F12):** derive `band` and `confidence` from retrieval
   agreement / signal count (tighter band = higher confidence, per the stub's
   `_confidence_for`). Make sure it flows through unchanged to the frontend gauge.

**Files:** `backend/agents/watch.py`, `backend/agents/rag.py`, possibly a small
provenance-lookup endpoint (coordinate with Dev A — may need a new route).

**Acceptance:** clicking a score in the official portal shows the real source
signals; confidence/band render on the gauge. Every displayed number traces back.

**Depends on:** Phase 2.

---

## Phase 6 — LLM conservation copy for `/public/status` — F7 slice

> **STATUS: ✅ LANDED** (PLAN.md Phase 9 — see [SPEC.md](../../SPEC.md) for the
> as-built spec). `backend/agents/conservation.py`'s
> `generate_conservation_copy(level, corridor_name)` replaces the old
> `_TIPS`/`_LEVELS` dicts' content for `message`/`conservation_plan`; the
> route (`backend/api/routes.py`) now also derives the scenario's worst
> corridor's human name from `RiskState.corridor_risk` and the `Corridor`
> table to pass in. Two deliberate simplifications vs. this section's
> original chunk list: a **single** model tier (not Watch's primary/
> fallback chain — proportionate to a P2/stretch, non-critical-path
> endpoint), and `status == "Normal"` **skips the LLM call entirely**
> (nothing scenario-specific to say when no corridor is elevated) rather
> than generating copy for every level.

**Goal:** replace the static citizen tips with scenario-specific, LLM-generated
conservation copy — **behind the same response shape** so Dev D's citizen board
needs no change.

**Chunks**
1. In [`backend/api/routes.py`](../../backend/api/routes.py), the `_TIPS`/`_LEVELS`
   dicts and the `NOTE: Dev B/D swap these...` comment mark the exact spot.
   Generate `conservation_plan` + `message` from the current scenario/severity via
   the LLM (cached, deterministic). Keep the returned keys identical:
   `{status, message, conservation_plan[], action_feed[], updated_at}`.
2. Keep the static tips as the **offline fallback** (same reasoning as Phase 1).

**Files:** `backend/api/routes.py`, `backend/agents/llm.py` (reuse the wrapper).
Coordinate with Dev A since the route lives in their file.

**Acceptance:** `GET /public/status` returns scenario-appropriate copy; response
shape unchanged; falls back to static tips with no API key.

**Depends on:** Phase 1.

---

## Phase 7 — Determinism, demo dataset, tests, cut-over

**Goal:** make it demo-safe and merge it in.

**Chunks**
1. **Deterministic demo dataset** (you are the demo-data owner, PRD §12): one
   curated set of headlines/signals in the repo so "works for me" = "works on
   stage". Pre-embed it; commit the LLM cache so the canonical demo runs offline.
2. **Tests:** add `tests/test_graph.py` (`test_predict.py` and
   `tests/test_watch.py`/`test_rag.py`/`test_llm.py` already exist — Phases 3
   and 4 landed). Assert real agent output validates against its envelope;
   assert a cached call is deterministic; assert `/state` still validates
   against `RiskState` after a real cascade (the drift alarm — README
   testing section).
3. **Cut-over:** flip `USE_REAL_AGENTS=1`; verify the full
   signal→Watch→Predict→Recommend→Advise cascade end-to-end against a running
   frontend, now including the wider v1.3 fields (power stress, geo, validation)
   from the other Segment 1 phases. Confirm the 91 original tests plus every
   phase's new tests all pass.
4. **Update PLAN.md's phase table and [PROJECT_GUIDE.md](../../PROJECT_GUIDE.md)'s
   status board** when each phase lands, so the next person sees accurate state
   in both places — this maps to PLAN.md Phase 10, the whole-project cut-over,
   not just this file's slice of it.

**Acceptance:** `python -m pytest` all green; live cascade runs with real agents;
deterministic on repeat; graceful offline fallback intact.

---

## Suggested order & parallelism (this file's slice only)

This is the ordering for the AI-specific chapters in this file. **For the full
Segment 1 picture — including Recommend depth, the geospatial/AIS data layer,
the dark-ship detector, and the backtest module, which this file doesn't detail —
see [PLAN.md](PLAN.md)'s own "Suggested order & parallelism" diagram.**

```
Phase 1 (scaffolding)  ── ✅ landed, see SPEC.md
        │
        ├── Phase 2 (Watch + RAG) ── ✅ landed, see SPEC.md ── Phase 5 (provenance/confidence, 🟡 confidence done, lookup endpoint deferred)
        ├── Phase 3 (Predict)      ── ✅ landed, see SPEC.md
        ├── Phase 4 (Knowledge graph) ── ✅ landed, see SPEC.md
        └── Phase 6 (conservation copy) ── ✅ landed, see SPEC.md
                                    │
                                Phase 7 (determinism, tests, cut-over) ── last,
                                and gated on PLAN.md Phases 2, 6, 7, 8 too
```

Phase 6 is independent once Phase 1 exists (Phases 2/3/4 have already
landed) — pick it up whenever it unblocks the demo fastest next. Note
PLAN.md's own diagram now shows its Phase 6 (geospatial/AIS, a *different*
phase number from this file's local "Phase 6") depending on this chapter's
Knowledge graph (PLAN.md Phase 5) for `affected_by()` — this file's chapters
are independent of each other, but PLAN.md's canonical phases are not.

---

## Do / Don't checklist

- ✅ Import contract models from `backend.schemas`, never from `contract.py`.
- ✅ Build JSON by dumping a model (`.model_dump(mode="json")`), never by hand.
- ✅ Normalize `med→medium`; clamp every percentage inside the agent.
- ✅ Cache every LLM/embedding call by input hash; ship an offline fallback.
- ✅ Keep the stub importable as the fallback until the real agent passes tests.
- ✅ Log-and-warn on unknown corridor ids; never reject them.
- ❌ Never edit `contract.py` or add a field to a contract model to carry extras.
- ❌ Never let an un-cached, un-mocked LLM call sit on the live demo path.
- ❌ Never change the `/public/status` or agent-envelope **shape** — the frontend
  renders whatever you emit; a shape change breaks it silently.

- ❌ Never add a field to `contract.py` that isn't already agreed in
  [PLAN.md](PLAN.md)'s Phase 1 contract-widening list — propose it there first.

*Urja Kavach · AI/ML implementation appendix · PRD v1.3 · contract is law · see
[PLAN.md](PLAN.md) for phase status.*
