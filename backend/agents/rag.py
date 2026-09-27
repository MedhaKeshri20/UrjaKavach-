"""RAG snippet store for Watch (F2) — a small, curated, committed corpus of
real paraphrased headlines/sanctions notes, embedded into Chroma so Watch can
retrieve grounded, cited context for a scoring prompt instead of guessing.

Embeddings are local (Chroma's bundled ONNX MiniLM model, no API calls) —
retrieval must work with zero API keys configured (SPEC.md Phase 4 decision
#3), the same offline-safety bar as everything else in this repo (PRD §17).
Telemetry is disabled for the same reason: no incidental network calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

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


def _client(vector_store_path: str | None = None) -> chromadb.ClientAPI:
    path = vector_store_path or get_settings().vector_store_path
    return chromadb.PersistentClient(
        path=path, settings=ChromaSettings(anonymized_telemetry=False)
    )


def load_corpus() -> list[dict]:
    return json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))


def ensure_corpus_embedded(vector_store_path: str | None = None) -> None:
    """Idempotent (decision #18): embeds the corpus once, skips on later
    boots once the collection already holds every row — same spirit as
    seed.py's upsert-on-startup."""

    corpus = load_corpus()
    collection = _client(vector_store_path).get_or_create_collection(_COLLECTION_NAME)
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


def retrieve(
    corridor: str,
    query: str,
    k: int = 5,
    *,
    as_of: str | None = None,
    vector_store_path: str | None = None,
) -> list[Snippet]:
    """Top-k snippets for ``corridor``, ranked by similarity to ``query``
    (the injected headline). Returns ``[]`` if the corridor has no (eligible)
    snippets in the corpus — callers (watch.py) treat that as a fallback
    trigger (decision #9), not an error to raise.

    ``as_of`` (SPEC.md Phase 8, decision #3): an ISO date string. When set,
    only snippets dated on or before it are eligible — stops a historical
    backtest replay from retrieving snippets that postdate the headline
    being scored (the future-info leak PLAN.md's own Phase 4 architecture
    note flagged). ``None`` (the default — every live ``POST /signal`` call)
    applies no cutoff; behavior is byte-identical to pre-Phase-8.

    Implemented as an over-fetch + Python-side filter, not a Chroma ``where``
    date-range operator, so this doesn't depend on Chroma's string-comparison
    semantics for a metadata field.
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
