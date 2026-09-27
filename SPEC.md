# SPEC — Segment 1 implementation specs (Urja Kavach v1.3)

> This file is a **running log**, one section per landed/in-progress
> [PLAN.md](.claude/docs/PLAN.md) phase, each refined through an interview that surfaced
> gaps PLAN.md's phase description left open. A section is the
> implementation-ready spec for *that phase only* — it doesn't re-litigate
> other phases. Where a question genuinely belongs to a later phase, it's
> listed under that section's "Explicitly deferred", not answered early.
>
> **Sections:** [Phase 1 — Contract v2 & data-model foundation](#spec--segment-1-phase-1-contract-v2--data-model-foundation)
> (✅ landed) · [Phase 2 — Recommend depth: wrong-oil gate + real route cost](#spec--segment-1-phase-2-recommend-depth-wrong-oil-gate--real-route-cost-f16-f17)
> (✅ landed) · [Phase 3 — Predict v1.3: power stress + sourced assumptions + override audit](#spec--segment-1-phase-3-predict-v13--power-stress--sourced-assumptions--override-audit-f3-f15-f20-f9)
> (interview complete, implementation-ready) · [Phase 4 — Watch real agent: RAG + LLM scoring, provenance, confidence bands](#spec--segment-1-phase-4-watch-real-agent-rag--llm-scoring-provenance-confidence-bands-f1-f2-f8-f12)
> (interview complete, implementation-ready) · [Phase 5 — Knowledge graph](#spec--segment-1-phase-5-knowledge-graph-f10)
> (interview complete, implementation-ready) · [Phase 6 — Geospatial data layer: AIS replay + GeoJSON + `/geo/state`](#spec--segment-1-phase-6-geospatial-data-layer-ais-replay--geojson--geostate-f11-f13)
> (interview complete, implementation-ready) · [Phase 7 — Dark-ship anomaly detector](#spec--segment-1-phase-7-dark-ship-anomaly-detector--the-real-ml-component-f18)
> (interview complete, implementation-ready) · [Phase 8 — Backtest / validation module](#spec--segment-1-phase-8-backtest--validation-module-f14)
> (interview complete, implementation-ready) · [Phase 9 — Alarm-language score + LLM conservation copy](#spec--segment-1-phase-9-alarm-language-score--llm-conservation-copy-f19-f7-slice)
> (interview complete, implementation-ready).

---

# SPEC — Segment 1, Phase 1: Contract v2 & data-model foundation

---

## 1 · Decisions made (interview log)

These resolve ambiguities PLAN.md's Phase 1 section didn't settle. Each
follows the same underlying principle: **within a block an agent writes, every
field stays required** (mirrors the contract's existing Impact/Assumptions/
Reserve philosophy — optionality lives at the RiskState block level, never
inside a populated block) — and where that forces a currently-passing stub or
agent to be touched, Phase 1 makes the **minimal mechanical edit** needed to
keep `pytest` green, deferring all *real* logic/modeling to its named later
phase.

| # | Decision | Why |
|---|---|---|
| 1 | **Assumptions migration**: mechanical patch to `stubs.py` now; real sourcing/coefficients/`power_stress` computation stay in Phase 3 | Keeps phases cleanly separated; avoids a dual-shape compat shim |
| 2 | **`Reroute.refinery_id`** added now; Recommend still emits one row per *supplier* in Phase 1 (unchanged); Phase 2 fans candidates out per (supplier × refinery) | Today's `compatible` check is refinery-agnostic (checks against the union of *all* refineries' grades) — the wrong-oil gate needs a specific refinery to be meaningful |
| 3 | **`Impact.power_stress_pct`**: required float, stub emits `0.0` | Consistent with every other `Impact` field being required |
| 4 | **Corridor/Refinery new columns**: seeded with real, cited estimates now, not placeholders | Cheap to source correctly up front; avoids a second seed-data pass |
| 5 | **`Reroute`'s five new fields** (`grade_ok`, `rank_eligible`, `reason`, `cost_breakdown`, `true_cost`): required, with a mechanical placeholder computed in `recommend.py` | Same consistency principle as #3; Phase 2 replaces the placeholder logic with the real gate + true-cost math |
| 6 | **`AssumptionEntry.range`**: metadata only, not enforced by Pydantic | Matches the existing philosophy of clamping in agents, not the schema |
| 7 | **`AssumptionOverride.who`**: typed as required `str` now; whether it's a verified JWT subject or a placeholder actor is a Phase 3 decision (ties to PLAN.md's open decision #4 on `/simulate` auth) | `/simulate` isn't auth-gated today; deciding to gate it is out of Phase 1's scope |
| 8 | **Local dev DB**: no migration script. Note that a local SQLite file created before this change should be deleted and let the app recreate it | Recommendation/audit_log rows serialized in the old `Assumptions` shape won't deserialize under the new contract; there's no Alembic in this repo and this is disposable dev/demo data, not shared state |

---

## 2 · Contract changes (`backend/schemas/contract.py`)

All new models get `model_config = _STRICT` (`extra="forbid"`), consistent
with every existing model. Version bump: add a module-level comment noting
this is the **v1.3 shape** (no runtime `CONTRACT_VERSION` constant — none
exists today and nothing currently consumes one; not introducing new surface
area beyond what PLAN.md asked for).

### 2.1 `Impact` — one new required field

```python
class Impact(BaseModel):
    supply_gap_pct: float
    price_rise_pct: float
    gdp_delta_pct: float
    refinery_runrate_pct: float
    power_stress_pct: float   # NEW — required. F15.
```

### 2.2 `AssumptionEntry` — new model, the typed replacement for a bare float

```python
class AssumptionEntry(BaseModel):
    model_config = _STRICT
    value: float
    type: Literal["fact", "estimate", "internal"]
    range: tuple[float, float]   # [lo, hi] — descriptive only, NOT validated (decision #6)
    src: str
```

### 2.3 `Assumptions` — breaking change, every field becomes an `AssumptionEntry`

```python
class Assumptions(BaseModel):
    model_config = _STRICT
    supply_lost_pct: AssumptionEntry
    buffer_days: AssumptionEntry
    price_elasticity: AssumptionEntry
    power_oil_dependence: AssumptionEntry      # NEW key. F20.
    gdp_oil_sensitivity: AssumptionEntry       # NEW key. F20.
    power_stress_multiplier: AssumptionEntry   # NEW key. F20.
```

All six keys are **required** — this is the one field-level breaking change
in Phase 1 (§4 below covers the stub patch that keeps it valid).

### 2.4 `AssumptionOverride` — new model

```python
class AssumptionOverride(BaseModel):
    model_config = _STRICT
    who: str          # decision #7 — identity source resolved in Phase 3
    field: str        # which assumption key was overridden, e.g. "price_elasticity"
    from_default: float
    to_value: float
    ts: datetime
```

### 2.5 `RiskState` — one new field

```python
assumption_overrides: list[AssumptionOverride] = Field(default_factory=list)
```

Always present, defaults to `[]` — same pattern as `reroutes` today.

### 2.6 `CostBreakdown` — new model

```python
class CostBreakdown(BaseModel):
    model_config = _STRICT
    crude: float = Field(ge=0)
    war_risk_insurance: float = Field(ge=0)
    detour: float = Field(ge=0)
```

### 2.7 `Reroute` — five new required fields + `reason`

```python
class Reroute(BaseModel):
    supplier: str
    route: str
    days: float
    cost: float                       # UNCHANGED semantics: crude price only (PLAN.md §6 decision #3, confirmed)
    compatible: bool                  # UNCHANGED — v1.0 soft-downweight field, left alone
    rank: int
    refinery_id: str                  # NEW, required. Decision #2.
    grade_ok: bool                    # NEW, required. F16 — placeholder value in Phase 1, real gate in Phase 2.
    rank_eligible: bool                # NEW, required. F16.
    reason: Optional[str] = None      # NEW, optional — only meaningful once Phase 2 populates it
    cost_breakdown: CostBreakdown     # NEW, required. F17.
    true_cost: float = Field(ge=0)    # NEW, required — the Phase 2 ranking field. F17.
```

`compatible` and `grade_ok` both exist post-Phase-1 with identical values
(`grade_ok` just mirrors `compatible` until Phase 2 makes it a real hard
gate) — this duplication is intentional and temporary, not a design mistake;
note it in the PR description so Phase 2's author isn't confused about which
field to change.

### 2.8 `Geo` — new model, optional block

```python
class Geo(BaseModel):
    model_config = _STRICT
    at_risk_tanker_ids: list[str]
    dark_tanker_ids: list[str]
    affected_refinery_ids: list[str]
```

`RiskState.geo: Optional[Geo] = None` — stays `None` until Phase 6/7 populate
it. All three list fields are required *within* the model (no defaults) —
Phase 6 must explicitly pass `[]`, mirroring `CorridorRiskEntry`'s style.

### 2.9 `Validation` — new model, optional block

```python
class Validation(BaseModel):
    model_config = _STRICT
    backtest_id: str
    signal_lead_hours: float

RiskState.validation: Optional[Validation] = None
```

Stays `None` until Phase 8.

### 2.10 `PredictAgentOutput` — unchanged shape, wider contents

No structural change (`{impact, assumptions}`); both nested types are wider
per above.

---

## 3 · DB / seed changes

### 3.1 `backend/models.py`

```python
class Corridor(Base):
    ...
    war_risk_pct: Mapped[float] = mapped_column(Float, nullable=False)
    detour_days: Mapped[float] = mapped_column(Float, nullable=False)
    geojson_path: Mapped[str] = mapped_column(String, nullable=False)

class Refinery(Base):
    ...
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
```

`nullable=False` matches every existing column's style — seed data supplies a
value for every row (§3.2), so there's no null-backfill case to handle.

### 3.2 Seed data — real, cited values (decision #4)

**`backend/seed/corridors.json`** — `war_risk_pct` is a fraction of crude
value (e.g. `0.004` = 0.4%), sourced from public reporting on Joint War
Committee–listed high-risk transit zones and Red Sea/Cape-reroute coverage;
`detour_days` is the extra transit time this route/corridor adds versus the
shortest available path. These are **estimates**, not measured facts — flag
them as such wherever they surface in the UI later (the same `type: "estimate"`
honesty framing PRD §20 applies to Predict's assumptions applies here too,
even though corridors aren't part of the `Assumptions` model):

| id | war_risk_pct | detour_days | geojson_path | rationale |
|---|---|---|---|---|
| hormuz | 0.004 | 0.0 | `backend/seed/geo/hormuz.geojson` | JWC-listed elevated-risk strait; direct route, no detour baseline |
| suez_cape | 0.001 | 10.0 | `backend/seed/geo/suez_cape.geojson` | Lower war-risk than Red Sea proper; Cape-of-Good-Hope reroute adds ~10 days transit vs. Suez, per widely reported Red-Sea-crisis rerouting figures (10–14 day range cited) |
| atlantic | 0.0005 | 0.0 | `backend/seed/geo/atlantic.geojson` | Open ocean, no chokepoint, already the direct path |
| malacca | 0.0015 | 0.0 | `backend/seed/geo/malacca.geojson` | Historical piracy risk, lower than Hormuz; already the direct Asia-Pacific path |

The `.geojson` files themselves are **not** created in Phase 1 — the column
just carries the path Phase 6 will commit a real polyline to. Document this
explicitly in the seed file's structure/comments so it isn't mistaken for a
missing-file bug.

**`backend/seed/refineries.json`** — approximate public-domain refinery
coordinates (verify precisely against OSM/satellite imagery when Phase 6
actually renders map pins; good enough for seeding now):

| id | lat | lon | rationale |
|---|---|---|---|
| jamnagar | 22.34 | 69.85 | Reliance Jamnagar refinery complex, Gujarat |
| vadinar | 22.47 | 69.73 | Nayara Energy refinery, Vadinar, Gujarat |
| paradip | 20.29 | 86.60 | IOCL Paradip refinery, Odisha |

### 3.3 Dev DB reset (decision #8)

No migration script. Document in this phase's PR: **delete your local
`*.db` file before running `uvicorn` after pulling this change** — startup
recreates tables and reseeds config idempotently; any old `risk_state` /
`recommendations` / `audit_log` rows serialized under the pre-Phase-1
`Assumptions` shape are dev/demo data, not something to preserve.

---

## 4 · Mechanical agent patches (required to keep `pytest` / the cascade green)

Scope discipline: these edits change **shape-filling defaults only** — zero
new modeling logic. Anything that changes *what number comes out* (real
sourcing arithmetic, the real wrong-oil gate, real true-cost ranking) is
explicitly out of scope here and belongs to Phase 2/3.

### 4.1 `backend/agents/stubs.py` — `assumptions_from_severity`

Wrap the three existing values in `AssumptionEntry`, and add the three new
keys using the PRD's own already-sourced defaults (PROJECT_GUIDE.md §08) —
these aren't invented placeholders, they're the PRD's stated defaults, just
not yet wired into any arithmetic:

```python
def assumptions_from_severity(
    severity: float, buffer_days: float = 9.0, price_elasticity: float = 3.0
) -> Assumptions:
    supply_lost = round(_clamp(severity * 100, 0.0, 100.0), 1)
    return Assumptions(
        supply_lost_pct=AssumptionEntry(
            value=supply_lost, type="fact", range=(35.0, 45.0),
            src="brief: Hormuz transit share",
        ),
        buffer_days=AssumptionEntry(
            value=float(buffer_days), type="fact", range=(6.0, 9.5),
            src="ISPRL SPR capacity vs. typical fill level",
        ),
        price_elasticity=AssumptionEntry(
            value=float(price_elasticity), type="estimate", range=(3.0, 10.0),
            src="inverse of published short-run oil demand elasticity",
        ),
        power_oil_dependence=AssumptionEntry(
            value=0.015, type="fact", range=(0.01, 0.02),
            src="oil-fired generation share is negligible in India's grid",
        ),
        gdp_oil_sensitivity=AssumptionEntry(
            value=0.03, type="estimate", range=(0.02, 0.08),
            src="published $10-Brent-rise GDP-drag estimates",
        ),
        power_stress_multiplier=AssumptionEntry(
            value=7.5, type="internal", range=(5.0, 10.0),
            src="no external reference — internal calibration constant",
        ),
    )
```

> **Flag, don't silently resolve:** the PRD's illustrative `/state` example
> (PROJECT_GUIDE.md §08) shows `price_elasticity: 5` in a sample scenario, but
> the stub's actual default parameter is `3.0`. Phase 1 keeps the stub's
> existing default (`3.0`) unchanged — only the metadata (`type`/`range`/`src`)
> is new. Don't quietly change `3.0 → 5` while touching this function; that's
> a behavior change belonging to Phase 3 if it happens at all.

### 4.2 `backend/agents/stubs.py` — `run_predict_stub`

Unpack `.value` from each `AssumptionEntry` (arithmetic itself **unchanged**
— still the uncorrected `0.066` coefficient, still no power-stress
computation; Phase 3 replaces both), and add the placeholder `power_stress_pct`:

```python
def run_predict_stub(assumptions: Assumptions) -> PredictAgentOutput:
    gap = _clamp(assumptions.supply_lost_pct.value, 0.0, 100.0)
    price_rise = (gap / 10.0) * assumptions.price_elasticity.value
    gdp_delta = -(price_rise * 0.066)   # unchanged — Phase 3 corrects this
    run_rate = _clamp(100.0 - gap * 0.75, 0.0, 100.0)

    impact = Impact(
        supply_gap_pct=round(gap, 1),
        price_rise_pct=round(price_rise, 2),
        gdp_delta_pct=round(gdp_delta, 3),
        refinery_runrate_pct=round(run_rate, 1),
        power_stress_pct=0.0,   # placeholder — Phase 3 computes the real value
    )
    return PredictAgentOutput(impact=impact, assumptions=assumptions)
```

### 4.3 `backend/agents/recommend.py` — `score_options` / `Candidate` / `build_candidates`

Add a mechanical `refinery_id` resolution and wrap the existing
crude-price-only `cost` into a zero-surcharge `CostBreakdown`:

```python
@dataclass
class Candidate:
    supplier: str
    route: str
    days: float
    cost: float
    compatible: bool
    refinery_id: str   # NEW — resolved in build_candidates, see below
```

`build_candidates`: for each supplier, resolve `refinery_id` as the first
refinery (sorted by `id`) whose `compatible_grades` contains the supplier's
`crude_grade`; if none matches, fall back to the first refinery in the DB
(sorted by `id`) as a sentinel — the value is inert in Phase 1 (nothing reads
it yet besides the contract), Phase 2 is what makes it meaningful by fanning
candidates out per (supplier × refinery) instead of picking one.

`score_options`: when building each `Reroute`, add:

```python
refinery_id=c.refinery_id,
grade_ok=c.compatible,          # mirrors today's `compatible` — Phase 2 replaces with the real gate
rank_eligible=True,             # never hard-gated in Phase 1 — Phase 2's job
reason=None,
cost_breakdown=CostBreakdown(crude=c.cost, war_risk_insurance=0.0, detour=0.0),
true_cost=c.cost,               # equals crude cost while surcharges are 0 — Phase 2 makes this real
```

Ranking/sort order (`scored.sort(...)`) is **unchanged** in Phase 1 — still
sorts on `.total`/`.cost`/`.days`, not `.true_cost` (identical values right
now anyway since `true_cost == cost` while surcharges are zero).

---

## 5 · Frontend contract sync (Segment 2, Chunk A — paired with this phase per PLAN.md §4)

Update `frontend/types/contract.ts` by hand to mirror every change above:
`Impact.power_stress_pct`, the new `AssumptionEntry`/typed `Assumptions`,
`AssumptionOverride` + `RiskState.assumption_overrides`, `CostBreakdown` +
the five new `Reroute` fields, and `Geo`/`Validation` as nullable blocks on
`RiskState`. This is a type-only change — no component logic changes yet (the
UI that *reads* these new fields meaningfully is Chunks B/C/E/F/G, gated on
Phases 2/3/5/6/8 respectively). Existing components that spread/read `Impact`
or `Reroute` (e.g. `frontend/components/official/rerun-simulator.tsx`) should
still compile since they only read pre-existing fields — verify with
`npm run build` after the sync, not just visually.

---

## 6 · Test updates

- **`tests/test_contract.py`** — update fixtures for: `Impact` requiring
  `power_stress_pct`; `Assumptions` requiring six `AssumptionEntry` values
  instead of six floats; the round-trip/`extra="forbid"` tests need a
  contract-valid `Reroute` with all five new fields; add coverage for
  `AssumptionEntry`, `AssumptionOverride`, `CostBreakdown`, `Geo`,
  `Validation` (both "present and populated" and "absent/`None`" cases for
  the two optional blocks).
- **`tests/test_state_store.py`** — the direct `Impact(...)`, `Assumptions(...)`,
  `Reroute(...)` constructions (lines ~32, ~35, ~71) need the new required
  fields filled in.
- **`tests/test_recommend.py`** — `Candidate(...)` calls need a `refinery_id`
  argument; assertions on `.to_dict()` output can optionally check the new
  keys exist, but shouldn't assert on their *values* yet (Phase 2's job).
- No changes needed to `test_advise.py`, `test_api.py`, `test_auth.py` unless
  they happen to construct `Reroute`/`Assumptions`/`Impact` directly (grep
  before assuming).

---

## 7 · Documentation updates (same change, per the contract-change protocol)

- **`backend/schemas/contract.py`** module docstring — note the v1.3 shape.
- **`README.md`** — update the "Full state example" and "Partial state
  example" JSON blocks (§"Full state example (steady state)") to the new
  shape; update the "What's changing next" note to say Phase 1 has landed.
- **`PROJECT_GUIDE.md`** §08's target-shape JSON — mark it as **shipped**,
  not "target v1.3 shared risk-state shape"; update the status board line for
  the relevant Dev A / Dev B rows once this phase lands (per CLAUDE.md's
  standing rule not to let PLAN.md and PROJECT_GUIDE.md drift).
- **`PLAN.md`** — flip Phase 1's status once merged; note decisions #1–#8
  above inline or link back to this file so Phase 2/3's implementer isn't
  surprised by the placeholder fields they inherit.

---

## 8 · Acceptance criteria

1. `python -m pytest` fully green — the original 91 plus every fixture
   updated per §6.
2. `GET /state` on a **fresh boot** (no signal injected) still validates
   against the widened `RiskState`; `impact`, `assumptions`, `reserve` are
   `None`, `reroutes`/`assumption_overrides` are `[]`, `geo`/`validation` are
   `None`.
3. `POST /signal` still runs the full cascade end-to-end; the resulting
   `RiskState.assumptions` has all six typed keys populated with real
   `type`/`range`/`src` metadata; every `Reroute` in `reroutes` has
   `refinery_id`, `grade_ok`, `rank_eligible=True`, `reason=None`,
   `cost_breakdown` (with `war_risk_insurance=0.0`, `detour=0.0`), and
   `true_cost == cost`.
4. `frontend`: `npm run build` passes with the updated `types/contract.ts`
   (typecheck is the acceptance bar here, not new UI).
5. No behavior change to any *computed number* the demo currently shows —
   Phase 1 only widens shape; `gdp_delta_pct`, `price_rise_pct`,
   `refinery_runrate_pct`, and reroute ranking order are bit-identical to
   pre-Phase-1 output for the same input signal.

---

## 9 · Explicitly deferred (not decided here — flagged for the named phase)

- **Which refinery a Reroute is actually evaluated against** beyond the
  mechanical `refinery_id` resolution in §4.3 — real candidate fan-out
  per (supplier × refinery) is **Phase 2**.
- **The real wrong-oil gate and true-cost math** — **Phase 2**.
- **Real `power_stress_pct` computation and the corrected `gdp_delta`
  coefficient** — **Phase 3**.
- **Whether `AssumptionOverride.who` is a verified JWT subject and whether
  `/simulate` becomes auth-gated**, plus the override-logging endpoint shape
  (flag on `/simulate` vs. a dedicated endpoint — PLAN.md's own open decision
  #4) — **Phase 3**.
- **Real corridor GeoJSON files, AIS replay data, and `GET /geo/state`** —
  **Phase 6**.
- **`GET /backtest/{id}` and the `Validation` block's real values** —
  **Phase 8**.
- **Refining the war-risk/detour estimates in §3.2 with harder sourcing** —
  worth revisiting once Phase 2 needs them to actually flip a ranking on
  stage; Phase 1's numbers only need to be directionally defensible, not
  final.

---

---

# SPEC — Segment 1, Phase 2: Recommend depth — wrong-oil gate + real route cost (F16, F17)

> Scope: exactly [PLAN.md](.claude/docs/PLAN.md)'s Phase 2. Turns `Reroute.grade_ok` from
> Phase 1's mirror-of-`compatible` placeholder into a real hard eligibility
> gate, and turns `true_cost` from `true_cost == cost` into a real
> crude + war-risk-insurance + detour figure that can outrank the cheapest
> crude on the sheet. No contract changes — every field Phase 2 populates
> for real already exists on `Reroute`/`CostBreakdown` (Phase 1 added the
> shape; this phase gives it meaning). Depends on Phase 1 (landed).

## 1 · Decisions made (interview log)

| # | Decision | Why |
|---|---|---|
| 1 | **This file stays a running log** — this section is appended below Phase 1's rather than forking a new file | Matches PLAN.md's own living-document convention; SPEC.md's intro now indexes both sections |
| 2 | **`DAILY_SHIP_COST = 1.20`** (USD/bbl per detour-day), a module constant in `recommend.py` | In the range widely reported for Red-Sea-crisis Cape-of-Good-Hope reroute freight-cost impact (~$1–3/bbl). At `suez_cape`'s 10-day detour this adds ~$12/bbl — enough to unseat the cheapest-by-crude supplier from rank 1 with today's seed prices (§3 worked example). Labeled `estimate`-tier reasoning, same honesty framing as Phase 1's `war_risk_pct`/`detour_days` |
| 3 | **Seed revision: bump `suez_cape.war_risk_pct` 0.001 → 0.02, not `hormuz`'s** | **Correction of the literal interview question**, which asked about bumping `hormuz`. On reflection: in the canonical `hormuz_partial_closure` demo scenario, `hormuz` is the *disrupted, excluded* corridor — its own war-risk premium never appears in a rendered `Reroute` row, because no candidate routes through it. The corridor whose insurance premium actually needs to be visible is whichever one the *reroutes* run through — here, `suez_cape`. Its real-world justification is stronger too: Red Sea/Suez transits have carried genuinely elevated, widely-reported war-risk insurance premiums since the Houthi attacks began, and `0.02` (2%) matches the exact figure PROJECT_GUIDE.md §09 already cites ("war-risk insurance can jump from ~0.07% to ~2% of ship value"). `hormuz`/`atlantic`/`malacca` stay at their Phase 1 baseline — revisit if a future demo scenario disrupts a different corridor and routes reroutes through `hormuz` instead |
| 4 | **Scoring formula stays 3-term** (price/speed/compat); `compat_score` keeps deriving from the existing system-wide `compatible` flag (1.0/0.3), untouched by the new per-refinery `grade_ok` gate | Minimal diff — `WEIGHT_PRESETS` and the `scores` dict shape (`{price, speed, compat, total}`) are unchanged, so no caller/test outside `recommend.py` needs to know the gate exists. `grade_ok=True` always implies `compatible=True` (if *this* refinery accepts the grade, the union of all refineries does too), so `compat_score` is always `1.0` for any row that clears the gate — informational, not decisive |
| 5 | **Full `(supplier × refinery)` cross-product**, including grade-incompatible rows | Confirms SPEC.md Phase 1 decision #2. 7 suppliers × 3 refineries = 21 candidates pre-exclusion; with `hormuz` excluded in the canonical demo, 4 suppliers × 3 refineries = 12. §3's worked example shows this naturally produces both eligible and ineligible rows with *today's* seed data — no synthetic scenario needed to demo the gate |
| 6 | **Explicit eligible-first sort key**: `(not rank_eligible, -total, true_cost, days)`, replacing today's `(-total, cost, days)` | Self-documenting and robust to future weight/scoring changes, rather than relying on the incidental fact that a pinned `compat=1.0` keeps every eligible total above the forced `0.0` ineligible total. Tie-break also switches from `cost` to `true_cost` — the field that now actually drives ranking |
| 7 | **Min-max normalization uses eligible candidates only**, falling back to the full candidate set only if *zero* candidates are eligible (avoids an empty-list divide) | An ineligible row with an accidentally-cheap `true_cost` (wrong grade, but happens to be cheap crude) must not compress the price scale for the options that actually matter — that would mute the "insurance+detour flips the ranking" beat this phase exists to produce |
| 8 | **`true_cost`/`CostBreakdown` math lives inside `score_options`** (kept pure, DB-free, directly unit-testable); `Candidate` gains `war_risk_pct`, `detour_days`, `grade_ok`, `crude_grade`, `refinery_name` fields, populated by `build_candidates` from the `Corridor`/`Refinery` rows | Preserves `score_options`'s existing architecture note ("pure function — no DB, fully unit-testable"); `crude_grade`/`refinery_name` are needed only to build the `reason` string (decision #10) |
| 9 | **Round every `CostBreakdown` field and `true_cost` to 2 decimals** | USD-cents-level precision a procurement officer would actually read, applied once in the agent rather than pushed downstream to the API/UI |
| 10 | **`reason` is specific**: `f"{crude_grade} not compatible with {refinery_name}"`, e.g. `"Urals not compatible with Paradip (IOCL)"` | Self-explanatory in a UI tooltip with no cross-reference needed — demonstrates the "won't recommend oil a refinery can't run" pitch line on its own |
| 11 | **`cascade.py`'s `refill_days`**: first `rank_eligible=True` reroute's `days`, else `0.0` — not just `reroutes[0].days` | `reroutes[0]` is no longer guaranteed eligible in general (only guaranteed by decision #6's sort key, which is an invariant worth stating explicitly rather than relying on implicitly) — Advise must never simulate a refill against an option nobody could actually use |
| 12 | **No `GET /reroutes` signature change** — no new query params; ineligible rows stay in the default response body | Matches PLAN.md's own constraint. Any client-side filtering/greying is Segment 2, Chunk B's job, not this phase's |

## 2 · Backend changes (`backend/agents/recommend.py`)

### 2.1 `Candidate` — five new fields

```python
@dataclass
class Candidate:
    supplier: str
    route: str
    days: float
    cost: float
    compatible: bool        # UNCHANGED — system-wide (union) soft-downweight flag
    refinery_id: str
    grade_ok: bool           # NEW — per-refinery hard gate (F16)
    war_risk_pct: float      # NEW — from Corridor, for true_cost
    detour_days: float       # NEW — from Corridor, for true_cost
    crude_grade: str         # NEW — only used to build `reason` when grade_ok is False
    refinery_name: str       # NEW — ditto
```

### 2.2 `build_candidates` — fan out per `(supplier × refinery)`

Replaces `_resolve_refinery_id` (deleted — obsolete once every refinery gets
its own row) with a full cross-product:

```python
def build_candidates(
    session: Session, exclude_corridors: set[str] | None = None
) -> list[Candidate]:
    exclude_corridors = exclude_corridors or set()
    grades = _all_grades(session)
    corridors = {c.id: c for c in session.query(Corridor).all()}
    refineries = session.query(Refinery).all()

    candidates: list[Candidate] = []
    for s in session.query(Supplier).all():
        if s.corridor_id in exclude_corridors:
            continue
        corridor = corridors[s.corridor_id]
        for r in refineries:
            candidates.append(
                Candidate(
                    supplier=s.id,
                    route=s.corridor_id,
                    days=float(s.lead_days),
                    cost=float(s.base_price),
                    compatible=s.crude_grade in grades,
                    refinery_id=r.id,
                    grade_ok=s.crude_grade in (r.compatible_grades or []),
                    war_risk_pct=float(corridor.war_risk_pct),
                    detour_days=float(corridor.detour_days),
                    crude_grade=s.crude_grade,
                    refinery_name=r.name,
                )
            )
    return candidates
```

(`corridors` is prefetched into a dict once, not re-queried per supplier —
same spirit as the existing single-pass `_all_grades`.)

### 2.3 `score_options` — hard gate + true-cost ranking + eligible-first sort

```python
def _true_cost(cost: float, war_risk_pct: float, detour_days: float) -> tuple[float, CostBreakdown]:
    insurance = cost * war_risk_pct
    detour = detour_days * DAILY_SHIP_COST
    total = cost + insurance + detour
    return round(total, 2), CostBreakdown(
        crude=round(cost, 2),
        war_risk_insurance=round(insurance, 2),
        detour=round(detour, 2),
    )


def score_options(candidates: list[Candidate], weights: Weights) -> list[ScoredOption]:
    if not candidates:
        return []

    weights = weights.normalised()

    priced = [
        (c, *_true_cost(c.cost, c.war_risk_pct, c.detour_days))
        for c in candidates
    ]
    eligible = [(c, tc, cb) for c, tc, cb in priced if c.grade_ok] or priced

    true_costs = [tc for _, tc, _ in eligible]
    days = [c.days for c, _, _ in eligible]
    min_cost, max_cost = min(true_costs), max(true_costs)
    min_days, max_days = min(days), max(days)

    scored: list[ScoredOption] = []
    for c, true_cost, breakdown in priced:
        price = _norm(true_cost, min_cost, max_cost)
        speed = _norm(c.days, min_days, max_days)
        compat = 1.0 if c.compatible else 0.3

        if not c.grade_ok:
            total = 0.0
            reason = f"{c.crude_grade} not compatible with {c.refinery_name}"
        else:
            total = weights.price * price + weights.speed * speed + weights.compat * compat
            reason = None

        scored.append(
            ScoredOption(
                reroute=Reroute(
                    supplier=c.supplier,
                    route=c.route,
                    days=c.days,
                    cost=c.cost,               # UNCHANGED semantics: crude only
                    compatible=c.compatible,
                    rank=1,                     # placeholder; set after sort
                    refinery_id=c.refinery_id,
                    grade_ok=c.grade_ok,
                    rank_eligible=c.grade_ok,
                    reason=reason,
                    cost_breakdown=breakdown,
                    true_cost=true_cost,
                ),
                price_score=price,
                speed_score=speed,
                compat_score=compat,
                total=total,
            )
        )

    scored.sort(
        key=lambda s: (
            not s.reroute.rank_eligible,
            -s.total,
            s.reroute.true_cost,
            s.reroute.days,
        )
    )
    for i, opt in enumerate(scored, start=1):
        opt.reroute.rank = i
    return scored
```

`DAILY_SHIP_COST: float = 1.20` is a new module constant, defined next to
`WEIGHT_PRESETS`.

### 2.4 `backend/cascade.py` — one-line refill_days fix

```python
eligible = [r for r in reroutes if r.rank_eligible]
refill_days = eligible[0].days if eligible else 0.0
```

replaces `refill_days = reroutes[0].days if reroutes else 0.0`.

## 3 · Seed changes + worked example

### 3.1 `backend/seed/corridors.json`

Only `suez_cape.war_risk_pct` changes, `0.001 → 0.02` (decision #3):

```jsonc
{ "id": "suez_cape", "name": "Suez / Cape of Good Hope", "chokepoint": "Suez Canal",
  "base_volume_pct": 18.0, "status": "normal",
  "war_risk_pct": 0.02, "detour_days": 10.0,
  "geojson_path": "backend/seed/geo/suez_cape.geojson" }
```

Rationale to record in the seed file/PR: matches PROJECT_GUIDE.md §09's own
cited figure for Red-Sea-crisis war-risk premiums (~2% of ship value,
Houthi-attack era), replacing Phase 1's pre-crisis placeholder baseline.
`hormuz` (0.004), `atlantic` (0.0005), `malacca` (0.0015) are unchanged.

### 3.2 Worked example (`hormuz_partial_closure`, today's seed data)

With `hormuz` excluded, candidates are the 4 non-hormuz suppliers × 3
refineries = 12 rows:

| supplier | grade | crude | corridor | true_cost | eligible refineries | ineligible (reason) |
|---|---|---|---|---|---|---|
| `ru_urals` | Urals | 74.1 | suez_cape | **87.58** | jamnagar, vadinar | paradip ("Urals not compatible with Paradip (IOCL)") |
| `ng_bonny` | Bonny Light | 86.5 | suez_cape | 100.23 | jamnagar | vadinar, paradip |
| `us_wti` | WTI | 88.9 | atlantic | 88.94 | paradip | jamnagar, vadinar |
| `br_tupi` | Lula | 83.7 | atlantic | **83.74** | paradip | jamnagar, vadinar |

`true_cost = crude + crude*war_risk_pct + detour_days*1.20`, e.g.
`ru_urals`: `74.1 + 74.1*0.02 + 10*1.20 = 74.1 + 1.482 + 12.0 = 87.58`.

**The Phase 2 acceptance beat, demonstrated by today's seed data with no
synthetic scenario needed:** by raw crude price, `ru_urals` (74.1) is
cheapest. By `true_cost`, `br_tupi` (83.74) is cheapest — `ru_urals`'s 10-day
Cape detour plus Red Sea war-risk insurance (+$13.48/bbl combined) pushes it
behind a pricier-on-paper Atlantic route with zero detour and negligible
insurance. This is PRD §18 beat 6 and PROJECT_GUIDE.md §09's "ranking on
crude price alone is what a naive tool does" line, made concrete. The same
12-row set also naturally exercises the hard gate: 7 of the 12 rows are
`rank_eligible=False` with a specific `reason`, e.g. `ng_bonny`→`vadinar` and
`ng_bonny`→`paradip` (Bonny Light isn't in either refinery's
`compatible_grades`).

## 4 · Test updates

- **`tests/test_recommend.py`** — every `Candidate(...)` construction needs
  `grade_ok`, `war_risk_pct`, `detour_days`, `crude_grade`, `refinery_name`.
  `test_new_reroute_fields_are_mechanical_placeholders` and
  `test_incompatible_candidate_has_grade_ok_false_but_still_ranked` (Phase 1's
  placeholder-behavior tests) get replaced with real-behavior versions:
  - a `grade_ok=False` candidate gets `rank_eligible=False`, a non-`None`
    `reason` naming the grade and refinery, `total=0.0`, and is still present
    in the output (never dropped).
  - a candidate with the cheapest raw `cost` but a high-`detour_days`/
    `war_risk_pct` corridor can rank behind a pricier-crude, zero-detour
    candidate once `true_cost` is compared (mirrors §3.2's worked example
    with small hand-built numbers).
  - eligible rows always sort before ineligible rows regardless of preset
    (`cost`/`speed`/`balanced`) — construct a case where an ineligible
    candidate would win on raw cost/days alone and assert it still ranks
    last.
  - normalization uses only eligible candidates: an ineligible candidate with
    an extreme cost/days shouldn't change the `price_score`/`speed_score` of
    the eligible candidates (compare scores with and without the extreme
    ineligible row present).
  - `build_candidates`-level (or a small DB-backed test): confirms the full
    `(supplier × refinery)` cardinality for a known corridor-exclusion set.
- **`tests/test_api.py`** — existing assertions (`rank` forms a dense
  `1..len(reroutes)` sequence, `>=1` reroutes present) still hold unchanged.
  Add one assertion that a live `/signal` cascade's `GET /reroutes` response
  contains at least one `rank_eligible=False` row with a non-null `reason` —
  today's seed data guarantees this per §3.2, so it's a real regression
  check, not a synthetic fixture.
- **`tests/test_state_store.py`** — any direct `Reroute(...)` construction
  needs its `grade_ok`/`rank_eligible`/`reason`/`cost_breakdown`/`true_cost`
  values to actually be internally consistent now (e.g. `rank_eligible`
  matching whether `reason` is `None`), not just contract-shape-valid.

## 5 · Documentation updates (same change, per the contract-change protocol)

- **`backend/agents/recommend.py`** module docstring — note the hard gate and
  true-cost ranking replace the Phase 1 mechanical placeholders.
- **`PROJECT_GUIDE.md`** §09 — flip the "target" Recommend code sample to
  "shipped"; update the Dev A / status-board notes.
- **`PLAN.md`** — flip Phase 2's status once merged; link back to this
  section for the `DAILY_SHIP_COST`/seed-revision rationale so Phase 3+'s
  implementer isn't surprised by why `suez_cape`'s `war_risk_pct` changed
  after Phase 1 seeded it.

## 6 · Acceptance criteria

1. `python -m pytest` fully green, including every new/updated test in §4.
2. A candidate whose crude grade isn't in a given refinery's
   `compatible_grades` gets `rank_eligible=False` with a specific `reason`,
   is never silently dropped from the response, and always sorts after every
   eligible row regardless of the `sort` preset.
3. A route through a higher-war-risk/longer-detour corridor visibly loses
   rank to a pricier-on-crude-alone route once insurance + detour are added
   — demonstrable with today's seed data per §3.2, no synthetic fixture
   required for the demo itself (tests may still use small synthetic numbers
   for precision/edge-case coverage).
4. `GET /reroutes` keeps its exact current signature (`sort=cost|speed|balanced`,
   same response envelope) — only the *values* inside each row change.
5. `POST /signal`'s full cascade still runs end-to-end; `reserve.days_cover`
   / `drawdown_per_day` are computed from an eligible reroute's `days`, never
   an ineligible one's.

## 7 · Explicitly deferred (not decided here — flagged for the named phase)

- **Frontend rendering of the longer reroute list and the grade-incompatible
  greyed-out state** — Segment 2, Chunk B (PLAN.md).
- **Revisiting `hormuz`/`atlantic`/`malacca`'s `war_risk_pct` baselines** —
  only needed if/when a demo scenario disrupts a corridor other than
  `hormuz`, routing reroutes through one of these instead of `suez_cape`.
- **`DAILY_SHIP_COST` varying by vessel class or route** — out of scope; PRD
  and PLAN.md both treat it as one constant.

---

# SPEC — Segment 1, Phase 3: Predict v1.3 — power stress + sourced assumptions + override audit (F3, F15, F20, F9)

> Scope: exactly [PLAN.md](.claude/docs/PLAN.md)'s Phase 3. Replaces `run_predict_stub`
> with a real, still-pure `run_predict()` in a new `backend/agents/predict.py`
> (Predict is no longer a stub — only Watch is, after this phase); corrects
> the `gdp_delta` coefficient from the v1.0 hardcoded `0.066` to the sourced,
> slider-adjustable `gdp_oil_sensitivity`; computes `power_stress_pct` for
> real; and adds a dedicated override-audit endpoint whose bookkeeping is
> deliberately split in two: every exploratory slider commit is logged to
> `audit_log` immediately, but `RiskState.assumption_overrides` (and the WS
> broadcast that follows from touching it) is only stamped at **Approve**
> time, tying the live contract field to a real decision instead of every
> drag. No contract changes — every field this phase populates for real
> already exists (`Impact.power_stress_pct`, all six `Assumptions` keys,
> `AssumptionOverride`, `RiskState.assumption_overrides` — all landed in
> Phase 1). Depends on Phase 1 (landed). Independent of Phase 2.

## 1 · Decisions made (interview log)

| # | Decision | Why |
|---|---|---|
| 1 | **Module move**: `assumptions_from_severity` and a renamed `run_predict` (was `run_predict_stub`) relocate from `backend/agents/stubs.py` to a new `backend/agents/predict.py`; `stubs.py` keeps only `run_watch_stub` (+ its private helpers) | Predict stops being a stub this phase — Watch is now the *only* remaining stub, and the module name should say so. `cascade.py` and `backend/api/routes.py` update their imports; nothing about the function signatures changes (`assumptions_from_severity(severity, ...) -> Assumptions`, `run_predict(assumptions: Assumptions) -> PredictAgentOutput`) |
| 2 | **Override endpoint**: a dedicated `POST /assumptions/override`, not a flag on `POST /simulate` | `/simulate` is documented (`CLAUDE.md`, `routes.py`'s own module docstring) as a **pure, no-mutation** what-if endpoint, and `frontend/components/official/rerun-simulator.tsx` already calls it on every 120ms debounce tick while a slider drags — logging an audit row there would mean one row per tick. A separate endpoint lets the frontend call it once, on slider *release* (a deliberate "commit"), decoupled from the live-preview debounce loop |
| 3 | **Identity**: the override endpoint requires auth (`Depends(get_current_user)`, any authenticated role — not `require_role("official")`) | Matches `/approve`'s existing principle ("never a client-supplied name") without over-restricting: the what-if simulator lives on the official cockpit today, but nothing about F20's override-audit story is official-only by nature, and `get_current_user` is the cheaper, already-existing dependency |
| 4 | **Default baseline**: each submitted field is diffed against `assumptions_from_severity(store.get().severity)` recomputed **at call time** | Same function the cascade itself calls to seed defaults, and the same thing a fresh page load would show — no session-tracked "previous value" state needed |
| 5 | **Visibility split**: an override commit writes to `audit_log` immediately (one row per divergent field, action `"override_assumption"`) but never touches `RiskState.assumption_overrides` or triggers a WS push by itself. That field is stamped only by `POST /approve`, from whatever is still pending at that moment | Ties the live, WS-broadcast contract field to an actual decision (matches PRD §18 beat 7: "Approve → audit entry, including any slider overrides"), while `audit_log` still captures the full exploratory history for replay (F9) regardless of whether anything is ever approved |
| 6 | **Pending tracking**: `StateStore` gains an in-memory `_pending_overrides: dict[str, AssumptionOverride]` (keyed by field, not persisted, not part of `RiskState` until snapshotted). The override endpoint upserts/removes entries; a new `merge_assumption_overrides()` snapshots `list(pending.values())` onto `RiskState.assumption_overrides` through the normal `_commit` path (re-validate, stamp `updated_at`, publish) and then clears the dict; `set_scenario()` (called at the top of every `run_cascade`) also clears it | Keeps the bookkeeping cheap and out of the DB — it's transient, session-local intent, not a durable record (the durable record is `audit_log`). Clearing on a new scenario stops a prior what-if session's leftovers from bleeding into an unrelated signal |
| 7 | **`POST /approve` always calls `merge_assumption_overrides()`**, even when nothing is pending | If it only ran when `pending` was non-empty, a *second* approve with no new overrides would leave a *first* approve's stale overrides visible on `RiskState` indefinitely. Always snapshotting means the field is always exactly "what's tied to the most recent approval," including an explicit reset to `[]` |
| 8 | **Dedup**: one entry per field in the pending dict — resubmitting the same field overwrites, it doesn't append | The eventual snapshot reflects "what's different right now," not a full drag history. That history isn't lost — it's still in `audit_log`, just not repeated in the `RiskState` snapshot |
| 9 | **Revert-to-default**: a submitted value equal to the recomputed default (within a `1e-9` epsilon) writes **no** `audit_log` row and removes any existing pending entry for that field | No divergence = nothing to log; and a field the user dragged back to default before approving shouldn't still show up as "overridden" in the approval snapshot |
| 10 | **Override scope**: all six `Assumptions` keys are diffed/logged generically, not just the three keys with a UI slider today (`supply_lost_pct`, `buffer_days`, `price_elasticity`) | Zero backend change needed when Segment 2 Chunk C wires sliders for `power_oil_dependence`/`gdp_oil_sensitivity`/`power_stress_multiplier` later |
| 11 | **Clamping**: `price_rise_pct` → `[0, 100]`, `gdp_delta_pct` → `[-50, 0]`, `power_stress_pct` → `[0, 100]` (new). `supply_gap_pct`/`refinery_runrate_pct` keep their existing `[0, 100]` clamps, unchanged | PLAN.md: "clamp every percentage before return (schema won't)." Once sliders can push `price_elasticity` to 10 or an out-of-documented-range `power_stress_multiplier`/`gdp_oil_sensitivity` through a raw API call (the contract's `AssumptionEntry.range` is descriptive metadata only, never enforced — Phase 1 decision #6), the formula alone can produce an implausible percentage; a floor/ceiling keeps every number the UI renders inside a believable range without changing the formula itself |
| 12 | **Reasoning side-channel** (DEV_B_ROADMAP.md's optional Phase 3 chunk 5 — per-step arithmetic exposed for the UI) is **out of scope** | `PredictAgentOutput` keeps its exact `{impact, assumptions}` shape (unchanged per SPEC.md Phase 1 §2.10). Revisit if/when a Segment 2 chunk wants to render the glass-box math step-by-step |
| 13 | **`/approve`'s existing `audit_log` row gets one new payload key**: `assumption_overrides` (the pending snapshot at that moment, possibly `[]`) | Records the decision and the assumptions live for it together in one row, so replaying `audit_log` shows *why* a reroute was approved under which overrides, without a join against a separate override table |

## 2 · Backend changes

### 2.1 `backend/agents/predict.py` (new file)

Relocates `assumptions_from_severity` verbatim (same defaults, same
fact/estimate/internal metadata — nothing about *that* function's behavior
changes in this phase) and replaces `run_predict_stub` with `run_predict`,
which now: reads `gdp_oil_sensitivity`/`power_oil_dependence`/
`power_stress_multiplier` instead of the hardcoded `0.066` and the `0.0`
placeholder, and clamps every output percentage (decision #11):

```python
"""Predict agent — the sourced, slider-adjustable v1.3 domino model (F3/F15/F20).

Every input is a named, typed AssumptionEntry (fact | estimate | internal),
so the arithmetic below is exactly what a slider drag recomputes — no hidden
coefficients. Pure function: no DB, no mutation, fully unit-testable (mirrors
backend/agents/recommend.py's architecture note).
"""

from __future__ import annotations

from backend.schemas import Assumptions, AssumptionEntry, Impact, PredictAgentOutput

# Percentage bounds the formulas can't guarantee on their own once a slider
# (or a raw API call) pushes an input past its documented `range` metadata —
# `AssumptionEntry.range` is descriptive only, never enforced (SPEC.md Phase 1
# decision #6). Clamping here, not in the schema, matches the contract's
# existing philosophy (module docstring, backend/schemas/contract.py).
_PRICE_RISE_BOUNDS = (0.0, 100.0)
_GDP_DELTA_BOUNDS = (-50.0, 0.0)
_POWER_STRESS_BOUNDS = (0.0, 100.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def assumptions_from_severity(
    severity: float, buffer_days: float = 9.0, price_elasticity: float = 3.0
) -> Assumptions:
    """Default Predict inputs derived from severity (each is a live slider).

    Relocated from stubs.py unchanged (SPEC.md Phase 1's mechanical patch
    already gave every key its typed/sourced shape) — Predict just isn't a
    stub anymore, so its input-defaulting function lives with it.
    """

    supply_lost = round(_clamp(severity * 100, 0.0, 100.0), 1)
    return Assumptions(
        supply_lost_pct=AssumptionEntry(
            value=supply_lost, type="fact", range=(35.0, 45.0),
            src="brief: Hormuz transit share",
        ),
        buffer_days=AssumptionEntry(
            value=float(buffer_days), type="fact", range=(6.0, 9.5),
            src="ISPRL SPR capacity vs. typical fill level",
        ),
        price_elasticity=AssumptionEntry(
            value=float(price_elasticity), type="estimate", range=(3.0, 10.0),
            src="inverse of published short-run oil demand elasticity",
        ),
        power_oil_dependence=AssumptionEntry(
            value=0.015, type="fact", range=(0.01, 0.02),
            src="oil-fired generation share is negligible in India's grid",
        ),
        gdp_oil_sensitivity=AssumptionEntry(
            value=0.03, type="estimate", range=(0.02, 0.08),
            src="published $10-Brent-rise GDP-drag estimates",
        ),
        power_stress_multiplier=AssumptionEntry(
            value=7.5, type="internal", range=(5.0, 10.0),
            src="no external reference — internal calibration constant",
        ),
    )


def run_predict(assumptions: Assumptions) -> PredictAgentOutput:
    """Glass-box domino model (PRD §10A, corrected v1.3 coefficients).

    gap          = supply_lost_pct
    price_rise   = (gap / 10) * price_elasticity
    gdp_delta    = -(price_rise * gdp_oil_sensitivity)   # was hardcoded 0.066
    power_stress = gap * power_oil_dependence * power_stress_multiplier
    run_rate     = 100 - gap * 0.75

    Replaces run_predict_stub: same signature, same shape out
    (PredictAgentOutput is unchanged), real power_stress_pct, and the
    sourced gdp_oil_sensitivity coefficient instead of the v1.0 magic number.
    """

    gap = _clamp(assumptions.supply_lost_pct.value, 0.0, 100.0)
    price_rise = _clamp(
        (gap / 10.0) * assumptions.price_elasticity.value, *_PRICE_RISE_BOUNDS
    )
    gdp_delta = _clamp(
        -(price_rise * assumptions.gdp_oil_sensitivity.value), *_GDP_DELTA_BOUNDS
    )
    power_stress = _clamp(
        gap
        * assumptions.power_oil_dependence.value
        * assumptions.power_stress_multiplier.value,
        *_POWER_STRESS_BOUNDS,
    )
    run_rate = _clamp(100.0 - gap * 0.75, 0.0, 100.0)

    impact = Impact(
        supply_gap_pct=round(gap, 1),
        price_rise_pct=round(price_rise, 2),
        gdp_delta_pct=round(gdp_delta, 3),
        refinery_runrate_pct=round(run_rate, 1),
        power_stress_pct=round(power_stress, 3),
    )
    return PredictAgentOutput(impact=impact, assumptions=assumptions)
```

**Worked example** (severity `0.4`, every other input at its
`assumptions_from_severity` default — the exact scenario
`tests/test_api.py::test_signal_runs_full_cascade` exercises):
`gap=40`, `price_rise=(40/10)*3=12`, `gdp_delta=-(12*0.03)=-0.36`,
`power_stress=40*0.015*7.5=4.5`, `run_rate=100-40*0.75=70`. This **replaces**
the old stub's `gdp_delta=-0.792` (`12*0.066`) — an intentional, documented
behavior change (PRD's corrected coefficient), not a regression; update
every test/doc asserting the old placeholder/coefficient (§4 below).

### 2.2 `backend/agents/stubs.py` — trim to Watch only

Remove `assumptions_from_severity`, `run_predict_stub`, and the
now-unused imports (`Assumptions`, `AssumptionEntry`, `Impact`,
`PredictAgentOutput`). Keep `run_watch_stub`, `_ESCALATION_WORDS`, `_clamp`,
`_confidence_for`. Update the module docstring: it no longer describes
"Watch + Predict stubs," just Watch — Predict graduated this phase.

### 2.3 `backend/cascade.py` — import swap only

```python
from backend.agents.predict import assumptions_from_severity, run_predict
```

replaces the `from backend.agents.stubs import (assumptions_from_severity,
run_predict_stub, run_watch_stub)` line; the one call site
(`run_predict_stub(assumptions)`) becomes `run_predict(assumptions)`. No
other change — `run_cascade`'s orchestration is untouched.

### 2.4 `backend/state_store.py` — pending-override bookkeeping

```python
class StateStore:
    def __init__(self, ...) -> None:
        ...
        self._pending_overrides: dict[str, AssumptionOverride] = {}

    # -- assumption overrides (F20/F9) -------------------------------------- #

    @property
    def pending_overrides(self) -> list[AssumptionOverride]:
        """Overrides currently diverging from default, not yet stamped onto
        RiskState — cleared by merge_assumption_overrides() or a new scenario
        (SPEC.md Phase 3 decisions #6-7)."""
        return list(self._pending_overrides.values())

    def upsert_pending_override(self, entry: AssumptionOverride) -> None:
        self._pending_overrides[entry.field] = entry  # decision #8: latest wins

    def clear_pending_override(self, field: str) -> None:
        self._pending_overrides.pop(field, None)

    def reset_pending_overrides(self) -> None:
        self._pending_overrides.clear()

    async def merge_assumption_overrides(self) -> RiskState:
        """Snapshot pending overrides onto RiskState — Approve-time only
        (decision #5/#7), then clear the pending set."""
        new_state = await self._commit(
            self._state.model_copy(
                update={"assumption_overrides": self.pending_overrides}
            )
        )
        self.reset_pending_overrides()
        return new_state
```

`set_scenario()` (unchanged signature) gains one line at its top:
`self.reset_pending_overrides()` before building the copy — so every
`run_cascade()` call (which calls `set_scenario()` first) starts clean.

### 2.5 `backend/api/routes.py`

Import swap: `from backend.agents.predict import assumptions_from_severity,
run_predict` replaces `from backend.agents.stubs import run_predict_stub`;
`post_simulate` calls `run_predict(body.assumptions)`.

New request model + endpoint:

```python
from datetime import datetime, timezone
from backend.middleware.auth import get_current_user, require_role  # get_current_user is new here
from backend.schemas import AssumptionOverride

_OVERRIDE_EPSILON = 1e-9


class AssumptionOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumptions: Assumptions  # full block; every field diffed generically (decision #10)


@router.post("/assumptions/override")
def post_assumption_override(
    body: AssumptionOverrideRequest,
    store=Depends(get_store),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Log a slider *commit* that diverges from the severity-derived default.

    Exploratory only (decision #5): writes one audit_log row per divergent
    field and updates the store's pending set. Never touches
    RiskState.assumption_overrides or triggers a WS push — POST /approve does
    that (see merge_assumption_overrides).
    """

    defaults = assumptions_from_severity(store.get().severity)
    now = datetime.now(timezone.utc)
    logged: list[str] = []

    for field in Assumptions.model_fields:
        submitted = getattr(body.assumptions, field).value
        default = getattr(defaults, field).value
        if abs(submitted - default) <= _OVERRIDE_EPSILON:
            store.clear_pending_override(field)  # decision #9
            continue

        entry = AssumptionOverride(
            who=user.email, field=field, from_default=default,
            to_value=submitted, ts=now,
        )
        store.upsert_pending_override(entry)
        session.add(AuditLog(
            actor=user.email, action="override_assumption",
            payload=entry.model_dump(mode="json"),
        ))
        logged.append(field)

    if logged:
        session.commit()

    return {
        "ok": True,
        "overrides_logged": logged,
        "pending": [o.model_dump(mode="json") for o in store.pending_overrides],
    }
```

`POST /approve` gains two changes (decisions #7, #13) — fetch `pending`
before writing the approve row so it can be embedded in the same payload,
then always snapshot it onto `RiskState` afterward:

```python
    payload = match.model_dump(mode="json")
    if body.note:
        payload["note"] = body.note
    pending = store.pending_overrides
    payload["assumption_overrides"] = [o.model_dump(mode="json") for o in pending]

    entry = AuditLog(actor=user.email, action="approve_reroute", payload=payload)
    session.add(entry)
    session.commit()
    session.refresh(entry)

    await store.merge_assumption_overrides()  # always — decision #7
```

The rest of `post_approve`'s body (the `{ok, audit_id, actor, ...}` return)
is unchanged. `post_approve` was already `async`, so `await` here is free.

## 3 · API surface changes

- **New**: `POST /assumptions/override` — auth required (any role), body
  `{assumptions: Assumptions}`, returns `{ok, overrides_logged, pending}`. Not
  part of the frozen contract (same category as `SignalRequest`/
  `SimulateRequest`/`ApproveRequest` — an API-surface model living in
  `routes.py`).
- **`POST /simulate`**: same signature (`{scenario, assumptions} ->
  {scenario, impact, assumptions}`), now backed by the real `run_predict` —
  the what-if simulator is wired to the real model the moment this swaps in,
  no frontend change required.
- **`POST /approve`**: same signature and response shape; two side effects
  added (payload gains `assumption_overrides`; `RiskState.assumption_overrides`
  gets snapshotted + one WS push follows). No breaking change to callers.
- **`POST /signal`**: same signature; `RiskState.impact.power_stress_pct` is
  now a real, non-zero number instead of the Phase 1 placeholder, and
  `gdp_delta_pct` reflects the corrected coefficient (§2.1's worked example).

## 4 · Test updates

- **`tests/test_predict.py`** (new, mirrors `tests/test_recommend.py`'s
  pure-function style):
  - `assumptions_from_severity` shape: six typed keys, correct
    fact/estimate/internal tiers, unchanged from Phase 1.
  - `run_predict` at the `severity=0.4` default: exact values from §2.1's
    worked example (`gap=40, price_rise=12, gdp_delta=-0.36,
    power_stress=4.5, run_rate=70`).
  - `gdp_delta_pct` derives from `assumptions.gdp_oil_sensitivity.value`, not
    a hardcoded `0.066` — assert changing `gdp_oil_sensitivity` changes the
    output.
  - `power_stress_pct` scales with all three of its inputs (`supply_lost_pct`,
    `power_oil_dependence`, `power_stress_multiplier`) — vary each
    independently.
  - Clamping: an extreme `price_elasticity` (e.g. `50`) still yields
    `price_rise_pct <= 100`; an extreme `gdp_oil_sensitivity` (e.g. `5`)
    still yields `gdp_delta_pct >= -50`; an extreme `power_stress_multiplier`
    (e.g. `1000`) still yields `power_stress_pct <= 100`.
  - Purity: same `Assumptions` in → byte-identical `PredictAgentOutput` out,
    no shared/global state touched.
- **`tests/test_api.py`**:
  - `test_signal_runs_full_cascade` — replace
    `assert state.impact.power_stress_pct == 0.0  # v1.3 placeholder until Phase 3`
    with `assert state.impact.power_stress_pct == 4.5` (§2.1's worked
    example) and drop the "placeholder" comment.
  - `test_simulate_returns_impact_and_is_pure` — same replacement for
    `data["impact"]["power_stress_pct"]`.
  - New: `test_assumption_override_requires_auth` — unauthenticated
    `POST /assumptions/override` → 401.
  - New: `test_assumption_override_logs_audit_row_on_divergence` —
    authenticated, one divergent field → one new `audit_log` row
    (`action="override_assumption"`); `GET /state`'s
    `assumption_overrides` is still `[]` immediately after (not yet
    approved — decision #5).
  - New: `test_assumption_override_no_row_at_default` — submitting exactly
    the recomputed defaults logs nothing.
  - New: `test_repeated_override_same_field_dedups_pending_not_audit` — two
    different values for the same field, two calls → two `audit_log` rows,
    but only one pending entry (latest) once queried.
  - New: `test_revert_to_default_clears_pending` — override, then resubmit
    the default → no audit row for the revert, and a subsequent approve
    shows that field absent from `assumption_overrides`.
  - New: `test_approve_snapshots_and_clears_pending_overrides` — override →
    approve → `assumption_overrides` on the next `GET /state` (or the
    approve's own effect) contains the pending entries; approve's own
    `audit_log` row's payload contains the same list under
    `assumption_overrides`; a **second** approve with nothing newly pending
    → `assumption_overrides` resets to `[]` (decision #7).
  - New: `test_new_signal_clears_pending_overrides` — override (unapproved)
    → `POST /signal` → the next approve shows no stale overrides from the
    prior scenario.
- **`tests/test_state_store.py`**: add direct tests for
  `upsert_pending_override`/`clear_pending_override`/`reset_pending_overrides`/
  `merge_assumption_overrides` (dedup-by-field, clears after snapshot,
  `set_scenario()` also clears).
- No changes needed to `tests/test_contract.py` (no contract changes this
  phase) or `tests/test_recommend.py`/`test_advise.py` (they hand-construct
  `Impact`/`Assumptions` with literal values, never call `run_predict`, so
  the coefficient change doesn't touch them — confirmed by grep, no
  `0.066`/`run_predict_stub` references outside `stubs.py`/`cascade.py`/
  `routes.py`).

## 5 · Documentation updates (same change, per the contract-change protocol)

- **`backend/agents/predict.py`** — new module, docstring per §2.1.
- **`backend/agents/stubs.py`** — docstring trimmed to describe Watch only.
- **`PROJECT_GUIDE.md`** §08's example JSON — flip
  `"power_stress_pct": 0.0  // [v1.3] real computation is Phase 3; 0.0 today`
  to note Phase 3 landed; §09/§10's "target" Predict code sample → "shipped";
  update the Dev A/B status-board rows and the F3/F15/F20/F9 rows in the
  features table (§04).
- **`PLAN.md`** — flip Phase 3's status once merged; note this file's
  decisions #1-13 inline or link back so Segment 2 Chunk C's implementer
  (fact/estimate/internal slider UX) isn't surprised by the override-endpoint
  shape it needs to call.

## 6 · Acceptance criteria

1. `python -m pytest` fully green, including every new/updated test in §4.
2. `run_predict(assumptions)` returns a valid `PredictAgentOutput` with
   `power_stress_pct` computed for real (never `0.0` by construction) and
   `gdp_delta_pct` derived from `assumptions.gdp_oil_sensitivity.value`,
   never a hardcoded `0.066`.
3. `POST /simulate` recomputes via the real model; §2.1's worked example
   values hold for the default-assumptions case.
4. `POST /assumptions/override`: unauthenticated → 401; a divergent field →
   exactly one new `audit_log` row per field, `RiskState.assumption_overrides`
   unchanged; a value equal to default → no row, and clears any existing
   pending entry for that field; repeating the same field before an approve
   → multiple `audit_log` rows but one pending entry (latest wins).
5. `POST /approve` always snapshots the current pending set onto
   `RiskState.assumption_overrides` (including resetting to `[]` when
   nothing is pending) and pushes one WS update reflecting it; the approve's
   own `audit_log` row's payload includes the same list under
   `assumption_overrides`.
6. `POST /signal` clears any pending overrides left over from a prior
   what-if session before the cascade runs.
7. `price_rise_pct` never exceeds `100`, `gdp_delta_pct` never drops below
   `-50`, `power_stress_pct` stays within `[0, 100]` — verified with
   deliberately out-of-documented-range inputs submitted directly (bypassing
   any UI slider bound).
8. No contract change: `backend/schemas/contract.py` is untouched by this
   phase; `tests/test_contract.py` needs no updates.

## 7 · Explicitly deferred (not decided here — flagged for the named phase)

- **Fact/estimate/internal slider UX for `power_oil_dependence`,
  `gdp_oil_sensitivity`, `power_stress_multiplier`**, and wiring the
  official cockpit's slider-release handler to call
  `POST /assumptions/override` — Segment 2, Chunk C (PLAN.md).
- **Rendering the audit trail panel's override rows** (today's panel already
  reads `GET /audit`; it needs a row-type-aware view for
  `action="override_assumption"` vs `"approve_reroute"`) — Segment 2, Chunk C.
- **The per-step reasoning-chain side-channel** (decision #12) — revisit if a
  later UI chunk wants to show the glass-box arithmetic step-by-step.
- **Whether `/simulate` itself becomes auth-gated** — it stays unauthenticated
  in this phase (only the new override endpoint requires auth); revisit only
  if a future phase needs `/simulate` to know the caller's identity for a
  reason unrelated to override logging.

---

# SPEC — Segment 1, Phase 4: Watch real agent — RAG + LLM scoring, provenance, confidence bands (F1, F2, F8, F12)

> Scope: exactly [PLAN.md](.claude/docs/PLAN.md)'s Phase 4 (cross-referenced as
> `DEV_B_ROADMAP.md`'s Phase 2 chapter). Replaces the keyword-bump
> `run_watch_stub` with a real, grounded pipeline: retrieve top-k relevant
> snippets from a curated, committed RAG corpus, score the corridor via an
> LLM prompt built from them, and derive `confidence`/`band` from retrieval
> agreement rather than the LLM's own say-so. `WatchAgentOutput` is
> unchanged (no contract work this phase — Watch's output shape didn't need
> new fields, per PLAN.md). After this phase, **Watch is the only agent
> still capable of falling back to a stub** — Predict/Recommend/Advise are
> all real. Depends on Phase 1 (landed, for the widened contract other
> phases need — Watch itself doesn't read any v1.3 field). Independent of
> Phases 2/3/5/6.
>
> **Deviates from PLAN.md §6 open decision #1**: neither the PRD's named
> Gemini 3.5 Flash/Haiku 4.5 nor this repo's Anthropic-leaning scaffolding —
> the interview settled on **Groq's free tier** (fast inference over
> open-weight models, OpenAI-compatible-shaped API, no cost pressure for a
> hackathon demo with many cascade runs during rehearsal). This closes
> PLAN.md's open decision, just not with either option it listed.

## 1 · Decisions made (interview log)

| # | Decision | Why |
|---|---|---|
| 1 | **LLM provider: Groq**, not Anthropic or Gemini | User's explicit call — free tier, no cost pressure for repeated demo/rehearsal runs. Overrides PLAN.md §6 decision #1's two named options; documented here so Phase 5+'s implementer isn't surprised `backend/agents/llm.py` isn't an Anthropic client despite CLAUDE.md's env conventions |
| 2 | **Two-tier model fallback**: `llama-3.3-70b-versatile` primary, `llama-3.1-8b-instant` fallback, both Groq-hosted | 70B for scoring/instruction-following quality; 8B as a fast, higher-rate-limit-headroom second attempt before finally dropping to the offline stub — three-tier degradation (70B → 8B → stub), matching PRD §17's "LLM flakiness is High risk" posture with more graceful steps than a single cliff-edge fallback |
| 3 | **Embeddings: Chroma's bundled local ONNX MiniLM** (`all-MiniLM-L6-v2` via `onnxruntime`), not an embeddings API | Anthropic has no embeddings endpoint, and Groq doesn't host one either — retrieval needs a separate source regardless of LLM choice. A local model keeps retrieval working with **zero API keys**, satisfies the offline-fallback bar even more strictly than the LLM call itself, and needs only a one-time ~90MB download (documented in SETUP.md), not a live network dependency during the demo |
| 4 | **Vector store: ChromaDB**, `PersistentClient` pointed at a local directory | PRD's stated default, zero external service to run, gives free metadata storage (`{source_id, date, corridor}`) instead of hand-rolling an id→metadata map (FAISS's cost) |
| 5 | **Composite scoring: LLM-authoritative when available** — `run_watch_stub`'s keyword-bump/severity arithmetic becomes *purely* the offline-fallback path, never blended with a real LLM score | Simplest mental model: one code path is "real," one is "fallback," nothing to tune or defend on stage ("why 70/30?"). Matches how Phase 3 treated Predict's stub — replaced wholesale, not blended |
| 6 | **`confidence`/`band` derived from retrieval agreement, never the LLM's self-report** | The LLM prompt (§3.3) doesn't even ask for a confidence label — asking an LLM to self-assess confidence is a well-known unreliable pattern, and retrieval stats (snippet count, date spread) are a more principled, cheaper, and already-precedented signal (the stub already derives `band` from source count) |
| 7 | **`_confidence_for(band)` is reused from `stubs.py`, not duplicated** | Single source of truth for the band→label mapping (`≤8 high, ≤16 medium, else low`); Watch and the stub agree by construction, not by copy-paste |
| 8 | **Fallback branching lives inside `watch.py`'s `run_watch()`**, not as a visible `if` in `cascade.py` | Mirrors exactly how Phase 3 replaced Predict's stub — `cascade.py` imports one name and calls it unconditionally. Keeps the orchestrator ignorant of Watch's internal reliability concerns, consistent with the existing "swap behind the same envelope" pattern every prior phase used |
| 9 | **Fallback uniformity**: an unrecognized corridor, an empty retrieval, `USE_REAL_AGENTS=0`, a missing API key, and an LLM failure on *both* model tiers all funnel to the exact same `run_watch_stub(signal)` call | One fallback code path to reason about and test instead of several bespoke degraded-scoring formulas. An empty retrieval in particular is a fallback trigger, not "score anyway with no citations" — F2's whole point is that scores come with real sources; a score with an empty `source_ids` list undercuts that story more than falling back cleanly does |
| 10 | **`source_ids` = every retrieved snippet id**, not an LLM-selected subset | More robust than trusting a smaller/free-tier model to accurately echo back which specific ids (out of the ones it was given) it "used" — a model can drop or hallucinate an id in that subset-selection step. Using the full retrieved set is simpler and can't under- or over-cite |
| 11 | **Cache key**: `f"{model}:{corridor}|{headline.strip().lower()}|{sorted(retrieved_ids)}"` | Per interview: hashing corridor + normalized headline + retrieved ids keeps the cache stable across runs (the corpus is curated/committed, so retrieval for a given corridor+headline is deterministic) and correctly invalidates if the corpus changes (different ids retrieved ⇒ different cache entry). The `model:` prefix keeps the two tiers from colliding on the same cache file if both were ever tried for the same input |
| 12 | **No retries within a model tier** — one attempt per tier, immediate fall-through on any failure | Retrying a rate-limited free-tier call in a loop both slows the live demo and burns through the same limit that just tripped; moving to the next tier (or the stub) is faster and just as deterministic once cached |
| 13 | **Corridor validation: a static `KNOWN_CORRIDORS` set in `watch.py`**, kept in sync with `corridors.json` **by convention plus a guardrail test** (user's addition to the recommended option) | Keeps `run_watch(signal) -> WatchAgentOutput` a pure, DB-free function, matching `predict.py`'s and `recommend.py`'s architecture notes on testability — no session parameter needed just to check a corridor id exists. `tests/test_watch.py::test_known_corridors_matches_seed_config` diffs the hardcoded set against `backend/seed/corridors.json` and fails loudly the moment they drift, closing the gap a live DB query would have caught automatically |
| 14 | **Test strategy: mock `backend.agents.llm.complete_json` entirely** — no live Groq call anywhere in `pytest` | No API key should ever be required for the suite to pass (PRD §17). A separate, small set of tests exercises the fallback path directly against `run_watch_stub`. There is no VCR-cassette/live-recording test in this repo's suite |
| 15 | **RAG corpus: real paraphrased events with citations**, committed at `backend/agents/data/watch_corpus.json` | Consistent with this project's existing sourcing discipline (Phase 1's `war_risk_pct`/lat-lon, Phase 3's assumption `src` fields) — "these are real reported events, not invented ones" is a stronger claim on stage than admitting the grounding is fictional |
| 16 | **Provenance lookup endpoint (id → `{headline, source, timestamp}`) deferred to Segment 2, Chunk D** | This phase's job is done once `source_ids` are real retrieved ids; designing the lookup response shape against the actual popover UI (rather than guessing now) avoids a wasted-effort shape mismatch. `frontend/components/official/provenance.tsx` today only classifies by id prefix (`news_`/`ais_`/`sanc_`/`price_`) and needs no backend change to keep working as-is |
| 17 | **`USE_REAL_AGENTS` defaults to `0`** in `.env.example` and therefore in a fresh clone / CI | A fresh `pip install && pytest` must stay fully offline and deterministic with zero configuration (mirrors `SEED_ON_STARTUP`'s existing "safe default" convention). A demo operator flips it to `1` locally once a `GROQ_API_KEY` is set |
| 18 | **Corpus embedding is idempotent and startup-gated on `use_real_agents and groq_api_key`** — wired into `backend/app.py`'s existing `lifespan`, right after `run_seed()` | A stub-only run (the CI/fresh-clone default) never touches Chroma or triggers the one-time ONNX model download; only an operator who's actually opted into real agents pays that cost. Idempotency (skip if the collection already holds `len(corpus)` rows) mirrors `seed.py`'s upsert-on-startup pattern exactly |
| 19 | **Defensive JSON parsing**: `complete_json` tries `json.loads` on the raw response first; if that fails, it extracts the substring between the first `{` and the last `}` and retries once before raising `LLMUnavailable` | Groq's free-tier/smaller models don't uniformly guarantee strict JSON-mode compliance the way a top-tier model might; a small, cheap salvage step avoids treating "the model added a stray sentence before the JSON" as a hard failure that burns a fallback tier for no reason |

## 2 · New dependencies & config

### 2.1 `requirements.txt`

```
# ---- Dev B (Phase 4): Watch RAG + LLM ----
groq>=0.11            # Groq API client (free-tier LLM calls)
chromadb>=0.5          # RAG vector store; bundles local ONNX MiniLM embeddings
```

### 2.2 `backend/config.py` — new `Settings` fields

```python
groq_api_key: str = field(
    default_factory=lambda: os.environ.get("GROQ_API_KEY", "")
)
watch_model_primary: str = field(
    default_factory=lambda: os.environ.get(
        "WATCH_MODEL_PRIMARY", "llama-3.3-70b-versatile"
    )
)
watch_model_fallback: str = field(
    default_factory=lambda: os.environ.get(
        "WATCH_MODEL_FALLBACK", "llama-3.1-8b-instant"
    )
)
vector_store_path: str = field(
    default_factory=lambda: os.environ.get(
        "VECTOR_STORE_PATH", str(REPO_ROOT / "backend" / "agents" / ".chroma")
    )
)
llm_cache_dir: str = field(
    default_factory=lambda: os.environ.get(
        "LLM_CACHE_DIR", str(REPO_ROOT / "backend" / "agents" / ".llm_cache")
    )
)
# Off by default (decision #17) — a fresh clone/CI run never needs a key.
use_real_agents: bool = field(
    default_factory=lambda: os.environ.get("USE_REAL_AGENTS", "0") == "1"
)
```

### 2.3 `.env.example` additions

```
# --- Watch agent (Groq LLM + RAG) -----------------------------------------
# Unset/0 => Watch always uses the deterministic keyword-bump stub (default,
# safe for a fresh clone and CI). Set to 1 + a real GROQ_API_KEY to enable
# the real RAG+LLM agent, falling back to the stub automatically on any
# failure (missing key, rate limit, network error, unknown corridor).
USE_REAL_AGENTS=0
GROQ_API_KEY=
WATCH_MODEL_PRIMARY=llama-3.3-70b-versatile
WATCH_MODEL_FALLBACK=llama-3.1-8b-instant
VECTOR_STORE_PATH=
LLM_CACHE_DIR=
```

## 3 · Backend changes

### 3.1 `backend/agents/llm.py` (new) — thin Groq wrapper + disk cache

```python
"""Thin Groq LLM client wrapper — the only place backend/agents/*.py talks to
an external LLM API. Every call is cached to disk by input hash so the same
prompt always returns the same JSON, on stage and in CI (PRD §10/§17).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from groq import Groq

from backend.config import get_settings

_CALL_TIMEOUT_SECONDS = 8.0


class LLMUnavailable(Exception):
    """Any failure to get a usable JSON response — network error, timeout,
    non-2xx, rate limit, or a response that isn't (recoverably) JSON.
    Callers (watch.py) catch this and move to the next fallback tier."""


def _cache_path(cache_key: str) -> Path:
    cache_dir = Path(get_settings().llm_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.json"


def _salvage_json(text: str) -> dict:
    """Decision #19: strict parse first, then a one-shot salvage of the
    substring between the first '{' and the last '}'."""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise
        return json.loads(text[start : end + 1])


def complete_json(prompt: str, *, cache_key: str, model: str) -> dict:
    """Call the LLM, expecting a JSON object back. Cached by ``cache_key``
    (a stable, normalized key the caller builds — see watch.py, not the raw
    prompt). Raises LLMUnavailable on any failure; never returns a partial
    result."""

    path = _cache_path(f"{model}:{cache_key}")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    settings = get_settings()
    if not settings.groq_api_key:
        raise LLMUnavailable("no GROQ_API_KEY configured")

    client = Groq(api_key=settings.groq_api_key, timeout=_CALL_TIMEOUT_SECONDS)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        data = _salvage_json(response.choices[0].message.content)
    except Exception as exc:  # network, timeout, rate limit, bad JSON — uniform
        raise LLMUnavailable(str(exc)) from exc

    path.write_text(json.dumps(data), encoding="utf-8")
    return data
```

> Verify `Groq(...)`'s exact constructor/`chat.completions.create` kwargs
> against the installed `groq` package version at implementation time — the
> shape above matches the OpenAI-compatible convention Groq's SDK follows,
> but pin the version in `requirements.txt` (decision area, not re-litigated
> here) and smoke-test one live call before trusting the cache/fallback path.

### 3.2 `backend/agents/rag.py` (new) — corpus embedding + retrieval

```python
"""RAG snippet store for Watch (F2) — a small, curated, committed corpus of
real paraphrased headlines/sanctions notes, embedded into Chroma so Watch can
retrieve grounded, cited context for a scoring prompt instead of guessing.

Embeddings are local (Chroma's bundled ONNX MiniLM model, no API calls) —
retrieval must work with zero API keys configured (decision #3), the same
offline-safety bar as everything else in this repo (PRD §17).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import chromadb

from backend.config import get_settings

_CORPUS_PATH = Path(__file__).resolve().parent / "data" / "watch_corpus.json"
_COLLECTION_NAME = "watch_corpus"


@dataclass(frozen=True)
class Snippet:
    id: str
    corridor: str
    date: str
    source: str
    text: str


def _client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=get_settings().vector_store_path)


def ensure_corpus_embedded() -> None:
    """Idempotent (decision #18): embeds the corpus once, skips on later
    boots once the collection already holds every row — same spirit as
    seed.py's upsert-on-startup."""

    corpus = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
    collection = _client().get_or_create_collection(_COLLECTION_NAME)
    if collection.count() == len(corpus):
        return

    collection.upsert(
        ids=[row["id"] for row in corpus],
        documents=[row["text"] for row in corpus],
        metadatas=[
            {"corridor": row["corridor"], "date": row["date"], "source": row["source"]}
            for row in corpus
        ],
    )


def retrieve(corridor: str, query: str, k: int = 5) -> list[Snippet]:
    """Top-k snippets for ``corridor``, ranked by similarity to ``query``
    (the injected headline). Returns ``[]`` if the corridor has no snippets
    in the corpus — callers (watch.py) treat that as a fallback trigger
    (decision #9), not an error to raise."""

    collection = _client().get_or_create_collection(_COLLECTION_NAME)
    result = collection.query(query_texts=[query], n_results=k, where={"corridor": corridor})
    ids = result["ids"][0] if result["ids"] else []
    docs = result["documents"][0] if result["documents"] else []
    metas = result["metadatas"][0] if result["metadatas"] else []
    return [
        Snippet(id=i, corridor=m["corridor"], date=m["date"], source=m["source"], text=d)
        for i, d, m in zip(ids, docs, metas)
    ]
```

### 3.3 `backend/agents/watch.py` (new) — the real agent

```python
"""Watch agent — grounded, cited corridor risk scoring (F1, F2, F8, F12).

Retrieve top-k relevant snippets (RAG, backend/agents/rag.py), score via an
LLM prompt built from them, and derive confidence/band from retrieval
agreement — never from the LLM's own self-report (decision #6).

Graceful degradation is uniform (decision #9): an unrecognized corridor, an
empty retrieval, a disabled USE_REAL_AGENTS flag, a missing API key, or any
LLM call/parse failure (after trying both model tiers) all fall back to the
same place — run_watch_stub(signal) — one fallback path to reason about and
test, not several.
"""

from __future__ import annotations

import logging
from datetime import date

from backend.agents.llm import LLMUnavailable, complete_json
from backend.agents.rag import Snippet, retrieve
from backend.agents.stubs import _confidence_for, run_watch_stub
from backend.config import get_settings
from backend.schemas import CorridorRiskEntry, WatchAgentOutput

logger = logging.getLogger(__name__)

# Kept in sync with backend/seed/corridors.json BY CONVENTION, not a live
# query — run_watch() stays pure/DB-free, mirroring predict.py's and
# recommend.py's architecture notes (decision #13).
# tests/test_watch.py::test_known_corridors_matches_seed_config guards drift.
KNOWN_CORRIDORS = {"hormuz", "suez_cape", "atlantic", "malacca"}

_RETRIEVE_K = 5
_STALENESS_DAYS = 180

_PROMPT_TEMPLATE = """You are a corridor risk analyst. Score how much the \
following headline raises disruption risk for the "{corridor}" oil transit \
corridor, from 0 (no added risk) to 100 (severe, imminent disruption).

Headline: {headline}

Context from prior reporting on this corridor:
{context}

Respond with a JSON object only: {{"score": <0-100 number>, "reason": \
"<one sentence>"}}"""


def _build_prompt(corridor: str, headline: str, snippets: list[Snippet]) -> str:
    context = "\n".join(f"- ({s.date}, {s.source}) {s.text}" for s in snippets)
    return _PROMPT_TEMPLATE.format(corridor=corridor, headline=headline, context=context)


def _band_from_retrieval(snippets: list[Snippet]) -> float:
    """Tighter band when several, date-consistent snippets were retrieved;
    wider when evidence is thin or stale (decision #6)."""

    band = max(4.0, min(20.0, 20.0 - 3.0 * len(snippets)))
    if len(snippets) < _RETRIEVE_K:
        band += 6.0  # thin evidence for this corridor
    dates = sorted(date.fromisoformat(s.date) for s in snippets)
    if dates and (dates[-1] - dates[0]).days > _STALENESS_DAYS:
        band += 4.0  # retrieved snippets span a stale/mixed-recency range
    return round(max(4.0, min(20.0, band)), 1)


def _score_with_llm(corridor: str, headline: str, snippets: list[Snippet]) -> float:
    prompt = _build_prompt(corridor, headline, snippets)
    cache_key = f"{corridor}|{headline.strip().lower()}|{','.join(sorted(s.id for s in snippets))}"
    settings = get_settings()

    for model in (settings.watch_model_primary, settings.watch_model_fallback):
        try:
            data = complete_json(prompt, cache_key=cache_key, model=model)
            return max(0.0, min(100.0, float(data["score"])))
        except (LLMUnavailable, KeyError, TypeError, ValueError) as exc:
            logger.warning("Watch: model %s failed (%s), trying next tier", model, exc)
    raise LLMUnavailable("both model tiers failed")


def run_watch(signal: dict) -> WatchAgentOutput:
    """Score the affected corridor from an injected signal — the real Watch
    agent. Falls back to run_watch_stub(signal) per decision #9's uniform
    fallback list."""

    settings = get_settings()
    corridor = signal["corridor"]

    if not settings.use_real_agents or not settings.groq_api_key:
        return run_watch_stub(signal)

    if corridor not in KNOWN_CORRIDORS:
        logger.warning("Watch: unknown corridor %r, falling back to stub", corridor)
        return run_watch_stub(signal)

    headline = str(signal.get("headline", ""))
    snippets = retrieve(corridor, headline, k=_RETRIEVE_K)
    if not snippets:
        logger.warning("Watch: no snippets retrieved for %r, falling back to stub", corridor)
        return run_watch_stub(signal)

    try:
        score = _score_with_llm(corridor, headline, snippets)
    except LLMUnavailable as exc:
        logger.warning("Watch: LLM unavailable (%s), falling back to stub", exc)
        return run_watch_stub(signal)

    band = _band_from_retrieval(snippets)
    entry = CorridorRiskEntry(
        score=round(score, 1),
        confidence=_confidence_for(band),
        band=band,
        source_ids=[s.id for s in snippets],
    )
    return WatchAgentOutput(corridor_risk={corridor: entry})
```

`_confidence_for` stays defined once, in `stubs.py` (decision #7) — `watch.py`
imports it rather than duplicating the band→label mapping.

### 3.4 `backend/cascade.py` — one-line import swap

```python
from backend.agents.watch import run_watch
```

replaces `from backend.agents.stubs import run_watch_stub`; the one call
site (`run_watch_stub(signal)`) becomes `run_watch(signal)`. No other
change — identical shape to Phase 3's cascade.py update (decision #8).

### 3.5 `backend/app.py` — pre-embed the corpus at startup

One addition inside the existing `lifespan`, right after `run_seed()`,
gated per decision #18:

```python
if settings.use_real_agents and settings.groq_api_key:
    from backend.agents.rag import ensure_corpus_embedded

    ensure_corpus_embedded()
    log.info("watch corpus embedded/verified")
```

A stub-only boot (`USE_REAL_AGENTS=0`, the default) never imports `chromadb`
or triggers the one-time ONNX model download.

## 4 · RAG corpus content (`backend/agents/data/watch_corpus.json`)

Decision #15: real paraphrased events, cited generically (no verbatim
quotes), matching the honesty framing already used for `war_risk_pct`/
lat-lon (Phase 1) and every `Assumptions.src` (Phase 3). One row per
snippet: `{id, corridor, date, source, text}`. Illustrative subset (the
full corpus should give each of the four seeded corridors at least
`_RETRIEVE_K` = 5 snippets so retrieval never falls back on thinness alone):

| id | corridor | date | source | text (paraphrased) |
|---|---|---|---|---|
| `news_hormuz_2019_seizure` | hormuz | 2019-07-19 | wire reporting | Iranian forces seized a UK-flagged tanker transiting the Strait of Hormuz amid rising tension over sanctions enforcement. |
| `news_hormuz_2018_threat` | hormuz | 2018-07-04 | wire reporting | Iranian officials publicly threatened to close the Strait of Hormuz to all shipping if the country's own oil exports were blocked by sanctions. |
| `sanc_hormuz_2019` | hormuz | 2019-05-08 | sanctions notice | The US ended sanctions waivers for countries importing Iranian crude, escalating the standoff around Gulf shipping lanes. |
| `news_hormuz_2019_tanker_war` | hormuz | 2019-06-13 | wire reporting | Two tankers were attacked in the Gulf of Oman near the Strait of Hormuz; Gulf states raised naval alert levels in response. |
| `news_hormuz_2011_threat` | hormuz | 2011-12-27 | wire reporting | Iran conducted naval exercises near the Strait of Hormuz and reiterated its ability to close the strait in response to further sanctions. |
| `news_suez_2023_houthi` | suez_cape | 2023-11-19 | wire reporting | Houthi forces began targeting commercial vessels in the southern Red Sea approach to the Suez Canal, citing the Gaza conflict. |
| `news_suez_2024_reroute` | suez_cape | 2024-01-15 | wire reporting | Multiple major shipping lines announced rerouting around the Cape of Good Hope rather than transiting the Red Sea, citing attack risk. |
| `sanc_suez_2024_insurance` | suez_cape | 2024-02-02 | maritime insurance notice | War-risk insurance premiums for Red Sea transits rose sharply, reported in the range of 1–2% of vessel value versus a pre-crisis baseline near 0.1%. |
| `news_suez_2021_blockage` | suez_cape | 2021-03-23 | wire reporting | A container ship ran aground and blocked the Suez Canal for six days, halting an estimated $9 billion/day of transiting trade. |
| `news_suez_2024_strike` | suez_cape | 2024-03-06 | wire reporting | A Houthi missile strike sank a bulk carrier in the Red Sea, the first vessel loss of the campaign against shipping in the corridor. |
| `news_atlantic_2022_sanctions` | atlantic | 2022-03-08 | wire reporting | The US and allies moved to restrict imports of Russian-origin crude, redirecting some Atlantic-basin supply flows. |
| `news_atlantic_2024_opec` | atlantic | 2024-06-02 | wire reporting | OPEC+ producers, several with Atlantic-basin export terminals, adjusted output quotas, with muted effect on shipping-lane risk. |
| `news_atlantic_2023_weather` | atlantic | 2023-09-14 | wire reporting | A hurricane forced temporary closure of several US Gulf Coast export terminals feeding Atlantic crude routes. |
| `news_atlantic_2020_price_war` | atlantic | 2020-03-09 | wire reporting | A Russia-Saudi production dispute triggered a sharp oil price collapse, with no direct shipping-lane disruption reported. |
| `news_atlantic_2019_sanctions` | atlantic | 2019-01-28 | sanctions notice | The US sanctioned a major Atlantic-basin state oil company, disrupting some crude export financing without closing shipping lanes. |
| `news_malacca_2015_piracy` | malacca | 2015-06-11 | wire reporting | A regional piracy-reporting center logged a rise in small-tanker hijackings for fuel theft in the Malacca Strait approaches. |
| `news_malacca_2021_congestion` | malacca | 2021-08-30 | wire reporting | Port congestion and COVID-related crew-change restrictions slowed tanker transits through the Malacca Strait. |
| `news_malacca_2010_patrol` | malacca | 2010-05-20 | wire reporting | Littoral states expanded joint naval patrols in the Malacca Strait following a multi-year rise in reported piracy incidents. |
| `news_malacca_2023_traffic` | malacca | 2023-04-11 | wire reporting | Malacca Strait tanker traffic reached a multi-year high as Asia-Pacific refiners increased throughput, with no security incidents reported. |
| `news_malacca_2016_grounding` | malacca | 2016-01-05 | wire reporting | A tanker ran aground in the Malacca Strait's shallow traffic separation scheme, briefly disrupting transit scheduling. |

Every corridor gets 5 snippets, deliberately spanning both genuinely
elevated-risk events (seizures, strikes, sanctions) and calmer/neutral ones
(congestion, routine patrols) — so `_band_from_retrieval`'s date-spread and
count logic has real variation to work with rather than every row reading
as maximally alarming, and so the LLM's score has to actually weigh
relevance rather than pattern-match "any hit ⇒ high score."

## 5 · API surface changes

None. `run_watch`'s return type (`WatchAgentOutput`) is unchanged from the
stub's; `POST /signal` and every downstream endpoint keep their exact
current signatures. The provenance-lookup endpoint PLAN.md Phase 4
mentions as a maybe is explicitly deferred (decision #16) to Segment 2,
Chunk D.

## 6 · Test updates

- **`tests/test_watch.py`** (new):
  - `test_known_corridors_matches_seed_config` — diffs `watch.KNOWN_CORRIDORS`
    against the corridor ids in `backend/seed/corridors.json`; fails loudly
    on any drift (decision #13's guardrail).
  - `test_run_watch_falls_back_when_flag_off` — `USE_REAL_AGENTS=0` (or
    unset) → `run_watch(signal)` returns byte-identical output to
    `run_watch_stub(signal)` for the same input, and `complete_json` is
    never called (patch it to raise if invoked, assert it doesn't).
  - `test_run_watch_falls_back_when_no_api_key` — flag on, `GROQ_API_KEY`
    unset → same fallback assertion.
  - `test_run_watch_falls_back_on_unknown_corridor` — a corridor id not in
    `KNOWN_CORRIDORS` → stub output, a warning is logged, `retrieve()` is
    never called.
  - `test_run_watch_falls_back_on_empty_retrieval` — mock `retrieve()` to
    return `[]` → stub output.
  - `test_run_watch_uses_llm_score_when_available` — mock `complete_json` to
    return `{"score": 72, "reason": "..."}` for the primary model → returned
    `CorridorRiskEntry.score == 72.0`, `source_ids` equals the mocked
    snippets' ids exactly (decision #10), never the raw signal id.
  - `test_run_watch_falls_through_model_tiers` — mock `complete_json` to
    raise `LLMUnavailable` for the primary model and succeed for the
    fallback model → fallback model's score is used, no stub fallback.
  - `test_run_watch_falls_back_after_both_tiers_fail` — both models raise →
    stub output.
  - `test_band_from_retrieval_widens_on_thin_or_stale_evidence` — fewer than
    `_RETRIEVE_K` snippets, or a date spread over `_STALENESS_DAYS`, produces
    a wider band (lower `_confidence_for` tier) than a full, recent,
    consistent set.
  - `test_confidence_never_from_llm_response` — a mocked LLM response that
    includes an extraneous `"confidence": "high"` key is ignored; the
    returned `confidence` is still computed from `_band_from_retrieval`
    (guards against a future prompt tweak silently reintroducing
    self-reported confidence).
- **`tests/test_llm.py`** (new):
  - `complete_json` caches: two calls with the same `cache_key`/`model` hit
    the same file, second call doesn't invoke the Groq client (patch it to
    raise if constructed twice).
  - `complete_json` raises `LLMUnavailable` (not the underlying SDK
    exception) on a client-construction/network/timeout error, and on
    persistently malformed JSON.
  - `_salvage_json` recovers a JSON object embedded in surrounding prose
    (decision #19); still raises on genuinely non-JSON content.
  - No `GROQ_API_KEY` set → `complete_json` raises `LLMUnavailable`
    immediately, without attempting a network call.
- **`tests/test_rag.py`** (new, uses a throwaway Chroma path per test via a
  `tmp_path` fixture, never the real `.chroma/` dir):
  - `ensure_corpus_embedded` is idempotent — calling it twice doesn't
    re-embed (assert collection count stable, or patch `upsert` to fail on
    a second call).
  - `retrieve(corridor, query, k)` only returns snippets whose metadata
    `corridor` matches; returns `[]` for a corridor with no corpus rows.
- **`tests/test_api.py`**: no change required — `POST /signal`'s cascade
  test already runs with `USE_REAL_AGENTS` unset (the default), so it
  continues exercising `run_watch`'s fallback-to-stub path, which is
  byte-identical to today's stub output. Add one assertion instead of a new
  test: `run_watch is run_watch_stub`-shaped output (same score for the
  same signal) to lock in that the default cascade path is unaffected by
  this phase.
- No changes needed to `tests/test_contract.py` (no contract change),
  `tests/test_predict.py`, `tests/test_recommend.py`, `tests/test_advise.py`,
  `tests/test_state_store.py` (none of them touch Watch).

## 7 · Documentation updates (same change, per the contract-change protocol)

- **`backend/agents/watch.py`/`llm.py`/`rag.py`** — module docstrings per §3.
- **`backend/agents/stubs.py`** — docstring note: Watch now has a real
  agent behind a flag; the stub remains the offline fallback, not dead code.
- **`requirements.txt`** — add the `groq`/`chromadb` block with a comment
  noting Phase 4 landed and which provider was chosen (decision #1), so a
  future reader doesn't wonder why the repo isn't using Anthropic despite
  CLAUDE.md's conventions.
- **`.env.example`** — add the block from §2.3.
- **`SETUP.md`** — note the one-time ONNX embedding-model download when
  `USE_REAL_AGENTS=1` is first enabled (needs network once, then fully
  offline/cached).
- **`PROJECT_GUIDE.md`** — flip Watch's status-board rows (Dev B section,
  §04 feature table F1/F2/F8/F12, the architecture diagram's `W["Watch 🟡
  stub→Dev B"]` node) once implemented; note the Groq provider choice
  since PROJECT_GUIDE.md's tech-stack table (§06) still shows the LLM
  provider as an open decision.
- **`PLAN.md`** — flip Phase 4's status once merged; resolve §6 open
  decision #1 by linking back to this section instead of leaving it open;
  note the vector-store decision (#2) is resolved as ChromaDB + local
  embeddings, not ChromaDB-with-an-embedding-API as PLAN.md's phrasing
  might have implied.
- **`DEV_B_ROADMAP.md`** — mark its Phase 2 chapter's chunks 1–4 as
  superseded by this SPEC.md section (as-built spec), same convention Phase
  3 used for that file's Phase 3 chapter.

## 8 · Acceptance criteria

1. `python -m pytest` fully green, including every new test in §6, with
   **no `GROQ_API_KEY` set anywhere in the test environment**.
2. `run_watch(signal)` returns a valid `WatchAgentOutput` in every case:
   flag off, no key, unknown corridor, empty retrieval, both model tiers
   failing, and the real success path — never raises out to the caller.
3. The same `(corridor, headline)` pair always yields the same score on a
   second call (cache hit, not a fresh LLM call) — verified by mocking the
   Groq client to raise if constructed more than once across two calls with
   an identical cache key.
4. `source_ids` on a real (non-fallback) score are the retrieved snippets'
   real ids from `watch_corpus.json`, never the raw signal id echoed back.
5. `POST /signal`'s full cascade still runs end-to-end with the default
   `USE_REAL_AGENTS=0`; `/state` still validates against `RiskState`
   (the drift alarm) — no behavior change to the demo's default path.
6. `tests/test_watch.py::test_known_corridors_matches_seed_config` passes,
   proving `KNOWN_CORRIDORS` and `corridors.json` agree today.
7. No contract change: `backend/schemas/contract.py` is untouched;
   `tests/test_contract.py` needs no updates.

## 9 · Explicitly deferred (not decided here — flagged for the named phase)

- **The provenance-lookup endpoint** (id → `{headline, source, timestamp}`)
  and the popover UI wiring — **Segment 2, Chunk D**.
- **Feeding the F18 dark-ship signal into Watch** — **Phase 7**, which needs
  Phase 6's AIS data first. **Post-implementation correction:** there is no
  "composite score" left to feed a number into (decision #5 made the real
  path LLM-authoritative, full stop) — the actual wire is a line added to
  `_build_prompt()`'s context, not an arithmetic blend term. PLAN.md's
  Phase 7 section now carries this note directly.
- **The alarm-language tone score as an extra Watch input (F19)** —
  **Phase 9**, stretch/P2, cut first if time runs short. Same correction as
  Phase 7's: it's prompt context, not a composite-score input. PLAN.md's
  Phase 9 section now carries this note directly.
- **Replacing the static `KNOWN_CORRIDORS` set with a live knowledge-graph
  or DB-backed check** — only worth it once Phase 5's graph exists and
  something already needs Watch to take a DB/graph dependency for another
  reason; not on its own. **Post-Phase-5 note:** Phase 5 has since landed
  (`backend/agents/graph.py`) but, per its own decision #1, stays a
  self-contained library nothing else calls yet — its existence doesn't
  obligate this swap on its own, only makes it possible once something else
  needs Watch to take a DB dependency for an unrelated reason. Still deferred.
- **Committing a pre-populated `.llm_cache/` and the embedded `.chroma/`
  store so the canonical demo runs fully offline with zero live calls at
  all** — **Phase 10** (determinism/cut-over), per PLAN.md §5's own
  "pre-embed the RAG store and commit the LLM response cache" requirement.
  Phase 10 also inherits a decision to make on purpose, not by accident: its
  planned "flip `USE_REAL_AGENTS=1` by default" doesn't break anything
  (the missing-key check still gates real calls independently of the flag —
  decision #9), but it does relax decision #17's "flag *and* key" double
  opt-in down to "key alone" — fine for a curated demo environment, just
  don't let it change `.env.example`'s own shipped default.
- **A date-cutoff for `retrieve()`, needed by Phase 8's backtest.**
  `backend/agents/rag.py`'s `retrieve(corridor, query, k)` has no notion of
  "as of when" — it queries the full committed corpus regardless of which
  historical moment is being replayed. A naive chronological backtest replay
  could retrieve post-dated snippets, leaking future information into a
  past score and quietly invalidating the lead-time measurement. Not caught
  by this phase's own interview (it wasn't in scope — no backtest existed
  yet to expose it); surfaced once Phase 4 actually landed and Phase 8 was
  reconsidered against the real `retrieve()` signature. PLAN.md's Phase 8
  section now carries this note directly; resolve it there via either an
  `as_of` parameter or a wholly separate backtest corpus.
- **Confirming the exact `groq` SDK call signature** (constructor/`timeout`/
  `response_format` kwargs) against the pinned package version — verified at
  implementation time (matches the SDK as shipped); no longer open.

---

# SPEC — Segment 1, Phase 5: Knowledge graph (F10)

> Scope: exactly [PLAN.md](.claude/docs/PLAN.md)'s Phase 5. Ships a new, self-contained
> `backend/agents/graph.py` — a NetworkX model of the supplier/corridor/
> refinery network, built fresh from the seeded DB config tables, plus the
> `affected_by()` query ("if hormuz closes, what's affected?"). **No contract,
> `cascade.py`, or API change in this phase** (see decision #1) — `RiskState.geo`
> stays `None` exactly as `contract.py`'s own `Geo` docstring already commits
> to, and PLAN.md Phase 6 is what actually stamps it, using this phase's
> `affected_by()` to fill `affected_refinery_ids`. Depends on Phase 1 (landed,
> for `Corridor`/`Refinery`'s v1.3 columns, unused by this phase but confirms
> the schema this graph reads is stable). Independent of Phases 2–4.

## 1 · Decisions made (interview log)

| # | Decision | Why |
|---|---|---|
| 1 | **Library only — no `RiskState`/`cascade.py`/API change this phase.** `geo` stays `None`; Phase 6 is the one that populates the whole `Geo` block (all three fields together, once AIS data exists for the other two) and does the actual wiring, calling this phase's `affected_by()` for `affected_refinery_ids` | Resolves a real contradiction: PLAN.md's Phase 5 section says this phase "eventually feed[s] `geo.affected_refinery_ids`," but `contract.py`'s own `Geo` docstring already says the field "Stays `None` on RiskState until PLAN.md Phase 6 ... and Phase 7." Treating the landed contract docstring as authoritative avoids inventing a transient non-contract field or a partially-`None` `Geo` just to have somewhere to put a Phase-5-only computation nobody consumes yet |
| 2 | **"Affected" is broad/inclusive**: a refinery counts as affected by a corridor closing if it had *any* grade-compatible supplier on that corridor — even if it also has other compatible suppliers elsewhere | Matches PROJECT_GUIDE.md's "pulse the affected-refinery nodes" exposure framing over a stricter "only refineries left with zero supply" definition, which would under-report exposure for a map feature whose whole point is showing risk, not just failure |
| 3 | **Chokepoint collapses into the corridor node** — one node type per `Corridor` row (`type="corridor"`, `chokepoint` as an attribute), not a separate fourth node tier, since today's seed data is 1:1 (every corridor has exactly one chokepoint) | Keeps `affected_by()`'s input the same id space already used everywhere else in the codebase (`corridor_risk` keys, `cascade.py`'s `exclude_corridors`) — no second id space to keep in sync. Revisit only if a future corridor shares a chokepoint with another |
| 4 | **No new API route this phase** — `graph.py` is exercised by `tests/test_graph.py` only (and, per decision #1, not even `cascade.py` yet) | Matches PLAN.md's own Phase 5 section, which lists no API changes. A route (or the Phase-6 wiring) can come once there's a real consumer for the shape, rather than guessing one now |
| 5 | **`affected_by()` returns a structured `AffectedAssets(suppliers: set[str], refineries: set[str])`**, not a flat mixed `set[str]` of node ids | A caller (Phase 6, populating `affected_refinery_ids`) gets exactly the refinery ids it needs with zero extra filtering/re-querying to figure out which returned id belongs to which table |
| 6 | **`affected_by()` accepts a set/iterable of corridor ids**, unioning results, not one id at a time | Matches the shape `cascade.py`'s own `affected_corridors()` already returns (`set[str]`) — a future caller passes that straight through with no loop-and-merge boilerplate |
| 7 | **Unknown corridor id raises `ValueError`** naming the bad id(s), rather than returning an empty result silently | Matches the codebase's existing fail-loud philosophy (`extra="forbid"`, `corridors[s.corridor_id]` in `recommend.py` already raises `KeyError` on a bad id) — a typo'd corridor id silently reporting "nothing affected" would be a much harder bug to notice on stage than a crash in a unit test |
| 8 | **Two edge types only, both derived from the exact same `Supplier`/`Refinery` rows Recommend already reads** — `ships_via` (supplier → corridor, from `supplier.corridor_id`) and `compatible_with` (supplier → refinery, wherever `supplier.crude_grade` is in `refinery.compatible_grades`). No precomputed corridor → refinery "feeds" edge is stored; it's a derived two-hop path `affected_by()` computes on the fly | Mirrors `recommend.py`'s own per-refinery grade-compatibility check (`Phase 2`) exactly, off the same source of truth (`Refinery.compatible_grades`) — there is no second copy of "what's compatible with what" that could quietly drift from the real wrong-oil gate |
| 9 | **No caching, no startup hook**: `build_graph(session)` builds fresh from current DB rows on every call, same spirit as `recommend.py`'s `build_candidates` | "Rebuilds automatically when a seed row changes, no code change needed" (PLAN.md) holds trivially because nothing is cached between calls. PLAN.md's acceptance phrase "graph rebuilds cleanly on startup" is satisfied by a test that builds against a freshly-seeded DB session — not a literal FastAPI startup-event hook, which would need a cache-invalidation story this phase has no consumer to justify yet |
| 10 | **`to_dict()` emits plain JSON-safe primitives only** — `{"nodes": [{"id", "type", ...attrs}], "edges": [{"source", "target", "relation", ...attrs}]}` — no NetworkX/graph objects leak out | Nothing reads this yet (decision #4), but it should already be `json.dumps`-safe the moment a future endpoint or static-diagram script does, without a serialization pass added later |

## 2 · Backend changes (`backend/agents/graph.py`, new file)

```python
"""Knowledge graph agent (Dev B) — supplier -> corridor -> refinery network (F10).

A NetworkX model of the supply network, built fresh from the seeded DB config
tables on every call (no caching — mirrors backend/agents/recommend.py's
build_candidates), so an edited/added corridor, supplier, or refinery row is
reflected with zero code change (SPEC.md Phase 5 decision #9).

affected_by() answers "if these corridors close, what's affected?" (F10) --
the query PLAN.md Phase 6 will read from to populate geo.affected_refinery_ids
once RiskState.geo exists for real. This phase stays a self-contained library:
no RiskState, cascade.py, or API change yet (decision #1) -- geo stays None
exactly as contract.py's own Geo docstring already commits to.

Two edge types, both derived from the same Supplier/Refinery rows Recommend
already reads -- no second copy of "what's compatible with what" that could
drift from backend/agents/recommend.py's real per-refinery wrong-oil gate
(Phase 2):
  - ships_via:       supplier -> corridor   (supplier.corridor_id)
  - compatible_with: supplier -> refinery   (supplier.crude_grade in
                                              refinery.compatible_grades)

"corridor" doubles as the "chokepoint" node PLAN.md's supplier->route->
chokepoint->refinery phrasing describes -- one node per Corridor row,
carrying `chokepoint` as an attribute, since today's seed data is 1:1
(decision #3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import networkx as nx
from sqlalchemy.orm import Session

from backend.models import Corridor, Refinery, Supplier


@dataclass(frozen=True)
class AffectedAssets:
    """affected_by()'s result, split by node type (decision #5) so a caller
    never has to re-derive which returned id belongs to which table."""

    suppliers: set[str] = field(default_factory=set)
    refineries: set[str] = field(default_factory=set)


def build_graph(session: Session) -> nx.DiGraph:
    """Build the supplier/corridor/refinery graph from the current DB rows.

    No caching (decision #9): call this fresh whenever you need it, same
    spirit as build_candidates -- a new seed row shows up with zero code
    change, at the cost of a (trivially cheap, ~15-node) rebuild per call.
    """

    g = nx.DiGraph()

    for c in session.query(Corridor).all():
        g.add_node(c.id, type="corridor", name=c.name, chokepoint=c.chokepoint)

    refineries = session.query(Refinery).all()
    for r in refineries:
        g.add_node(
            r.id, type="refinery", name=r.name,
            compatible_grades=list(r.compatible_grades),
        )

    for s in session.query(Supplier).all():
        g.add_node(s.id, type="supplier", country=s.country, crude_grade=s.crude_grade)
        g.add_edge(s.id, s.corridor_id, relation="ships_via")
        for r in refineries:
            if s.crude_grade in (r.compatible_grades or []):
                g.add_edge(s.id, r.id, relation="compatible_with")

    return g


def affected_by(graph: nx.DiGraph, corridor_ids: Iterable[str]) -> AffectedAssets:
    """"If these corridors close, what's affected?" (F10).

    Broad/inclusive (decision #2): a refinery counts as affected if it had
    *any* grade-compatible supplier on one of the given corridors, even if it
    also has other compatible suppliers elsewhere. Accepts a *set* of
    corridor ids, not just one (decision #6), so cascade.py's own
    affected_corridors() -> set[str] result can be passed straight through.
    Raises ValueError on an unknown corridor id (decision #7) rather than
    silently returning nothing.
    """

    corridor_ids = set(corridor_ids)
    known = {n for n, d in graph.nodes(data=True) if d.get("type") == "corridor"}
    unknown = corridor_ids - known
    if unknown:
        raise ValueError(f"unknown corridor id(s): {sorted(unknown)}")

    suppliers: set[str] = set()
    for u, v, data in graph.edges(data=True):
        if data.get("relation") == "ships_via" and v in corridor_ids:
            suppliers.add(u)

    refineries: set[str] = set()
    for s in suppliers:
        for _, target, data in graph.out_edges(s, data=True):
            if data.get("relation") == "compatible_with":
                refineries.add(target)

    return AffectedAssets(suppliers=suppliers, refineries=refineries)


def to_dict(graph: nx.DiGraph) -> dict:
    """Plain-JSON graph serialization (decision #10) -- a future endpoint or
    static-diagram script can json.dumps() this directly. No route reads it
    yet (decision #4)."""

    return {
        "nodes": [{"id": n, **data} for n, data in graph.nodes(data=True)],
        "edges": [
            {"source": u, "target": v, **data} for u, v, data in graph.edges(data=True)
        ],
    }
```

**New dep:** `networkx` — add to `requirements.txt` under a new `# ---- Dev B
(Phase 5): knowledge graph ----` section, next to the existing Phase 4 block.

No changes to `backend/cascade.py`, `backend/schemas/contract.py`,
`backend/state_store.py`, or `backend/api/routes.py` (decisions #1, #4).

## 3 · Worked examples (today's seed data, no synthetic scenario needed)

| Closed corridor(s) | Affected suppliers | Affected refineries | Why |
|---|---|---|---|
| `hormuz` | `iq_basrah`, `sa_arablight`, `ae_murban` | `jamnagar`, `vadinar`, `paradip` (**all three**) | Basrah Medium/Arab Light/Murban between them touch every refinery's `compatible_grades` |
| `suez_cape` | `ru_urals`, `ng_bonny` | `jamnagar`, `vadinar` — **not** `paradip` | Urals/Bonny Light aren't in `paradip`'s `compatible_grades` (`["Arab Light","Murban","Lula","WTI"]`) |
| `atlantic` | `us_wti`, `br_tupi` | `paradip` only | WTI/Lula are only in `paradip`'s `compatible_grades`; `jamnagar`/`vadinar` don't carry either |
| `malacca` | *(none)* | *(none)* | A **known, valid** corridor id with zero suppliers currently routed through it in seed data — `affected_by({"malacca"})` returns `AffectedAssets(set(), set())`, not an error (contrast with an unknown id, decision #7) |
| `{"suez_cape", "atlantic"}` | union of both rows above | `jamnagar`, `vadinar`, `paradip` (all three, via union) | Demonstrates decision #6's multi-corridor union |

The `suez_cape`/`atlantic` rows are the demo-worthy cases — each excludes at
least one refinery, proving the query actually discriminates rather than
trivially returning "everything" every time (`hormuz`'s "all three" result is
real but less illustrative on its own).

## 4 · Test updates (`tests/test_graph.py`, new)

Reuses the exact `_seeded_session()` fixture pattern from
`tests/test_recommend.py` (`create_engine("sqlite:///:memory:")` +
`Base.metadata.create_all` + `seed_all(session)`):

- `test_build_graph_node_and_edge_counts` — node count equals
  `n_corridors + n_suppliers + n_refineries`; every supplier has exactly one
  outgoing `ships_via` edge.
- `test_affected_by_hormuz_reaches_all_three_refineries` — §3's first row.
- `test_affected_by_suez_cape_excludes_paradip` — §3's second row, the
  headline "discriminates, doesn't just return everything" case.
- `test_affected_by_atlantic_only_paradip` — §3's third row.
- `test_affected_by_known_corridor_with_no_suppliers_returns_empty` —
  `malacca`, distinguishing "valid id, empty result" from the next case.
- `test_affected_by_unknown_corridor_raises` — `affected_by(graph,
  {"not_a_real_corridor"})` raises `ValueError`.
- `test_affected_by_unions_multiple_corridors` — §3's last row.
- `test_to_dict_is_json_serializable` — `json.dumps(to_dict(graph))` doesn't
  raise; spot-check a node and an edge have the expected keys.
- `test_build_graph_rebuilds_cleanly` — building twice from the same
  (freshly-seeded) session produces the same node/edge counts both times —
  this is what PLAN.md's "graph rebuilds cleanly on startup" acceptance
  criterion means in practice (decision #9), not a literal app-startup hook.

## 5 · Documentation updates (same change, per the contract-change protocol)

- **`requirements.txt`** — add `networkx` under a new Dev B/Phase 5 section
  comment.
- **`PROJECT_GUIDE.md`** — flip F10's status row and the Dev B section's
  "Remaining" list item 1 from ⬜ to done; note explicitly that
  `geo.affected_refinery_ids` itself is still `None`/unpopulated until Phase
  6 (so the status board doesn't overclaim what this phase shipped).
- **`PLAN.md`** — flip Phase 5's status once merged; add a short
  post-implementation note (matching Phase 4/7's existing style) that this
  phase deliberately does **not** wire into `cascade.py` or `RiskState.geo`
  — that wiring is Phase 6's job — since PLAN.md's own Phase 5 prose implied
  otherwise ("wire into ... the `geo.affected_refinery_ids` field from Phase
  1"). Also update Phase 4's already-existing "Explicitly deferred" note
  about replacing `KNOWN_CORRIDORS` with a live graph/DB check (SPEC.md
  Phase 4 §9) — that idea remains deferred; Phase 5 landing doesn't obligate
  it on its own, only makes it *possible* once something else needs Watch to
  take a DB dependency for another reason.

## 6 · Acceptance criteria

1. `python -m pytest` fully green, including every new test in §4 — no
   existing test touches `graph.py`, so nothing else should need updating.
2. `affected_by(build_graph(session), {"hormuz"})` returns
   `AffectedAssets(suppliers={"iq_basrah","sa_arablight","ae_murban"},
   refineries={"jamnagar","vadinar","paradip"})` against today's seed data.
3. `affected_by(build_graph(session), {"suez_cape"})` excludes `paradip` from
   its `refineries` set — the concrete, non-trivial discrimination case.
4. An unknown corridor id raises `ValueError`; a known corridor id with no
   current suppliers (`malacca`) returns an empty (not erroring)
   `AffectedAssets`.
5. `to_dict(build_graph(session))` round-trips through `json.dumps`/`json.loads`
   with no error.
6. Zero behavior change anywhere else: `GET /state`, `GET /reroutes`,
   `POST /signal`'s full cascade, and every existing test are bit-identical
   to pre-Phase-5 output — this phase adds a new, uncalled module, nothing
   more.

## 7 · Explicitly deferred (not decided here — flagged for the named phase)

- **Actually populating `RiskState.geo`** (all three fields, including
  `affected_refinery_ids` via this phase's `affected_by()`) and wiring
  `cascade.py` to call it — **Phase 6**, which needs the AIS/tanker data for
  `at_risk_tanker_ids` anyway, so the whole block lands as one atomic,
  testable change rather than a partial `Geo` today.
- **A `GET /graph` (or similar) debug/read endpoint** exposing `to_dict()` —
  not built this phase (decision #4); revisit once Phase 6/Segment 2 Chunk E
  has a real consumer for the shape.
- **Replacing Watch's static `KNOWN_CORRIDORS` set with a live graph/DB-backed
  check** (SPEC.md Phase 4 §9's own deferred item) — still not obligated by
  this phase landing; only worth doing once something else needs Watch to
  take a DB/graph dependency for an unrelated reason.
- **Modeling a chokepoint shared by more than one corridor** — decision #3's
  collapse assumes today's 1:1 seed data; revisit the node model only if a
  future corridor addition actually needs it.

---

# SPEC — Segment 1, Phase 6: Geospatial data layer — AIS replay + GeoJSON + `/geo/state` (F11, F13)

> Scope: exactly [PLAN.md](.claude/docs/PLAN.md)'s Phase 6. Curates a small, deterministic,
> committed AIS tanker-track replay dataset; authors real (illustrative,
> honestly-labeled) corridor GeoJSON polylines for the four
> `geojson_path` values Phase 1 reserved but left empty; adds
> `backend/agents/geo.py` (the module that actually builds the `Geo` block);
> wires it into `cascade.py` so **this is the phase that stamps
> `RiskState.geo` for the first time** (Phase 5's `affected_by()` shipped
> uncalled, per its own decision #1 — this phase is that call); and adds
> `GET /geo/state`. No contract change — `Geo` already exists from Phase 1;
> this phase gives it real values. Depends on Phase 1 (landed, `Corridor`/
> `Refinery` v1.3 columns) and Phase 5 (landed, `affected_by()`). Independent
> of Phases 2–4.

## 1 · Decisions made (interview log)

| # | Decision | Why |
|---|---|---|
| 1 | **All four seeded corridors** (`hormuz`, `suez_cape`, `atlantic`, `malacca`) get curated tankers — 4 each, 16 total | User call. Keeps the map populated everywhere a corridor can render, and means `suez_cape`/`atlantic` already have tankers positioned to visually react when Phase 2's `hormuz_partial_closure` worked example reroutes traffic through them, not just the disrupted corridor itself |
| 2 | **Each tanker is a real multi-point timestamped track**, not a single snapshot position — 8 points per tanker at a fixed 3-hour cadence over a committed synthetic 21-hour window (`2026-01-15T00:00:00Z` … `21:00:00Z`, matching PROJECT_GUIDE.md §08's existing illustrative date so the whole repo's example data reads as one consistent "day") | User call. Matches PLAN.md's own "tanker-track **replay**" wording — Segment 2 needs actual movement to animate, not synthetic client-side interpolation from one point |
| 3 | **Tanker↔corridor membership is a static tag in the curated data**, not geometric point-in-polygon against the corridor GeoJSON. Corridor GeoJSON is map decoration only — no backend logic reads it | User call, confirms PLAN.md's explicit "New deps: none beyond what Phase 4/7 already add" for this phase — a real point-in-polygon check would need `shapely`, which PLAN.md didn't budget here |
| 4 | **Track geometry is a small local drift near each corridor's existing map anchor**, not a corridor-to-refinery ocean crossing | A tanker moving at a realistic ~11–13 knots covers roughly 0.4–0.5° of latitude in 21 hours — spreading 8 points across the full corridor→India distance (tens of degrees) would visibly teleport on stage. Anchors reuse the **exact coordinates `frontend/components/shared/interactive-map.client.tsx`'s `NODES` constant already hardcodes** (`hormuz [26.57,56.25]`, `suez_cape [12.6,43.3]`, `atlantic [-34.0,18.5]`, `malacca [2.5,101.4]`) so the AIS layer visually lines up with the map's existing corridor markers instead of introducing a second, slightly-different set of "where is Hormuz" coordinates |
| 5 | **`GET /geo/state` reads `geo` live from `RiskState`** (via a new `StateStore.merge_geo()`, `None` on fresh boot exactly like `impact`/`reserve` today) rather than recomputing it fresh on every call | User call. No sort-style toggle exists for `geo` (unlike `/reroutes`' `sort=`), so there's no reason to recompute on read; this is also the literal mechanism PLAN.md means by "stamps `RiskState.geo` for the first time" — a recompute-on-read design would never actually populate the WS-pushed snapshot |
| 6 | **`GET /geo/state` also bundles `corridors` and `refineries` config rows** (id, name, `geojson_path`, `war_risk_pct`, `detour_days` / id, name, `lat`, `lon`, `capacity_bpd`), not just `geo` + tanker tracks | Neither table is exposed by any existing endpoint — `Corridor.geojson_path` and `Refinery.lat/lon` (both landed in Phase 1) have had **no HTTP consumer at all** until now. Without this, Segment 2 can't discover which GeoJSON files exist or where refineries sit without hardcoding them client-side (as `interactive-map.client.tsx`'s `NODES` already does today, decision #4) — which breaks the "new corridor = one config row, not a code change" scalability pitch PLAN.md §15 repeats. Bundling them here, in the one endpoint whose stated goal is "the backend half of the geospatial layer" (PLAN.md's own Phase 6 goal line), avoids inventing a second `GET /corridors`/`GET /refineries` pair with no other reason to exist yet |
| 7 | **`at_risk_tanker_ids` and `affected_refinery_ids` share one corridor-set definition**: `cascade.py`'s own `excluded` (the signal-fallback-augmented set already computed for Recommend at cascade step 3 — see `cascade.py:63`), not a second, stricter `affected_corridors(state)` call | One definition of "which corridors count as disrupted right now" for the whole `Geo` block, reused rather than duplicated (same reuse-over-drift principle as graph.py's own decision #8). Also means the corridor the demo just disrupted shows up as both "tankers at risk" and "reroutes exist" in the same sweep, which is the actual demo beat, not an edge case to route around |
| 8 | **`affected_by()`'s `ValueError` on an unknown corridor id is caught, not propagated**, inside the new `build_geo()` — logged as a warning, treated as "no refineries affected via the graph query" | Found while wiring this phase, not called out in PLAN.md's own Phase 6 section: `POST /signal`'s handler already tolerates an unrecognized `corridor` string by design (`routes.py`'s "soft-validate … warn, never reject" comment), and `run_watch_stub` will happily score a corridor id that doesn't exist in the `corridors` table. That id can end up in `excluded` and reach `affected_by()`, whose Phase 5 decision #7 deliberately fails loud on exactly that input. Phase 5's fail-loud choice is right for a *unit test* passing a typo'd literal; it would be wrong here, where it's reachable from an unauthenticated `POST /signal` body and must not 500 the whole cascade. `at_risk_tanker_ids` needs no equivalent guard — decision #3's static-tag matching simply matches nothing for an unknown id, no exception path exists to catch |
| 9 | **AIS data location/format**: new `backend/agents/data/ais_sample.json`, one record per tanker with a nested `track` array | Mirrors Phase 4's `backend/agents/data/watch_corpus.json` placement exactly — this is agent input data read directly by Python, not a DB-seeded config table (unlike `corridors.json`/`refineries.json`, which *are* loaded into SQL rows by `seed.py`). JSON over CSV because the nested per-tanker track is naturally a JSON array, avoiding a second (tanker_id, timestamp) join key a flat CSV would need |
| 10 | **Corridor GeoJSON files are hand-authored, illustrative polylines** (3–5 vertices each, `backend/seed/geo/{id}.geojson`), explicitly labeled as approximate — not sourced from a real OSM/navigational dataset | Matches the project's existing honesty framing for every other estimated/illustrative figure (`war_risk_pct`, `detour_days`, refinery lat/lon "verify precisely... when Phase 6 actually renders map pins" — SPEC.md Phase 1 §3.2). PLAN.md's "free OSM-derived GeoJSON" framing assumed a download step this environment can't perform against a live tile/data service; hand-authored is the honest substitute, documented as such in each file rather than silently passed off as surveyed data |
| 11 | **`dark_tanker_ids` is always `[]` in this phase's output** | Confirms `contract.py`'s own `Geo` docstring and PLAN.md Phase 7's scope — the anomaly detector that populates it doesn't exist until Phase 7 |
| 12 | **`cascade.py` gains a 5th step, after Advise, not inserted into the existing 1–4 sequence** | Nothing downstream of Advise depends on `geo`, and appending avoids renumbering/re-reviewing the four already-tested cascade steps for an unrelated change |

## 2 · Backend changes

### 2.1 `backend/agents/geo.py` (new file)

```python
"""Geospatial agent (Dev B) — AIS tanker-track replay + Geo block (F11, F13).

Loads the curated, committed AIS sample (backend/agents/data/ais_sample.json)
once per process and answers two questions:
  - which tankers are "at risk" (static corridor tag, no geometry -- SPEC.md
    Phase 6 decision #3) given the set of currently-elevated corridors
  - which refineries are "affected" (via graph.py's affected_by(), Phase 5)

build_geo() is the one function cascade.py calls; it is the first thing that
ever populates RiskState.geo for real (Phase 5 shipped affected_by() uncalled
by design -- this is that call, SPEC.md Phase 6 decision #5/#12).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from backend.agents.graph import affected_by, build_graph
from backend.schemas import Geo

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).parent / "data" / "ais_sample.json"


@lru_cache(maxsize=1)
def _load_tankers() -> list[dict]:
    """The curated AIS replay set, loaded once per process (static, committed
    data -- no reason to re-read the file on every call)."""

    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def list_tankers() -> list[dict]:
    """Raw tanker records (id, corridor_id, track[]) for GET /geo/state."""

    return _load_tankers()


def at_risk_tanker_ids(elevated_corridors: set[str]) -> list[str]:
    """Tankers whose static corridor tag is in an elevated-risk set.

    No geometry (decision #3): an unrecognized corridor id in
    `elevated_corridors` simply matches no tanker -- unlike affected_by(),
    there's no fail-loud path to guard here.
    """

    return sorted(
        t["id"] for t in _load_tankers() if t["corridor_id"] in elevated_corridors
    )


def build_geo(session: Session, elevated_corridors: set[str]) -> Geo:
    """Build the real Geo block for this cascade run (F11/F13; F18's
    dark_tanker_ids stays [] until Phase 7 — decision #11)."""

    try:
        graph = build_graph(session)
        affected_refineries = sorted(affected_by(graph, elevated_corridors).refineries)
    except ValueError as exc:
        # An unrecognized corridor id reached us (POST /signal's "warn, never
        # reject" tolerance — decision #8). affected_by()'s own fail-loud
        # choice (SPEC.md Phase 5 decision #7) is right for a bad literal in
        # a unit test; it must not 500 a live cascade.
        logger.warning("geo: affected_by() rejected corridor set (%s), treating as none affected", exc)
        affected_refineries = []

    return Geo(
        at_risk_tanker_ids=at_risk_tanker_ids(elevated_corridors),
        dark_tanker_ids=[],
        affected_refinery_ids=affected_refineries,
    )
```

### 2.2 `backend/state_store.py` — `merge_geo`

Same one-field-commit shape as `merge_reserve` (§`state_store.py:156`):

```python
async def merge_geo(self, geo: Geo) -> RiskState:
    return await self._commit(self._state.model_copy(update={"geo": geo}))
```

### 2.3 `backend/cascade.py` — step 5

```python
from backend.agents.geo import build_geo
```

appended after the existing step 4 (`merge_reserve`), reusing the same
`excluded` set already computed at step 3 (decision #7):

```python
    # 5) Geo: at-risk tankers (static AIS tag) + affected refineries (Phase 5's
    # knowledge graph) for whichever corridors are currently excluded/elevated.
    # First real stamp of RiskState.geo — Phase 5 shipped affected_by() uncalled.
    with session_factory() as session:
        geo = build_geo(session, excluded)
    await store.merge_geo(geo)

    return store.get()
```

(`excluded` is already in scope from step 3 — `cascade.py:63` — no recomputation.)

### 2.4 `backend/api/routes.py` — `GET /geo/state`

No auth (matches `GET /state`/`GET /public/status` precedent — this is
read-only, non-sensitive config + replay data):

```python
@router.get("/geo/state")
def get_geo_state(
    store=Depends(get_store),
    session: Session = Depends(get_session),
) -> dict:
    """The geospatial layer's one-stop read: current Geo block (None until a
    signal's been injected — same pattern as impact/reserve), corridor/
    refinery config (F11 map data with no other HTTP consumer today), and the
    curated AIS tanker-track replay set (F13)."""

    state = store.get()
    corridors = session.query(Corridor).all()
    refineries = session.query(Refinery).all()
    return {
        "geo": state.geo.model_dump(mode="json") if state.geo else None,
        "corridors": [
            {
                "id": c.id, "name": c.name, "chokepoint": c.chokepoint,
                "war_risk_pct": c.war_risk_pct, "detour_days": c.detour_days,
                "geojson_path": c.geojson_path,
            }
            for c in corridors
        ],
        "refineries": [
            {
                "id": r.id, "name": r.name, "capacity_bpd": r.capacity_bpd,
                "lat": r.lat, "lon": r.lon,
            }
            for r in refineries
        ],
        "tankers": list_tankers(),
    }
```

`Corridor`, `Refinery`, and `list_tankers` join the existing import block at
the top of `routes.py`.

## 3 · Data changes + worked example

### 3.1 `backend/seed/geo/{id}.geojson` (new, 4 files)

One `FeatureCollection` per corridor, a single `LineString` geometry,
3–5 hand-authored vertices `[lon, lat]` (GeoJSON's own axis order) running
from the corridor's `NODES` anchor (decision #4) toward the Arabian
Sea/Indian Ocean approach, tagged as illustrative (decision #10):

```jsonc
// backend/seed/geo/hormuz.geojson
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "properties": {
      "id": "hormuz", "name": "Strait of Hormuz",
      "note": "Illustrative, hand-authored approximate route — not surveyed navigational data."
    },
    "geometry": {
      "type": "LineString",
      "coordinates": [[56.25, 26.57], [57.8, 25.0], [61.0, 22.0], [68.0, 19.0]]
    }
  }]
}
```

The other three (`suez_cape`, `atlantic`, `malacca`) follow the identical
shape, anchored at their own `NODES` coordinate (decision #4) and bending
toward India with 3–4 more vertices each. No `Corridor.geojson_path` value
changes — Phase 1 already seeded the paths these files now fill.

### 3.2 `backend/agents/data/ais_sample.json` (new)

16 tankers (decision #1: 4 per corridor × `hormuz`/`suez_cape`/`atlantic`/
`malacca`), each an 8-point track (decision #2) generated by this exact
deterministic recipe — small drift around the corridor's `NODES` anchor
(decision #4), not an ocean crossing:

- Tanker `i` (0-indexed, 0–3) within a corridor starts at
  `anchor + (dLat[i], dLon[i])` where `dLat/dLon` is a fixed per-index
  scatter — `[(0.0,0.0), (0.5,-0.3), (-0.4,0.6), (0.8,0.4)]` — so the four
  tankers in one corridor don't render on top of each other.
- Each of the 8 track points advances from the start by
  `step * (0.02, 0.03)` in the corridor's fixed bearing direction (a small
  per-corridor unit vector pointed roughly toward India — e.g. hormuz's is
  southeast, malacca's is west), `step = 0..7`, timestamped
  `2026-01-15T00:00:00Z + step * 3h`.
- `heading_deg` is that corridor's fixed bearing (rounded); `speed_knots` is
  `11.0 + i * 0.5` (11.0–12.5 across the four tankers) — plausible laden-tanker
  cruise speed, not measured.
- Tanker `id` is `f"{corridor}_{i+1:02d}"` (e.g. `hormuz_01`).

One worked example row:

```jsonc
{
  "id": "hormuz_01",
  "corridor_id": "hormuz",
  "track": [
    { "ts": "2026-01-15T00:00:00Z", "lat": 26.57, "lon": 56.25, "heading_deg": 135.0, "speed_knots": 11.0 },
    { "ts": "2026-01-15T03:00:00Z", "lat": 26.44, "lon": 56.34, "heading_deg": 135.0, "speed_knots": 11.0 },
    // ... 6 more 3-hour steps through 21:00:00Z
  ]
}
```

The generation recipe (not a hand-typed 128-row table) is the spec artifact
here — implement it as a small one-off script (or hand-apply it) that emits
the committed, static `ais_sample.json`; nothing computes tanker positions
at runtime.

### 3.3 Worked example — `hormuz_partial_closure` (today's seed data)

With `hormuz`'s score crossing `AFFECTED_THRESHOLD` (50.0) and `excluded =
{"hormuz"}` (cascade.py step 3, no other corridor scored):

- `at_risk_tanker_ids` = `["hormuz_01", "hormuz_02", "hormuz_03", "hormuz_04"]`
  — exactly the four `hormuz`-tagged tankers, none of the other twelve.
- `affected_refinery_ids` = `["jamnagar", "paradip", "vadinar"]` — identical
  to `graph.affected_by(build_graph(session), {"hormuz"}).refineries`, per
  SPEC.md Phase 5 §3's own worked table (`hormuz` reaches all three
  refineries).
- `dark_tanker_ids` = `[]`.

## 4 · API surface changes

New: `GET /geo/state`, unauthenticated, no query params. Response shape
per §2.4 — `geo` is `null` on a fresh boot (no signal injected yet, same
pattern as `impact`/`reserve`), populated after the first `POST /signal`;
`corridors`/`refineries`/`tankers` are always present regardless of cascade
state (static config + committed replay data). No change to any existing
endpoint's signature or response shape.

## 5 · Test updates

- **`tests/test_geo.py`** (new), reusing the `_seeded_session()` fixture
  pattern from `tests/test_graph.py`:
  - `test_list_tankers_returns_16_records_across_four_corridors` — counts
    and `corridor_id` distribution match §3.2.
  - `test_at_risk_tanker_ids_matches_static_tags` — `at_risk_tanker_ids({"hormuz"})`
    returns exactly the four `hormuz_*` ids, sorted; `at_risk_tanker_ids(set())`
    returns `[]`; an unrecognized corridor id in the input set matches
    nothing (no exception — decision #3's no-geometry guarantee).
  - `test_build_geo_matches_graph_affected_by` — `build_geo(session, {"hormuz"})`'s
    `affected_refinery_ids` equals `sorted(affected_by(build_graph(session), {"hormuz"}).refineries)`.
  - `test_build_geo_handles_unknown_corridor_without_raising` — `build_geo(session, {"not_a_real_corridor"})`
    returns a valid `Geo` with `affected_refinery_ids=[]` (decision #8's crash guard),
    not a raised `ValueError`.
  - `test_build_geo_dark_tanker_ids_always_empty` — decision #11.
- **`tests/test_state_store.py`** — a `merge_geo` test mirroring the existing
  `merge_reserve` one: commits, re-validates, publishes, `store.get().geo`
  reflects the merged value.
- **`tests/test_api.py`**:
  - `GET /geo/state` on a fresh app: `200`, `geo: null`, `len(tankers) == 16`,
    `len(corridors) == 4`, `len(refineries) == 3`.
  - After `POST /signal` with a `hormuz`-disrupting payload (reuses the
    existing full-cascade fixture), `GET /geo/state`'s `geo.at_risk_tanker_ids`
    contains exactly the four `hormuz_*` ids and `geo.affected_refinery_ids`
    matches §3.3's three refineries — a real regression check against live
    seed data, not a synthetic fixture.
- No changes needed to `tests/test_contract.py` (no contract change — Phase
  1 already added `Geo`'s present/absent round-trip coverage), `test_recommend.py`,
  `test_predict.py`, `test_watch.py`, `test_graph.py`, `test_advise.py`,
  `test_auth.py`, `test_llm.py`, `test_rag.py`.

## 6 · Documentation updates (same change, per the contract-change protocol)

- **`backend/agents/geo.py`** module docstring — per §2.1.
- **`backend/seed/geo/*.geojson`** — each file's own `properties.note` carries
  the "illustrative, not surveyed" honesty label (decision #10); no separate
  doc needed.
- **`PROJECT_GUIDE.md`** — flip F11/F13's status rows (§04 feature table,
  §05A geospatial section, §06 tech-stack row, the Dev B "Remaining" list,
  the architecture diagram) from planned to shipped; note `Geo` is now
  genuinely populated post-signal, not just contract-shaped; add
  `GET /geo/state` to the endpoints table (§08).
- **`PLAN.md`** — flip Phase 6's status once merged; note decision #6
  (bundling `corridors`/`refineries` into the response) since PLAN.md's own
  Phase 6 section only mentioned the `Geo` block + tanker data, not corridor/
  refinery config: the next implementer shouldn't be surprised those two
  keys exist in the response too. Note decision #8's crash guard so Phase
  7/8's implementer doesn't reintroduce an unguarded `affected_by()` call
  reachable from `POST /signal`.

## 7 · Acceptance criteria

1. `python -m pytest` fully green, including every new test in §5.
2. `GET /geo/state` on a fresh boot (no signal injected): `200`, `geo: null`,
   `tankers`/`corridors`/`refineries` all populated from committed/seeded
   data.
3. A `hormuz`-disrupting `POST /signal` followed by `GET /geo/state` (or a
   fresh `GET /state`) shows `geo.at_risk_tanker_ids` containing exactly the
   `hormuz`-tagged tankers and `geo.affected_refinery_ids` exactly matching
   `graph.affected_by(build_graph(session), {"hormuz"}).refineries` —
   `{"jamnagar","vadinar","paradip"}` against today's seed data (matches
   PLAN.md's own acceptance line and SPEC.md Phase 5 §3).
4. All four `backend/seed/geo/*.geojson` files parse as valid GeoJSON and
   load in a manual/quick Leaflet smoke test (PLAN.md's own bar — can be
   manual, ahead of Segment 2 wiring it up for real).
5. An unrecognized corridor id reaching `build_geo()` (e.g. via a malformed
   `POST /signal`) never raises out of the cascade — `POST /signal` still
   returns `200` with a valid, contract-checked `RiskState`.
6. Zero behavior change to any pre-existing endpoint or computed field —
   this phase is additive (`geo` was already `None`-shaped and unread by
   anything; now it's populated).
7. No new dependency added (`requirements.txt` unchanged) — confirms
   decision #3.

## 8 · Explicitly deferred (not decided here — flagged for the named phase)

- **`dark_tanker_ids` real values** (the anomaly detector itself) — **Phase 7**,
  which reads this same `backend/agents/data/ais_sample.json` (PLAN.md's own
  "Phase 7 reads the same AIS dataset this phase curates" note) to derive
  per-vessel features (speed, heading-change rate, distance off the corridor
  line, transponder-gap length) — none of which this phase's straight-line
  synthetic tracks are designed to exercise realistically; Phase 7's own
  interview should decide whether `ais_sample.json` needs a few
  deliberately-anomalous tracks added, or a separate synthetic-anomaly
  fixture.
- **Real point-in-polygon geometry against the corridor GeoJSON** (decision
  #3's rejected alternative) — not planned at all currently; revisit only if
  a future phase has an independent reason to add a geometry dependency.
- **A time-scrubbing / `?t=` playback-position query param on
  `GET /geo/state`** — not needed; the endpoint returns full tracks and
  Segment 2 animates client-side over the array.
- **Refining the hand-authored GeoJSON vertices against real navigational
  charts** — only worth it if a judge/demo audience zooms in far enough for
  the approximation to visibly matter; the honesty label (decision #10)
  covers the gap until then.
- **A live/backend-driven replacement for `interactive-map.client.tsx`'s
  hardcoded `NODES` constant**, now that `GET /geo/state` serves the same
  corridor coordinates it's derived from — Segment 2, whichever chunk wires
  the map to this endpoint (Chunk E/F per PLAN.md §3).

---

---

# SPEC — Segment 1, Phase 7: Dark-ship anomaly detector — the real ML component (F18)

> Scope: exactly [PLAN.md](.claude/docs/PLAN.md)'s Phase 7. Adds `backend/agents/anomaly.py`
> — an unsupervised `sklearn.ensemble.IsolationForest` over per-vessel AIS
> features from Phase 6's committed replay set — and wires its output into
> two places: `RiskState.geo.dark_tanker_ids` (via `geo.py`'s `build_geo()`,
> the field Phase 1 already shaped and Phase 6 left permanently `[]`) and, as
> grounded prompt context, Watch's real LLM scoring path (`watch.py`) plus
> Watch's offline stub fallback (`stubs.py`). No contract changes — every
> field this phase populates for real already exists. Depends on Phase 6
> (the AIS data) and, for the Watch-wiring half, Phase 4 (both landed).

## 1 · Decisions made (interview log)

| # | Decision | Why |
|---|---|---|
| 1 | **Anomaly signature: transponder gap + course deviation, combined on the same tankers** | A single-axis signature (just a gap, or just a course change) is weaker evidence and a weaker demo beat than "went dark, then reappeared somewhere it shouldn't be" — the two together is what actually reads as suspicious, and gives the detector two independent, corroborating features instead of one |
| 2 | **3 of Hormuz's 4 tankers become the synthetic dark case** (`hormuz_02`, `hormuz_03`, `hormuz_04`); `hormuz_01` and all 12 tankers in the other three corridors stay untouched | Matches PLAN.md's own PRD-beat wording ("Three tankers just went dark near Hormuz") exactly, and keeping one Hormuz tanker clean proves the detector discriminates *within* a corridor, not just "Hormuz vs. everywhere else" |
| 3 | **Corridor-line-distance feature dropped in favor of a self-referential "deviation from the tanker's own initial course" feature — a correction of the literal interview answer** (which picked adding `shapely` for distance-to-the-official-corridor-polyline) | Verified numerically before committing to it (§3 below): every clean tanker in the curated set is deliberately seeded in its own parallel "lane" offset from the corridor GeoJSON's polyline (Phase 6 anchored that polyline to one representative point, `interactive-map.client.tsx`'s `NODES` constant, not the whole fleet) — so distance-to-the-official-line ranges ~0–113km across clean tankers regardless of behavior, and a dark tanker's *added* deviation doesn't stand out against that noise (e.g. clean `suez_cape_04` sits 98.9km off its corridor's line, matching dark `hormuz_04`'s 112.6km). Extrapolating each tanker from its own first observed leg and measuring deviation from *that* is self-consistent per-vessel, immune to the lane-offset confound, needs no geometry library, and — confirmed by an actual `IsolationForest` run (§3) — gives a clean, wide-margin split. This also means `shapely` is never added, which keeps PLAN.md's original "New deps: scikit-learn" (no second library) accurate |
| 4 | **Four features, one row per tanker (aggregated over its full 8-point track), each rounded before fitting**: `max_gap_hours` (1dp), `max_heading_delta_deg` (1dp), `speed_std_knots` (2dp), `max_path_deviation_km` (1dp) | "Per-vessel features over a time window," per PLAN.md. Rounding matters more than it looks: without it, floating-point noise on the order of 1e-11–1e-13 (an artifact of projecting different tankers' different absolute lat/lon into a common km-space) made `IsolationForest` treat 13 behaviorally-identical "clean straight line" tankers as 13 subtly-different points, producing inconsistent, noisy scores between them (verified — see §3); rounding collapses them into exact ties, which is what they actually are |
| 5 | **One global model, fit across all 16 tankers**, not one per corridor | `max_path_deviation_km` (decision #3) is already per-vessel-relative, not corridor-relative, so nothing is lost by pooling; 16 samples is little enough already without splitting it four ways |
| 6 | **`IsolationForest(n_estimators=200, contamination=0.19, random_state=42)`**, no `StandardScaler` | `contamination≈0.19` ≈ 3/16, the intended dark-tanker fraction — empirically verified stable: the exact same 3 tankers (`hormuz_02/03/04`) are flagged, no more and no less, across `contamination` values from 0.15 to 0.25 and across five different `random_state` seeds (§3) — comfortable margin, not a knife-edge tune. No scaling: `IsolationForest` splits are per-feature axis-aligned thresholds, not distance-based, so differing feature units (hours vs. degrees vs. knots vs. km) don't bias it the way they would a distance-based method |
| 7 | **No rule-based (z-score) fallback path** | PRD §13's graceful-degradation allowance exists for components with a real runtime failure mode (a network call, a missing API key). The anomaly detector has none — it's a pure function over static, committed data, like `geo.py`'s `list_tankers()` — so there is nothing for it to degrade *from*. A parallel rule-based path here would be unused code, not a safety net |
| 8 | **`geo.dark_tanker_ids` filtered by `elevated_corridors`**, mirroring `at_risk_tanker_ids()` | Consistent with Phase 6's existing pattern and the map only ever surfacing dark markers relevant to the disruption currently being viewed; a Malacca signal's `geo` block doesn't carry Hormuz's dark tankers |
| 9 | **A second, unfiltered `dark_tanker_count(corridor) -> int` for Watch's prompt** | Watch scores one specific corridor straight from the signal (`run_watch(signal)`), never computing an "elevated" set — that concept doesn't exist at Watch's point in the cascade (it's derived *from* Watch's own score, one step later). A corridor-scoped count is the only input that makes sense to hand it |
| 10 | **`watch.py` imports `anomaly.py` directly**, same pattern as its existing `rag.py` import — no `cascade.py` resequencing | Anomaly detection doesn't depend on Watch's own output or on DB state (decision #7's "pure function over static data" applies here too), so there's no real sequencing problem to solve — Watch can just call it, the same way it already calls `retrieve()` |
| 11 | **`dark_count` folded into the LLM cache key** | Keeps the existing "same effective inputs -> same cached response" invariant technically correct if `ais_sample.json` is ever revised later, even though today's dark-tanker set never changes at runtime (matches the existing `source_ids` inclusion in the same cache key, same reasoning) |
| 12 | **`run_watch_stub` gets a matching dark-tanker bump term**, `+10.0` points per dark tanker in the signal's corridor | PLAN.md's own open question, resolved: unlike the LLM/RAG path, the detector has no network dependency and is available even when `USE_REAL_AGENTS` is off or no key is set — so there's no reason the fully-offline demo path shouldn't also visibly react to "3 dark tankers near Hormuz." `+10.0` sits below `_ESCALATION_WORDS`' 15–30 range (corroborating signal, not headline-level on its own); an unrecognized corridor gets `dark_tanker_count()`'s existing `0`-on-unknown tolerance, so the stub never raises on a bad corridor string |
| 13 | **Fit-once, `lru_cache`'d**, exactly `geo.py`'s `list_tankers()` pattern | The AIS data never changes at runtime; there's no reason to refit a forest on every `/signal` or every prompt build |

## 2 · Verification method (why §1's numbers aren't guesses)

Before writing this section, the exact synthetic track edits in §3 and the
exact feature/model parameters in §5 were run for real — `pip install
scikit-learn shapely` locally, a small script reproducing
`backend/agents/data/ais_sample.json` with the proposed dark-tanker edits
applied, and both the rejected corridor-distance approach and the adopted
self-referential one computed and fed through an actual `IsolationForest`.
The corridor-distance approach's failure (decision #3) and the adopted
approach's clean, stable 3-tanker split across contamination/seed sweeps
(decision #6) are both measured facts from that run, not projected — the
implementer can reproduce the same numbers by pasting §3's track values into
`ais_sample.json` and §5's feature code.

## 3 · Synthetic AIS data changes (`backend/agents/data/ais_sample.json`)

`hormuz_01` is untouched (stays the clean, in-corridor control). For
`hormuz_02`, `hormuz_03`, `hormuz_04`, indices `0`–`2` (`00:00`, `03:00`,
`06:00`) are untouched — each tanker transits normally, then "goes dark."
Indices `3`–`7` are replaced with the values below: a 12-hour transponder
gap (vs. the normal 3-hour cadence) to `18:00`, reappearing on a materially
different heading at sharply reduced ("loitering") speed, drifting for two
more 3-hour steps, then resuming near-normal speed on a heading that never
rejoins the original 135° track line — a "went dark, possible ship-to-ship
transfer, resumed on a diverted course" story, not a clean return to formation:

**`hormuz_02`** (indices 3–7 replace the existing entries; 0–2 unchanged):
```json
{ "ts": "2026-01-15T18:00:00Z", "lat": 26.62, "lon": 56.55, "heading_deg": 230.0, "speed_knots": 3.5 },
{ "ts": "2026-01-15T21:00:00Z", "lat": 26.55, "lon": 56.62, "heading_deg": 205.0, "speed_knots": 4.0 },
{ "ts": "2026-01-16T00:00:00Z", "lat": 26.50, "lon": 56.70, "heading_deg": 190.0, "speed_knots": 4.5 },
{ "ts": "2026-01-16T03:00:00Z", "lat": 26.40, "lon": 56.90, "heading_deg": 110.0, "speed_knots": 10.0 },
{ "ts": "2026-01-16T06:00:00Z", "lat": 26.33, "lon": 57.05, "heading_deg": 105.0, "speed_knots": 10.5 }
```

**`hormuz_03`** (indices 3–7):
```json
{ "ts": "2026-01-15T18:00:00Z", "lat": 25.75, "lon": 57.35, "heading_deg": 250.0, "speed_knots": 3.0 },
{ "ts": "2026-01-15T21:00:00Z", "lat": 25.70, "lon": 57.42, "heading_deg": 240.0, "speed_knots": 3.5 },
{ "ts": "2026-01-16T00:00:00Z", "lat": 25.66, "lon": 57.50, "heading_deg": 220.0, "speed_knots": 4.0 },
{ "ts": "2026-01-16T03:00:00Z", "lat": 25.55, "lon": 57.68, "heading_deg": 100.0, "speed_knots": 9.5 },
{ "ts": "2026-01-16T06:00:00Z", "lat": 25.47, "lon": 57.85, "heading_deg": 95.0, "speed_knots": 10.0 }
```

**`hormuz_04`** (indices 3–7):
```json
{ "ts": "2026-01-15T18:00:00Z", "lat": 26.95, "lon": 57.15, "heading_deg": 215.0, "speed_knots": 3.8 },
{ "ts": "2026-01-15T21:00:00Z", "lat": 26.90, "lon": 57.22, "heading_deg": 200.0, "speed_knots": 4.2 },
{ "ts": "2026-01-16T00:00:00Z", "lat": 26.85, "lon": 57.30, "heading_deg": 185.0, "speed_knots": 4.5 },
{ "ts": "2026-01-16T03:00:00Z", "lat": 26.73, "lon": 57.50, "heading_deg": 115.0, "speed_knots": 10.2 },
{ "ts": "2026-01-16T06:00:00Z", "lat": 26.65, "lon": 57.68, "heading_deg": 110.0, "speed_knots": 10.8 }
```

Every other tanker record (`hormuz_01` and all 12 in `suez_cape`/`atlantic`/
`malacca`) is byte-identical to Phase 6's committed file. Note the track's
total span grows from 21h to 30h for these three tankers (the gap adds time,
it doesn't compress the remaining cadence) — `list_tankers()`/`GET
/geo/state`'s consumers don't assume a fixed span, only a `track: list[Point]`
per tanker, so this needs no other code change.

## 4 · Resulting features (measured, §2's verification run)

| tanker | max_gap_hours | max_heading_delta_deg | speed_std_knots | max_path_deviation_km | flagged? |
|---|---|---|---|---|---|
| `hormuz_01` | 3.0 | 0.0 | 0.00 | 0.0 | no |
| `hormuz_02` | 12.0 | 95.0 | 3.43 | 85.5 | **yes** |
| `hormuz_03` | 12.0 | 120.0 | 3.79 | 75.2 | **yes** |
| `hormuz_04` | 12.0 | 80.0 | 3.74 | 78.3 | **yes** |
| every other tanker (13 total) | 3.0 | 0.0 | 0.00 | 0.0 | no |

All 13 clean tankers tie exactly (post-rounding) and score identically under
the fitted model; the three dark tankers separate with a wide margin
(`decision_function` ≈ −0.18 to −0.22 vs. +0.03 for every clean tanker, in
the verification run). This split held across `contamination` ∈
`{0.10, 0.15, 0.19, 0.20, 0.25}` (0.10 under-flags to 2; 0.15–0.25 all give
exactly the intended 3) and across `random_state` ∈ `{0, 1, 7, 42, 123}` —
§1 decision #6's constants aren't a knife-edge fit.

## 5 · Backend changes

### 5.1 `backend/agents/anomaly.py` (new file)

```python
"""Dark-ship anomaly detector (F18) — the project's one real, learned-from-
data component. Unsupervised sklearn.ensemble.IsolationForest over per-vessel
AIS features (speed variability, heading-change rate, deviation from the
vessel's own initial course, transponder-gap length) — no labelled
"suspicious ship" dataset exists, so learning what normal looks like and
flagging deviations is the right tool, not a forced ML story
(PROJECT_GUIDE.md §10E).

Pure/DB-free, fed only by the static, committed AIS replay set (Phase 6) --
like geo.py's list_tankers()/at_risk_tanker_ids(), this has no network
dependency and nothing that can fail at runtime, so unlike Watch's LLM path
there is no offline-fallback branch here (SPEC.md Phase 7 decision #7).
"""

from __future__ import annotations

import math
from datetime import datetime
from functools import lru_cache

from sklearn.ensemble import IsolationForest

from backend.agents.geo import list_tankers

_KM_PER_DEG_LAT = 111.32

# Tuned against the curated AIS set (SPEC.md Phase 7 §4) so the three
# synthetic "went dark" Hormuz tankers cross the threshold and the other 13
# don't -- verified stable across a contamination/seed sweep, not a
# principled statistical derivation (n=16 is too small for one).
# random_state fixes the forest's split choices for byte-identical output
# across runs (PLAN.md §5's determinism rule).
_N_ESTIMATORS = 200
_CONTAMINATION = 0.19
_RANDOM_STATE = 42


def _project_km(lat: float, lon: float, ref_lat: float) -> tuple[float, float]:
    """Flat equirectangular projection, accurate to well under 1km at this
    scale -- the same 'illustrative, not surveyed' honesty Phase 6 already
    applied to the corridor GeoJSON itself."""

    x = lon * _KM_PER_DEG_LAT * math.cos(math.radians(ref_lat))
    y = lat * _KM_PER_DEG_LAT
    return x, y


def _heading_delta(a: float, b: float) -> float:
    """Smallest angle between two compass headings (handles the 350deg ->
    10deg wraparound as a 20deg change, not 340deg)."""

    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _features(tanker: dict) -> tuple[float, float, float, float]:
    """(max_gap_hours, max_heading_delta_deg, speed_std_knots,
    max_path_deviation_km) over one tanker's full committed track.

    max_path_deviation_km is self-referential (decision #3): each tanker is
    extrapolated from its own first observed leg's velocity, not compared
    against the shared corridor polyline -- the curated fleet deliberately
    seeds each clean tanker in its own parallel "lane" offset from that
    polyline, which would otherwise swamp the actual anomaly signal.
    Every value is rounded (decision #4) to collapse floating-point noise
    between genuinely-identical "clean straight line" tankers into exact
    ties, rather than 13 numerically-almost-equal-but-distinct rows.
    """

    track = tanker["track"]
    timestamps = [datetime.fromisoformat(p["ts"].replace("Z", "+00:00")) for p in track]

    gaps = [
        (timestamps[i + 1] - timestamps[i]).total_seconds() / 3600.0
        for i in range(len(timestamps) - 1)
    ]
    headings = [p["heading_deg"] for p in track]
    heading_deltas = [
        _heading_delta(headings[i], headings[i + 1]) for i in range(len(headings) - 1)
    ]
    speeds = [p["speed_knots"] for p in track]
    speed_mean = sum(speeds) / len(speeds)
    speed_std = math.sqrt(sum((s - speed_mean) ** 2 for s in speeds) / len(speeds))

    ref_lat = track[0]["lat"]
    projected = [_project_km(p["lat"], p["lon"], ref_lat) for p in track]
    x0, y0 = projected[0]
    x1, y1 = projected[1]
    dt0 = (timestamps[1] - timestamps[0]).total_seconds() / 3600.0
    vx, vy = (x1 - x0) / dt0, (y1 - y0) / dt0

    deviations = []
    for i in range(2, len(track)):
        elapsed_h = (timestamps[i] - timestamps[0]).total_seconds() / 3600.0
        pred_x, pred_y = x0 + vx * elapsed_h, y0 + vy * elapsed_h
        act_x, act_y = projected[i]
        deviations.append(math.hypot(act_x - pred_x, act_y - pred_y))

    return (
        round(max(gaps), 1),
        round(max(heading_deltas), 1),
        round(speed_std, 2),
        round(max(deviations), 1),
    )


@lru_cache(maxsize=1)
def _anomalous_ids() -> frozenset[str]:
    """Fit once over the whole committed fleet (16 samples) and cache -- the
    AIS data never changes at runtime, so this is a one-time cost per
    process, mirroring geo.py's list_tankers() lru_cache."""

    tankers = list_tankers()
    X = [_features(t) for t in tankers]
    model = IsolationForest(
        n_estimators=_N_ESTIMATORS,
        contamination=_CONTAMINATION,
        random_state=_RANDOM_STATE,
    )
    labels = model.fit_predict(X)  # -1 = anomaly, 1 = normal
    return frozenset(t["id"] for t, label in zip(tankers, labels) if label == -1)


def dark_tanker_ids(elevated_corridors: set[str]) -> list[str]:
    """Anomalous tankers within the currently-elevated/excluded corridor set
    -- filtered the same way geo.at_risk_tanker_ids() is (decision #8), so a
    signal's geo block only ever carries dark markers relevant to it."""

    by_corridor = {t["id"]: t["corridor_id"] for t in list_tankers()}
    return sorted(
        tid for tid in _anomalous_ids() if by_corridor.get(tid) in elevated_corridors
    )


def dark_tanker_count(corridor: str) -> int:
    """Anomalous tankers in one specific corridor, independent of any
    elevated-threshold concept -- Watch scores a signal's corridor directly
    and never computes an elevated set (decision #9). An unrecognized
    corridor returns 0 rather than raising, matching at_risk_tanker_ids()'s
    'no geometry to fail on' tolerance for bad input."""

    by_corridor = {t["id"]: t["corridor_id"] for t in list_tankers()}
    return sum(1 for tid in _anomalous_ids() if by_corridor.get(tid) == corridor)
```

### 5.2 `backend/agents/geo.py` — one new import, one line

```python
from backend.agents.anomaly import dark_tanker_ids as _dark_tanker_ids
```

```python
    return Geo(
        at_risk_tanker_ids=at_risk_tanker_ids(elevated_corridors),
        dark_tanker_ids=_dark_tanker_ids(elevated_corridors),   # was: []
        affected_refinery_ids=affected_refineries,
    )
```

No other change to `build_geo()` — `elevated_corridors` is already the
parameter `cascade.py` passes in (the same `excluded` set used for
`at_risk_tanker_ids`/`affected_by()`), so no new plumbing is needed there.

### 5.3 `backend/agents/watch.py` — dark-tanker line in the prompt

```python
from backend.agents.anomaly import dark_tanker_count
```

```python
_PROMPT_TEMPLATE = """You are a corridor risk analyst. Score how much the \
following headline raises disruption risk for the "{corridor}" oil transit \
corridor, from 0 (no added risk) to 100 (severe, imminent disruption).

Headline: {headline}

Context from prior reporting on this corridor:
{context}
{dark_ship_line}
Respond with a JSON object only: {{"score": <0-100 number>, "reason": \
"<one sentence>"}}"""


def _build_prompt(
    corridor: str, headline: str, snippets: list[Snippet], dark_count: int
) -> str:
    context = "\n".join(f"- ({s.date}, {s.source}) {s.text}" for s in snippets)
    dark_ship_line = (
        f"\n{dark_count} tanker(s) near this corridor are currently flagged by AIS "
        "anomaly detection as behaving suspiciously (transponder gap and/or "
        "off-course deviation) -- weigh this as one more grounded signal, not "
        "a deciding factor on its own.\n"
        if dark_count > 0
        else ""
    )
    return _PROMPT_TEMPLATE.format(
        corridor=corridor, headline=headline, context=context,
        dark_ship_line=dark_ship_line,
    )
```

`_score_with_llm` threads `dark_count` through and folds it into the cache
key (decision #11):

```python
def _score_with_llm(
    corridor: str, headline: str, snippets: list[Snippet], dark_count: int
) -> float:
    prompt = _build_prompt(corridor, headline, snippets, dark_count)
    cache_key = (
        f"{corridor}|{headline.strip().lower()}|"
        f"{','.join(sorted(s.id for s in snippets))}|dark={dark_count}"
    )
    ...  # unchanged below this line
```

`run_watch()` computes `dark_count` once and passes it through:

```python
    dark_count = dark_tanker_count(corridor)
    try:
        score = _score_with_llm(corridor, headline, snippets, dark_count)
    except LLMUnavailable as exc:
        ...  # unchanged
```

### 5.4 `backend/agents/stubs.py` — matching offline-path bump

```python
from backend.agents.anomaly import dark_tanker_count

# Per flagged tanker in the signal's corridor -- same rough scale as
# _ESCALATION_WORDS (15-30), deliberately smaller since a dark-ship signal
# corroborates a headline, it isn't a headline-level escalation word itself
# (SPEC.md Phase 7 decision #12).
_DARK_TANKER_BUMP = 10.0


def run_watch_stub(signal: dict) -> WatchAgentOutput:
    corridor = signal["corridor"]
    severity = float(signal.get("severity", 0.4))
    headline = str(signal.get("headline", "")).lower()

    bump = sum(w for kw, w in _ESCALATION_WORDS.items() if kw in headline)
    dark_bump = _DARK_TANKER_BUMP * dark_tanker_count(corridor)
    score = _clamp(severity * 100 + bump + dark_bump, 0.0, 100.0)
    # ...unchanged below (source_ids/band/entry construction)
```

Update the module docstring's "Everything here is pure arithmetic on the
injected signal" line — it gains one real (if trivially cheap, no-network)
dependency for the first time; still fully deterministic, still no live call.

### 5.5 `requirements.txt`

```
# ---- Dev B (Phase 7): dark-ship anomaly detector (SPEC.md Phase 7, F18) ----
scikit-learn>=1.5     # IsolationForest over AIS features
```

`shapely` is **not** added (decision #3) — PLAN.md's original "New deps:
scikit-learn" line for this phase turns out to be exactly right.

## 6 · Test updates

- **`tests/test_anomaly.py`** (new) —
  - `dark_tanker_ids({"hormuz"}) == ["hormuz_02", "hormuz_03", "hormuz_04"]`
    (exact match, not just "contains" — the whole point of §4's tuned
    constants).
  - `dark_tanker_ids({"suez_cape"}) == []`, same for `atlantic`/`malacca` —
    a clearly normal transit is never flagged (PLAN.md's own acceptance
    line).
  - `dark_tanker_ids(set()) == []`; `dark_tanker_ids({"hormuz", "malacca"})`
    unions correctly (still just the 3 Hormuz ids).
  - `dark_tanker_count("hormuz") == 3`; `dark_tanker_count("suez_cape") == 0`;
    `dark_tanker_count("not_a_real_corridor") == 0` (no raise).
  - `_anomalous_ids()` (or `dark_tanker_ids`/`dark_tanker_count` calls in
    sequence) is byte-identical across repeated calls in the same process —
    the determinism PLAN.md's acceptance criteria names explicitly.
  - A direct `_features(hormuz_01_record) == (3.0, 0.0, 0.0, 0.0)` /
    `_features(hormuz_02_record) == (12.0, 95.0, 3.43, 85.5)` pair of
    assertions, pinning §4's table so a future edit to the synthetic data
    can't silently drift without a test noticing.
- **`tests/test_geo.py`** —
  - `test_build_geo_hormuz_matches_worked_example` updates its
    `dark_tanker_ids` assertion from `[]` to
    `["hormuz_02", "hormuz_03", "hormuz_04"]`.
  - `test_build_geo_dark_tanker_ids_always_empty` (Phase 6's "detector
    doesn't exist yet" placeholder test) is deleted and replaced with a test
    asserting `build_geo(session, {"hormuz"})` carries the 3 dark ids while
    `build_geo(session, {"suez_cape", "atlantic"})` carries none.
- **`tests/test_watch.py`** — add a case monkeypatching `complete_json` to
  capture the prompt it was called with (via a closure/list, matching this
  file's existing `_complete`-capturing style in
  `test_run_watch_falls_through_model_tiers`), asserting the dark-tanker
  context line appears in the built prompt for `corridor="hormuz"` and is
  absent for `corridor="malacca"`. Existing tests need no changes — none of
  them assert on `cache_key` or the prompt's exact text, and the mocked
  `complete_json` return value drives `entry.score` directly regardless of
  what was in the prompt.
- **`tests/test_api.py`** — no change needed; its existing stub-comparison
  assertion (line ~131) calls `run_watch_stub()` itself rather than hardcoding
  a score number, so it stays correct once the stub gains the dark-ship bump.

## 7 · Documentation updates (same change, per the contract-change protocol)

- **`backend/agents/anomaly.py`** — new module, docstring per §5.1.
- **`PROJECT_GUIDE.md`** §5A/§10E/status-board — flip F18's row from
  "PLAN.md Phase 7" (planned) to shipped; note the self-referential
  path-deviation feature choice so a reader comparing against the PRD's
  literal "distance off the corridor line" phrasing isn't confused (decision
  #3's correction, restated briefly).
- **`PLAN.md`** — flip Phase 7's status once merged; link back to this
  section for the feature-engineering correction and the tuned
  `contamination`/`random_state` constants so Phase 9 (if it ever touches
  Watch's prompt again) doesn't have to re-derive them.

## 8 · Acceptance criteria

1. `python -m pytest` fully green, including every new/updated test in §6.
2. `dark_tanker_ids({"hormuz"})` returns exactly `["hormuz_02", "hormuz_03",
   "hormuz_04"]`; a clearly normal corridor's transit (any of the other 13
   tankers) is never flagged — PLAN.md's own acceptance wording, satisfied
   exactly, not approximately.
3. Two calls to `dark_tanker_ids`/`dark_tanker_count` in the same process
   return byte-identical results (no run-to-run drift) — the `lru_cache` plus
   fixed `random_state` makes this true by construction, but the test in §6
   asserts it directly per PLAN.md's own acceptance line.
4. A `POST /signal` on the `hormuz` corridor produces a `RiskState.geo`
   with `dark_tanker_ids == ["hormuz_02", "hormuz_03", "hormuz_04"]`; a
   signal on any other corridor's `geo.dark_tanker_ids` is `[]`.
5. Watch's real path (`USE_REAL_AGENTS=1` + a key) includes the dark-tanker
   context line in its prompt for `hormuz`, omits it for corridors with zero
   dark tankers; Watch's offline stub path visibly scores a Hormuz signal
   higher than an otherwise-identical non-Hormuz signal, attributable to the
   dark-tanker bump alone (isolate by comparing against the pre-Phase-7
   stub score with `_DARK_TANKER_BUMP` zeroed out in a test double, or by
   asserting the score delta equals `3 * _DARK_TANKER_BUMP` when no
   escalation words are present).
6. No behavior change for any signal/corridor with zero dark tankers —
   Phase 7 is additive; `suez_cape`/`atlantic`/`malacca` scenarios score
   identically to their pre-Phase-7 values.

## 9 · Explicitly deferred (not decided here — flagged for the named phase)

- **Frontend rendering of dark-tanker markers on the map** — Segment 2,
  Chunk F (PLAN.md), gated on this phase.
- **A rule-based (z-score) detector path** — deliberately not built (decision
  #7); revisit only if a future phase introduces a genuine runtime failure
  mode for anomaly detection that doesn't exist today.
- **Refining the synthetic dark-tanker tracks' geographic plausibility
  against real AIS spoofing/dark-ship case studies** — today's §3 values are
  tuned for clean feature separation and a good demo story, not modeled on a
  specific real incident; revisit only if a judge/domain expert flags the
  geography as implausible.
- **A trained (labelled) classifier as an alternative to `IsolationForest`**
  — explicitly rejected by PLAN.md/PROJECT_GUIDE.md §10E's own reasoning
  (no "this ship was suspicious" labelled dataset exists); not revisited
  here.

---

# SPEC — Segment 1, Phase 8: Backtest / validation module (F14)

> Scope: exactly [PLAN.md](.claude/docs/PLAN.md)'s Phase 8. Adds `backend/agents/backtest.py`
> — a pure, DB-free replay of one curated historical shock through the real
> Watch agent (`run_watch`, Phase 4), chronologically, with a strict `as_of`
> cutoff so no future snippet leaks into a past headline's score — and
> `GET /backtest/{id}`, which returns the score timeline, an illustrative
> Brent price timeline, and the lead time between them. No contract change —
> `Validation` already exists (Phase 1); this phase is the first to compute
> real values for it, but (per this section's own decision #5) never writes
> them onto the live `RiskState`. Depends on Phase 4 (landed, real `run_watch`
> — replaying against the stub would be meaningless per PLAN.md's own
> acceptance line).

## 1 · Decisions made (interview log)

| # | Decision | Why |
|---|---|---|
| 1 | **Historical case: the Red Sea / Houthi shipping crisis, Nov 2023 – Mar 2024**, scored on the `suez_cape` corridor | User call. `watch_corpus.json` already carries four real, dated `suez_cape` events across this exact window, and it's the same crisis Phase 2 already cited to justify `suez_cape.war_risk_pct = 0.02` (SPEC.md Phase 2 decision #3) — reusing it keeps the whole v1.3 narrative internally consistent instead of introducing an unrelated third historical thread |
| 2 | **Three more real, dated `suez_cape` headlines added to `watch_corpus.json`** (Dec 3 2023 triple-vessel attack claim, Dec 18 2023 BP's Red Sea transit pause, Jan 12 2024 US/UK strikes on Houthi sites) | The four pre-existing entries span 3.5 months with one gap of nearly two months (Nov 19 → Jan 15) — too sparse for a readable timeline chart. All three additions are real, well-documented public events (paraphrased, not verbatim), and adding them to the shared corpus (not a backtest-only side file) also densifies live `suez_cape` RAG retrieval for the ordinary demo path, not just the backtest |
| 3 | **`retrieve()`/`run_watch()` gain an optional `as_of: str \| None` cutoff**, implemented as an over-fetch-then-Python-filter (query up to `collection.count()` results, then keep only `date <= as_of`, then slice to `k`) rather than a Chroma `where` date-range operator | User call on the *approach* (add a cutoff vs. a separate never-shared corpus vs. accept the leak); the over-fetch implementation is my call — it avoids depending on Chroma's string-comparison semantics for a metadata field across versions, and the corpus is small enough (~35 rows) that fetching the full corridor subset is cheap. `as_of` defaults to `None` everywhere in the live cascade (`cascade.py` never passes it), so `POST /signal` is byte-identical to pre-Phase-8 behavior — only `backtest.py` ever sets it |
| 4 | **`run_watch(signal, as_of=...)` forces `dark_count = 0`** whenever `as_of` is set, instead of calling `dark_tanker_count(corridor)` | The anomaly detector's AIS data (Phase 6/7) is one fixed, present-day (`2026-01-15`) synthetic window — attaching "3 tankers are currently flagged dark" to a headline replayed from November 2023 would be nonsensical, not just imprecise. `run_watch_stub` (the no-key/flag-off fallback) is left unchanged — it doesn't accept `as_of` at all, since a stub-degraded backtest is already explicitly non-representative per PLAN.md's own framing, and `dark_tanker_count("suez_cape")` is `0` in today's curated set regardless |
| 5 | **`GET /backtest/{id}` never writes to `RiskState.validation`** — no `StateStore.merge_validation()`, no WS push. Fully standalone: computes (or reads from an in-process cache) and returns | User call. A GET with a side effect that broadcasts a full-state WS update to every connected client (including other judges' sessions) is a REST smell with no precedent elsewhere in this codebase, and the demo script's own flow treats "open the backtest" (beat 2) as an exploratory step decoupled from "inject the signal" (beat 3). **Consequence:** `RiskState.validation` stays permanently `None` in this codebase unless a future phase wires it differently — CLAUDE.md's "`validation` stays `None` until Phase 8" line needs correcting to "…stays `None`; Phase 8 adds `GET /backtest/{id}` as a fully decoupled read, never merged into `RiskState`" |
| 6 | **Brent series: hand-curated, illustrative, directionally-correct figures**, not sourced daily closes | User call. Matches the exact honesty framing already used for `war_risk_pct`/`detour_days` (SPEC.md Phase 1 decision #4) — this environment has no live financial-data feed to verify exact numbers against, so the series is built to be *directionally* right (Brent's known dip in late Nov 2023, climb through the Dec–Jan escalation, further rise after the March sinking) and is labeled `"illustrative... not audited market data"` everywhere it surfaces, never presented as precise |
| 7 | **Watch's alert threshold reuses `cascade.AFFECTED_THRESHOLD` (50.0)**, imported, not redefined | Same "one definition, not a fork" principle Phase 6 applied to `at_risk_tanker_ids`/`affected_refinery_ids` sharing one corridor-set definition — "crossed alert" should mean the same thing here as it does for the live cascade's own reroute-exclusion logic, not a second, drifting threshold |
| 8 | **Brent "spike" = first point ≥ 5% above the mean of a hand-picked pre-crisis baseline window** (`brent_baseline_start`/`brent_baseline_end` in the case file), not a `+Xσ` statistical threshold despite PLAN.md's literal wording | Correction of PLAN.md's phrasing: a standard-deviation threshold needs enough baseline density to be a meaningful statistic, which a small, sparse, hand-curated series (11 points total) can't honestly support — computing a "σ" from 4 baseline points and treating it as if it means something would be false precision. A plain, clearly-labeled percentage-above-baseline test is simpler, equally explainable on stage, and doesn't pretend to be more rigorous than the underlying data is |
| 9 | **"Crossed" = first point, in chronological order, at or above the threshold** — computed independently for the score timeline and the price timeline, no smoothing or "must stay above" requirement | Both curated series (§3) are deliberately built to cross their own threshold exactly once, so the simplest possible definition already gives a clean, unambiguous single answer — no need for a more defensive definition the data doesn't require |
| 10 | **No graceful-degradation path if a curated case never crosses its own threshold** — `_first_crossing` raises (uncaught, surfaces as a 500) rather than returning `None`/`0` | Mirrors Phase 7 decision #7's reasoning: this is a pure function over static, committed, curated data with no runtime failure mode — a case that doesn't produce a clean crossing is a curation bug to catch in `tests/test_backtest.py`, not a runtime scenario to paper over with a fallback value that would misrepresent the panel |
| 11 | **`severity` is fixed at `0.0`** in every synthetic signal `backtest.py` builds for `run_watch()` | `run_watch()`'s real (LLM) path never reads `severity` at all — only `run_watch_stub` does. Fixing it at `0.0` keeps the stub-fallback path's score attributable purely to escalation-word matching (§3's worked example), not muddied by an arbitrary guessed severity value |
| 12 | **Backtest case data lives at `backend/agents/data/backtest/{id}.json`**, one file per case, headlines referencing `watch_corpus.json` ids rather than duplicating headline text | Deviates from PLAN.md's literal `backend/seed/backtest/` wording — same correction Phase 6 made for AIS data (decision #9 there): this is data a Python agent module reads directly, not a DB-seeded config table, so it belongs under `agents/data/` next to `watch_corpus.json`/`ais_sample.json`. Referencing corpus ids instead of copy-pasting headline text means the two files can never drift out of sync with each other |
| 13 | **Response bundles a contract-shaped `validation: {backtest_id, signal_lead_hours}` object** alongside the raw `score_timeline`/`price_timeline` arrays, even though (decision #5) it's never merged into `RiskState` | Mirrors `/geo/state`'s own pattern (SPEC.md Phase 6 §2.4) of bundling the contract-shaped block plus the raw supporting data a chart needs — gives Segment 2 a `Validation`-shaped value it can type against with no separate parsing, without pretending the endpoint mutates shared state |
| 14 | **No auth on `GET /backtest/{id}`** | Matches `/geo/state`/`/public/status` precedent — read-only, non-sensitive, static/curated data, same bar as those two |
| 15 | **Unknown `{id}` → `404`** via a dedicated `BacktestCaseNotFound` exception, kept distinct from `_first_crossing`'s uncaught "curation bug" error (which should surface as a `500`, not be mistaken for "not found") | Matches `routes.py`'s existing `HTTPException(status_code=404, ...)` precedent (`routes.py:283`) for "no ranked reroute for supplier X". Splitting the two exception types stops a genuine implementation bug from being silently reported to the client as an ordinary 404 |
| 16 | **`run_backtest(case_id)` is `lru_cache`'d** | Mirrors `anomaly.py`'s fit-once and `geo.py`'s load-once pattern — the curated case data never changes at runtime, so there's no reason a second `GET /backtest/{id}` should re-issue up to 7 Watch calls (even cheaply, via the on-disk LLM cache) when an in-process cache avoids the round-trip entirely |

## 2 · Backend changes

### 2.1 `backend/agents/rag.py` — `as_of` cutoff on `retrieve()`

```python
def retrieve(
    corridor: str,
    query: str,
    k: int = 5,
    *,
    as_of: str | None = None,
    vector_store_path: str | None = None,
) -> list[Snippet]:
    """Top-k snippets for ``corridor``, ranked by similarity to ``query``.

    ``as_of`` (SPEC.md Phase 8, decision #3): an ISO date string. When set,
    only snippets dated on or before it are eligible -- stops a historical
    backtest replay from retrieving snippets that postdate the headline being
    scored (the future-info leak PLAN.md's own Phase 4 architecture note
    flagged). ``None`` (the default -- every live POST /signal call) applies
    no cutoff; behavior is byte-identical to pre-Phase-8.

    Implemented as an over-fetch + Python-side filter, not a Chroma `where`
    date-range operator, so this doesn't depend on Chroma's string-comparison
    semantics for a metadata field. Returns ``[]`` if the corridor has no
    (eligible) snippets -- callers still treat that as a fallback trigger.
    """

    collection = _client(vector_store_path).get_or_create_collection(_COLLECTION_NAME)
    if collection.count() == 0:
        return []
    fetch_n = collection.count() if as_of else k
    result = collection.query(query_texts=[query], n_results=fetch_n, where={"corridor": corridor})
    ids = result["ids"][0] if result["ids"] else []
    docs = result["documents"][0] if result["documents"] else []
    metas = result["metadatas"][0] if result["metadatas"] else []
    snippets = [
        Snippet(id=i, corridor=m["corridor"], date=m["date"], source=m["source"], text=d)
        for i, d, m in zip(ids, docs, metas)
    ]
    if as_of:
        snippets = [s for s in snippets if s.date <= as_of]
    return snippets[:k]
```

### 2.2 `backend/agents/watch.py` — thread `as_of` through, suppress dark-ship context

```python
def run_watch(signal: dict, *, as_of: str | None = None) -> WatchAgentOutput:
    """Score the affected corridor from an injected signal.

    ``as_of`` (SPEC.md Phase 8): historical-replay mode for backtest.py. When
    set: (a) retrieve() only sees snippets dated on/before it, and (b) the
    dark-ship anomaly context line is suppressed -- the anomaly detector's
    AIS window is a fixed present-day snapshot (Phase 6/7), meaningless
    attached to a 2023 headline. ``None`` (default) is unchanged live
    cascade behavior; cascade.py never passes as_of.
    """

    settings = get_settings()
    corridor = signal["corridor"]

    if not settings.use_real_agents or not settings.groq_api_key:
        return run_watch_stub(signal)

    if corridor not in KNOWN_CORRIDORS:
        logger.warning("Watch: unknown corridor %r, falling back to stub", corridor)
        return run_watch_stub(signal)

    headline = str(signal.get("headline", ""))
    snippets = retrieve(corridor, headline, k=_RETRIEVE_K, as_of=as_of)
    if not snippets:
        logger.warning("Watch: no snippets retrieved for %r, falling back to stub", corridor)
        return run_watch_stub(signal)

    dark_count = 0 if as_of is not None else dark_tanker_count(corridor)
    try:
        score = _score_with_llm(corridor, headline, snippets, dark_count, as_of)
    except LLMUnavailable as exc:
        logger.warning("Watch: LLM unavailable (%s), falling back to stub", exc)
        return run_watch_stub(signal)

    band = _band_from_retrieval(snippets)
    entry = CorridorRiskEntry(
        score=round(score, 1),
        confidence=_confidence_for(band),
        band=band,
        source_ids=[s.id for s in snippets],
    )
    return WatchAgentOutput(corridor_risk={corridor: entry})
```

`_score_with_llm` gains the same parameter, folded into the cache key (same
pattern as Phase 7's `dark=` suffix):

```python
def _score_with_llm(
    corridor: str, headline: str, snippets: list[Snippet], dark_count: int, as_of: str | None
) -> float:
    prompt = _build_prompt(corridor, headline, snippets, dark_count)
    cache_key = (
        f"{corridor}|{headline.strip().lower()}|"
        f"{','.join(sorted(s.id for s in snippets))}|dark={dark_count}|as_of={as_of or 'live'}"
    )
    ...  # unchanged below this line
```

### 2.3 `backend/agents/backtest.py` (new file)

```python
"""Backtest / validation module (F14) -- replays one curated historical shock
through the real Watch agent, chronologically, with a strict as_of cutoff so
no future snippet leaks into the past (SPEC.md Phase 8 decision #3), and
measures how long before a hand-curated, illustrative Brent price series
crossed a notable-move threshold Watch's own score crossed its alert
threshold first.

Framed explicitly, everywhere this surfaces, as one illustrative historical
case -- never a validated statistical accuracy claim (PRD's own honesty
guard, repeated in the API response's own "note" field).

Pure/DB-free, like anomaly.py -- no runtime failure mode to degrade from, so
a curated case that never crosses its own threshold is a bug to catch in
tests, not something this module papers over (decision #10).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Callable, TypeVar

from backend.agents.rag import load_corpus
from backend.agents.watch import run_watch
from backend.cascade import AFFECTED_THRESHOLD
from backend.schemas import Validation

_DATA_DIR = Path(__file__).parent / "data" / "backtest"
_BRENT_SPIKE_PCT = 5.0  # decision #8 -- % above the pre-crisis baseline mean

T = TypeVar("T")


class BacktestCaseNotFound(Exception):
    """No curated data file for this case id -- a real 404 (decision #15),
    distinct from _first_crossing's "curation bug" error below."""


@dataclass(frozen=True)
class ScorePoint:
    ts: str
    headline_id: str
    score: float
    source_ids: list[str]


@dataclass(frozen=True)
class PricePoint:
    ts: str
    price_usd_bbl: float


@dataclass(frozen=True)
class BacktestResult:
    validation: Validation
    corridor: str
    label: str
    watch_alert_threshold: float
    watch_crossed_at: str
    brent_spike_threshold_usd: float
    brent_crossed_at: str
    score_timeline: list[ScorePoint]
    price_timeline: list[PricePoint]


def _load_case(case_id: str) -> dict:
    path = _DATA_DIR / f"{case_id}.json"
    if not path.exists():
        raise BacktestCaseNotFound(f"no curated backtest case {case_id!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def _score_timeline(case: dict) -> list[ScorePoint]:
    corpus = {row["id"]: row for row in load_corpus()}
    points = []
    for h in case["headlines"]:
        row = corpus[h["source_id"]]
        as_of = h["ts"][:10]  # date part -- matches Snippet.date's "YYYY-MM-DD" format
        signal = {"corridor": case["corridor"], "headline": row["text"], "severity": 0.0}
        out = run_watch(signal, as_of=as_of)
        entry = out.corridor_risk[case["corridor"]]
        points.append(
            ScorePoint(ts=h["ts"], headline_id=h["source_id"], score=entry.score, source_ids=entry.source_ids)
        )
    return points


def _price_timeline(case: dict) -> list[PricePoint]:
    return [PricePoint(ts=p["ts"], price_usd_bbl=p["price_usd_bbl"]) for p in case["brent_series"]]


def _baseline_mean(case: dict) -> float:
    start, end = case["brent_baseline_start"], case["brent_baseline_end"]
    baseline = [p["price_usd_bbl"] for p in case["brent_series"] if start <= p["ts"][:10] <= end]
    if not baseline:
        raise ValueError(f"backtest case {case['id']!r}: empty baseline window")
    return sum(baseline) / len(baseline)


def _first_crossing(points: list[T], value_fn: Callable[[T], float], threshold: float) -> T:
    for p in points:
        if value_fn(p) >= threshold:
            return p
    raise ValueError(
        "curated backtest data never crosses its own threshold -- fix the "
        "case data, don't silently degrade (SPEC.md Phase 8 decision #10)"
    )


@lru_cache(maxsize=8)
def run_backtest(case_id: str) -> BacktestResult:
    case = _load_case(case_id)
    score_timeline = _score_timeline(case)
    price_timeline = _price_timeline(case)

    watch_point = _first_crossing(score_timeline, lambda p: p.score, AFFECTED_THRESHOLD)
    spike_threshold = round(_baseline_mean(case) * (1 + _BRENT_SPIKE_PCT / 100.0), 2)
    price_point = _first_crossing(price_timeline, lambda p: p.price_usd_bbl, spike_threshold)

    watch_dt = datetime.fromisoformat(watch_point.ts.replace("Z", "+00:00"))
    price_dt = datetime.fromisoformat(price_point.ts.replace("Z", "+00:00"))
    lead_hours = round((price_dt - watch_dt).total_seconds() / 3600.0, 1)

    return BacktestResult(
        validation=Validation(backtest_id=case_id, signal_lead_hours=lead_hours),
        corridor=case["corridor"],
        label=case["label"],
        watch_alert_threshold=AFFECTED_THRESHOLD,
        watch_crossed_at=watch_point.ts,
        brent_spike_threshold_usd=spike_threshold,
        brent_crossed_at=price_point.ts,
        score_timeline=score_timeline,
        price_timeline=price_timeline,
    )
```

### 2.4 `backend/api/routes.py` — `GET /backtest/{backtest_id}`

No auth (decision #14); 404 on an unknown id, distinct from an uncaught
curation-bug error (decision #15):

```python
from dataclasses import asdict

from backend.agents.backtest import BacktestCaseNotFound, run_backtest


@router.get("/backtest/{backtest_id}")
def get_backtest(backtest_id: str) -> dict:
    """One curated historical case (F14): Watch's real score timeline vs. an
    illustrative Brent price timeline, and the lead time between them. Never
    touches RiskState (decision #5) -- a side-effect-free read, unlike every
    cascade-adjacent endpoint elsewhere in this file. Framed explicitly as
    one illustrative case, never a validated accuracy metric (PRD's honesty
    guard) -- see the response's own "note" field.
    """

    try:
        result = run_backtest(backtest_id)
    except BacktestCaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "validation": result.validation.model_dump(mode="json"),
        "corridor": result.corridor,
        "label": result.label,
        "watch_alert_threshold": result.watch_alert_threshold,
        "watch_crossed_at": result.watch_crossed_at,
        "brent_spike_threshold_usd": result.brent_spike_threshold_usd,
        "brent_crossed_at": result.brent_crossed_at,
        "score_timeline": [asdict(p) for p in result.score_timeline],
        "price_timeline": [asdict(p) for p in result.price_timeline],
        "note": (
            "Illustrative single historical case; Brent series is "
            "hand-curated/approximate, not audited market data. Not a "
            "validated statistical accuracy claim."
        ),
    }
```

`_first_crossing`'s `ValueError` (a curation bug in the committed data, not a
client error) is deliberately **not** caught here — it propagates to a `500`,
distinct from `BacktestCaseNotFound`'s `404` (decision #15).

## 3 · Data changes + worked example

### 3.1 `backend/agents/data/watch_corpus.json` — three new `suez_cape` entries

```jsonc
{
  "id": "news_suez_2023_dec_triple_attack",
  "corridor": "suez_cape",
  "date": "2023-12-03",
  "source": "wire reporting",
  "text": "Houthi forces claimed a missile and drone attack on three commercial vessels in the Red Sea in a single day, marking a sharp escalation from earlier isolated incidents."
},
{
  "id": "news_suez_2023_bp_pause",
  "corridor": "suez_cape",
  "date": "2023-12-18",
  "source": "wire reporting",
  "text": "BP announced a temporary pause of all Red Sea oil transits following renewed Houthi attacks, becoming the first major oil company to publicly halt transits through the corridor."
},
{
  "id": "news_suez_2024_us_uk_strikes",
  "corridor": "suez_cape",
  "date": "2024-01-12",
  "source": "wire reporting",
  "text": "US and UK forces conducted air strikes against Houthi missile and radar sites in Yemen in direct response to the escalating shipping attacks."
}
```

(Paraphrased from real, publicly reported events — decision #2 — not
verbatim quotes, matching every other corpus row's style.)

### 3.2 `backend/agents/data/backtest/red_sea_2023.json` (new)

```jsonc
{
  "id": "red_sea_2023",
  "corridor": "suez_cape",
  "label": "Red Sea / Houthi shipping crisis (Nov 2023 – Mar 2024)",
  "brent_baseline_start": "2023-11-01",
  "brent_baseline_end": "2023-11-18",
  "headlines": [
    { "ts": "2023-11-19T00:00:00Z", "source_id": "news_suez_2023_houthi" },
    { "ts": "2023-12-03T00:00:00Z", "source_id": "news_suez_2023_dec_triple_attack" },
    { "ts": "2023-12-18T00:00:00Z", "source_id": "news_suez_2023_bp_pause" },
    { "ts": "2024-01-12T00:00:00Z", "source_id": "news_suez_2024_us_uk_strikes" },
    { "ts": "2024-01-15T00:00:00Z", "source_id": "news_suez_2024_reroute" },
    { "ts": "2024-02-02T00:00:00Z", "source_id": "sanc_suez_2024_insurance" },
    { "ts": "2024-03-06T00:00:00Z", "source_id": "news_suez_2024_strike" }
  ],
  "brent_series": [
    { "ts": "2023-11-01T00:00:00Z", "price_usd_bbl": 80.40 },
    { "ts": "2023-11-08T00:00:00Z", "price_usd_bbl": 80.70 },
    { "ts": "2023-11-15T00:00:00Z", "price_usd_bbl": 80.20 },
    { "ts": "2023-11-18T00:00:00Z", "price_usd_bbl": 80.60 },
    { "ts": "2023-11-19T00:00:00Z", "price_usd_bbl": 79.30 },
    { "ts": "2023-12-03T00:00:00Z", "price_usd_bbl": 79.80 },
    { "ts": "2023-12-18T00:00:00Z", "price_usd_bbl": 81.20 },
    { "ts": "2024-01-12T00:00:00Z", "price_usd_bbl": 82.90 },
    { "ts": "2024-01-15T00:00:00Z", "price_usd_bbl": 83.40 },
    { "ts": "2024-02-02T00:00:00Z", "price_usd_bbl": 85.10 },
    { "ts": "2024-03-06T00:00:00Z", "price_usd_bbl": 87.60 }
  ]
}
```

Every timestamp is a synthetic fixed `00:00:00Z` (decision #11's spirit —
day-level source data, no invented sub-daily precision), mirroring Phase 6's
committed-synthetic-window pattern for AIS data. `signal_lead_hours` is
therefore always a multiple of 24 — an honest consequence of daily-only
input granularity, not hidden or rounded away.

### 3.3 Worked example — stub-fallback path (deterministic, hand-verified, no API key needed)

`tests/test_backtest.py` runs with `USE_REAL_AGENTS=0` (the default), so
`run_watch()` degrades to `run_watch_stub()` for every headline. With
`severity=0.0` fixed (decision #11) and `dark_tanker_count("suez_cape") == 0`
regardless, each stub score is pure `_ESCALATION_WORDS` keyword-bump
arithmetic — hand-computed here, not asserted blindly:

| headline (`source_id`) | date | matched keywords | stub score |
|---|---|---|---|
| `news_suez_2023_houthi` | 2023-11-19 | none | 0.0 |
| `news_suez_2023_dec_triple_attack` | 2023-12-03 | missile(26) + attack(30) | **56.0** ← first ≥ 50 |
| `news_suez_2023_bp_pause` | 2023-12-18 | attack(30) | 30.0 |
| `news_suez_2024_us_uk_strikes` | 2024-01-12 | strike(22) + missile(26) + attack(30) | 78.0 |
| `news_suez_2024_reroute` | 2024-01-15 | attack(30) | 30.0 |
| `sanc_suez_2024_insurance` | 2024-02-02 | none | 0.0 |
| `news_suez_2024_strike` | 2024-03-06 | missile(26) + strike(22) | 48.0 |

First crossing of `AFFECTED_THRESHOLD` (50.0): **2023-12-03T00:00:00Z**
(score 56.0).

Brent baseline mean (4 points, Nov 1–18): `(80.40+80.70+80.20+80.60)/4 =
80.475`. Spike threshold: `80.475 × 1.05 = 84.4988` → rounds to **84.50**.
Walking `brent_series` in order, the first point ≥ 84.50 is
**2024-02-02T00:00:00Z** (85.10).

`signal_lead_hours = (2024-02-02T00:00:00Z − 2023-12-03T00:00:00Z) = 61 days
= 1464.0 hours`. This exact figure is what `tests/test_backtest.py` pins
(§5) — it's fully deterministic and CI-computable with zero API key, unlike
the real-LLM-path number below.

**Explicitly not verified here** (unlike Phase 7's fully local, offline-
verifiable `IsolationForest` numbers): the *real* demo path calls the actual
Groq LLM for each of the 7 headlines. A contextually-reasoning LLM would
plausibly score the very first headline (`news_suez_2023_houthi`,
2023-11-19 — "Houthi forces began targeting commercial vessels") well above
the stub's `0.0`, likely crossing the alert threshold earlier than
2023-12-03 — which would only *widen* the lead-time gap, not close it,
since Brent's own crossing point is independent of Watch's exact number.
The qualitative story (headline-driven scoring reacts near-instantly; a
physical commodity market takes weeks to fully price in a slow-building
supply risk) is robust to exactly which headline first crosses. The
implementer must still run this once with a real `GROQ_API_KEY`, commit the
resulting `.llm_cache/` entries (Phase 10's own "commit the LLM response
cache" step), and confirm both curated series still cross exactly once each
— adjusting `_BRENT_SPIKE_PCT` or `brent_series` only if the real numbers
ever produced a degenerate (zero or negative) lead time, which is not
expected given the margin above.

## 4 · API surface changes

New: `GET /backtest/{backtest_id}`, unauthenticated, no query params.
`200` with the shape in §2.4 for a known id; `404` for an unknown one. Never
mutates `RiskState` — a fresh `GET /state` immediately after still shows
`validation: null` (decision #5). No change to any existing endpoint's
signature or response shape. `run_watch()`'s new `as_of` keyword argument is
additive and defaults to `None` — `cascade.py`'s existing `run_watch(signal)`
call needs no change.

## 5 · Test updates

- **`tests/test_rag.py`** — `retrieve(..., as_of=<date>)` excludes snippets
  dated after the cutoff, includes ones on/before it;
  `retrieve(..., as_of=None)` (and the existing calls with no `as_of` at
  all) behave exactly as before Phase 8 — a regression check that the
  default is truly a no-op.
- **`tests/test_watch.py`** — `run_watch(signal, as_of="2023-12-01")` for
  `corridor="hormuz"` (which normally carries the 3-dark-tanker case) omits
  the dark-ship prompt line and the resulting cache key contains
  `dark=0|as_of=2023-12-01`, even though `dark_tanker_count("hormuz")` is
  nonzero — proves the suppression is unconditional on `as_of` being set,
  not accidentally still reading live AIS state.
- **`tests/test_backtest.py`** (new):
  - `test_run_backtest_stub_fallback_matches_worked_example` — with
    `USE_REAL_AGENTS=0` (no env override needed, matches the default),
    asserts `signal_lead_hours == 1464.0`, `watch_crossed_at ==
    "2023-12-03T00:00:00Z"`, `brent_crossed_at == "2024-02-02T00:00:00Z"`,
    `brent_spike_threshold_usd == 84.5` — pins §3.3's table so a future edit
    to the curated case can't silently drift without a test noticing (same
    spirit as Phase 7's `_features()`-pinning test).
  - `test_run_backtest_unknown_case_raises_not_found` —
    `run_backtest("not_a_real_case")` raises `BacktestCaseNotFound`.
  - `test_score_timeline_passes_each_headlines_own_date_as_of` — monkeypatch
    `backend.agents.backtest.run_watch` to capture every `as_of` it's called
    with; assert each equals that headline's own date, never `None` and
    never a later headline's date.
  - `test_run_backtest_is_cached` — monkeypatch `run_watch` to count calls;
    two `run_backtest("red_sea_2023")` calls in the same process only
    invoke it 7 times total, not 14 (`lru_cache`, decision #16).
  - `test_price_timeline_matches_case_data` — `price_timeline` length and
    values match `red_sea_2023.json`'s `brent_series` exactly.
  - `test_first_crossing_raises_if_never_crossed` — a small synthetic
    points list with every value below threshold raises `ValueError`
    (decision #10), independent of the real curated case.
- **`tests/test_api.py`**:
  - `GET /backtest/red_sea_2023` → `200`; `validation.signal_lead_hours >
    0`; `len(score_timeline) == 7`; `len(price_timeline) == 11`; `note` is
    present and non-empty.
  - `GET /backtest/not_a_real_case` → `404`.
  - A `GET /state` immediately after the above two calls still shows
    `validation: null` — the standalone-ness in decision #5 is a real
    regression check, not just a design note.
- No changes needed to `tests/test_contract.py` (no contract change —
  `Validation`'s present/absent round-trip coverage already landed in
  Phase 1), `test_recommend.py`, `test_predict.py`, `test_graph.py`,
  `test_geo.py`, `test_anomaly.py`, `test_advise.py`, `test_auth.py`,
  `test_llm.py`, `test_ais.py`.

## 6 · Documentation updates (same change, per the contract-change protocol)

- **`backend/agents/backtest.py`** — new module, docstring per §2.3.
- **`CLAUDE.md`** — correct "`validation` stays `None` until Phase 8" to
  reflect decision #5: `validation` stays `None` in `RiskState`
  permanently; Phase 8 adds `GET /backtest/{id}` as a fully decoupled read
  that computes real `Validation` values without ever merging them in.
- **`PROJECT_GUIDE.md`** — flip F14's status rows (§04 feature table, §05A/
  §10 backtest section, status board) to shipped; §18's demo script beat 2
  line ("our score crossed alert 34 hours before Brent spiked") should be
  corrected to reflect the actual order of magnitude once the real-LLM
  number is verified (§3.3's stub-path worked example already shows ~61
  days/1464 hours, not 34 hours — PLAN.md's "34 hours" was illustrative
  color text from the phase description, not a sourced figure); add
  `GET /backtest/{id}` to the endpoints table (§08).
- **`PLAN.md`** — flip Phase 8's status once merged; note decision #3 (the
  `as_of` cutoff) prominently, since any future change to `watch.py`'s
  prompt/scoring path must preserve it or silently reintroduce the
  future-info leak this phase exists to close.

## 7 · Acceptance criteria

1. `python -m pytest` fully green, including every new/updated test in §5.
2. `GET /backtest/red_sea_2023` returns `200` with a positive
   `signal_lead_hours`, a 7-point `score_timeline`, an 11-point
   `price_timeline`, and the honesty `note` field — PLAN.md's own
   acceptance line, satisfied with a real (not synthetic-for-tests-only)
   curated case.
3. `GET /backtest/{unknown id}` returns `404`.
4. `RiskState.validation` is unaffected by any number of `GET /backtest/...`
   calls — stays exactly what it was before (`None` on a fresh boot).
5. `POST /signal`'s live cascade is behaviorally unchanged — `retrieve()`
   and `run_watch()`'s new `as_of` parameter defaults to `None` everywhere
   `cascade.py` calls them, so every existing Watch test continues to pass
   unmodified.
6. The stub-fallback path's `signal_lead_hours` is exactly `1464.0` against
   the committed `red_sea_2023.json` — a real regression check pinned by
   `tests/test_backtest.py`, not merely "some positive number."
7. Framed, in the endpoint's own docstring and response body (`note`
   field), explicitly as one illustrative historical case — never a
   validated production accuracy metric (PRD's own honesty guard,
   PLAN.md's own acceptance line).
8. No new dependency added (`requirements.txt` unchanged) — everything this
   phase needs (`groq`, `chromadb`, stdlib `json`/`datetime`/`functools`)
   is already present from Phase 4.

## 8 · Explicitly deferred (not decided here — flagged for the named phase)

- **Frontend rendering of the backtest chart** (Watch-score-vs-Brent
  overlay, the lead-time callout number) — Segment 2, Chunk G (PLAN.md),
  gated on this phase.
- **A second curated historical case** — out of scope; PLAN.md §6 decision
  #5 says "pick one, don't build two," and this phase does exactly that.
- **Precisely sourced/verified daily Brent closes**, replacing the
  hand-curated illustrative series — only worth it if a judge/domain expert
  challenges the specific numbers; the response's own `note` field covers
  the gap honestly until then (same posture as Phase 6's hand-authored
  corridor GeoJSON).
- **A `+Xσ` statistical volatility threshold**, replacing the plain
  percentage-above-baseline test (decision #8's rejected alternative) —
  revisit only if a denser, genuinely-sourced daily-close dataset is ever
  substituted in, dense enough for a standard deviation to mean something.
- **Verifying the real-LLM-path `signal_lead_hours` number** and committing
  the corresponding `.llm_cache/` entries — implementation-time work,
  explicitly not done as part of writing this spec (no live `GROQ_API_KEY`
  available in this environment); see §3.3's caveat.
- **A time-scrubbing playback UI or a `?t=` query param** on
  `GET /backtest/{id}` — not needed; the endpoint returns full timelines
  and Segment 2 animates/charts client-side over the arrays, same posture
  as `/geo/state` (SPEC.md Phase 6 §8).

---

---

# SPEC — Segment 1, Phase 9: Alarm-language score + LLM conservation copy (F19, F7 slice)

> Scope: exactly [PLAN.md](.claude/docs/PLAN.md)'s Phase 9 — the two cheapest, lowest-
> priority v1.3 additions, P2/stretch, built only after Phases 1–8 (all
> landed). Two independent slices sharing this section because PLAN.md
> scopes them together: **F19**, a small TF-IDF + logistic-regression
> alarm-language classifier feeding one more labeled context line into
> Watch (real agent + offline stub alike), and a slice of **F7**, replacing
> `GET /public/status`'s static tip dictionary with LLM-generated,
> scenario-specific conservation copy behind the identical response shape.
> No contract changes — neither slice touches `RiskState`; `CorridorRiskEntry`
> gains no new field (decision #4 below) and `/public/status`'s response
> shape is byte-identical to today's. No new dependency —
> `scikit-learn` (Phase 7) and `backend/agents/llm.py` (Phase 4) already
> exist. Depends on Phase 4 (LLM client + Watch's prompt-injection pattern
> to extend) and, transitively, Phase 7 (established the
> prompt-context-line-not-composite-score wiring pattern this phase reuses
> for the second time).

## 1 · Decisions made (interview log)

| # | Decision | Why |
|---|---|---|
| 1 | **Alarm training data: a hand-curated, committed, general-tone corpus** — not a keyword lexicon, not a new pretrained-sentiment dependency | Matches Phase 7/8's "curated, deterministic, committed, cited" pattern rather than either extreme (a lexicon would just duplicate `stubs.py`'s existing `_ESCALATION_WORDS`; a new dependency contradicts PLAN.md's own "no new heavy dep" framing for this phase) |
| 2 | **Corpus composition, revised after testing**: the first draft (disaster/emergency vocabulary only, zero conflict/security words) put every real oil-corridor headline within a few hundredths of the 0.5 decision boundary — see §3.1's rejected-draft note. The committed corpus adds a third of its "alarming" rows as generic (non-oil) conflict/security sentences — border skirmishes, missile strikes, blockades, seizures, threats — so the vocabulary actually overlaps with how oil-disruption headlines are worded, without training on oil outcomes specifically | A classifier that can't discriminate on the one domain it will actually see live headlines from would read as broken on stage, not as an honest limitation — verified empirically (§3.1's before/after numbers), the same "test it, don't just design it" discipline as Phase 7's rejected shapely-distance feature |
| 3 | **Binary output** (`alarming` / not), no probability surfaced, no three-tier scale | Confirmed per interview — "never the deciding number" reads more honestly as a flag than as a second score sitting next to Watch's real 0–100 risk score for a judge to (wrongly) try to reconcile |
| 4 | **No contract change** — the alarm label reaches Watch's LLM prompt as one more context line (mirrors Phase 7's dark-ship line exactly) and the offline stub as an arithmetic bump; it is not stored on `CorridorRiskEntry` or anywhere else in `RiskState` | Confirmed per interview: PLAN.md's "visibly present as a labeled, secondary input" is satisfied by the prompt line + test coverage, the same bar Phase 7's dark-ship context line was held to before any map UI existed for it. No Segment 2 chunk plans a UI surface for this signal; adding a field nobody reads would be exactly the kind of unused-abstraction PLAN.md's own phases avoid elsewhere |
| 5 | **Stub gets the bump too** (mirrors Phase 7 decision #12) | Confirmed per interview: the classifier is local, network-free, and always available (like the anomaly detector) — there's no reason the fully-offline demo path shouldn't also visibly react to alarm language |
| 6 | **`_ALARM_BUMP = 8.0`**, a flat one-time addition when `is_alarming(headline)` is true, not scaled by classifier probability | Smaller than `_ESCALATION_WORDS`' per-keyword range (15–30 — those are direct oil-risk signals) and slightly smaller than `_DARK_TANKER_BUMP` (10.0, a physical AIS corroboration) — tone classification is the most indirect of the three inputs the stub combines, so it gets the smallest weight. A flat bump (not probability-scaled) matches decision #3's binary framing — there is no continuous number to scale by once the output is a flag |
| 7 | **Alarm classification is *not* suppressed under `as_of` (backtest/historical replay)**, unlike Phase 8's dark-ship suppression | Phase 8 suppressed the dark-ship line under `as_of` because AIS anomaly state is an present-day snapshot with no meaning attached to a years-old headline. Tone classification has no such temporal dependency — it's a pure function of the headline *text* being replayed, so `backtest.py`'s historical replay should score it exactly like the live path. Document this contrast explicitly so a future reader doesn't assume both v1.3 Watch inputs follow the same `as_of` rule |
| 8 | **`backend/agents/alarm.py`, fit-once-and-cached** (`functools.lru_cache(maxsize=1)`), mirrors `anomaly.py`'s `_anomalous_ids()` pattern exactly — a `sklearn.pipeline.Pipeline(TfidfVectorizer, LogisticRegression)` fit once per process over the committed corpus | Same rationale as Phase 7: the corpus never changes at runtime, so fitting is a one-time per-process cost, not a per-call one |
| 9 | **F7 slice: only `message` and `conservation_plan` become LLM-generated; `status` stays the existing rule-based `_level_for(severity)` threshold** | Confirmed per interview — `status` (Normal/Elevated/Shortage) almost certainly drives citizen-board colour/styling; letting an LLM call choose the category itself (rather than just the prose under it) would make the portal's core state classification non-deterministic in a way nothing else in this codebase's citizen-facing surface is |
| 10 | **Conservation-copy cache key: `f"{level}\|{corridor_name or 'none'}"`** (12-entry space: 3 levels × 4 corridors, `none` for a fresh boot with no signal) | Confirmed per interview — matches PLAN.md's "scenario-specific" framing (Hormuz vs. Suez gets different copy) while staying a small, finite, fully-precomputable-and-cacheable key space, the same demo-determinism discipline every other LLM call in this codebase follows (`watch.py`'s and `backtest.py`'s cache keys are both bounded, never a raw state hash) |
| 11 | **The LLM prompt's own inputs are limited to exactly the two cache-key dimensions** (`level`, `corridor_name`) — never raw `severity`, `impact`, or reserve numbers | A prompt that references finer numbers than the cache key would go stale the moment a *second*, differently-detailed scenario lands on the same `level`/`corridor` pair and reuses the first call's cached response — the prompt's inputs and the cache key's inputs must describe the same granularity by construction, not by discipline |
| 12 | **`status == "Normal"` skips the LLM call entirely**, always uses the static fallback | "Business as usual, no action needed" has no scenario-specific content to generate (no corridor is elevated) and Normal is the resting state the demo starts and often returns to — an LLM round-trip (even a cached one) buys nothing here and this endpoint's own docstring can say so plainly |
| 13 | **Single model tier** (`settings.watch_model_primary` only), not Watch's two-tier primary/fallback chain, before falling back to the static tips | Deliberate simplification for a P2/stretch, unauthenticated, non-critical-path endpoint — confirmed proportionate to scope; Watch's two-tier chain exists because a missed corridor score is felt immediately on the official cockpit's gauge, while a slightly-plainer static conservation tip is a fully acceptable degrade with no loss of the "reassuring, no raw numbers" citizen-portal promise |
| 14 | **`backend/agents/conservation.py`** (new module) holds the prompt template, the cache-key/prompt-input discipline, and the static fallback content (`_LEVELS`' message column + `_TIPS`, relocated here); `backend/api/routes.py`'s `public_status()` keeps only the DB lookup (worst corridor's human name) and the `status` derivation | Matches this codebase's existing separation — route handlers stay thin, agent/generation logic lives under `backend/agents/*` (mirrors `predict.py`/`recommend.py`/`backtest.py`, all called from a route handler that does little more than DB glue) |

## 2 · Backend changes

### 2.1 `backend/agents/alarm.py` (new)

```python
"""Alarm-language tone classifier (F19) -- the second, much smaller ML
component in this codebase (after Phase 7's dark-ship IsolationForest).

TF-IDF + logistic regression over a small, hand-curated, committed corpus of
GENERAL alarming-vs-calm language (border incidents, natural disasters, and
deliberately boring routine news -- not oil-crisis outcomes). Mirrors
anomaly.py's architecture: fit once per process over static, committed data,
cached, no network dependency, no runtime failure mode to degrade from
(SPEC.md Phase 7 decision #7's reasoning applies again here).

Binary output only (SPEC.md Phase 9 decision #3) -- this is a flag Watch's
prompt and stub weigh as one more grounded-ish signal, never a number blended
into any score (SPEC.md Phase 4 decision #5, same rule Phase 7's dark-ship
count and this classifier both follow).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline

_CORPUS_PATH = Path(__file__).resolve().parent / "data" / "alarm_corpus.json"

# Deterministic given a fixed corpus + fixed random_state (SPEC.md Phase 7's
# determinism rule, PLAN.md §5) -- LogisticRegression's lbfgs solver is
# already deterministic on data this size, random_state is pinned defensively
# for the same documentation-of-intent reason anomaly.py pins one.
_RANDOM_STATE = 42


@lru_cache(maxsize=1)
def _classifier() -> Pipeline:
    corpus = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
    texts = [row["text"] for row in corpus]
    labels = [row["label"] for row in corpus]
    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")),
            ("clf", LogisticRegression(max_iter=1000, random_state=_RANDOM_STATE)),
        ]
    )
    pipeline.fit(texts, labels)
    return pipeline


def is_alarming(headline: str) -> bool:
    """True if the headline's *language* (not its oil-domain content)
    classifies as alarming in tone. Pure function of the text -- no as_of
    suppression, unlike Phase 7's dark-ship count (SPEC.md Phase 9 decision
    #7): a historical replay's headline text is scored exactly like a live
    one."""

    return bool(_classifier().predict([headline])[0])
```

### 2.2 `backend/agents/data/alarm_corpus.json` (new, curated)

67 rows, 35 labelled `1` (alarming), 32 labelled `0` (calm) — `{"text": str,
"label": 0 | 1}`. General-tone, not oil-domain: natural disasters, violent
crime, market panics, and emergency-services language for the alarming
class; routine municipal/community/commerce announcements for the calm
class — **plus** (decision #2) a third alarming sub-group of generic,
non-oil conflict/security language (border skirmishes, missile strikes,
blockades, tanker-adjacent-but-not-oil-specific seizures, threats) so the
vocabulary genuinely overlaps with how a live oil-corridor headline is
worded. Representative rows:

```jsonc
// alarming (1)
{"text": "Massive explosion rocks downtown area, dozens feared trapped under rubble", "label": 1}
{"text": "Panic grips markets as index plunges more than ten percent in a single trading session", "label": 1}
{"text": "Rebel forces seized control of a key border town after fierce overnight fighting", "label": 1}
{"text": "Government forces launched a missile strike targeting insurgent positions overnight", "label": 1}
{"text": "Naval forces exchanged fire near disputed waters, raising fears of wider conflict", "label": 1}

// calm (0)
{"text": "Local council approves new bicycle lane along the riverside walking path", "label": 0}
{"text": "Farmers report a steady, healthy harvest season across the valley", "label": 0}
{"text": "Joint naval exercise concluded smoothly with no incidents reported", "label": 0}
{"text": "Diplomats described the trade talks as constructive and cordial", "label": 0}
{"text": "Customs authority reported a routine increase in seasonal cargo volumes", "label": 0}
```

Full 67-row file is committed verbatim at implementation time; the
representative rows above are enough to see the composition. §3.1 documents
why the conflict/security sub-group exists — it isn't decorative.

### 2.3 `backend/agents/watch.py` — one more prompt context line

Mirrors `_build_prompt`'s existing `dark_ship_line` parameter exactly (same
function signature-extension pattern Phase 7 established):

```python
from backend.agents.alarm import is_alarming

def _build_prompt(
    corridor: str, headline: str, snippets: list[Snippet], dark_count: int, alarming: bool,
) -> str:
    ...
    alarm_line = (
        "\nThis headline's language was independently classified as alarming in "
        "tone by a separate tone classifier -- weigh this as one more grounded "
        "signal, not a deciding factor on its own.\n"
        if alarming
        else ""
    )
    return _PROMPT_TEMPLATE.format(
        corridor=corridor, headline=headline, context=context,
        dark_ship_line=dark_ship_line, alarm_line=alarm_line,
    )
```

`_PROMPT_TEMPLATE` gains one more `{alarm_line}` slot next to the existing
`{dark_ship_line}` slot. `_score_with_llm`'s `cache_key` gains one more
component: `f"...|alarm={alarming}"`. `run_watch()` computes
`alarming = is_alarming(headline)` unconditionally (decision #7 — never
gated on `as_of`, unlike `dark_count`) and threads it through
`_build_prompt`/`_score_with_llm`.

### 2.4 `backend/agents/stubs.py` — matching arithmetic bump

```python
from backend.agents.alarm import is_alarming

_ALARM_BUMP = 8.0  # decision #6 -- flat, smaller than a dark-tanker corroboration

def run_watch_stub(signal: dict) -> WatchAgentOutput:
    ...
    dark_bump = _DARK_TANKER_BUMP * dark_tanker_count(corridor)
    alarm_bump = _ALARM_BUMP if is_alarming(str(signal.get("headline", ""))) else 0.0
    score = _clamp(severity * 100 + bump + dark_bump + alarm_bump, 0.0, 100.0)
    ...
```

(Uses the original-case headline for classification — the existing
`headline = str(signal.get("headline", "")).lower()` lowercasing is kept for
the keyword-bump loop only; the classifier gets the unmodified text since
its own TF-IDF vectorizer does its own casing-insensitive tokenization via
`stop_words`/lowercasing defaults, and there's no reason to pre-lowercase
before handing text to a separate pure function.)

### 2.5 `backend/agents/conservation.py` (new)

```python
"""LLM-generated citizen conservation copy (F7 slice of Phase 9).

Reuses backend/agents/llm.py's complete_json (Phase 4) -- provider-generic
despite being Groq-backed today. Falls back to static, hand-written copy
(moved here from routes.py's old _TIPS/_LEVELS) on any failure, exactly the
same graceful-degradation posture as watch.py's LLM path, just single-tier
(SPEC.md Phase 9 decision #13).

The prompt's inputs (level, corridor_name) are deliberately limited to
exactly the two dimensions in the cache key (decision #11) -- never raw
severity/impact numbers, so a cached response is never stale relative to
what it was cached under.
"""

from __future__ import annotations

from backend.agents.llm import LLMUnavailable, complete_json
from backend.config import get_settings

_LEVELS_FALLBACK = {
    "Normal": ("Supplies are steady. No action needed.", ["Business as usual — no conservation required."]),
    "Elevated": (
        "A supply route is under stress. Officials are rerouting; stay informed.",
        [
            "Combine errands into fewer trips.",
            "Keep tyres properly inflated to save fuel.",
            "Avoid topping-up your tank out of worry — there is no shortage.",
        ],
    ),
    "Shortage": (
        "Significant disruption. Please conserve fuel where you can.",
        [
            "Use public transport or car-pool where possible.",
            "Defer non-essential road travel.",
            "Do not panic-buy fuel — reserves are being managed.",
        ],
    ),
}

_PROMPT_TEMPLATE = """You are writing calm, plain-language guidance for a public \
citizen status board about India's crude-oil supply chain. The current status \
is "{level}"{corridor_clause}.

Write reassuring, non-alarming guidance appropriate to this status level -- \
never mention raw numbers, percentages, or internal model details. Respond \
with a JSON object only: {{"message": "<one or two calm sentences>", \
"conservation_plan": ["<short actionable tip>", ...]}} with 2 to 4 tips."""


def _fallback(level: str) -> dict:
    message, plan = _LEVELS_FALLBACK[level]
    return {"message": message, "conservation_plan": plan}


def generate_conservation_copy(level: str, corridor_name: str | None) -> dict:
    """Returns {"message": str, "conservation_plan": list[str]}."""

    settings = get_settings()
    if level == "Normal":  # decision #12 -- nothing scenario-specific to say
        return _fallback(level)
    if not settings.use_real_agents or not settings.groq_api_key:
        return _fallback(level)

    corridor_clause = f", driven by disruption on the {corridor_name} corridor" if corridor_name else ""
    prompt = _PROMPT_TEMPLATE.format(level=level, corridor_clause=corridor_clause)
    cache_key = f"{level}|{corridor_name or 'none'}"

    try:
        data = complete_json(prompt, cache_key=cache_key, model=settings.watch_model_primary)
        message = str(data["message"])
        plan = [str(tip) for tip in data["conservation_plan"]]
        if not message or not (1 <= len(plan) <= 6):
            raise ValueError("malformed conservation copy payload")
        return {"message": message, "conservation_plan": plan}
    except (LLMUnavailable, KeyError, TypeError, ValueError):
        return _fallback(level)
```

### 2.6 `backend/api/routes.py` — thinner `public_status()`

`_LEVELS`/`_TIPS` shrink to just the `(ceiling, name)` pairs `_level_for`
needs for `status` (decision #9); the message/tip content they used to hold
moves into `conservation.py`'s `_LEVELS_FALLBACK` (decision #14):

```python
from backend.agents.conservation import generate_conservation_copy

_LEVELS = [
    (0.34, "Normal"),
    (0.67, "Elevated"),
    (1.01, "Shortage"),
]

def _level_for(severity: float) -> str:
    for ceiling, name in _LEVELS:
        if severity < ceiling:
            return name
    return _LEVELS[-1][1]


@router.get("/public/status")
def public_status(
    store=Depends(get_store),
    session: Session = Depends(get_session),
) -> dict:
    state = store.get()
    level = _level_for(state.severity)

    worst_corridor_id = (
        max(state.corridor_risk, key=lambda cid: state.corridor_risk[cid].score)
        if state.corridor_risk
        else None
    )
    corridor_name = None
    if worst_corridor_id:
        corridor = session.query(Corridor).filter_by(id=worst_corridor_id).first()
        corridor_name = corridor.name if corridor else worst_corridor_id

    copy = generate_conservation_copy(level, corridor_name)

    recent = session.query(AuditLog).order_by(AuditLog.ts.desc()).limit(5).all()
    action_feed = [
        {"action": a.action, "supplier": a.payload.get("supplier"), "route": a.payload.get("route"), "ts": a.ts.isoformat()}
        for a in recent
    ]

    return {
        "status": level,
        "message": copy["message"],
        "conservation_plan": copy["conservation_plan"],
        "action_feed": action_feed,
        "updated_at": state.updated_at.isoformat(),
    }
```

Response shape is byte-identical to today's (`{status, message,
conservation_plan[], action_feed[], updated_at}`) — only how `message`/
`conservation_plan` get populated changes.

## 3 · Worked examples (real numbers, run against the committed corpus)

### 3.1 Alarm classifier — rejected first draft vs. the committed corpus

**First draft** (disaster/emergency vocabulary only, 51 rows, no
conflict/security sub-group): every real headline in
`backend/agents/data/watch_corpus.json` scored within **0.447–0.543**
probability of "alarming" — essentially noise clustered on the decision
boundary, and not correlated with actual severity (a mundane Malacca traffic
report scored *higher* than a literal Houthi attack headline). Rejected —
this would read as a broken/random flag on stage, not an honest secondary
signal.

**Committed corpus** (67 rows, adds the conflict/security sub-group,
decision #2): re-run against the same headlines, discrimination is real
though still modest (small-corpus, bag-of-words, honestly documented in the
module's own tests, not hidden):

| input | predict_proba(alarming) | label |
|---|---|---|
| *(canonical demo headline)* "Missile strike closes Strait of Hormuz shipping lane" | 0.548 | **alarming** |
| "Iran seizes tanker in the Strait of Hormuz amid rising tensions" | 0.567 | **alarming** |
| "Officials report routine tanker inspection near Malacca Strait" | 0.494 | calm |
| "Shipping companies report steady, on-schedule deliveries this quarter" | 0.447 | calm |
| "Suez Canal traffic returns to normal after brief inspection delay" | 0.527 | alarming *(a known miss — see below)* |

The canonical demo headline (`frontend/components/mission/launch-simulation.tsx`'s
hardcoded Mission Control signal) classifies correctly. 5-fold cross-validation
on the 67-row corpus itself averages **~0.65** accuracy — honestly document
this in the module docstring and PR description, not just the clean demo-path
number: with 67 hand-written examples this is a small, illustrative classifier,
not a validated production model, the same honesty framing Phase 8 applied to
its Brent price series. The one documented miss above ("Suez Canal traffic
returns to normal..." scoring as alarming) is exactly the kind of
near-boundary case a judge could find by hand-testing the endpoint — worth
being ready to explain rather than surprised by: it shares "Suez," "canal,"
and "closure/closed"-adjacent tokens with several alarming-class training
rows, and the corpus is too small for TF-IDF to have learned that
"*returns to normal*" reverses that.

### 3.2 Conservation copy — worked prompt

For `level="Elevated"`, `corridor_name="Strait of Hormuz"` (assuming
`corridors.json`'s `hormuz` row's `name` field is `"Strait of Hormuz"` —
confirm exact string against the seed file at implementation time), the
rendered prompt is:

```
You are writing calm, plain-language guidance for a public citizen status board
about India's crude-oil supply chain. The current status is "Elevated", driven
by disruption on the Strait of Hormuz corridor.

Write reassuring, non-alarming guidance appropriate to this status level --
never mention raw numbers, percentages, or internal model details. Respond
with a JSON object only: {"message": "<one or two calm sentences>",
"conservation_plan": ["<short actionable tip>", ...]} with 2 to 4 tips.
```

cached under key `"Elevated|Strait of Hormuz"`. The real-LLM-path response
text needs implementation-time verification against a live `GROQ_API_KEY`
(this environment has none, same caveat as Phase 8's §3.3) — the
offline-fallback path (§2.5's `_fallback("Elevated")`) is fully deterministic
and CI-testable today with no key required.

## 4 · API surface changes

None. `GET /public/status` keeps its exact route, auth (none — public), and
response shape. No new endpoint. `run_watch()`'s signature is unchanged from
the outside (`alarming` is computed internally, not a new parameter any
caller passes).

## 5 · Test updates

- **`tests/test_alarm.py`** (new):
  - `test_is_alarming_true_for_canonical_demo_headline` — pins §3.1's
    `"Missile strike closes Strait of Hormuz shipping lane"` result.
  - `test_is_alarming_false_for_routine_headline` — pins a clearly-calm
    input (`"Shipping companies report steady, on-schedule deliveries this
    quarter"`).
  - `test_classifier_is_deterministic_across_calls` — two `_classifier()`
    calls in-process return the identical fitted pipeline (the `lru_cache`
    contract), and `is_alarming()` on the same text twice agrees.
  - `test_corpus_label_balance` — a light regression guard that the
    committed corpus stays roughly balanced (e.g. between 30% and 70%
    alarming) so a future careless edit can't silently skew it to
    all-one-class.
- **`tests/test_watch.py`**:
  - `test_run_watch_prompt_includes_alarm_line_for_alarming_headline` /
    `test_run_watch_prompt_omits_alarm_line_for_calm_headline` — mirrors the
    existing dark-ship-line pair of tests exactly.
  - `test_run_watch_cache_key_includes_alarm_flag` — mirrors
    `test_run_watch_as_of_suppresses_dark_ship_line_even_for_hormuz`'s
    cache-key-capture pattern.
  - `test_run_watch_alarm_line_not_suppressed_by_as_of` — regression guard
    for decision #7: unlike the dark-ship line, `as_of` being set must
    **not** remove the alarm line when the replayed headline classifies as
    alarming.
- **`tests/test_watch.py`** (stub side, alongside the existing
  `test_run_watch_stub_dark_tanker_bump_matches_direct_stub_call`):
  - `test_run_watch_stub_alarm_bump_matches_direct_call` — a signal with an
    alarming headline scores `_ALARM_BUMP` higher than the same signal's
    calm-headline variant, all else equal.
- **`tests/test_conservation.py`** (new):
  - `test_generate_conservation_copy_normal_skips_llm` — monkeypatch
    `complete_json` to raise if called; assert `generate_conservation_copy("Normal", None)`
    never invokes it (decision #12).
  - `test_generate_conservation_copy_falls_back_without_api_key` — with
    `USE_REAL_AGENTS=0` (the test-suite default), any level/corridor
    combination returns the static `_LEVELS_FALLBACK` content unchanged.
  - `test_generate_conservation_copy_cache_key_is_level_and_corridor` —
    monkeypatch `complete_json` to capture `cache_key`; assert it equals
    `f"{level}|{corridor_name or 'none'}"` exactly.
  - `test_generate_conservation_copy_malformed_payload_falls_back` — a
    mocked `complete_json` returning e.g. an empty `conservation_plan` or a
    non-string `message` falls back to static copy rather than propagating
    a bad response to the citizen board.
- **`tests/test_api.py`**:
  - `GET /public/status` on a fresh boot (`severity=0`, no signal injected)
    still returns `status="Normal"` and the exact static message/plan —
    regression check that decision #12's LLM-skip really fires.
  - After a live `/signal` cascade raises severity into `"Elevated"`, `GET
    /public/status`'s response shape is unchanged
    (`{status, message, conservation_plan[], action_feed[], updated_at}`,
    same keys/types as before this phase) — with the test suite's default
    `USE_REAL_AGENTS=0`, `message`/`conservation_plan` still match the
    static fallback content exactly (deterministic, no live LLM call in
    CI).
- No changes needed to `tests/test_contract.py` (no contract change),
  `test_predict.py`, `test_recommend.py`, `test_advise.py`, `test_graph.py`,
  `test_geo.py`, `test_anomaly.py`, `test_ais.py`, `test_backtest.py`,
  `test_rag.py`, `test_llm.py`, `test_auth.py`.

## 6 · Documentation updates (same change, per the contract-change protocol)

- **`backend/agents/alarm.py`**, **`backend/agents/conservation.py`** — new
  modules, docstrings per §2.1/§2.5.
- **`CLAUDE.md`** — note the Watch agent now also folds in a tone-classifier
  context line (alongside Phase 7's dark-ship line); note `/public/status`
  now calls `generate_conservation_copy()` instead of static dict lookups
  directly.
- **`PROJECT_GUIDE.md`** — flip F19's status row (§04) to shipped; flip F7's
  row from "🟡 static tips today" to reflect the LLM-copy slice landing;
  §10's "built instead" alarm-language paragraph gets a "✅ shipped" note
  and the honest cross-validation-accuracy caveat from §3.1.
- **`PLAN.md`** — flip Phase 9's status once merged; link back to this
  section for the corpus-composition rejection/revision (decision #2) so a
  future contributor extending the corpus understands why the
  conflict/security sub-group exists and doesn't accidentally remove it
  thinking it's off-topic "not really general tone" content.

## 7 · Acceptance criteria

1. `python -m pytest` fully green, including every new/updated test in §5.
2. The alarm score is a labeled, secondary input, never presented as (and
   never wired as) a disruption predictor — verified by decision #4's "no
   contract field, no composite-score blend" constraint holding in code:
   `CorridorRiskEntry`/`RiskState` are untouched, and `is_alarming()`'s only
   two call sites are a prompt-context line and a stub arithmetic bump.
3. `GET /public/status` returns scenario-appropriate copy varying by
   `status`/corridor once a signal is injected, with the exact pre-existing
   response shape — verified by `test_api.py`'s shape assertions.
4. Both new components fall back gracefully with no `GROQ_API_KEY` and no
   `USE_REAL_AGENTS` flag set (the CI/fresh-clone default): the alarm
   classifier has no such dependency to begin with (decision #8, always
   runs), and `generate_conservation_copy` falls back to static copy
   (decision covering §2.5).
5. The canonical Mission Control demo headline ("Missile strike closes
   Strait of Hormuz shipping lane") classifies as alarming — a real
   regression check pinned in `tests/test_alarm.py`, not merely "some
   classifier exists."
6. No new dependency added (`requirements.txt` unchanged) — `scikit-learn`
   (Phase 7) and the existing Groq/`llm.py` stack (Phase 4) cover everything
   this phase needs.
7. No contract change — `python -m pytest tests/test_contract.py` needs zero
   new fixtures.

## 8 · Explicitly deferred (not decided here — flagged for the named phase or out of scope)

- **Any UI surface for the alarm label** — deliberately out of scope per
  decision #4; Segment 2 has no chunk planned for it. If a future demo wants
  to show it, that's a new contract field + new frontend chunk, not
  something this phase's "prompt line + tests" bar already covers.
- **Verifying the real-LLM-path conservation-copy text** and committing the
  corresponding `.llm_cache/` entries — implementation-time work, not done
  here (no live `GROQ_API_KEY` in this environment), same posture as Phase
  8's equivalent deferral.
- **Expanding the alarm corpus beyond 67 rows, or replacing TF-IDF+LogReg
  with a pretrained model** — only worth it if the ~0.65 cross-validated
  accuracy (§3.1) becomes a real problem on stage; PLAN.md frames this whole
  phase as P2/cut-first-if-time-is-short, so more corpus-curation time is
  better spent elsewhere unless a judge specifically probes this feature.
- **A two-tier model fallback for `generate_conservation_copy`** (mirroring
  Watch's primary/fallback chain) — decision #13 deliberately keeps this
  single-tier; revisit only if the static fallback content is ever judged
  insufficient for the demo.
- **Multi-corridor conservation copy** (both a Hormuz *and* a Suez signal
  elevated simultaneously) — `corridor_risk` can hold multiple entries
  (`state_store.py`'s `merge_watch` accumulates, doesn't replace), and
  `public_status()` picks the single worst-scoring corridor by design (§2.6)
  — a multi-corridor-aware copy prompt is out of scope for a P2/stretch
  slice.

---

---

*Urja Kavach · SPEC v9 · Phase 1 (landed) + Phase 2 (landed) + Phase 3
(interview complete, implementation-ready) + Phase 4 (interview complete,
implementation-ready) + Phase 5 (interview complete, implementation-ready) +
Phase 6 (interview complete, implementation-ready) + Phase 7 (interview
complete, implementation-ready) + Phase 8 (interview complete,
implementation-ready) + Phase 9 (interview complete, implementation-ready) ·
supersedes nothing in PLAN.md/PROJECT_GUIDE.md, just fills the gaps each
phase's PLAN.md section left open.*
