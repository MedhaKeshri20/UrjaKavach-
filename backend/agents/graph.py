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
