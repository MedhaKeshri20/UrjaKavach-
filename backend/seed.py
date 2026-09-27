"""Idempotent config seeding: JSON files -> config tables on startup.

Loading is a merge (upsert by primary key), so running it on every boot never
duplicates rows and lets you edit a seed JSON and restart to pick up changes.
Only the config tables are seeded here; state/log tables are agent-written.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from backend.config import SEED_DIR
from backend.db import session_scope
from backend.models import Corridor, Refinery, Supplier


def _load(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def seed_all(session: Session, seed_dir: Path | None = None) -> dict[str, int]:
    """Upsert corridors, suppliers, refineries. Returns per-table row counts."""

    seed_dir = seed_dir or SEED_DIR

    for row in _load(seed_dir / "corridors.json"):
        session.merge(Corridor(**row))
    for row in _load(seed_dir / "suppliers.json"):
        session.merge(Supplier(**row))
    for row in _load(seed_dir / "refineries.json"):
        session.merge(Refinery(**row))

    session.flush()
    return {
        "corridors": session.query(Corridor).count(),
        "suppliers": session.query(Supplier).count(),
        "refineries": session.query(Refinery).count(),
    }


def run_seed() -> dict[str, int]:
    """Convenience entrypoint used at app startup and by ``python -m``."""

    with session_scope() as session:
        return seed_all(session)


if __name__ == "__main__":  # pragma: no cover - manual seed helper
    from backend.db import init_db

    init_db()
    counts = run_seed()
    print("Seeded:", counts)
