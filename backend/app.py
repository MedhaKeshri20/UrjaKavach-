"""FastAPI application factory for Urja Kavach (Dev A).

Wires the whole backend together: DB init + config seeding, the in-memory event
bus, the shared :class:`StateStore`, the WebSocket broadcaster, CORS for the two
React portals, and the REST/WS routes. One ``create_app`` so tests can build an
isolated app against a throwaway database.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from backend.bus import TOPIC_STATE_UPDATED, InMemoryBus
from backend.config import Settings, get_settings
from backend.db import init_db, session_scope
from backend.state_store import StateStore

log = logging.getLogger("urja.app")


class ConnectionManager:
    """Tracks live WebSocket clients and broadcasts state snapshots to them.

    Subscribed once to ``state.updated`` at startup, so every merge in the store
    fans out to all connected portals — the live cascade animation.
    """

    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        for ws in list(self.active):
            try:
                await ws.send_json(payload)
            except Exception:  # pragma: no cover - client vanished mid-send
                self.disconnect(ws)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        if settings.seed_on_startup:
            from backend.seed import run_seed

            counts = run_seed()
            log.info("seeded config: %s", counts)
        # v1.3 Phase 4: pre-embed the Watch RAG corpus, but only when the
        # real agent is actually enabled — a stub-only boot (the default)
        # never touches Chroma or triggers the one-time ONNX model download.
        if settings.use_real_agents and settings.groq_api_key:
            from backend.agents.rag import ensure_corpus_embedded

            ensure_corpus_embedded()
            log.info("watch corpus embedded/verified")
        yield

    app = FastAPI(
        title="Urja Kavach — Backend (Dev A)",
        version="0.1.0",
        summary="API gateway, event bus, agents and shared risk-state.",
        lifespan=lifespan,
    )

    # Security: a wildcard origin must NOT be combined with credentials — that
    # would reflect any site's origin back with allow-credentials:true. Auth
    # uses Bearer tokens in the Authorization header (not cookies), so we only
    # enable credentials when an explicit origin allowlist is configured.
    origins = settings.cors_origins
    allow_credentials = "*" not in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Singletons on app.state so routes/deps can reach them.
    bus = InMemoryBus()
    manager = ConnectionManager()
    store = StateStore(bus=bus, session_factory=session_scope)

    # The broadcaster listens once; each store merge publishes a full snapshot.
    bus.subscribe(TOPIC_STATE_UPDATED, manager.broadcast)

    app.state.settings = settings
    app.state.bus = bus
    app.state.manager = manager
    app.state.store = store
    app.state.session_factory = session_scope

    # Routes imported here to avoid a circular import at module load.
    from backend.api.routes import router
    from backend.auth.routes import router as auth_router

    app.include_router(router)
    app.include_router(auth_router)
    return app


# ASGI entrypoint: ``uvicorn backend.app:app``
app = create_app()
