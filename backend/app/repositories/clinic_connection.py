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


class DuplicateLiveConnectionError(Exception):
    """A non-revoked connection already links this patient and clinic.

    The storage backstop for the invite flow's check-then-insert (ADR-0012): both
    implementations raise it from `add`, mirroring the `uq_clinic_connection_live`
    partial unique index, so concurrent invitations can never create duplicates.
    """

    def __init__(self, patient_id: uuid.UUID, clinic_id: uuid.UUID) -> None:
        super().__init__(
            f"live connection already exists: patient {patient_id}, clinic {clinic_id}"
        )


class ClinicConnectionRepository(Protocol):
    """Persistence contract for patient-clinic connections."""

    async def add(self, connection: ClinicConnection) -> ClinicConnection:
        """Persist a newly created connection.

        Raises DuplicateLiveConnectionError when a non-revoked connection for the
        same (patient_id, clinic_id) already exists.
        """
        ...

    async def get(self, connection_id: uuid.UUID) -> ClinicConnection | None:
        """Fetch a connection by id."""
        ...

    async def list_for_patient(
        self, patient_id: uuid.UUID, *, for_share: bool = False
    ) -> list[ClinicConnection]:
        """All of one patient's connections (every status), oldest first.

        `for_share=True` (write flows judging authority) takes a shared row lock in
        Postgres so a concurrent consent grant cannot slip between the check and the
        dependent write (ADR-0013 review finding); in-memory mode has no concurrent
        transactions to defend against and ignores it.
        """
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
        # Mirror the uq_clinic_connection_live partial unique index so in-memory and
        # Postgres modes enforce the same invariant.
        for existing in self._connections.values():
            if (
                existing.patient_id == connection.patient_id
                and existing.clinic_id == connection.clinic_id
                and existing.status is not ConnectionStatus.revoked
            ):
                raise DuplicateLiveConnectionError(connection.patient_id, connection.clinic_id)
        # Column defaults (id, created_at) only apply on DB flush; mirror them here.
        if connection.id is None:
            connection.id = uuid.uuid4()
        if connection.created_at is None:
            connection.created_at = datetime.now(UTC)
        self._connections[connection.id] = connection
        return connection

    async def get(self, connection_id: uuid.UUID) -> ClinicConnection | None:
        return self._connections.get(connection_id)

    async def list_for_patient(
        self, patient_id: uuid.UUID, *, for_share: bool = False
    ) -> list[ClinicConnection]:
        # for_share is a Postgres-transaction concern; single-process dict storage
        # has nothing to lock.
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
