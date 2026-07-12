"""Observation repository — interface + in-memory implementation (ADR-0006/0007).

Works directly with the research-grade `models.Observation` row (the unified
longitudinal record). Reads return the analyzable dataset only: current,
non-`entered_in_error` records (data-standards.md — "Analytical queries select
current, non-errored records only"), via the same predicate the integrity rules
unit-test (`app.services.observation.counts_toward_analysis`).
"""

from __future__ import annotations

import uuid
from typing import Protocol

from app.models.observation import Observation
from app.services.observation import counts_toward_analysis


class ObservationRepository(Protocol):
    """Persistence contract for the unified longitudinal record."""

    async def add(self, observation: Observation) -> Observation:
        """Persist a research-grade Observation (append-only; never an overwrite)."""
        ...

    async def list_for_patient(
        self, patient_id: uuid.UUID, code: str | None = None
    ) -> list[Observation]:
        """Analyzable records for one patient (optionally one code), oldest first."""
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
        self, patient_id: uuid.UUID, code: str | None = None
    ) -> list[Observation]:
        rows = [
            o
            for o in self._observations
            if o.patient_id == patient_id
            and (code is None or o.code == code)
            and counts_toward_analysis(o.status)
        ]
        return sorted(rows, key=lambda o: o.effective_at)
