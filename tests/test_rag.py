"""Tests for backend/agents/rag.py — the Watch RAG corpus store (SPEC.md
Phase 4). Every test uses an isolated Chroma path (pytest's ``tmp_path``/
``tmp_path_factory`` fixtures), never the real ``.chroma/`` directory used
by a running server.

Embeddings are local (Chroma's bundled ONNX MiniLM model) — these tests make
no network calls once that model is present in the local cache (see
SETUP.md's one-time-download note), matching the offline-safety bar the
rest of the suite holds to. Most tests share one module-scoped, pre-embedded
corpus (embedding the same 20-row corpus per test function is needlessly
slow); only the tests that specifically probe embedding-time behavior use
their own isolated path.
"""

from __future__ import annotations

import pytest

from backend.agents.rag import ensure_corpus_embedded, load_corpus, retrieve
from backend.agents.watch import KNOWN_CORRIDORS


@pytest.fixture(scope="module")
def embedded_path(tmp_path_factory) -> str:
    path = str(tmp_path_factory.mktemp("watch_corpus_shared"))
    ensure_corpus_embedded(vector_store_path=path)
    return path


def test_corpus_covers_every_known_corridor_with_at_least_five_snippets():
    """Guards the assumption watch.py's retrieval-thinness penalty relies on
    (_RETRIEVE_K = 5) — every corridor Watch might score should have enough
    corpus depth that a normal query isn't automatically penalized as thin."""

    corpus = load_corpus()
    counts: dict[str, int] = {}
    for row in corpus:
        counts[row["corridor"]] = counts.get(row["corridor"], 0) + 1

    assert set(counts) == KNOWN_CORRIDORS
    for corridor, count in counts.items():
        assert count >= 5, f"{corridor} only has {count} corpus snippets"


def test_corpus_ids_are_unique():
    corpus = load_corpus()
    ids = [row["id"] for row in corpus]
    assert len(ids) == len(set(ids))


def test_ensure_corpus_embedded_is_idempotent(embedded_path):
    first = retrieve(
        "hormuz", "tanker seized near the strait", k=5, vector_store_path=embedded_path
    )

    # Calling again against the already-embedded path must not duplicate
    # rows — same retrieval result.
    ensure_corpus_embedded(vector_store_path=embedded_path)
    second = retrieve(
        "hormuz", "tanker seized near the strait", k=5, vector_store_path=embedded_path
    )

    assert [s.id for s in first] == [s.id for s in second]


def test_retrieve_only_returns_matching_corridor(embedded_path):
    for corridor in KNOWN_CORRIDORS:
        snippets = retrieve(corridor, "risk event", k=10, vector_store_path=embedded_path)
        assert snippets, f"expected snippets for {corridor}"
        assert all(s.corridor == corridor for s in snippets)


def test_retrieve_respects_k(embedded_path):
    snippets = retrieve("hormuz", "tanker seized", k=2, vector_store_path=embedded_path)
    assert len(snippets) == 2


def test_retrieve_returns_empty_for_unknown_corridor(embedded_path):
    assert retrieve("not_a_real_corridor", "anything", vector_store_path=embedded_path) == []


def test_retrieve_returns_empty_before_any_embedding(tmp_path):
    """A collection that was never embedded (fresh, isolated path,
    ensure_corpus_embedded never called) must degrade to an empty result,
    not raise. Uses its own path — must NOT share the module-scoped
    already-embedded fixture."""

    assert retrieve("hormuz", "anything", vector_store_path=str(tmp_path)) == []


def test_retrieved_snippet_fields_round_trip(embedded_path):
    snippets = retrieve(
        "suez_cape", "Houthi attack on shipping", k=3, vector_store_path=embedded_path
    )
    assert snippets
    for s in snippets:
        assert s.corridor == "suez_cape"
        assert s.id
        assert s.date
        assert s.source
        assert s.text


# --------------------------------------------------------------------------- #
# v1.3 (SPEC.md Segment 1, Phase 8): as_of cutoff -- backtest.py's historical
# replay must never see a snippet dated after the headline being scored.
# --------------------------------------------------------------------------- #


def test_retrieve_as_of_none_is_unchanged_default_behavior(embedded_path):
    """No as_of at all, and as_of=None explicitly, must behave identically to
    pre-Phase-8 -- the live cascade never passes as_of, so this must be a
    true no-op."""

    no_kwarg = retrieve("suez_cape", "Red Sea shipping attack", k=5, vector_store_path=embedded_path)
    explicit_none = retrieve(
        "suez_cape", "Red Sea shipping attack", k=5, as_of=None, vector_store_path=embedded_path
    )
    assert [s.id for s in no_kwarg] == [s.id for s in explicit_none]


def test_retrieve_as_of_excludes_snippets_dated_after_cutoff(embedded_path):
    """suez_cape has snippets on both sides of 2023-12-03 (SPEC.md Phase 8
    decision #2's new corpus entries) -- an as_of cutoff on that date must
    exclude every later one."""

    snippets = retrieve(
        "suez_cape",
        "Red Sea shipping attack",
        k=20,
        as_of="2023-12-03",
        vector_store_path=embedded_path,
    )
    assert snippets, "expected at least one eligible snippet on/before the cutoff"
    assert all(s.date <= "2023-12-03" for s in snippets)
    # a real later snippet exists in the full (unfiltered) corpus, proving the
    # cutoff actually excluded something rather than vacuously passing
    unfiltered = retrieve(
        "suez_cape", "Red Sea shipping attack", k=20, vector_store_path=embedded_path
    )
    assert any(s.date > "2023-12-03" for s in unfiltered)


def test_retrieve_as_of_still_respects_k(embedded_path):
    snippets = retrieve(
        "suez_cape", "Red Sea shipping attack", k=2, as_of="2024-03-06", vector_store_path=embedded_path
    )
    assert len(snippets) == 2


def test_retrieve_as_of_before_earliest_snippet_returns_empty(embedded_path):
    snippets = retrieve(
        "suez_cape", "Red Sea shipping attack", k=5, as_of="1999-01-01", vector_store_path=embedded_path
    )
    assert snippets == []
