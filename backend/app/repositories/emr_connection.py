"""EMR connection repository — interface + in-memory implementation (ADR-0009).

`ConnectionRecord` is the storage-agnostic twin of `models.EmrConnection`. OAuth
tokens are never part of the record — only the `token_ref` pointing into the secret
store (ADR-0008).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from app.models.emr_connection import EmrConnectionStatus


@dataclass
class ConnectionRecord:
    """Storage-agnostic twin of models.EmrConnection (same fields the DB row holds)."""

    id: uuid.UUID
    patient_id: uuid.UUID
    fhir_base: str
    provider_name: str | None
    status: EmrConnectionStatus = EmrConnectionStatus.authorizing
    granted_scope: str | None = None
    patient_fhir_id: str | None = None
    token_ref: str | None = None
    token_expires_at: datetime | None = None
    revoked_at: datetime | None = None
    # Watermark for the incremental clinical-note pull (ADR-0045 P2 #27).
    last_notes_pulled_at: datetime | None = None


class EmrConnectionRepository(Protocol):
    """Persistence contract for a patient's EMR connections."""

    async def add(self, connection: ConnectionRecord) -> None:
        """Persist a newly created connection."""
        ...

    async def get(self, connection_id: uuid.UUID) -> ConnectionRecord | None:
        """Fetch a connection by id."""
        ...

    async def update(self, connection: ConnectionRecord) -> None:
        """Persist the current state of an existing connection."""
        ...

    async def set_last_notes_pulled_at(
        self, connection_id: uuid.UUID, last_notes_pulled_at: datetime
    ) -> None:
        """Persist ONLY the note-pull watermark — a targeted single-field write.

        The note pull holds its ConnectionRecord snapshot across a long EHR fetch, so
        writing the whole record back could resurrect a concurrently revoked connection
        (stale status/token_ref clobbering the revoke). This method must never touch any
        field but ``last_notes_pulled_at``. An unknown id is a quiet no-op.
        """
        ...

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[ConnectionRecord]:
        """All of one patient's EMR connections, every status.

        Account deletion (ADR-0027) reads this to find the token refs to purge from
        the vault and the connection ids whose pending-auth rows must go first.
        """
        ...

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        """Destroy every EMR connection row for one patient (ADR-0027).

        Callers own the FK order: pending_auth rows referencing these connections are
        deleted BEFORE this, and vaulted secrets are purged via SecretStore.delete —
        this removes only the connection rows themselves.
        """
        ...


class InMemoryEmrConnectionRepository:
    """Dict-backed store for unit tests and DB-less development.

    Reads return COPIES (and writes store copies), mirroring the DB repository's
    detached-row semantics: a caller holding a record across an await never shares
    mutable state with the store, so stale-snapshot bugs (e.g. a pull write-back
    racing a revoke) reproduce in unit tests instead of only in deployment.
    """

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, ConnectionRecord] = {}

    async def add(self, connection: ConnectionRecord) -> None:
        self._connections[connection.id] = replace(connection)

    async def get(self, connection_id: uuid.UUID) -> ConnectionRecord | None:
        record = self._connections.get(connection_id)
        return None if record is None else replace(record)

    async def update(self, connection: ConnectionRecord) -> None:
        self._connections[connection.id] = replace(connection)

    async def set_last_notes_pulled_at(
        self, connection_id: uuid.UUID, last_notes_pulled_at: datetime
    ) -> None:
        record = self._connections.get(connection_id)
        if record is not None:
            record.last_notes_pulled_at = last_notes_pulled_at

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[ConnectionRecord]:
        return [replace(c) for c in self._connections.values() if c.patient_id == patient_id]

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        self._connections = {
            cid: c for cid, c in self._connections.items() if c.patient_id != patient_id
        }
