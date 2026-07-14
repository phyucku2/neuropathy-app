"""Unit tests for the sliding-window rate limiter (ADR-0017).

All window math is asserted on FIXED injected timestamps — the limiter never reads
the wall clock, so nothing here can flake with time (the ADR-0013 CI rule).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.models.audit import AuditEvent
from app.repositories.audit import InMemoryAuditEventRepository
from app.services.clinic import invitation_rate_limiter
from app.services.rate_limit import SlidingWindowRateLimiter

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
ACTOR = uuid.uuid4()
WINDOW = timedelta(hours=1)


class RecordingCounter:
    """Counter fake: returns a preset count and records what was asked."""

    def __init__(self, count: int) -> None:
        self.count = count
        self.calls: list[tuple[uuid.UUID, str, datetime]] = []

    async def count_actor_events_since(
        self, *, actor_id: uuid.UUID, action: str, since: datetime
    ) -> int:
        self.calls.append((actor_id, action, since))
        return self.count


def _limiter(counter: RecordingCounter, max_events: int = 3) -> SlidingWindowRateLimiter:
    return SlidingWindowRateLimiter(
        counter=counter, action="invite_patient", max_events=max_events, window=WINDOW
    )


async def test_allows_under_the_budget_and_refuses_at_it() -> None:
    assert await _limiter(RecordingCounter(0)).allow(ACTOR, now=NOW) is True
    assert await _limiter(RecordingCounter(2)).allow(ACTOR, now=NOW) is True  # budget - 1
    assert await _limiter(RecordingCounter(3)).allow(ACTOR, now=NOW) is False  # at budget
    assert await _limiter(RecordingCounter(50)).allow(ACTOR, now=NOW) is False


async def test_counts_exactly_the_trailing_window_for_this_actor_and_action() -> None:
    counter = RecordingCounter(0)
    await _limiter(counter).allow(ACTOR, now=NOW)
    assert counter.calls == [(ACTOR, "invite_patient", NOW - WINDOW)]


async def test_a_zero_budget_refuses_everything() -> None:
    assert await _limiter(RecordingCounter(0), max_events=0).allow(ACTOR, now=NOW) is False


async def test_audit_repository_counter_window_edges_on_fixed_timestamps() -> None:
    """The in-memory counter under the limiter: the window is closed on its trailing
    edge (an event exactly `window` old still counts) and open before it; other
    actors and other actions never count."""
    repo = InMemoryAuditEventRepository()

    async def _event(actor: uuid.UUID, action: str, at: datetime) -> None:
        await repo.add(
            AuditEvent(
                actor_id=actor, occurred_at=at, actor_role="clinician", action=action, detail={}
            )
        )

    since = NOW - WINDOW
    await _event(ACTOR, "invite_patient", since - timedelta(seconds=1))  # left the window
    await _event(ACTOR, "invite_patient", since)  # exactly on the edge — counts
    await _event(ACTOR, "invite_patient", NOW)  # in the window
    await _event(uuid.uuid4(), "invite_patient", NOW)  # someone else
    await _event(ACTOR, "rate_limited", NOW)  # refusals never count (ADR-0017)

    count = await repo.count_actor_events_since(
        actor_id=ACTOR, action="invite_patient", since=since
    )
    assert count == 2

    limiter = SlidingWindowRateLimiter(
        counter=repo, action="invite_patient", max_events=2, window=WINDOW
    )
    assert await limiter.allow(ACTOR, now=NOW) is False  # 2 of 2 spent
    # One second later the edge event leaves the window and the budget frees up.
    assert await limiter.allow(ACTOR, now=NOW + timedelta(seconds=1)) is True


async def test_invitation_limiter_is_settings_driven(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "invite_rate_limit_max", 5)
    monkeypatch.setattr(settings, "invite_rate_limit_window_seconds", 120)
    repo = InMemoryAuditEventRepository()
    limiter = invitation_rate_limiter(repo)
    assert limiter.counter is repo
    assert limiter.action == "invite_patient"
    assert limiter.max_events == 5
    assert limiter.window == timedelta(seconds=120)
