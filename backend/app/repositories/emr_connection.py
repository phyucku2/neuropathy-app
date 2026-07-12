"""EMR connection repository — interface + in-memory implementation (ADR-0009).

`ConnectionRecord` is the storage-agnostic twin of `models.EmrConnection`. OAuth
tokens are never part of the record — only the `token_ref` pointing into the secret
store (ADR-0008).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
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


class InMemoryEmrConnectionRepository:
    """Dict-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, ConnectionRecord] = {}

    async def add(self, connection: ConnectionRecord) -> None:
        self._connections[connection.id] = connection

    async def get(self, connection_id: uuid.UUID) -> ConnectionRecord | None:
        return self._connections.get(connection_id)

    async def update(self, connection: ConnectionRecord) -> None:
        self._connections[connection.id] = connection
