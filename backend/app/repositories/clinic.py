"""Clinic repository — interface + in-memory implementation (ADR-0012).

Works directly with `models.Clinic` (identity + display name only, no secrets); the
Postgres implementation lives in repositories/postgres.py like the others.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from app.models.clinic import Clinic


class ClinicRepository(Protocol):
    """Persistence contract for servicing clinics."""

    async def add(self, clinic: Clinic) -> Clinic:
        """Persist a new clinic."""
        ...

    async def get(self, clinic_id: uuid.UUID) -> Clinic | None:
        """Fetch a clinic by id."""
        ...


class InMemoryClinicRepository:
    """Dict-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._clinics: dict[uuid.UUID, Clinic] = {}

    async def add(self, clinic: Clinic) -> Clinic:
        # Column defaults (id, created_at) only apply on DB flush; mirror them here.
        if clinic.id is None:
            clinic.id = uuid.uuid4()
        if clinic.created_at is None:
            clinic.created_at = datetime.now(UTC)
        self._clinics[clinic.id] = clinic
        return clinic

    async def get(self, clinic_id: uuid.UUID) -> Clinic | None:
        return self._clinics.get(clinic_id)
