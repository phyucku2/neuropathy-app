"""Observation repository — interface + in-memory implementation (ADR-0006/0007).

Works directly with the research-grade `models.Observation` row (the unified
longitudinal record). Reads return the analyzable dataset only: current,
non-`entered_in_error` records (data-standards.md — "Analytical queries select
current, non-errored records only"), via the same predicate the integrity rules
unit-test (`app.services.observation.counts_toward_analysis`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from app.models.observation import Observation
from app.services.observation import counts_toward_analysis


def _aware(value: datetime) -> datetime:
    """Treat a naive stored timestamp as UTC (defense in depth; intake coerces, but a
    naive row must never crash comparisons or sorting on the read path)."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class ObservationRepository(Protocol):
    """Persistence contract for the unified longitudinal record."""

    async def add(self, observation: Observation) -> Observation:
        """Persist a research-grade Observation (append-only; never an overwrite)."""
        ...

    async def list_for_patient(
        self, patient_id: uuid.UUID, code: str | None = None, since: datetime | None = None
    ) -> list[Observation]:
        """Analyzable records for one patient (optionally one code), oldest first.

        "Analyzable" = non-errored status AND not superseded by a newer row's
        revises_id (data-standards.md: current records only). `since` bounds the
        lookback (hot-path budget) by effective_at; supersession is still computed
        over the patient's full history so a recent correction hides an old original.
        """
        ...

    async def has_import_key(self, patient_id: uuid.UUID, import_key: str) -> bool:
        """Whether a record with this import idempotency key already exists."""
        ...


class InMemoryObservationRepository:
    """List-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._observations: list[Observation] = []

    async def add(self, observation: Observation) -> Observation:
        # Column defaults (id) only apply on DB flush; mirror them here.
        if observation.id is None:
            observation.id = uuid.uuid4()
        self._observations.append(observation)
        return observation

    async def list_for_patient(
        self, patient_id: uuid.UUID, code: str | None = None, since: datetime | None = None
    ) -> list[Observation]:
        superseded = {
            o.revises_id
            for o in self._observations
            if o.patient_id == patient_id and o.revises_id is not None
        }
        rows = [
            o
            for o in self._observations
            if o.patient_id == patient_id
            and (code is None or o.code == code)
            and counts_toward_analysis(o.status)
            and o.id not in superseded
            and (since is None or _aware(o.effective_at) >= since)
        ]
        return sorted(rows, key=lambda o: _aware(o.effective_at))

    async def has_import_key(self, patient_id: uuid.UUID, import_key: str) -> bool:
        return any(
            o.patient_id == patient_id and o.payload.get("import_key") == import_key
            for o in self._observations
        )
