"""Tests for the FHIR-aligned lab intake contract (ADR-0007): LOINC-coded, UCUM-united,
and never a numeric value without a unit.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.lab import Interpretation, LabResultIn, LabStatus, ReferenceRange


def test_valid_quantitative_lab_result() -> None:
    r = LabResultIn(
        loinc_code="4548-4",
        display="Hemoglobin A1c",
        value=7.2,
        unit="%",
        effective_at=datetime(2026, 5, 1, tzinfo=UTC),
        reference_range=ReferenceRange(low=4.0, high=5.6, unit="%"),
        interpretation=Interpretation.high,
    )
    assert r.code_system == "LOINC"
    assert r.unit_system == "UCUM"
    assert r.status is LabStatus.final


def test_numeric_value_without_unit_is_rejected() -> None:
    # UCUM unit is mandatory for a quantity (poolable, trendable data).
    with pytest.raises(ValidationError):
        LabResultIn(
            loinc_code="4548-4",
            display="Hemoglobin A1c",
            value=7.2,
            effective_at=datetime(2026, 5, 1, tzinfo=UTC),
        )


def test_result_with_no_value_at_all_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LabResultIn(
            loinc_code="5811-5",
            display="Specific gravity",
            effective_at=datetime(2026, 5, 1, tzinfo=UTC),
        )


def test_qualitative_result_is_allowed_without_unit() -> None:
    r = LabResultIn(
        loinc_code="5802-4",
        display="Nitrite",
        value_text="positive",
        effective_at=datetime(2026, 5, 1, tzinfo=UTC),
        status=LabStatus.preliminary,
    )
    assert r.value is None
    assert r.value_text == "positive"
