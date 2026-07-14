"""Per-patient capability activation repository — interface + in-memory implementation
(ADR-0013).

Works directly with `models.PatientCapability` — the row the effective-state
computation judges (active + expiry + who set it). One row per (patient, capability):
`upsert` owns that invariant, race-safely in Postgres via `uq_patient_capability`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from app.models.capability import Actor, PatientCapability


class PatientCapabilityRepository(Protocol):
    """Persistence contract for per-patient capability activation state."""

    async def get(
        self, patient_id: uuid.UUID, capability_id: uuid.UUID
    ) -> PatientCapability | None:
        """Fetch the one activation row for a (patient, capability) pair."""
        ...

    async def upsert(
        self,
        *,
        patient_id: uuid.UUID,
        capability_id: uuid.UUID,
        active: bool,
        set_by: Actor,
        expires_at: datetime | None,
    ) -> PatientCapability:
        """Create or replace the activation state for a (patient, capability) pair.

        Race-safe: `uq_patient_capability` guarantees one row per pair even under
        concurrent requests (Postgres absorbs the losing insert and updates instead).
        """
        ...

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[PatientCapability]:
        """All of one patient's activation rows, oldest first."""
        ...

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        """Destroy every activation row for one patient (ADR-0027 account deletion)."""
        ...


class InMemoryPatientCapabilityRepository:
    """Dict-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._rows: dict[tuple[uuid.UUID, uuid.UUID], PatientCapability] = {}

    async def get(
        self, patient_id: uuid.UUID, capability_id: uuid.UUID
    ) -> PatientCapability | None:
        return self._rows.get((patient_id, capability_id))

    async def upsert(
        self,
        *,
        patient_id: uuid.UUID,
        capability_id: uuid.UUID,
        active: bool,
        set_by: Actor,
        expires_at: datetime | None,
    ) -> PatientCapability:
        # Mirror uq_patient_capability: one row per pair, updated in place.
        row = self._rows.get((patient_id, capability_id))
        if row is None:
            row = PatientCapability(
                id=uuid.uuid4(),
                patient_id=patient_id,
                capability_id=capability_id,
                active=active,
                set_by=set_by,
                expires_at=expires_at,
            )
            # Column defaults only apply on DB flush; mirror them here.
            row.created_at = datetime.now(UTC)
            self._rows[(patient_id, capability_id)] = row
        else:
            row.active = active
            row.set_by = set_by
            row.expires_at = expires_at
        return row

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[PatientCapability]:
        rows = [r for r in self._rows.values() if r.patient_id == patient_id]
        return sorted(rows, key=lambda r: r.created_at)

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        self._rows = {key: row for key, row in self._rows.items() if key[0] != patient_id}
