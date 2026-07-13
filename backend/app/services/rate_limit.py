"""Sliding-window rate limiting over the audit log (ADR-0017).

Dependency-free and storage-agnostic: the limiter is pure window math over a
`RateLimitCounter` — anything that can count one actor's events for one action since
an instant. Both audit repositories (in-memory and Postgres) satisfy the protocol,
so the counter is exactly as durable as the audit trail itself and a separate
rate-limit table cannot drift from the audited truth: every accepted invitation is
already exactly one 'invite_patient' audit event.

Time is always injected (`now=`): the limiter never reads the wall clock, so tests
assert window math on fixed timestamps (the CI-flake rule, ADR-0013).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

__all__ = ["RateLimitCounter", "RateLimitExceededError", "SlidingWindowRateLimiter"]


class RateLimitCounter(Protocol):
    """Counting contract the limiter needs — structurally satisfied by
    `AuditEventRepository.count_actor_events_since`."""

    async def count_actor_events_since(
        self, *, actor_id: uuid.UUID, action: str, since: datetime
    ) -> int:
        """How many events one actor produced for one action at/after `since`."""
        ...


class RateLimitExceededError(Exception):
    """The actor is over the window budget; routes map this to 429."""


@dataclass(frozen=True)
class SlidingWindowRateLimiter:
    """At most `max_events` per actor per trailing `window`. The window is closed on
    its trailing edge: an event exactly `window` old still counts (>= since), so the
    budget frees up strictly after the window has fully elapsed."""

    counter: RateLimitCounter
    action: str
    max_events: int
    window: timedelta

    async def allow(self, actor_id: uuid.UUID, *, now: datetime) -> bool:
        """True when the actor still has budget for one more event at `now`."""
        count = await self.counter.count_actor_events_since(
            actor_id=actor_id, action=self.action, since=now - self.window
        )
        return count < self.max_events
