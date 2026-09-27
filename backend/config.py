"""Runtime configuration for the Dev A backend (API, DB, bus).

Env-driven so the identical image runs locally (SQLite + in-memory bus) and in
production (Postgres + Redis) without code changes — the scalability story the
PRD sells. No secrets live here; they arrive as environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Repo root == parent of the ``backend`` package. Used to anchor the default
# SQLite file and the seed JSON directory regardless of the process CWD.
REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = Path(__file__).resolve().parent / "seed"


def _load_dotenv(path: Path | None = None) -> None:
    """Load ``KEY=VALUE`` lines from a local ``.env`` into ``os.environ``.

    Dependency-free (no python-dotenv). Real environment variables always win,
    so this only fills in what isn't already set. Missing file is a no-op.
    """

    path = path or (REPO_ROOT / ".env")
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        # Skip empty values so "DATABASE_URL=" means "use the built-in default"
        # rather than overriding it with an empty (unparseable) string.
        if value:
            os.environ.setdefault(key, value)


# Load .env at import time so Settings() below sees its values.
_load_dotenv()


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Immutable settings snapshot, read once from the environment."""

    # SQLite by default (zero setup). Override with a Postgres URL in prod, e.g.
    #   postgresql+psycopg://user:pass@host:5432/urja
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", f"sqlite:///{REPO_ROOT / 'urja.db'}"
        )
    )
    # Present for parity with the compose file; the in-memory bus ignores it.
    redis_url: str = field(
        default_factory=lambda: os.environ.get("REDIS_URL", "")
    )
    # CORS origins for the two React portals (Dev C/D). "*" in dev.
    cors_origins: list[str] = field(
        default_factory=lambda: _split_csv(os.environ.get("CORS_ORIGINS", "*"))
    )
    # Re-seed config tables on startup. Idempotent, so safe to leave on.
    seed_on_startup: bool = field(
        default_factory=lambda: os.environ.get("SEED_ON_STARTUP", "1") != "0"
    )

    # --- Auth (JWT) --------------------------------------------------------
    # A dev-only default so the app runs out of the box; ALWAYS override with a
    # real random secret in production (set JWT_SECRET in the environment).
    jwt_secret: str = field(
        default_factory=lambda: os.environ.get(
            "JWT_SECRET", "dev-only-insecure-change-me"
        )
    )
    jwt_algorithm: str = field(
        default_factory=lambda: os.environ.get("JWT_ALGORITHM", "HS256")
    )
    jwt_expiry_minutes: int = field(
        default_factory=lambda: int(os.environ.get("JWT_EXPIRY_MINUTES", "720"))
    )

    # --- Watch agent (Groq LLM + RAG) --------------------------------------
    # Off by default: a fresh clone/CI run always uses the deterministic
    # Watch stub, never requiring a key (SPEC.md Phase 4 decision #17).
    use_real_agents: bool = field(
        default_factory=lambda: os.environ.get("USE_REAL_AGENTS", "0") == "1"
    )
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

    # --- Geospatial data (Phase 6/7: AIS replay + dark-ship detector) ------
    # Defaults to the curated, committed replay set. This is the one seam a
    # live AIS feed would plug into: anomaly.py/geo.py only ever consume
    # ais.py's list_tankers() -- point this at a different file (same
    # {id, corridor_id, track[]} shape) and every downstream consumer picks
    # it up with no code change, same pattern as DATABASE_URL/REDIS_URL
    # swapping the DB/bus without touching agent code.
    ais_data_path: str = field(
        default_factory=lambda: os.environ.get(
            "AIS_DATA_PATH",
            str(REPO_ROOT / "backend" / "agents" / "data" / "ais_sample.json"),
        )
    )

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def get_settings() -> Settings:
    """Return a fresh Settings read from the current environment."""

    return Settings()
