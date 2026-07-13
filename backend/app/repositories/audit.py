"""Audit event repository — interface + in-memory implementation (CLAUDE.md §5).

Append-only by contract: events are added and listed, never updated or deleted.
Works directly with `models.AuditEvent`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from app.models.audit import AuditEvent


class AuditEventRepository(Protocol):
    """Persistence contract for the append-only PHI/config audit log."""

    async def add(self, event: AuditEvent) -> AuditEvent:
        """Append an audit event. Events are never updated or deleted."""
        ...

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[AuditEvent]:
        """Events touching one patient's record, oldest first."""
        ...

    async def count_actor_events_since(
        self, *, actor_id: uuid.UUID, action: str, since: datetime
    ) -> int:
        """How many events one actor produced for one action at/after `since`.

        This makes the append-only audit log double as the durable sliding-window
        rate-limit counter (ADR-0017): every accepted invitation is already exactly
        one 'invite_patient' event, so no separate rate-limit table can drift from
        the audited truth.
        """
        ...


class InMemoryAuditEventRepository:
    """List-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    async def add(self, event: AuditEvent) -> AuditEvent:
        # Server defaults (id, occurred_at) only apply on DB flush; mirror them here.
        if event.id is None:
            event.id = uuid.uuid4()
        if event.occurred_at is None:
            event.occurred_at = datetime.now(UTC)
        self._events.append(event)
        return event

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[AuditEvent]:
        rows = [e for e in self._events if e.patient_id == patient_id]
        return sorted(rows, key=lambda e: e.occurred_at)

    async def count_actor_events_since(
        self, *, actor_id: uuid.UUID, action: str, since: datetime
    ) -> int:
        return sum(
            1
            for e in self._events
            if e.actor_id == actor_id and e.action == action and e.occurred_at >= since
        )
