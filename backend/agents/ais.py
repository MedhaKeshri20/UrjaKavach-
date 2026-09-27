"""The AIS tanker-track dataset (F13) — loading only, source configurable.

Split out of geo.py (SPEC.md Phase 7) so both geo.py and anomaly.py can read
the same tanker records without a circular import: geo.py's build_geo() now
calls into anomaly.py for dark_tanker_ids, and anomaly.py needs the raw
tracks anomaly detection runs over, so neither module can own this data and
be imported by the other.

This module is the *only* place any agent reads AIS data from -- geo.py and
anomaly.py both go through list_tankers() below, never the file/setting
directly. That makes it the one seam a live AIS feed would plug into: point
Settings.ais_data_path (env AIS_DATA_PATH) at a different source producing
the same {id, corridor_id, track: [{ts, lat, lon, heading_deg, speed_knots}]}
shape -- a feed adapter's periodic export, a DB view, whatever -- and every
downstream consumer (the geo endpoint, the anomaly detector, Watch's
dark-tanker prompt context) picks it up with no code change. The default
still points at the curated, committed replay set (backend/agents/data/
ais_sample.json): live AIS is a paid commercial feed, deliberately out of
scope for this build the same way a live Brent price feed is (PRD's own
"replayed, not live" scope guard) -- but nothing here hardcodes that choice.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from backend.config import get_settings


@lru_cache(maxsize=1)
def _load_tankers() -> list[dict]:
    """The AIS replay set, loaded once per process from Settings.ais_data_path
    (static, committed data by default -- no reason to re-read the file on
    every call; a live-feed source would want its own caching/refresh policy,
    which is exactly the kind of change that belongs behind this one seam)."""

    path = Path(get_settings().ais_data_path)
    return json.loads(path.read_text(encoding="utf-8"))


def list_tankers() -> list[dict]:
    """Raw tanker records (id, corridor_id, track[]) for GET /geo/state."""

    return _load_tankers()
