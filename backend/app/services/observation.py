"""Observation integrity rules (ADR-0006, data-standards.md).

Pure, DB-free predicates encoding the research-grade integrity invariants so they're
locked by unit tests and reused wherever the analytical dataset is assembled.
"""

from __future__ import annotations

from app.models.observation import Observation, ObservationStatus

# Statuses that count toward analysis. `entered_in_error` is retained for the record
# (ALCOA: Enduring) but must never influence a trajectory (ALCOA: Accurate).
_ANALYZABLE_STATUSES = frozenset(
    {
        ObservationStatus.preliminary,
        ObservationStatus.final,
        ObservationStatus.amended,
        ObservationStatus.corrected,
    }
)


def counts_toward_analysis(status: ObservationStatus) -> bool:
    """Whether a record with this status is part of the analytical dataset."""
    return status in _ANALYZABLE_STATUSES


def is_correction(observation: Observation) -> bool:
    """A correction/amendment is a new record that supersedes a prior one."""
    return observation.revises_id is not None
