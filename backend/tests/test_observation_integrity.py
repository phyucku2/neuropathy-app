"""Tests for research-grade integrity rules (ADR-0006): errored data is retained but
never analyzed, and corrections are superseding records.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.services.observation import counts_toward_analysis, is_correction


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ObservationStatus.preliminary, True),
        (ObservationStatus.final, True),
        (ObservationStatus.amended, True),
        (ObservationStatus.corrected, True),
        (ObservationStatus.entered_in_error, False),  # retained, but excluded
    ],
)
def test_counts_toward_analysis(status: ObservationStatus, expected: bool) -> None:
    assert counts_toward_analysis(status) is expected


def _obs(revises: object = None) -> Observation:
    return Observation(
        patient_id=uuid4(),
        source=SourceType.lab,
        origin=DataOrigin.document_imported,
        code="hba1c",
        effective_at=datetime.now(UTC),
        recorded_at=datetime.now(UTC),
        revises_id=revises,
    )


def test_original_record_is_not_a_correction() -> None:
    assert is_correction(_obs()) is False


def test_record_that_supersedes_another_is_a_correction() -> None:
    assert is_correction(_obs(revises=uuid4())) is True
