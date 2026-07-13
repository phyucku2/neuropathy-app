"""Clinic connection repository — interface + in-memory implementation (ADR-0005/0012).

Works directly with `models.ClinicConnection` — the row `may_transmit_to_clinic`
(app/services/connection.py) judges, so the consent gate is applied to exactly what
storage holds, never a diverging copy.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from app.models.connection import ClinicConnection, ConnectionStatus


class ClinicConnectionRepository(Protocol):
    """Persistence contract for patient-clinic connections."""

    async def add(self, connection: ClinicConnection) -> ClinicConnection:
        """Persist a newly created connection."""
        ...

    async def get(self, connection_id: uuid.UUID) -> ClinicConnection | None:
        """Fetch a connection by id."""
        ...

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[ClinicConnection]:
        """All of one patient's connections (every status), oldest first."""
        ...

    async def list_active_for_clinic(self, clinic_id: uuid.UUID) -> list[ClinicConnection]:
        """One clinic's status=active connections, oldest first.

        Storage-level narrowing only — callers MUST still apply
        `may_transmit_to_clinic` before any data flows (ADR-0005: consent, not
        status alone, gates transmission).
        """
        ...

    async def update(self, connection: ClinicConnection) -> None:
        """Persist the current state of an existing connection."""
        ...


class InMemoryClinicConnectionRepository:
    """Dict-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, ClinicConnection] = {}

    async def add(self, connection: ClinicConnection) -> ClinicConnection:
        # Column defaults (id, created_at) only apply on DB flush; mirror them here.
        if connection.id is None:
            connection.id = uuid.uuid4()
        if connection.created_at is None:
            connection.created_at = datetime.now(UTC)
        self._connections[connection.id] = connection
        return connection

    async def get(self, connection_id: uuid.UUID) -> ClinicConnection | None:
        return self._connections.get(connection_id)

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[ClinicConnection]:
        rows = [c for c in self._connections.values() if c.patient_id == patient_id]
        return sorted(rows, key=lambda c: c.created_at)

    async def list_active_for_clinic(self, clinic_id: uuid.UUID) -> list[ClinicConnection]:
        rows = [
            c
            for c in self._connections.values()
            if c.clinic_id == clinic_id and c.status is ConnectionStatus.active
        ]
        return sorted(rows, key=lambda c: c.created_at)

    async def update(self, connection: ClinicConnection) -> None:
        self._connections[connection.id] = connection
