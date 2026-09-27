"""AIS data loading (backend/agents/ais.py): the source is configurable via
Settings.ais_data_path / the AIS_DATA_PATH env var -- the one seam a live
feed would plug into instead of the committed replay set (see ais.py's own
docstring). This proves the seam is real, not just a documentation claim."""

import json

from backend.agents import ais


def test_list_tankers_default_source_is_committed_replay_set():
    ais._load_tankers.cache_clear()
    try:
        tankers = ais.list_tankers()
        assert len(tankers) == 16
        assert {t["corridor_id"] for t in tankers} == {
            "hormuz", "suez_cape", "atlantic", "malacca",
        }
    finally:
        ais._load_tankers.cache_clear()


def test_list_tankers_honors_ais_data_path_override(tmp_path, monkeypatch):
    """Pointing AIS_DATA_PATH at a different file changes what
    list_tankers() returns, with zero code change to geo.py/anomaly.py --
    the swap this module's docstring promises actually works."""

    custom_records = [
        {
            "id": "test_tanker_01",
            "corridor_id": "hormuz",
            "track": [
                {
                    "ts": "2026-01-01T00:00:00Z",
                    "lat": 1.0, "lon": 1.0,
                    "heading_deg": 90.0, "speed_knots": 10.0,
                },
            ],
        }
    ]
    custom_path = tmp_path / "custom_ais.json"
    custom_path.write_text(json.dumps(custom_records), encoding="utf-8")

    monkeypatch.setenv("AIS_DATA_PATH", str(custom_path))
    ais._load_tankers.cache_clear()
    try:
        assert ais.list_tankers() == custom_records
    finally:
        # Unset the override (monkeypatch reverts it at teardown regardless,
        # but doing it explicitly here lets this test also prove reverting
        # actually restores the default) and clear the process-global cache
        # so no other test in the suite inherits the swapped-in data.
        monkeypatch.delenv("AIS_DATA_PATH", raising=False)
        ais._load_tankers.cache_clear()

    assert len(ais.list_tankers()) == 16
