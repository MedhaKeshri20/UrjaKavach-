"""Pytest bootstrap: make the repo root importable so ``backend`` resolves.

Allows ``pytest`` to be run from anywhere without an editable install.
"""

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture(autouse=True)
def _isolate_real_agents_flag(monkeypatch):
    """The suite must be hermetic against the developer's own local `.env`
    (found live: a real USE_REAL_AGENTS=1/GROQ_API_KEY in .env silently
    flipped several pinned-stub tests in test_api.py/test_auth.py/
    test_backtest.py onto the real LLM path, breaking their assertions,
    since those files construct Settings()/call run_watch() without ever
    overriding these two fields themselves). Forces the deterministic stub
    path by default for every test; test_watch.py's own `_real_agents_on`
    autouse fixture (file-scoped, runs after this one) still overrides it
    back on for the tests that specifically want the real-agent code path,
    same as before -- monkeypatch.setenv is last-write-wins on the same
    shared os.environ, not dependent on fixture teardown order.
    """

    monkeypatch.setenv("USE_REAL_AGENTS", "0")
    monkeypatch.setenv("GROQ_API_KEY", "")
