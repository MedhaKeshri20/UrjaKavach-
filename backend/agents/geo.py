"""Geospatial agent (Dev B) — AIS tanker-track replay + Geo block (F11, F13).

Reads the curated, committed AIS sample (via ais.py) and answers two
questions:
  - which tankers are "at risk" (static corridor tag, no geometry -- SPEC.md
    Phase 6 decision #3) given the set of currently-elevated corridors
  - which refineries are "affected" (via graph.py's affected_by(), Phase 5)

build_geo() is the one function cascade.py calls; it is the first thing that
ever populates RiskState.geo for real (Phase 5 shipped affected_by() uncalled
by design -- this is that call, SPEC.md Phase 6 decision #5/#12). Since
Phase 7, it also carries real dark_tanker_ids from anomaly.py.

list_tankers() itself lives in ais.py, not here, and is re-exported below --
anomaly.py needs it too, and anomaly.py is in turn imported by this module
(for dark_tanker_ids), so the raw AIS-loading code can't live in whichever
of the two modules would create a cycle (SPEC.md Phase 7 §5.2).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.agents.ais import list_tankers
from backend.agents.anomaly import dark_tanker_ids as _dark_tanker_ids
from backend.agents.graph import affected_by, build_graph
from backend.schemas import Geo

logger = logging.getLogger(__name__)


def at_risk_tanker_ids(elevated_corridors: set[str]) -> list[str]:
    """Tankers whose static corridor tag is in an elevated-risk set.

    No geometry (decision #3): an unrecognized corridor id in
    `elevated_corridors` simply matches no tanker -- unlike affected_by(),
    there's no fail-loud path to guard here.
    """

    return sorted(
        t["id"] for t in list_tankers() if t["corridor_id"] in elevated_corridors
    )


def build_geo(session: Session, elevated_corridors: set[str]) -> Geo:
    """Build the real Geo block for this cascade run (F11/F13/F18)."""

    try:
        graph = build_graph(session)
        affected_refineries = sorted(affected_by(graph, elevated_corridors).refineries)
    except ValueError as exc:
        # An unrecognized corridor id reached us (POST /signal's "warn, never
        # reject" tolerance — decision #8). affected_by()'s own fail-loud
        # choice (SPEC.md Phase 5 decision #7) is right for a bad literal in
        # a unit test; it must not 500 a live cascade.
        logger.warning(
            "geo: affected_by() rejected corridor set (%s), treating as none affected",
            exc,
        )
        affected_refineries = []

    return Geo(
        at_risk_tanker_ids=at_risk_tanker_ids(elevated_corridors),
        dark_tanker_ids=_dark_tanker_ids(elevated_corridors),
        affected_refinery_ids=affected_refineries,
    )
