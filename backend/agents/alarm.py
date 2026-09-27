"""Alarm-language tone classifier (F19) -- the second, much smaller ML
component in this codebase (after Phase 7's dark-ship IsolationForest).

TF-IDF + logistic regression over a small, hand-curated, committed corpus of
GENERAL alarming-vs-calm language (border incidents, natural disasters, and
deliberately boring routine news -- not oil-crisis outcomes). Mirrors
anomaly.py's architecture: fit once per process over static, committed data,
cached, no network dependency, no runtime failure mode to degrade from
(SPEC.md Phase 7 decision #7's reasoning applies again here).

Binary output only (SPEC.md Phase 9 decision #3) -- this is a flag Watch's
prompt and stub weigh as one more grounded-ish signal, never a number blended
into any score (SPEC.md Phase 4 decision #5, same rule Phase 7's dark-ship
count and this classifier both follow).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

_CORPUS_PATH = Path(__file__).resolve().parent / "data" / "alarm_corpus.json"

# Deterministic given a fixed corpus + fixed random_state (SPEC.md Phase 7's
# determinism rule, PLAN.md §5) -- LogisticRegression's lbfgs solver is
# already deterministic on data this size, random_state is pinned defensively
# for the same documentation-of-intent reason anomaly.py pins one.
_RANDOM_STATE = 42


@lru_cache(maxsize=1)
def _classifier() -> Pipeline:
    corpus = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
    texts = [row["text"] for row in corpus]
    labels = [row["label"] for row in corpus]
    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")),
            ("clf", LogisticRegression(max_iter=1000, random_state=_RANDOM_STATE)),
        ]
    )
    pipeline.fit(texts, labels)
    return pipeline


def is_alarming(headline: str) -> bool:
    """True if the headline's *language* (not its oil-domain content)
    classifies as alarming in tone. Pure function of the text -- no as_of
    suppression, unlike Phase 7's dark-ship count (SPEC.md Phase 9 decision
    #7): a historical replay's headline text is scored exactly like a live
    one."""

    return bool(_classifier().predict([headline])[0])
