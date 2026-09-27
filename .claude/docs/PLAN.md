# PLAN — Urja Kavach build plan (PRD v1.0 → v1.3)

> **What this file is:** the single forward-looking build plan. [PROJECT_GUIDE.md](../../PROJECT_GUIDE.md)
> is the architecture + PRD reference and the historical record of what shipped;
> this file is *what's next*, broken into shippable phases. When a phase lands,
> update its status here **and** the status board in PROJECT_GUIDE.md — don't let
> the two drift.
>
> **Read order for a new contributor:** [CLAUDE.md](../../CLAUDE.md) (orientation) →
> this file (what to build next) → [PROJECT_GUIDE.md](../../PROJECT_GUIDE.md) (why it's
> shaped this way, full PRD) → the relevant code.

---

## 0 · Where the project actually stands

`main` is the **single integrated branch** — the `swosti_kavach` merge (Dev A's
backend + Dev C/D's frontend onto Dev B's contract) already happened; there is no
outstanding merge step. `git diff main swosti_kavach` is empty. Any older doc that
says "main holds Deliverable 0 only, merge `swosti_kavach` first" is describing a
step that is **done** — that framing is retired as of this file.

What's built and tested today (PRD **v1.0** scope — see
[PROJECT_GUIDE.md](../../PROJECT_GUIDE.md) for the full record):

- **Contract v1.0** (`backend/schemas/contract.py`) — frozen, 43 conformance tests.
- **Backend**: DB/seed/bus/state_store/cascade, real **Recommend** (min-max
  price/speed/compat scoring) and **Advise** (reserve depletion sim), full REST +
  WebSocket API, JWT auth (`citizen`/`official`), `/approve` + `/audit`. 91 tests
  green.
- **Watch** and **Predict** are still **deterministic arithmetic stubs**
  (`backend/agents/stubs.py`) — no LLM, no RAG, no real domino model yet.
- **Frontend**: Next.js 16 landing page, Mission Control (one-button cascade demo),
  official cockpit (gauge, static Leaflet map, what-if simulator, reroute cards,
  SPR chart, audit trail), citizen board. Builds clean, verified in-browser.

**The gap this file plans:** the PRD moved to **v1.3** (see the PRD section of
[PROJECT_GUIDE.md](../../PROJECT_GUIDE.md)) and added ten features — **F11, F13–F20** —
none of which exist in code yet:

| Feature | What it needs |
|---|---|
| F11 | Geospatial layer — corridors/chokepoints/ports/refineries on the map |
| F13 | Replayed AIS tanker-track dataset feeding the map |
| F14 | Backtest/validation module — historical replay, measured signal lead-time |
| F15 | Power-sector stress as a computed `Impact` field |
| F16 | "Wrong oil" grade-compatibility gate on Recommend (partially present as a `bool`; not the full gate) |
| F17 | Real route cost — war-risk insurance + detour surcharge, cost breakdown |
| F18 | Dark-ship anomaly detector (unsupervised ML) — the project's one real ML component |
| F19 | Alarm-language tone score — small text classifier, one extra Watch input |
| F20 | Assumption sourcing framework — fact/estimate/internal typing, bounded ranges, override audit |

None of these are cosmetic — F16/F17/F20 change the **contract**, F11/F13/F18
need a **new data source** (AIS), and F14/F18/F19 are genuinely new model code.
That is what makes this a real second phase of the build, not a polish pass.

---

## 1 · Two segments

**Segment 1 — AI + Backend.** Contract, database, seed config, all four agents,
the REST/WS API, the knowledge graph, RAG, and the two ML components (dark-ship
detector, alarm-language score). Owns everything that produces or shapes
`RiskState`.

**Segment 2 — Frontend + Integration.** Both Next.js portals, the `types/contract.ts`
mirror, the geospatial map (AIS animation, dark-ship markers), the assumption
slider UX (fact/estimate/internal tiers), the backtest chart, and end-to-end demo
rehearsal against the PRD §18 script.

**Why merged into one segment instead of split by person (as v1.0 was):** every
v1.3 feature is a *vertical* concern, not a layer. F16/F17 (wrong-oil gate + real
route cost) touch the contract's `Reroute` model **and** `recommend.py`'s scoring
function in the same breath. F20 (assumption sourcing) touches the contract's
`Assumptions` model, `predict.py`'s output, **and** the audit log. Splitting these
by "backend person" vs "AI person" would just recreate the hand-off overhead the
v1.0 mock-first contract was built to avoid. So Segment 1 is phased as vertical
slices — each phase touches schema + DB/seed + agent logic + API together, and
ships as one working, testable unit.

---

## 2 · Segment 1 — AI + Backend: phased vertical slices

Each phase lists: **goal**, the **PRD features** it closes, what changes at each
layer, **new dependencies**, **acceptance criteria**, and what it **depends on**.
Contract changes always follow the existing
[contract-change protocol](../../README.md#contract-change-protocol) — propose the
field/type/why, update `contract.py` **and** the mock `/state` in the same change,
keep `pytest` green.

### Phase 1 — Contract v2 & data-model foundation *(blocking — do first)*

> **STATUS: ✅ LANDED.** Implemented per [SPEC.md](../../SPEC.md), which resolved
> several ambiguities this section left open (the Assumptions migration's
> interaction with the Predict stub, `Reroute`'s missing refinery reference,
> and whether new required fields get mechanical placeholders vs. stay
> optional). Read SPEC.md for the exact decisions and field-by-field spec.
> 153 backend tests pass (up from 91). Phases 2+ below are unaffected in
> scope — they replace Phase 1's placeholders with real logic.

**Goal:** widen the frozen contract and the DB/seed layer to hold every field the
rest of v1.3 needs, before any agent logic changes. This is the "freeze it in
hour one" step for the second build phase.

**Contract changes** (`backend/schemas/contract.py`, version bump, still
`extra="forbid"`):
- `Impact.power_stress_pct: float` — F15.
- `Assumptions` → typed entries: each value becomes `{value, type: "fact"|"estimate"|"internal", range: [lo, hi], src: str}` instead of a bare float, for `supply_lost_pct`, `buffer_days`, `price_elasticity`, plus two new assumptions `power_oil_dependence` and `gdp_oil_sensitivity`, plus the internal `power_stress_multiplier` — F20. This is a **breaking** change to `Assumptions`; plan the migration (old bare-float shape vs new typed shape) explicitly in the PR that does this.
- `RiskState.assumption_overrides: list[AssumptionOverride]` (new model: `who, field, from_default, to_value, ts`) — F9 extension, F20.
- `Reroute` gains `grade_ok: bool`, `rank_eligible: bool`, `reason: Optional[str]`, `cost_breakdown: CostBreakdown` (new model: `crude, war_risk_insurance, detour`), `true_cost: float` — F16, F17. Decide whether this replaces or sits alongside the existing `compatible`/`cost` fields (recommend keeping `cost` = crude price only, adding `true_cost` as the ranking field, to avoid silently changing what "cost" has meant since v1.0).
- New `Geo` model: `at_risk_tanker_ids`, `dark_tanker_ids`, `affected_refinery_ids` — F11/F13/F18. `RiskState.geo: Optional[Geo]`.
- New `Validation` model: `backtest_id`, `signal_lead_hours` — F14. `RiskState.validation: Optional[Validation]`.

**DB/seed changes:**
- `Corridor`: add `war_risk_pct: Float`, `detour_days: Float`, `geojson_path: String` — F17, F11.
- `Refinery`: add `lat: Float`, `lon: Float` — F11.
- `Supplier`: already has `crude_grade` — no change.
- Update `backend/seed/corridors.json` and `refineries.json` with the new columns (real, sourced figures per PRD §10A/§17 — cite where the war-risk % and lat/lon come from).

**API:** no new endpoints yet — this phase is schema/DB only, keeping the surface
stable for Phase 2 onward.

**New deps:** none.

**Acceptance:** `python -m pytest` still green after every model/table change
(update `tests/test_contract.py` fixtures for the new required/optional shapes);
`GET /state` still validates against the widened `RiskState` with all new blocks
`None`/empty on a fresh boot; existing stub agents still run unmodified (they
just don't populate the new fields yet).
>
> **Correction (post-implementation, see SPEC.md decision #1):** "existing
> stub agents still run unmodified" turned out not to literally hold for the
> Predict stub — `Assumptions`' float→typed-object change is a restructuring,
> not an addition, so `assumptions_from_severity`/`run_predict_stub` needed a
> minimal mechanical edit (unwrap `.value`, wrap outputs in `AssumptionEntry`)
> to keep validating. `recommend.py` genuinely stayed logic-unmodified aside
> from the same kind of mechanical placeholder-filling for Reroute's five new
> fields. Both edits are shape-filling only — zero new modeling logic.

**Depends on:** nothing — this is the gate everything else in Segment 1 (and any
Segment 2 work that reads new fields) waits on.

---

### Phase 2 — Recommend depth: wrong-oil gate + real route cost (F16, F17)

> **STATUS: ✅ LANDED.** Implemented per [SPEC.md](../../SPEC.md)'s Phase 2 section,
> which resolved the open questions this section left implicit (the exact
> `DAILY_SHIP_COST` value and its sourcing, which corridor's `war_risk_pct`
> needed revising for the surcharge to actually be visible in the canonical
> demo scenario, and the eligible-first sort/normalization semantics once
> ineligible rows are hard-gated). 159 backend tests pass (up from 153).

**Goal:** turn `Reroute.compatible` (a soft downweight today) into a hard
eligibility gate, and rank on `true_cost` (crude + war-risk insurance + detour)
instead of crude price alone. PRD calls this out as the cheapest, highest
depth-per-hour feature in the whole v1.3 scope — do it right after Phase 1.

**Backend changes** (`backend/agents/recommend.py`):
- `score_option`: if `crude_grade` isn't in any compatible refinery's list, return `rank_eligible=False, reason="grade incompatible", score=0.0` — do not merely downweight.
- `true_cost(opt, corridor)`: `crude + crude*corridor.war_risk_pct + corridor.detour_days*DAILY_SHIP_COST`, returning the three-way breakdown. Rank on `true_cost`, not `cost`.
- `build_candidates` reads `war_risk_pct`/`detour_days` from the `Corridor` row added in Phase 1.

**API:** `GET /reroutes` response now carries `grade_ok`, `rank_eligible`, `reason`, `cost_breakdown`, `true_cost` per the Phase 1 contract — no route signature change.

**New deps:** none.

**Acceptance:** a candidate with an incompatible grade is present in the response but `rank_eligible=false` with a reason, never silently ranked; a route through a high-war-risk corridor visibly loses rank once insurance + detour are added even if its crude price is lowest; `tests/test_recommend.py` covers both cases.

**Depends on:** Phase 1.

---

### Phase 3 — Predict v1.3: power stress + sourced assumptions + override audit (F3, F15, F20, F9)

> **STATUS: ✅ LANDED.** Implemented per [SPEC.md](../../SPEC.md), which resolved
> this section's open override-logging question (a **dedicated
> `POST /assumptions/override`**, not a flag on `/simulate` — keeps `/simulate`
> pure, and lets the frontend log a commit once on slider-release instead of
> once per debounce tick) plus several edge cases this section left implicit:
> the identity/auth requirement on the override endpoint (any authenticated
> role), the diff baseline (`assumptions_from_severity` recomputed at call
> time), dedup-by-field for the pending set, and — the biggest structural
> decision — that `RiskState.assumption_overrides` is stamped only at
> **Approve** time from a small in-memory pending set, never on the
> exploratory commit itself (which only ever writes to `audit_log`). **188
> backend tests pass** (up from 159).

**Goal:** replace the arithmetic stub with the sourced v1.3 model — every
coefficient typed and ranged, the two corrected constants
(`power_oil_dependence=0.015`, `gdp_oil_sensitivity=0.03`) applied, and slider
overrides written to the audit trail.

**Backend changes** (`backend/agents/predict.py`, replacing `run_predict_stub`):
- Implement the full chain from PRD §10: `gap → price_rise → gdp_delta → power_stress` using the corrected coefficients and the typed `Assumptions` shape from Phase 1.
- `assumptions_from_severity` upgraded to emit the typed/sourced defaults (fact/estimate/internal + range + src) rather than bare floats.
- Clamp every percentage before return (contract won't) — `price_rise_pct` → `[0,100]`, `gdp_delta_pct` → `[-50,0]`, `power_stress_pct` → `[0,100]`.
- Wherever an official's slider drag differs from default, write an `AssumptionOverride` row to `audit_log` (who, field, from-default, to-value, when) — reuses the existing audit machinery, this is a logging rule not new infrastructure.

**API:** `POST /simulate` keeps its exact signature, now backed by the real `run_predict`. A new, dedicated `POST /assumptions/override` (auth required, any role) logs one `audit_log` row per divergent field on every call; `RiskState.assumption_overrides` is untouched by it. `POST /approve` now always snapshots the pending override set onto `RiskState.assumption_overrides` (resetting to `[]` when nothing is pending) and embeds the same list in its own `audit_log` payload.

**New deps:** none (pure arithmetic, no LLM needed for this phase).

**Acceptance:** `run_predict(assumptions)` returns a valid `PredictAgentOutput` with `power_stress_pct` populated; `POST /simulate` recomputes correctly from typed assumptions; dragging a slider away from default and committing it produces one new `audit_log` row per divergent field; approving snapshots the pending set onto `RiskState.assumption_overrides`; `tests/test_predict.py` mirrors `tests/test_recommend.py`'s pure-function style.

**Depends on:** Phase 1. Independent of Phase 2 — ran in parallel.

---

### Phase 4 — Watch real agent: RAG + LLM scoring, provenance, confidence bands (F1, F2, F8, F12)

> **STATUS: ✅ LANDED.** Implemented per [SPEC.md](../../SPEC.md), which resolved
> this section's open LLM-provider decision differently than either option
> listed below — **Groq** (free tier), not Anthropic or Gemini — plus the
> vector-store/embeddings pairing (ChromaDB + its bundled local ONNX
> embeddings, since neither Anthropic nor Groq offers an embeddings
> endpoint), the composite-scoring approach (LLM-authoritative, not
> blended), and confidence/band derivation (retrieval-agreement based, never
> the LLM's self-report). The provenance-lookup endpoint is explicitly
> deferred to Segment 2, Chunk D. **223 backend tests pass** (up from 188).

**Goal:** replace the keyword-bump stub with grounded, cited corridor risk
scores — the first LLM call in the system.

**New deps:** an LLM client library + a vector store. ~~**Open decision** —
see [§6](#6--open-decisions): PRD's tech-stack table names Gemini 3.5 Flash
primary / Haiku fallback, but `.env.example`/CLAUDE.md conventions in this
repo lean Anthropic (`claude-sonnet-5` / `claude-haiku-4-5`). Confirm before
writing `backend/agents/llm.py`.~~ **Decided (SPEC.md): Groq**, neither
named option — free tier, no cost pressure for repeated demo/rehearsal
cascade runs. Added `chromadb` for RAG (local embeddings, not an API).

**Backend changes:**
- `backend/agents/llm.py` (new) — thin client wrapper, `complete_json(prompt, *, cache_key) -> dict` caching every call by input hash to disk (`backend/agents/.llm_cache/`) for demo determinism; offline fallback to the deterministic stub logic if no API key or a call fails — the demo must never hard-fail on a network blip.
- `backend/agents/rag.py` (new) — embed a curated headline/sanctions snippet set into the vector store with `{source_id, date, corridor}` metadata, pre-embedded at startup; `retrieve(corridor, k) -> list[Snippet]`.
- `backend/agents/watch.py` (new) — build the scoring prompt from retrieved snippets, get back `{score, confidence, source_ids, reason}`, normalize `"med"→"medium"`, clamp `score` to 0–100, combine with the existing price/AIS bump into a composite score + confidence band (drives F12). Emit the exact `WatchAgentOutput` envelope.
- Config: extend `Settings` with `anthropic_api_key` (or provider-equivalent), `llm_model`, `vector_store_path`, `use_real_agents` (env `USE_REAL_AGENTS=0/1`) — keep the stub importable as the offline fallback behind this flag.
- A small provenance lookup (id → `{headline, source, timestamp}`) the official portal's popover can call — coordinate the response shape with Segment 2.

**API:** `backend/cascade.py` swaps to `run_watch` behind `USE_REAL_AGENTS`; no route signature changes. If provenance needs its own endpoint (vs. embedding snippets in `source_ids`-adjacent data), add it here and document it.

**Acceptance:** `run_watch(signal)` returns a valid `WatchAgentOutput`; the same headline always yields the same score (cache hit, not a fresh LLM call); `source_ids` are real retrieved ids, not the signal id echoed back; full cascade still runs and `/state` still validates; `tests/test_watch.py` added.

**Depends on:** Phase 1 (for the widened contract; Watch's own output shape is
actually unchanged from v1.0 — `WatchAgentOutput` didn't need new fields). Can
run in parallel with Phases 2–3.

---

### Phase 5 — Knowledge graph (F10)

> **STATUS: ✅ LANDED.** Implemented per [SPEC.md](../../SPEC.md), which resolved
> a contradiction this section's wording had created with `contract.py`'s
> own `Geo` docstring (the latter already said `geo` stays `None` until
> Phase 6/7) — **this phase does not touch `RiskState`, `cascade.py`, or the
> API at all**. It ships `backend/agents/graph.py` (`build_graph()`,
> `affected_by()`, `to_dict()`) as a self-contained, fully-tested library;
> Phase 6 is what actually wires `affected_by()` into `geo.affected_refinery_ids`
> once the rest of the `Geo` block has AIS data to populate alongside it. Also
> resolved: chokepoint collapses into the corridor node (no separate fourth
> node tier, since today's seed data is 1:1), `affected_by()` takes a *set*
> of corridor ids and returns a structured `AffectedAssets(suppliers,
> refineries)`, and an unknown corridor id raises rather than returning
> silently-empty results. **232 backend tests pass** (up from 223).

**Goal:** a NetworkX model of the supply network for affected-asset queries,
sharpening `cascade.py`'s corridor-exclusion logic and eventually feeding
`geo.affected_refinery_ids`.

**Backend changes:**
- `backend/agents/graph.py` (new) — build nodes (suppliers, corridors/chokepoints, refineries) and edges ("ships via", "feeds") from seed config at startup; rebuilds automatically when a seed row changes, no code change needed for a new corridor.
- `affected_by(chokepoint) -> set[node]` query; wire into `cascade.py`'s `affected_corridors()` (today a simple score threshold) and into the `geo.affected_refinery_ids` field from Phase 1.
- Export a `to_dict()`/graph serialization the frontend map or a static diagram can render.

**New deps:** `networkx`.

**Acceptance:** "if hormuz closes, what's affected?" returns the correct
supplier/refinery set from seed data; graph rebuilds cleanly on startup;
`tests/test_graph.py` added.

**Depends on:** Phase 1. Independent of Phases 2–4.

---

### Phase 6 — Geospatial data layer: AIS replay + GeoJSON + `/geo/state` (F11, F13)

> **STATUS: ✅ LANDED.** Implemented per [SPEC.md](../../SPEC.md), which resolved
> several ambiguities this section left open: the dataset covers all **four**
> seeded corridors (`hormuz`, `suez_cape`, `atlantic`, `malacca` — this
> section's "three-corridor network" phrasing was stale), 4 tankers each (16
> total), each a real 8-point timestamped track over a committed synthetic
> window, not a single snapshot. "At-risk" tanker membership turned out to be
> a **static corridor tag on each curated tanker record, not geometric
> point-in-polygon** against the corridor GeoJSON — the polygons stayed
> map-decoration only, matching this section's own "New deps: none" line
> (a real polygon check would have needed `shapely`). Corridor GeoJSON is
> hand-authored/illustrative (labeled as such), anchored at the same
> coordinates `frontend/components/shared/interactive-map.client.tsx`'s
> `NODES` constant already hardcodes, rather than a downloaded OSM dataset.
> `GET /geo/state` also bundles `corridors`/`refineries` config rows
> alongside `geo` and the tanker tracks — neither table had any HTTP consumer
> before this phase. One correctness fix found during implementation, not
> anticipated by this section: `affected_by()`'s deliberate fail-loud
> `ValueError` on an unrecognized corridor id (SPEC.md Phase 5 decision #7)
> is reachable from an unauthenticated `POST /signal` body via `cascade.py`'s
> `excluded` set, so the new `build_geo()` catches it and degrades to
> `affected_refinery_ids: []` rather than 500ing the cascade. **252 backend
> tests pass** (up from 232).

**Goal:** the backend half of the geospatial layer — a curated, deterministic,
*replayed* AIS dataset and the endpoint that serves it, plus corridor/refinery
geo data. (The map rendering itself is Segment 2.)

**Backend changes:**
- Curate a small AIS sample dataset (CSV or JSON) — tanker id, timestamp, lat/lon, heading, speed — for tankers along the three-corridor network, under `backend/seed/` or a new `backend/agents/data/ais_sample.csv`. Deterministic and committed, not a live feed (explicit scope guard from the PRD).
- `GET /geo/state` (new endpoint) — returns the `Geo` block from Phase 1 (`at_risk_tanker_ids`, `dark_tanker_ids`, `affected_refinery_ids`) plus the raw tanker-track replay data the map animates.
- Populate `Corridor.geojson_path` (Phase 1 column) with real corridor polylines (Hormuz, Suez/Cape, Bab-el-Mandeb/Atlantic) — free OSM-derived GeoJSON, committed as static files.
- "At-risk" tanker logic: tankers whose replayed position falls inside a corridor whose `corridor_risk.score` is elevated get added to `at_risk_tanker_ids`.
- `affected_refinery_ids`: call Phase 5's `backend/agents/graph.affected_by(excluded_corridors)` with the same excluded-corridor set `cascade.py`'s `affected_corridors()` already computes, and take its `.refineries`. This phase is the one that actually stamps `RiskState.geo` for the first time (SPEC.md Phase 5 decision #1 — Phase 5 shipped the query only, deliberately not the wiring); this is that wiring.

**New deps:** none beyond what Phase 4/7 already add.

**Acceptance:** `GET /geo/state` returns contract-valid data; a Hormuz scenario
populates `at_risk_tanker_ids` with tankers actually inside that corridor's
polygon at replay time; the same scenario's `affected_refinery_ids` matches
`graph.affected_by({"hormuz"}).refineries` exactly (`{"jamnagar", "vadinar",
"paradip"}` against today's seed data — see SPEC.md Phase 5 §3); corridor
GeoJSON files load correctly in a quick Leaflet smoke test (can be manual,
ahead of Segment 2 wiring it up for real).

**Depends on:** Phase 1. Depends on **Phase 5** for `affected_by()` (this
phase is the first to actually call it — Phase 5 shipped it uncalled).
Independent of Phases 2–4. Phase 7 (dark-ship) reads the same AIS dataset
this phase curates, so do this one first if sequencing serially.

---

### Phase 7 — Dark-ship anomaly detector: the real ML component (F18)

> **STATUS: ✅ LANDED.** Implemented per [SPEC.md](../../SPEC.md), which resolved
> several ambiguities/corrections this section left open: the interview's
> literal pick of a shapely-based distance to the shared corridor polyline
> was tested and rejected once real numbers showed it's confounded by each
> clean tanker's own seeded "lane" offset (clean `suez_cape_04` sits
> further off its corridor line than dark `hormuz_04`) — replaced with a
> self-referential "deviation from the tanker's own initial course" feature
> that needs no geometry dependency at all, so `shapely` was never added.
> No rule-based fallback was built (SPEC.md decision #7: the detector has
> no runtime failure mode to degrade from — it's a pure function over
> static data, unlike the LLM/RAG path). Three of Hormuz's four tankers
> (`hormuz_02/03/04`) became the curated "went dark" case; the contamination
> (`0.19`) and `random_state` (`42`) constants were verified stable across a
> sweep, not hand-tuned to a knife-edge. The Watch-wiring question this
> section raised is resolved by direct import (`watch.py` imports
> `anomaly.py`, same pattern as its existing `rag.py` import) — no
> `cascade.py` resequencing needed, since anomaly detection depends on
> neither Watch's own output nor DB state. The stub-fallback question is
> resolved **yes**: `run_watch_stub` gets a matching `+10.0`-per-tanker bump
> (SPEC.md decision #12), since the detector has no network dependency and
> is available even when `USE_REAL_AGENTS` is off. One structural surprise
> found during implementation, not anticipated by this section: `geo.py`
> importing `anomaly.py` for `dark_tanker_ids` while `anomaly.py` needs
> `list_tankers()` creates a circular import — resolved by extracting the
> AIS-loading code (`list_tankers()`) into a new `backend/agents/ais.py`
> that both modules depend on instead of depending on each other. Follow-up
> hardening for demo defensibility: `ais.py`'s data source is now
> config-driven (`Settings.ais_data_path` / `AIS_DATA_PATH`, defaulting to
> the committed replay set) instead of a hardcoded path, so "swap in a live
> feed" is a literal, testable seam (`tests/test_ais.py`) rather than just a
> docstring claim. **273 backend tests pass** (up from 252).

**Goal:** unsupervised anomaly detection over the AIS replay set — the project's
one genuinely learned-from-data component. Answers the Technical Excellence
critique directly (see PRD §10E for the full "why this and not a trained
safe/unsafe classifier" reasoning — worth reading before building this).

**Backend changes:**
- `backend/agents/anomaly.py` (new) — per-vessel features over a time window from the Phase 6 AIS data: speed, heading-change rate, distance off the normal corridor line, transponder-gap length.
- Fit `sklearn.ensemble.IsolationForest` on the normal-behaviour window (a z-score/rolling-median rule is the documented fallback if time is tight — still a defensible signal per PRD §13's graceful-degradation note).
- Score each vessel; anomalies above threshold become `geo.dark_tanker_ids` (Phase 1 field) and feed into Watch's real scoring (Phase 4) — a real cross-phase wire, sequence accordingly.

> **Phase 4 architecture note (post-implementation):** "feed one extra input
> into the Watch composite score," as this section originally said, assumes
> a numeric blend — Phase 4 explicitly rejected that (SPEC.md Phase 4
> decision #5: the real agent is LLM-authoritative, `run_watch_stub`'s
> arithmetic is *only* the offline fallback, nothing is blended with the
> LLM's score). There is no composite-score slot left to feed a number into.
> The real wiring point is `backend/agents/watch.py`'s `_build_prompt()` —
> add a line to the prompt context (e.g. "N tankers are currently flagged
> dark near this corridor") so the LLM weighs it as grounded context, the
> same way retrieved snippets are. Decide at Phase 7 time whether the
> stub-fallback path also needs a (much simpler, arithmetic) dark-ship term
> for when Watch degrades to offline mode — today's stub has no such input.

**New deps:** `scikit-learn`.

**Acceptance:** on the curated replay set, a known "went dark near a chokepoint" synthetic case is correctly flagged; `dark_tanker_ids` populates and is stable across runs (deterministic — same replay, same anomalies); a unit test asserts the detector doesn't flag a clearly normal transit; `tests/test_anomaly.py` added.

**Depends on:** Phase 6 (AIS data) and, for the Watch-composite wiring, Phase 4.

---

### Phase 8 — Backtest / validation module (F14)

> **STATUS: ✅ LANDED.** Implemented per [SPEC.md](../../SPEC.md)'s Phase 8
> section, which resolved this section's own open decision #5 (historical
> case: **Red Sea / Houthi crisis, Nov 2023 – Mar 2024**, not the 2025 Iran
> standoff — reuses `watch_corpus.json`'s existing `suez_cape` events and
> Phase 2's own war-risk-premium sourcing, densified with three more real,
> dated headlines) plus a real bug risk this section's own architecture note
> flagged but didn't resolve: `retrieve()` had no date cutoff, so a naive
> replay could leak future snippets into a past headline's score. Fixed by
> threading an optional `as_of` cutoff through `retrieve()`/`run_watch()`
> (defaults to `None` everywhere in the live cascade — zero behavior change
> there, verified by the full pre-existing test suite passing unmodified).
> Also decided: `GET /backtest/{id}` is fully standalone and **never**
> writes to `RiskState.validation` (a GET with a WS-broadcasting side effect
> had no precedent in this codebase — `validation` stays permanently `None`
> on `RiskState`); the Brent price series is hand-curated and explicitly
> labeled illustrative, not sourced daily closes; and the "+Xσ" spike
> threshold this section's own wording proposed is replaced with a plain
> percentage-above-baseline test, since a `+Xσ` claim needs more baseline
> density than an 11-point hand-curated series can honestly support.
> **See SPEC.md for the full decision log, code, curated data, and a
> hand-verified worked example** (stub-fallback path — deterministic,
> CI-testable with no API key, pinned by `tests/test_backtest.py`:
> `signal_lead_hours == 1464.0`, `watch_crossed_at == 2023-12-03`,
> `brent_crossed_at == 2024-02-02` — the real-LLM-path number still needs
> implementation-time verification against a live `GROQ_API_KEY`, which this
> environment doesn't have). **293 backend tests pass** (up from 273).

**Goal:** manufacture the evidence for "signal detection lead time and accuracy"
— the axis v1.0 had zero coverage for — from one real historical shock.

**Backend changes:**
- Curate one historical signal set (PRD suggests the 2025 US-Iran standoff or a Red Sea/Houthi episode) — timestamped headlines/sanctions notes + a Brent price series, committed under `backend/seed/backtest/`.
- `backend/agents/backtest.py` (new) — replay the headlines through `run_watch` (Phase 4) in chronological order, record the score timeline, overlay against the Brent series, compute `signal_lead_hours = timestamp(Brent crosses +Xσ) − timestamp(Watch score crosses alert threshold)`.
- `GET /backtest/{id}` (new endpoint) — returns the score timeline, the price series, and the computed lead-time, matching the Phase 1 `Validation` model shape.

> **Phase 4 architecture note (post-implementation):** `backend/agents/rag.py`'s
> `retrieve(corridor, query, k)` has **no date cutoff** — it queries the
> entire committed corpus regardless of the replay timestamp being scored.
> A naive chronological replay could retrieve (and get scored against)
> snippets dated *after* the historical headline being replayed — using
> future information to score the past, which would quietly invalidate the
> lead-time measurement this whole phase exists to produce. Before wiring
> the replay loop, either (a) add an `as_of` cutoff parameter to `retrieve()`
> that the backtest passes on every call, or (b) curate the backtest's own
> historical headline/snippet set (`backend/seed/backtest/`) so it's never
> queried against `watch_corpus.json` in the first place. Pick one
> explicitly — don't let the replay silently leak future snippets.

**New deps:** none beyond Phase 4's.

**Acceptance:** `GET /backtest/2025_iran_spike` (or the chosen case id) returns a
positive `signal_lead_hours` with the two timelines; framed and documented
explicitly as "one curated historical case," not a statistical accuracy claim
(PRD's own honesty guard — repeat it in the endpoint's docstring and in any UI
copy Segment 2 writes against it).

**Depends on:** Phase 4 (needs real `run_watch` to replay against — running this
against the stub would produce a meaningless backtest).

---

### Phase 9 — Alarm-language score + LLM conservation copy *(stretch / P2)* (F19, F7 slice)

> **STATUS: 🟡 interview complete, implementation-ready.** Full spec in
> [SPEC.md](../../SPEC.md), which resolved this section's implicit open questions:
> the alarm classifier's training data is a **hand-curated, committed,
> general-tone corpus** (67 rows), not a keyword lexicon or a new
> dependency — and, found empirically while writing the spec, needed a
> revision after its first draft (disaster/emergency vocabulary only) left
> every real oil-corridor headline within a few hundredths of the 0.5
> decision boundary; the committed corpus adds a generic conflict/security
> vocabulary sub-group so the classifier can actually discriminate on the
> domain it's applied to, without training on oil-crisis outcomes. Also
> decided: binary output only, no contract change (the label reaches
> Watch's prompt and the offline stub exactly like Phase 7's dark-ship
> line, never a new `RiskState` field), the stub gets a matching
> `_ALARM_BUMP = 8.0`, alarm classification is *not* suppressed under
> `as_of` (unlike Phase 8's dark-ship suppression — tone has no temporal
> dependency), and the conservation-copy slice keeps `status` rule-based
> while only `message`/`conservation_plan` become LLM-generated, cached by
> `level|corridor_name` with the prompt's own inputs limited to exactly
> that same pair.
>
> **STATUS: ✅ LANDED.** Implemented exactly per SPEC.md's Phase 9 section —
> `backend/agents/alarm.py` (67-row committed corpus, TF-IDF+LogReg, fit
> once and cached), `backend/agents/conservation.py` (LLM conservation
> copy, single model tier, static fallback), the matching `watch.py`/
> `stubs.py` wiring, and `routes.py`'s thinner `public_status()`. One
> downstream regression found and fixed during implementation: Phase 8's
> pinned backtest score table (`tests/test_backtest.py`) assumed no alarm
> bump existed — every one of the Red Sea case's 7 curated headlines
> classifies as alarming, so each pinned score shifted by exactly `+8.0`;
> re-pinned after confirming the uniform shift doesn't move
> `watch_crossed_at`/`signal_lead_hours` (the first crossing of
> `AFFECTED_THRESHOLD=50.0` is unchanged). **319 backend tests pass** (up
> from 293).

**Goal:** the two cheapest, lowest-priority v1.3 additions. Build only after
Phases 1–8 are demo-safe; cut first if the timeline runs hot (PRD explicitly
marks F19 "P2, nice-to-have, cheap").

**Backend changes:**
- `backend/agents/alarm.py` (new) — a small TF-IDF + logistic-regression (or lightweight pretrained sentiment) classifier scoring headline urgency/tone, trained on general alarming-vs-calm language (not oil-crisis outcomes — see PRD §10B/§10C for why the "safe/unsafe" version was explicitly rejected). Feeds one extra, clearly-labeled input into Watch — never the deciding number.
  > **Phase 4 architecture note (post-implementation):** same caveat as
  > Phase 7's dark-ship wire — Watch's real path has no composite-score slot
  > to blend a numeric alarm score into (SPEC.md Phase 4 decision #5). Wire
  > the alarm-language label into `_build_prompt()`'s context instead (e.g.
  > "headline tone classified as: alarming"), so the LLM sees it as one more
  > labeled signal, not a number this phase has to combine with anything.
- `backend/api/routes.py` — replace the static `_TIPS`/`_LEVELS` dicts behind `GET /public/status` with LLM-generated, scenario-specific conservation copy (reuse `backend/agents/llm.py` from Phase 4 — its `complete_json(prompt, *, cache_key, model)` is provider-generic despite being Groq-backed today, so this reuses it unchanged), **keeping the exact response shape** (`{status, message, conservation_plan[], action_feed[], updated_at}`) so the citizen board needs no change. Keep the static tips as the offline fallback.

**New deps:** a small classical-ML text-classification stack (`scikit-learn` TF-IDF is enough; no new heavy dep if Phase 7 already pulled in scikit-learn).

**Acceptance:** alarm score is visibly present as a labeled, secondary input (never presented as a disruption predictor); `GET /public/status` returns scenario-appropriate copy with the same response shape; both fall back gracefully with no API key.

**Depends on:** Phase 4 (LLM client + Watch composite to plug into).

---

### Phase 10 — Determinism, demo dataset, full regression, cut-over

> **STATUS: ✅ landed**, once a live `GROQ_API_KEY` became available (the
> user configured `USE_REAL_AGENTS=1` + a real key in their own local
> `.env`). Of the five work items below: **#1 is done** (Phases 6–9 already
> committed the curated AIS/alarm/watch-corpus/backtest datasets).
>
> **#2 is fully done now.** With the real key active, injected the
> canonical Mission Control demo scenario (`hormuz`, "Missile strike closes
> Strait of Hormuz shipping lane", severity 0.6 — `India Connect
> Portal/src/routes/mission.tsx`'s own pre-filled default) and confirmed a
> genuine Groq call: a natural-language `reason` field
> ("The headline indicates a direct and immediate disruption to the Strait
> of Hormuz shipping lane due to a missile strike…") no deterministic stub
> could produce. Also ran the backtest replay (7 curated Red Sea headlines)
> through the real agent for the first time — its `signal_lead_hours`
> **changed from the previously-pinned stub-only value of 1464.0 to a real
> 1800.0** (~75 days), the actual number PLAN.md/spec.md had been flagging
> as "still needs verification against a live key" since Phase 8 landed.
> Committed 9 real `.llm_cache/` entries (the canonical scenario + all 7
> backtest headlines + one real LLM-generated `/public/status` conservation
> copy) — restarted the backend fresh afterward and confirmed every one of
> these reproduces byte-identically from the cache alone, with **no new
> network call**, satisfying "the canonical demo runs fully offline"
> literally, not just in theory. `.chroma/` stays gitignored as always
> (rebuilt idempotently at boot from the committed corpus JSON).
>
> **A real bug found and fixed along the way, not anticipated by this
> section**: the first `pytest` run against the real `.env` failed 11 tests.
> Root cause: `tests/test_api.py`/`test_auth.py`'s `client` fixture and
> `tests/test_backtest.py`'s direct `run_backtest()` calls never
> monkeypatched `USE_REAL_AGENTS`/`GROQ_API_KEY` themselves — they silently
> relied on the ambient environment defaulting to off, unlike
> `tests/test_watch.py`'s own explicit `_real_agents_on`/flag-off fixtures.
> CLAUDE.md's claim that "no `GROQ_API_KEY` is ever required for `pytest`
> to pass" was true only by accident, never enforced. Fixed with one new
> autouse fixture in `tests/conftest.py` that forces the stub path by
> default for every test (`test_watch.py`'s file-local autouse fixture,
> which runs after it, still overrides it back on for the tests that want
> the real path — verified the override chain actually works, not just
> assumed). **That first broken run also leaked 6 unrelated test-fixture
> headlines into `.llm_cache/`** (e.g. `test_api.py`'s literal `"seized"`/
> `"routine patrol"` headlines actually hit the live API before the fix
> landed) — identified by grepping the exact headline text back against
> the test files and deleted before committing, so only real demo/backtest
> content ended up in the committed cache.
>
> **#3 is done, at the API layer**: flipped `USE_REAL_AGENTS=1` in the
> user's own local `.env` first, then — an explicit, asked-and-confirmed
> decision reversing this section's own original "don't flip
> `.env.example`'s default" note below — **`.env.example`'s committed
> template default is now `1` too** (`GROQ_API_KEY` itself stays blank in
> the template, so `run_watch()`'s own missing-key check still safely
> degrades a fresh `.env` copy with no real key to the stub; only a clone
> with genuinely no `.env` file at all is unaffected, since `.env.example`
> is never read directly — `backend/config.py`'s own `Settings` default
> stays `0`). Verified the full `signal → Watch → Predict → Recommend →
> Advise → Geo`
> cascade end-to-end against a running frontend through the real Vite dev
> proxy, twice (India Connect Portal/spec.md Phase 10 has the full 9-beat
> breakdown). **Not literally browser-verified** — no
> browser-automation/screenshot tool was available in this environment, so
> "against a running frontend" means real HTTP calls through the same
> proxy path a browser would use, not an actual click-through. Flagged
> honestly, not silently skipped.
>
> **#4 and #5 are continuously true** (323 tests green, up from 319;
> CLAUDE.md/PROJECT_GUIDE.md/PLAN.md kept in sync per-phase, not batched).

**Goal:** make the whole v1.3 surface demo-safe and merge it in — the closing
gate for Segment 1, mirroring the PRD's own "never move the gate, cut scope"
discipline.

**Work:**
1. One curated, deterministic demo dataset (headlines, AIS replay, backtest case) committed to the repo — "works for me" must equal "works on stage" (PRD §12).
2. Pre-embed the RAG store and commit the LLM response cache so the canonical demo runs fully offline.
3. Flip `USE_REAL_AGENTS=1` by default; verify the full `signal → Watch → Predict → Recommend → Advise` cascade end-to-end against a running frontend, all new fields populated.
   > **Phase 4 architecture note (post-implementation):** this doesn't break
   > anything mechanically — `run_watch()`'s missing-`GROQ_API_KEY` check is
   > independent of the flag and still short-circuits to the stub either way
   > (SPEC.md Phase 4 decision #9) — but it does quietly abandon decision
   > #17's "both the flag *and* the key must be set" double opt-in, in favor
   > of the key alone being the real on/off switch. Fine for a curated demo
   > environment; make that trade-off on purpose here rather than by
   > accident, and don't flip `.env.example`'s own default while doing it —
   > a fresh clone/CI run still must stay stub-only with zero config.
   >
   > **Reversed, on purpose, at Phase 10 cut-over:** the user explicitly
   > chose to flip `.env.example`'s own committed `USE_REAL_AGENTS` default
   > to `1` too, not just the local `.env`. Still safe for a bare fresh
   > clone (`.env.example` is a template, never read directly — a clone
   > with no `.env` file stays on `backend/config.py`'s own `0` default) and
   > safe for a `.env` copy with no real key filled in (the flag alone
   > isn't enough — `run_watch()` still requires a real `GROQ_API_KEY`
   > too). The "must stay stub-only with zero config" guarantee this note
   > originally asked for now holds one level down — at the bare-clone/no-
   > `.env` level — rather than at the `.env.example`-copied level.
4. Full `pytest` run — every phase's new tests plus the original 91 — all green.
5. Update the status board in [PROJECT_GUIDE.md](../../PROJECT_GUIDE.md) and this file's phase table as each phase actually lands (don't batch this to the end).

**Acceptance:** `python -m pytest` all green; a fresh clone + `pip install` +
`uvicorn` + a browser reproduces the full v1.3 demo with no API keys required
(offline fallback path); repeat runs are byte-identical on the scored fields.

**Depends on:** Phases 1–8 (Phase 9 optional — cut it here if time is short;
✅ landed anyway).

---

### Suggested order & parallelism

```
Phase 1 (contract v2 + data model)  ── must be first, blocks everything below
        │
        ├── Phase 2 (Recommend: wrong-oil + true cost)   ── cheap, do it early
        ├── Phase 3 (Predict: power stress + sourcing)    ── parallel to 2
        ├── Phase 4 (Watch: RAG + LLM)                    ── parallel to 2/3
        │       │
        │       ├── Phase 8 (Backtest)  ── ✅ landed, needed real Watch from Phase 4
        │       └── Phase 9 (Alarm-language + LLM copy, stretch)  ── ✅ landed
        └── Phase 5 (Knowledge graph)                     ── independent, ✅ landed
                │
                └── Phase 6 (Geospatial data: AIS + GeoJSON)  ── ✅ landed, used
                │                                                Phase 5's affected_by()
                │                                                for affected_refinery_ids
                │       │
                │       └── Phase 7 (Dark-ship ML)  ── ✅ landed, needed Phase 6's AIS
                │                                      data + Phase 4's watch.py import
                │                   │
                │               Phase 10 (determinism, tests, cut-over) ── last
```

Phases 2, 3, 4, 5 are independent once Phase 1 lands — pick whichever unblocks
the next demo beat fastest. Phase 6 is no longer independent: it needs Phase 5's
`affected_by()` to populate `affected_refinery_ids` (SPEC.md Phase 5 decision #1
deliberately shipped the query without the wiring; Phase 6 is the wiring). Per
the PRD's own cost/benefit note, **Phase 2 is the highest depth-per-hour work in
the whole v1.3 scope** — do it right after Phase 1.

---

## 3 · Segment 2 — Frontend + Integration: scope by chunk

> **STATUS: stack decision changed.** The frontend of record is no longer
> `frontend/` (Next.js). A second, independently-built frontend —
> **`India Connect Portal/`** (Vite + TanStack Start/Router, Bun,
> Lovable-originated) — landed with a more complete visual design and has
> been chosen to **replace** `frontend/` as the real Urja Kavach frontend
> going forward. `frontend/` is now **legacy/superseded**, not deleted yet
> (deleting it is a separate, explicit action for later — PLAN.md doesn't do
> destructive repo changes on its own).
>
> The chunk table below (A–I) is still the correct **scope** breakdown and is
> kept for that reason, but it is no longer the *plan* — as of this stack
> switch, `India Connect Portal/` starts from zero backend wiring (it was
> built entirely against hardcoded mock data, with a fake client-side auth
> system, independent of `frontend/`'s work). **The real, current build plan
> is [India Connect Portal/spec.md](../../India%20Connect%20Portal/spec.md)**,
> which re-derives this same A–I scope as its Phases 4–9, but adds the
> baseline wiring work (contract sync, real JWT auth, live WS state, a
> signal-injection entry point) that this table's Segment-1-dependency
> framing assumed was already solved by `frontend/`'s existing
> `useRiskState()`/`lib/api.ts`/`lib/session.ts` — none of which
> `India Connect Portal/` had. Read spec.md before picking up any Segment 2
> work; treat this table as the feature checklist it maps to, not the
> sequencing.

Segment 2 is not phased as tightly as Segment 1 because each chunk is a fairly
self-contained UI slice that just needs its Segment-1 data source to exist first.
Listed roughly in the order its backing Segment-1 phase is expected to land.

| Chunk | What it builds | Needs (Segment 1) | India Connect Portal/spec.md phase |
|---|---|---|---|
| **A · Contract sync** | Hand-update `types/contract.ts` to mirror every contract change from Phase 1 onward (no codegen — this is a standing rule, not a one-time task) | Phase 1, ongoing | Phase 1 — ✅ landed |
| **B · Reroute cards v2** | Greyed-out "grade incompatible" state with the `reason` shown; cost-breakdown tooltip (crude / insurance / detour) on hover; rank driven by `true_cost` | Phase 2 | Phase 4 — ✅ landed (field-reconciliation + real Approve pulled forward into Phase 3; this phase added the sort toggle and selecting which reroute to approve) |
| **C · Assumption slider UX** | Fact-type = narrow locked-range slider; estimate-type = wide slider + source note on hover; the one internal constant = explicit "not sourced" tag; power-stress bar added to the what-if chart; slider drag-away-from-default triggers the override write (calls whatever Phase 3 exposes) and shows up in the audit trail panel | Phase 3 | Phase 5 — ✅ landed |
| **D · Provenance popovers v2** | Wire the existing click-a-score popover to real retrieved snippets (headline, source, timestamp) instead of placeholder text | Phase 4 | Phase 6 — ✅ landed (the shape wasn't just unconfirmed, it didn't exist — added `GET /provenance?ids=` to the backend) |
| **E · Knowledge-graph highlight** | When a scenario triggers, pulse the affected-refinery nodes on the map using `geo.affected_refinery_ids` | Phase 6 (Phase 5 ships the underlying `affected_by()` query, but `geo` itself stays `None` until Phase 6 calls it — see SPEC.md Phase 5 decision #1) | Phase 7 — ✅ landed |
| **F · Geospatial map v2** | Extend the existing Google Maps integration: animate AIS tanker tracks along corridors from `/geo/state`; render `dark_tanker_ids` as pulsing warning markers; corridor polylines from the committed GeoJSON, colour-bound to live `corridor_risk.score` | Phase 6 (+ Phase 7 for dark markers) | Phase 7 — ✅ landed (also found `geojson_path` wasn't browser-fetchable and embedded parsed geometry into `/geo/state` to fix it) |
| **G · Backtest chart** | New panel on the official cockpit: Watch-score-vs-Brent overlay chart + the lead-time callout number, calling `GET /backtest/{id}` | Phase 8 | Phase 8 — ✅ landed (also found `api.ts`'s hand-authored `BacktestResponse` type didn't match the live endpoint and fixed it before charting) |
| **H · Public portal copy** | Citizen board renders `GET /public/status`'s real `message`/`conservation_plan`/`action_feed` shape (`India Connect Portal/`'s citizen board currently renders unrelated hardcoded advisory copy, so — unlike this row's original "should need zero structural change" framing, written for `frontend/` — this is a real rebuild here, not just a visual check) | Phase 9 | Phase 9 — ✅ landed (also fixed a hardcoded "there is no shortage" headline that would have contradicted a real `Shortage` status) |
| **I · Demo rehearsal** | Run the full 9-beat demo script (PRD §18) against the live v1.3 stack end-to-end at least twice; fix any panel that doesn't animate correctly off a real (non-stub) cascade | Phase 10 | Phase 10 — ✅ landed (real agent path, not stub — a live `GROQ_API_KEY` became available; also formally marks `frontend/` legacy) |

**Standing rule carried over from v1.0, now retargeted:** a WS-backed
`useRiskState()`-equivalent hook remains the single subscription point
(✅ spec.md Phase 3 landed — `src/hooks/useRiskState.ts`, with **no**
demo-data fallback on disconnect, stricter than `frontend/`'s own version).
Every panel reads from that hook (or a sibling hook for `/geo/state` and
`/backtest/{id}`, which are not part of the WS-pushed `RiskState` snapshot)
— never a parallel ad hoc fetch.

**Non-negotiable added at the stack switch (see spec.md §1):** no committed
secrets (✅ spec.md Phase 0 landed — `.env` is now gitignored, the
Lovable-connector Maps key was replaced with a self-owned, restricted one),
real JWT auth only (✅ spec.md Phase 2 landed — no client-side-fake/
plaintext-password auth; role-gating verified server-side against a live
backend, 401/403 both confirmed), and the UI must never render fabricated
data with the same visual treatment as live data (✅ — every panel that
isn't wired yet is explicitly labeled "preview"/"sample copy"/"illustrative"
rather than silently mixed in with real numbers).

---

## 4 · Cross-segment sequencing

Segment 1 Phase 1 is the hard gate: no Segment 2 chunk beyond **A** can start
until the widened contract exists, because every other chunk reads a field that
doesn't exist before then. Beyond that, pair each Segment 1 phase with its
Segment 2 chunk and ship them close together — this mirrors the v1.0 "Gate 2:
one signal flows end-to-end, ugly is fine" discipline from the original build,
applied to each new feature instead of to the whole system once.

| Land this (Segment 1) | Then this (Segment 2) | Demoable outcome |
|---|---|---|
| Phase 1 | Chunk A | Nothing new to see yet, but the frontend no longer drifts from the contract |
| Phase 2 | Chunk B | "Cheapest option greyed out; insurance flips the ranking" — PRD §18 beat 6 |
| Phase 3 | Chunk C | "Drag a slider — dominoes recompute, power-stress bar moves" — PRD §18 beat 5 |
| Phase 4 | Chunk D | Provenance popovers show real sources instead of placeholders |
| Phase 5 + 6 | Chunk E + F | Tanker tracks animate; affected refineries pulse — PRD §18 beat 4 |
| Phase 7 | Chunk F (dark markers) | "Three tankers just went dark near Hormuz" — the real-ML beat |
| Phase 8 | Chunk G | "Score crossed alert weeks before Brent fully priced in the crisis" — PRD §18 beat 2 (SPEC.md's hand-verified worked example measured ~61 days/1,464 hours on the deterministic stub path; the real-agent number, verified once a live `GROQ_API_KEY` became available in Phase 10, is ~75 days/1,800 hours — not the "34 hours" this row originally estimated before the case was curated) |
| Phase 9 | Chunk H | Conservation copy is LLM-generated, portal unchanged visually |
| Phase 10 | Chunk I | Full demo script runs clean, twice, on real agents |

---

## 5 · Determinism, testing & demo-safety (non-negotiable, carried over from PRD §10/§17)

- Cache every LLM/embedding call by input hash — the same headline must always
  produce the same score on stage, every rehearsal, every judge's laptop.
- Every real agent ships with an **offline fallback** to its stub behind
  `USE_REAL_AGENTS` — a missing API key or a network blip must never hard-fail
  the demo.
- AIS and backtest data are **replayed, curated, and committed** — never a live
  paid feed. Say this openly; it's honest scoping, not a shortcut.
- The backtest result is framed as **one illustrative historical case**, never as
  a validated production accuracy metric — repeat this in code comments and any
  UI copy that surfaces `signal_lead_hours`.
- Whenever a contract field changes: update `contract.py` **and**
  `types/contract.ts` **and** the mock/example `/state` payload in
  [README.md](../../README.md) in the same change. `extra="forbid"` will catch drift
  loudly — treat that failure as the safety net working, not an obstacle.

---

## 6 · Open decisions

Flag these before the relevant phase starts — don't guess silently:

1. ~~**LLM provider (blocks Phase 4).** The PRD's tech-stack table names
   Gemini 3.5 Flash (primary) / Haiku 4.5 (fallback); this repo's existing
   scaffolding notes (CLAUDE.md, `.env.example` conventions) lean Anthropic
   (`claude-sonnet-5` primary / `claude-haiku-4-5` for cheap calls). Pick one
   before writing `backend/agents/llm.py` — don't build two clients.~~
   **Decided (SPEC.md): Groq** — neither named option; free tier, no cost
   pressure for repeated demo/rehearsal runs. `llama-3.3-70b-versatile`
   primary, `llama-3.1-8b-instant` fallback, then the deterministic stub.
2. ~~**Vector store** — ChromaDB vs FAISS for RAG (Phase 4). PRD allows either;
   ChromaDB is the PRD's stated default and is zero-config locally.~~
   **Decided (SPEC.md): ChromaDB**, with its bundled local ONNX MiniLM
   embeddings (not an embeddings API — neither Anthropic nor Groq offers
   one, and a local model keeps retrieval working with zero API keys).
3. ~~**`Reroute.cost` vs `true_cost`** (Phase 1/2)~~ **Decided (SPEC.md):** `cost`
   keeps meaning "crude price only" (v1.0 semantics preserved); `true_cost` is
   the new F17 ranking field, equal to `cost` until Phase 2 adds real surcharges.
4. ~~**Override-logging endpoint shape** (Phase 3) — a flag on `POST /simulate`
   vs. a dedicated `POST /assumptions/override`.~~ **Decided (SPEC.md):** a
   dedicated `POST /assumptions/override`, auth required (any role) — keeps
   `/simulate` pure/no-mutation; logs to `audit_log` immediately but only
   ever stamps `RiskState.assumption_overrides` at Approve time.
5. ~~**Backtest historical case** (Phase 8) — 2025 US-Iran standoff vs. a Red
   Sea/Houthi episode; PRD names both as options. Pick one, curate its dataset
   once, don't build two.~~ **Decided (SPEC.md): the Red Sea/Houthi shipping
   crisis, Nov 2023 – Mar 2024**, scored on `suez_cape` — reuses
   `watch_corpus.json`'s existing events (densified with three more real,
   dated headlines) and the same crisis Phase 2 already cited for
   `suez_cape.war_risk_pct`. Only one case was built.

---

*Urja Kavach · PLAN v1 · tracks the PRD v1.0 → v1.3 gap · keep this file and the
[PROJECT_GUIDE.md](../../PROJECT_GUIDE.md) status board in sync as phases land.*
