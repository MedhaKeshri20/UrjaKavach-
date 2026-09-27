"""API conformance: every state response validates against the contract,
boundary validation holds, and the injected-signal cascade runs end to end.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.db as db
from backend.app import create_app
from backend.config import Settings
from backend.schemas import RiskState


def _assumption_entry(value, type_="fact", lo=0.0, hi=100.0, src="test fixture"):
    return {"value": value, "type": type_, "range": [lo, hi], "src": src}


def _assumptions_payload(**value_overrides):
    """A fully-populated, contract-valid typed Assumptions body for /simulate.

    v1.3 (SPEC.md Phase 1): Assumptions now requires all six typed
    AssumptionEntry keys, not three bare floats.
    """
    defaults = {
        "supply_lost_pct": 40,
        "buffer_days": 9,
        "price_elasticity": 3,
        "power_oil_dependence": 0.015,
        "gdp_oil_sensitivity": 0.03,
        "power_stress_multiplier": 7.5,
    }
    defaults.update(value_overrides)
    return {k: _assumption_entry(v) for k, v in defaults.items()}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """App bound to an isolated temp SQLite DB, freshly seeded."""

    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False}, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    # Rebind the module globals that init_db() and session_scope() use.
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", SessionLocal)

    app = create_app(Settings(database_url=db_url, seed_on_startup=True))
    with TestClient(app) as c:
        yield c


def _official_headers(client, email="officer@gov.in"):
    """Register an official and return an Authorization header for them."""

    r = client.post(
        "/auth/register",
        json={"email": email, "password": "secret123", "role": "official"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _citizen_headers(client, email="citizen@in.gov"):
    """Register a citizen and return an Authorization header for them."""

    r = client.post(
        "/auth/register",
        json={"email": email, "password": "secret123", "role": "citizen"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_cors_wildcard_does_not_allow_credentials(client):
    # With the default "*" origin, we must NOT reflect an arbitrary origin with
    # credentials — that combination is the classic CORS misconfiguration.
    r = client.get("/state", headers={"Origin": "https://evil.example"})
    allow_origin = r.headers.get("access-control-allow-origin")
    assert allow_origin != "https://evil.example"  # not reflected
    assert r.headers.get("access-control-allow-credentials") != "true"


def test_initial_state_validates_as_riskstate(client):
    body = client.get("/state").json()
    RiskState.model_validate(body)  # raises if the shape drifts


def test_signal_runs_full_cascade(client):
    r = client.post(
        "/signal",
        json={
            "corridor": "hormuz",
            "headline": "Tanker seized near Hormuz",
            "severity": 0.4,
            "id": "news_412",
            "source_ids": ["news_412", "ais_88"],
        },
    )
    assert r.status_code == 200
    state = RiskState.model_validate(r.json())  # response is a valid RiskState
    assert "hormuz" in state.corridor_risk
    assert state.impact is not None
    # v1.3 (SPEC.md Phase 3): real power stress, no longer a 0.0 placeholder --
    # consistent with the documented formula over whatever assumptions the
    # cascade actually derived (the "seized" headline bumps severity above
    # the raw 0.4 input, so don't hardcode the resulting gap).
    a = state.assumptions
    assert state.impact.power_stress_pct == round(
        a.supply_lost_pct.value * a.power_oil_dependence.value * a.power_stress_multiplier.value,
        3,
    )
    assert state.impact.power_stress_pct > 0.0
    assert state.assumptions.power_stress_multiplier.value == 7.5  # typed shape (v1.3)
    assert state.reserve is not None
    assert len(state.reroutes) >= 1
    # v1.3 (SPEC.md Phase 4): USE_REAL_AGENTS defaults off in every test env
    # (no .env, no monkeypatch here), so run_watch() must fall back to the
    # exact same deterministic stub score run_watch_stub() would produce —
    # this phase must not change the cascade's default (offline) behavior.
    from backend.agents.stubs import run_watch_stub

    stub_entry = run_watch_stub(
        {"corridor": "hormuz", "headline": "Tanker seized near Hormuz", "severity": 0.4}
    )
    assert state.corridor_risk["hormuz"].score == stub_entry.corridor_risk["hormuz"].score
    # reroutes exclude the disrupted corridor
    assert all(rr.route != "hormuz" for rr in state.reroutes)
    # ranks are dense and 1-based
    assert [rr.rank for rr in state.reroutes] == list(range(1, len(state.reroutes) + 1))
    # v1.3 (SPEC.md Phase 2): the real wrong-oil gate + true-cost math, no
    # more mechanical placeholders.
    for rr in state.reroutes:
        assert rr.refinery_id
        assert rr.rank_eligible == rr.grade_ok
        assert (rr.reason is None) == rr.grade_ok
        assert rr.true_cost >= rr.cost  # insurance/detour never reduce cost
    # the hard gate actually fires with today's seed data (SPEC.md Phase 2
    # worked example: e.g. Bonny Light isn't compatible with vadinar/paradip)
    ineligible = [rr for rr in state.reroutes if not rr.rank_eligible]
    assert ineligible, "expected at least one grade-incompatible reroute"
    for rr in ineligible:
        assert rr.reason
    # eligible rows always sort before ineligible ones
    eligible_ranks = [rr.rank for rr in state.reroutes if rr.rank_eligible]
    ineligible_ranks = [rr.rank for rr in ineligible]
    assert max(eligible_ranks) < min(ineligible_ranks)
    assert state.assumption_overrides == []
    # v1.3 (SPEC.md Phase 6): geo is now genuinely populated post-signal --
    # matches SPEC.md Phase 6 §3.3's worked example for a hormuz disruption.
    assert state.geo is not None
    assert state.geo.at_risk_tanker_ids == [
        "hormuz_01", "hormuz_02", "hormuz_03", "hormuz_04",
    ]
    assert state.geo.affected_refinery_ids == ["jamnagar", "paradip", "vadinar"]
    # v1.3 (SPEC.md Phase 7): the curated dark-ship case lives in hormuz.
    assert state.geo.dark_tanker_ids == ["hormuz_02", "hormuz_03", "hormuz_04"]
    assert state.validation is None


def test_simulate_returns_impact_and_is_pure(client):
    r = client.post(
        "/simulate",
        json={"scenario": "whatif", "assumptions": _assumptions_payload()},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["impact"]["price_rise_pct"] == 12.0  # (40/10)*3
    # v1.3 (SPEC.md Phase 3): real power stress, e.g. 40*0.015*7.5=4.5.
    assert data["impact"]["power_stress_pct"] == 4.5
    assert data["assumptions"]["power_stress_multiplier"]["value"] == 7.5
    # pure: shared state untouched by a simulate call
    assert client.get("/state").json()["scenario"] == "steady_state"


def test_simulate_rejects_missing_assumption_field(client):
    assumptions = _assumptions_payload()
    del assumptions["price_elasticity"]
    r = client.post(
        "/simulate",
        json={"scenario": "bad", "assumptions": assumptions},
    )
    assert r.status_code == 422  # price_elasticity required


def test_simulate_rejects_missing_v13_assumption_field(client):
    """The three new F20/F15 keys are just as required as the original three."""
    assumptions = _assumptions_payload()
    del assumptions["power_stress_multiplier"]
    r = client.post(
        "/simulate",
        json={"scenario": "bad", "assumptions": assumptions},
    )
    assert r.status_code == 422


def test_simulate_rejects_extra_field(client):
    assumptions = _assumptions_payload()
    assumptions["reason"] = "x"
    r = client.post(
        "/simulate",
        json={"scenario": "bad", "assumptions": assumptions},
    )
    assert r.status_code == 422  # extra="forbid" on Assumptions


def test_simulate_rejects_bare_float_assumption_entry(client):
    """v1.3: each assumption key must be a typed {value,type,range,src} object,
    not a bare number (the v1.0 shape)."""
    r = client.post(
        "/simulate",
        json={
            "scenario": "bad",
            "assumptions": {
                "supply_lost_pct": 40,
                "buffer_days": 9,
                "price_elasticity": 3,
                "power_oil_dependence": 0.015,
                "gdp_oil_sensitivity": 0.03,
                "power_stress_multiplier": 7.5,
            },
        },
    )
    assert r.status_code == 422


def test_reroutes_sort_toggle(client):
    client.post("/signal", json={"corridor": "hormuz", "headline": "closure", "severity": 0.5})
    cost = client.get("/reroutes?sort=cost").json()
    speed = client.get("/reroutes?sort=speed").json()
    assert cost["options"][0]["scores"]["total"] >= 0
    # cheapest-first vs fastest-first should generally differ at the top
    assert cost["excluded_corridors"] == ["hormuz"]
    assert speed["sort"] == "speed"


def test_reroutes_bad_sort_rejected(client):
    assert client.get("/reroutes?sort=bogus").status_code == 400


# --------------------------------------------------------------------------- #
# v1.3 (SPEC.md Segment 1, Phase 6): GET /geo/state -- geo block + AIS replay
# + corridor/refinery config, the backend half of the geospatial layer (F11/F13).
# --------------------------------------------------------------------------- #


def test_geo_state_fresh_boot(client):
    r = client.get("/geo/state")
    assert r.status_code == 200
    body = r.json()
    assert body["geo"] is None  # no signal injected yet, same pattern as impact/reserve
    assert len(body["tankers"]) == 16
    assert len(body["corridors"]) == 4
    assert len(body["refineries"]) == 3


def test_geo_state_tankers_have_full_tracks(client):
    tankers = client.get("/geo/state").json()["tankers"]
    hormuz_ids = {t["id"] for t in tankers if t["corridor_id"] == "hormuz"}
    assert hormuz_ids == {"hormuz_01", "hormuz_02", "hormuz_03", "hormuz_04"}
    for t in tankers:
        assert len(t["track"]) == 8
        for point in t["track"]:
            assert set(point) >= {"ts", "lat", "lon", "heading_deg", "speed_knots"}


def test_geo_state_corridors_and_refineries_expose_map_config(client):
    body = client.get("/geo/state").json()
    corridor_ids = {c["id"] for c in body["corridors"]}
    assert corridor_ids == {"hormuz", "suez_cape", "atlantic", "malacca"}
    hormuz = next(c for c in body["corridors"] if c["id"] == "hormuz")
    assert hormuz["geojson_path"] == "backend/seed/geo/hormuz.geojson"
    assert hormuz["war_risk_pct"] == 0.004

    refinery_ids = {r["id"] for r in body["refineries"]}
    assert refinery_ids == {"jamnagar", "vadinar", "paradip"}
    jamnagar = next(r for r in body["refineries"] if r["id"] == "jamnagar")
    assert jamnagar["lat"] == 22.34 and jamnagar["lon"] == 69.85


def test_geo_state_after_hormuz_signal_matches_worked_example(client):
    """SPEC.md Phase 6 §3.3: hormuz's 4 tankers at risk, all 3 refineries
    affected. SPEC.md Phase 7: 3 of those 4 are also the curated dark-ship
    case."""

    client.post(
        "/signal", json={"corridor": "hormuz", "headline": "seized", "severity": 0.4}
    )
    geo = client.get("/geo/state").json()["geo"]
    assert geo is not None
    assert geo["at_risk_tanker_ids"] == [
        "hormuz_01", "hormuz_02", "hormuz_03", "hormuz_04",
    ]
    assert geo["affected_refinery_ids"] == ["jamnagar", "paradip", "vadinar"]
    assert geo["dark_tanker_ids"] == ["hormuz_02", "hormuz_03", "hormuz_04"]


def test_geo_state_matches_live_state_geo(client):
    """GET /geo/state reads geo live from RiskState (SPEC.md Phase 6 decision
    #5) -- it must always agree with GET /state, not a second computation."""

    client.post(
        "/signal", json={"corridor": "hormuz", "headline": "seized", "severity": 0.4}
    )
    assert client.get("/geo/state").json()["geo"] == client.get("/state").json()["geo"]


def test_geo_state_corridors_expose_parsed_geometry(client):
    """India Connect Portal/spec.md Phase 7: the map can't fetch
    `geojson_path` directly (it's a repo-relative path, not a URL), so
    `/geo/state` embeds each corridor's parsed GeoJSON `geometry` too."""

    body = client.get("/geo/state").json()
    hormuz = next(c for c in body["corridors"] if c["id"] == "hormuz")
    assert hormuz["geometry"]["type"] == "LineString"
    coords = hormuz["geometry"]["coordinates"]
    assert len(coords) >= 2
    assert coords[0] == [56.25, 26.57]  # [lon, lat], matches hormuz.geojson


def test_geo_state_unaffected_corridor_signal_has_no_at_risk_tankers(client):
    """A signal whose corridor never crosses AFFECTED_THRESHOLD leaves the
    excluded-corridor set built from the signal's own corridor (cascade.py's
    fallback) -- a quiet headline still tags that one corridor's tankers."""

    client.post(
        "/signal",
        json={"corridor": "malacca", "headline": "routine patrol", "severity": 0.05},
    )
    geo = client.get("/geo/state").json()["geo"]
    assert geo["at_risk_tanker_ids"] == [
        "malacca_01", "malacca_02", "malacca_03", "malacca_04",
    ]
    # malacca has no suppliers routed through it in seed data (SPEC.md Phase 5 §3)
    assert geo["affected_refinery_ids"] == []


# --------------------------------------------------------------------------- #
# India Connect Portal/spec.md Phase 6: GET /provenance -- resolves Watch's
# source_ids to real, citable snippets. Deferred by PLAN.md Phase 4 to
# "Segment 2, Chunk D" with no shape pinned; this is that endpoint.
# --------------------------------------------------------------------------- #


def test_provenance_resolves_known_corpus_ids(client):
    r = client.get("/provenance?ids=news_hormuz_2019_seizure,news_hormuz_2018_threat")
    assert r.status_code == 200
    body = r.json()
    assert body["missing"] == []
    ids = {item["id"] for item in body["items"]}
    assert ids == {"news_hormuz_2019_seizure", "news_hormuz_2018_threat"}
    seizure = next(i for i in body["items"] if i["id"] == "news_hormuz_2019_seizure")
    assert seizure["source"] == "wire reporting"
    assert seizure["timestamp"] == "2019-07-19"
    assert "Hormuz" in seizure["headline"]


def test_provenance_unknown_id_reports_missing_not_fabricated(client):
    """The offline stub's source_ids are the injected signal's own id (e.g.
    'sig_unknown'), not real corpus entries -- must come back honestly
    missing, never invented."""

    r = client.get("/provenance?ids=sig_unknown")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["missing"] == ["sig_unknown"]


def test_provenance_mixed_known_and_unknown_ids(client):
    r = client.get("/provenance?ids=news_hormuz_2019_seizure,sig_unknown")
    body = r.json()
    assert [i["id"] for i in body["items"]] == ["news_hormuz_2019_seizure"]
    assert body["missing"] == ["sig_unknown"]


def test_approve_writes_audit_and_shows_in_feed(client):
    headers = _official_headers(client)
    state = client.post(
        "/signal", json={"corridor": "hormuz", "headline": "seized", "severity": 0.4}
    ).json()
    supplier = state["reroutes"][0]["supplier"]
    ap = client.post(
        "/approve", json={"supplier": supplier, "note": "go"}, headers=headers
    )
    assert ap.status_code == 200
    assert ap.json()["ok"] is True
    # actor is taken from the token, not the request body
    assert ap.json()["actor"] == "officer@gov.in"

    feed = client.get("/public/status").json()["action_feed"]
    assert any(item["supplier"] == supplier for item in feed)


def test_audit_endpoint_official_only(client):
    # anonymous -> 401
    assert client.get("/audit").status_code == 401
    # citizen -> 403
    cit = client.post(
        "/auth/register",
        json={"email": "cit@in.gov", "password": "secret123", "role": "citizen"},
    ).json()
    r = client.get("/audit", headers={"Authorization": f"Bearer {cit['access_token']}"})
    assert r.status_code == 403

    # official sees the log after an approval
    headers = _official_headers(client)
    state = client.post(
        "/signal", json={"corridor": "hormuz", "headline": "seized", "severity": 0.4}
    ).json()
    supplier = state["reroutes"][0]["supplier"]
    client.post("/approve", json={"supplier": supplier}, headers=headers)

    audit = client.get("/audit", headers=headers)
    assert audit.status_code == 200
    rows = audit.json()
    assert len(rows) >= 1
    assert rows[0]["actor"] == "officer@gov.in"
    assert rows[0]["action"] == "approve_reroute"


def test_approve_requires_official_role(client):
    """Anonymous -> 401; a citizen user -> 403; only officials may approve."""

    state = client.post(
        "/signal", json={"corridor": "hormuz", "headline": "seized", "severity": 0.4}
    ).json()
    supplier = state["reroutes"][0]["supplier"]

    # no token
    assert client.post("/approve", json={"supplier": supplier}).status_code == 401

    # citizen token
    pub = client.post(
        "/auth/register",
        json={"email": "citizen@in.gov", "password": "secret123", "role": "citizen"},
    ).json()
    r = client.post(
        "/approve",
        json={"supplier": supplier},
        headers={"Authorization": f"Bearer {pub['access_token']}"},
    )
    assert r.status_code == 403


def test_approve_unknown_supplier_404(client):
    headers = _official_headers(client)
    client.post("/signal", json={"corridor": "hormuz", "headline": "seized", "severity": 0.4})
    r = client.post("/approve", json={"supplier": "does_not_exist"}, headers=headers)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# v1.3 (SPEC.md Segment 1, Phase 3): assumption-override audit (F20/F9).
# Exploratory commits log to audit_log immediately; RiskState.assumption_overrides
# is only ever stamped by POST /approve.
# --------------------------------------------------------------------------- #


def test_assumption_override_requires_auth(client):
    r = client.post(
        "/assumptions/override",
        json={"assumptions": _assumptions_payload(price_elasticity=6)},
    )
    assert r.status_code == 401


def test_assumption_override_any_authenticated_role_may_call_it(client):
    """Not officials-only -- a citizen token is enough (SPEC.md Phase 3 #3)."""

    # bump-free headline on a corridor with no dark tankers (SPEC.md Phase 7 --
    # hormuz's stub score now carries a real dark-ship bump, so atlantic is the
    # one that keeps severity exactly 0.4, matching _assumptions_payload()'s defaults
    client.post("/signal", json={"corridor": "atlantic", "headline": "quiet monitoring update", "severity": 0.4})
    headers = _citizen_headers(client)
    r = client.post(
        "/assumptions/override",
        json={"assumptions": _assumptions_payload(price_elasticity=6)},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["overrides_logged"] == ["price_elasticity"]


def test_assumption_override_logs_audit_row_on_divergence(client):
    headers = _official_headers(client)
    client.post("/signal", json={"corridor": "atlantic", "headline": "quiet monitoring update", "severity": 0.4})
    r = client.post(
        "/assumptions/override",
        json={"assumptions": _assumptions_payload(price_elasticity=6)},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["overrides_logged"] == ["price_elasticity"]
    assert len(body["pending"]) == 1
    assert body["pending"][0]["field"] == "price_elasticity"
    assert body["pending"][0]["from_default"] == 3.0
    assert body["pending"][0]["to_value"] == 6.0
    assert body["pending"][0]["who"] == "officer@gov.in"

    audit = client.get("/audit", headers=headers).json()
    override_rows = [a for a in audit if a["action"] == "override_assumption"]
    assert len(override_rows) == 1
    assert override_rows[0]["payload"]["field"] == "price_elasticity"

    # exploratory only -- shared state is untouched until an approve happens
    assert client.get("/state").json()["assumption_overrides"] == []


def test_assumption_override_no_row_at_default(client):
    headers = _official_headers(client)
    client.post("/signal", json={"corridor": "atlantic", "headline": "quiet monitoring update", "severity": 0.4})
    r = client.post(
        "/assumptions/override",
        json={"assumptions": _assumptions_payload()},  # every field at its default
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["overrides_logged"] == []
    assert body["pending"] == []

    audit = client.get("/audit", headers=headers).json()
    assert not any(a["action"] == "override_assumption" for a in audit)


def test_repeated_override_same_field_dedups_pending_not_audit(client):
    headers = _official_headers(client)
    client.post("/signal", json={"corridor": "atlantic", "headline": "quiet monitoring update", "severity": 0.4})
    client.post(
        "/assumptions/override",
        json={"assumptions": _assumptions_payload(price_elasticity=6)},
        headers=headers,
    )
    r = client.post(
        "/assumptions/override",
        json={"assumptions": _assumptions_payload(price_elasticity=8)},
        headers=headers,
    )
    # one pending entry, latest value
    pending = r.json()["pending"]
    assert len(pending) == 1
    assert pending[0]["to_value"] == 8.0

    # both commits are still in the durable audit history
    audit = client.get("/audit", headers=headers).json()
    override_rows = [a for a in audit if a["action"] == "override_assumption"]
    assert len(override_rows) == 2


def test_revert_to_default_clears_pending_and_logs_nothing(client):
    headers = _official_headers(client)
    client.post("/signal", json={"corridor": "atlantic", "headline": "quiet monitoring update", "severity": 0.4})
    client.post(
        "/assumptions/override",
        json={"assumptions": _assumptions_payload(price_elasticity=6)},
        headers=headers,
    )
    r = client.post(
        "/assumptions/override",
        json={"assumptions": _assumptions_payload()},  # back to default
        headers=headers,
    )
    assert r.json()["overrides_logged"] == []
    assert r.json()["pending"] == []

    # the revert itself wrote no audit row -- only the original commit did
    audit = client.get("/audit", headers=headers).json()
    override_rows = [a for a in audit if a["action"] == "override_assumption"]
    assert len(override_rows) == 1


def test_approve_snapshots_and_clears_pending_overrides(client):
    headers = _official_headers(client)
    state = client.post(
        "/signal", json={"corridor": "atlantic", "headline": "quiet monitoring update", "severity": 0.4}
    ).json()
    supplier = state["reroutes"][0]["supplier"]

    client.post(
        "/assumptions/override",
        json={"assumptions": _assumptions_payload(price_elasticity=6)},
        headers=headers,
    )
    # not yet stamped onto shared state
    assert client.get("/state").json()["assumption_overrides"] == []

    ap = client.post("/approve", json={"supplier": supplier}, headers=headers)
    assert ap.status_code == 200
    # the approve's own audit row carries the overrides live at that moment
    assert len(ap.json()["payload"]["assumption_overrides"]) == 1
    assert ap.json()["payload"]["assumption_overrides"][0]["field"] == "price_elasticity"

    after = client.get("/state").json()
    assert len(after["assumption_overrides"]) == 1
    assert after["assumption_overrides"][0]["to_value"] == 6.0

    # a second approve with nothing newly pending resets the field to empty
    ap2 = client.post("/approve", json={"supplier": supplier}, headers=headers)
    assert ap2.json()["payload"]["assumption_overrides"] == []
    assert client.get("/state").json()["assumption_overrides"] == []


def test_new_signal_clears_pending_overrides_from_a_prior_session(client):
    headers = _official_headers(client)
    client.post("/signal", json={"corridor": "hormuz", "headline": "seized", "severity": 0.4})
    client.post(
        "/assumptions/override",
        json={"assumptions": _assumptions_payload(price_elasticity=6)},
        headers=headers,
    )

    # a fresh signal starts a new scenario -- the unapproved override shouldn't survive
    state = client.post(
        "/signal", json={"corridor": "hormuz", "headline": "closure", "severity": 0.6}
    ).json()
    supplier = state["reroutes"][0]["supplier"]

    ap = client.post("/approve", json={"supplier": supplier}, headers=headers)
    assert ap.json()["payload"]["assumption_overrides"] == []
    assert client.get("/state").json()["assumption_overrides"] == []


def test_public_status_levels(client):
    # quiet -> Normal
    assert client.get("/public/status").json()["status"] == "Normal"
    # big shock -> Shortage
    client.post("/signal", json={"corridor": "hormuz", "headline": "blockade attack", "severity": 0.9})
    assert client.get("/public/status").json()["status"] == "Shortage"


# --------------------------------------------------------------------------- #
# v1.3 (SPEC.md Segment 1, Phase 9, F7 slice): GET /public/status's
# message/conservation_plan are now LLM-generated when USE_REAL_AGENTS+
# GROQ_API_KEY are set, falling back to static copy otherwise (the test
# suite's default env) -- status stays rule-based either way. Response shape
# must stay byte-identical to pre-Phase-9.
# --------------------------------------------------------------------------- #


def test_public_status_fresh_boot_uses_static_normal_copy(client):
    """Decision #12 regression check: Normal always skips the LLM, so a
    fresh boot's message/plan are the exact static fallback content."""

    from backend.agents.conservation import _LEVELS_FALLBACK

    body = client.get("/public/status").json()
    message, plan = _LEVELS_FALLBACK["Normal"]
    assert body["status"] == "Normal"
    assert body["message"] == message
    assert body["conservation_plan"] == plan


def test_public_status_shape_unchanged_after_signal(client):
    """With the test suite's default USE_REAL_AGENTS=0, message/plan still
    match the static fallback exactly (deterministic, no live LLM call in
    CI) -- but the response's key set/types are exactly what the citizen
    board has always read."""

    from backend.agents.conservation import _LEVELS_FALLBACK

    client.post(
        "/signal", json={"corridor": "hormuz", "headline": "blockade attack", "severity": 0.9}
    )
    body = client.get("/public/status").json()

    assert set(body.keys()) == {"status", "message", "conservation_plan", "action_feed", "updated_at"}
    assert body["status"] == "Shortage"
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["conservation_plan"], list) and body["conservation_plan"]
    assert isinstance(body["action_feed"], list)

    message, plan = _LEVELS_FALLBACK["Shortage"]
    assert body["message"] == message
    assert body["conservation_plan"] == plan


# --------------------------------------------------------------------------- #
# v1.3 (SPEC.md Segment 1, Phase 8): GET /backtest/{id} -- Watch's real score
# timeline vs. an illustrative Brent price timeline, and the lead time
# between them (F14). Never touches RiskState (decision #5).
# --------------------------------------------------------------------------- #


def test_backtest_known_case_returns_full_result(client):
    r = client.get("/backtest/red_sea_2023")
    assert r.status_code == 200
    body = r.json()

    assert body["validation"]["backtest_id"] == "red_sea_2023"
    assert body["validation"]["signal_lead_hours"] > 0
    assert body["corridor"] == "suez_cape"
    assert body["watch_alert_threshold"] == 50.0
    assert len(body["score_timeline"]) == 7
    assert len(body["price_timeline"]) == 11
    assert body["note"]  # honesty framing is present, never omitted

    # USE_REAL_AGENTS is off by default in the test env, so run_watch()
    # degrades to the deterministic stub -- pin the exact worked-example
    # number from SPEC.md Phase 8 §3.3 as a real regression check.
    assert body["validation"]["signal_lead_hours"] == 1464.0
    assert body["watch_crossed_at"] == "2023-12-03T00:00:00Z"
    assert body["brent_crossed_at"] == "2024-02-02T00:00:00Z"


def test_backtest_unknown_case_404(client):
    r = client.get("/backtest/not_a_real_case")
    assert r.status_code == 404


def test_backtest_never_mutates_riskstate(client):
    """SPEC.md Phase 8 decision #5: GET /backtest/{id} is fully standalone --
    validation stays None on RiskState no matter how many times it's called."""

    assert client.get("/state").json()["validation"] is None
    client.get("/backtest/red_sea_2023")
    client.get("/backtest/red_sea_2023")
    assert client.get("/state").json()["validation"] is None


def test_websocket_pushes_snapshot_on_signal(client):
    with client.websocket_connect("/ws/state") as ws:
        hydrate = ws.receive_json()  # immediate current snapshot
        RiskState.model_validate(hydrate)
        client.post("/signal", json={"corridor": "hormuz", "headline": "seized", "severity": 0.4})
        # the cascade publishes several snapshots; the last reflects the shock
        pushed = ws.receive_json()
        RiskState.model_validate(pushed)
