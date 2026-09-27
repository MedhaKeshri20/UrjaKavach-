"""Event bus — the decoupling layer from PRD Section 5.

Agents never call each other directly; they publish to a topic and subscribe to
others. That is the whole scalability pitch: a new signal source or a fifth
agent is a new publisher/subscriber, not a code change to existing agents.

Ships with an in-memory async implementation (zero setup, used for local dev,
tests, and the demo). A Redis Streams implementation can be dropped in behind
the same :class:`EventBus` interface at integration time — "in-memory first,
swap at the hour of integration" (PRD §6). Nothing above the bus knows which
implementation is live.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

# Canonical topic names. Kept here so producers and consumers can't drift.
TOPIC_SIGNALS_RAW = "signals.raw"
TOPIC_STATE_UPDATED = "state.updated"

Handler = Callable[[dict[str, Any]], Awaitable[None] | None]


class EventBus(Protocol):
    """The one interface every component depends on."""

    def subscribe(self, topic: str, handler: Handler) -> None: ...

    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...


class InMemoryBus:
    """Async pub/sub within one process.

    Handlers registered for a topic are invoked (in registration order) each
    time something is published to it. Sync and async handlers are both
    supported. A handler raising is logged-and-skipped so one bad subscriber
    never breaks the cascade mid-demo.
    """

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subs[topic].append(handler)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        for handler in list(self._subs.get(topic, ())):
            try:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # pragma: no cover - defensive, demo-safety
                # Never let a subscriber failure abort the publish loop.
                import logging

                logging.getLogger("urja.bus").warning(
                    "handler for %s failed: %s", topic, exc
                )

    def clear(self) -> None:
        """Drop all subscribers (used between tests)."""

        self._subs.clear()
