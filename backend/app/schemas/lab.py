"""FHIR-aligned lab result schema (ADR-0007).

Mirrors HL7 FHIR R4 `Observation` for laboratory results: a LOINC-coded concept, a
UCUM-quantified value, effective/issued timestamps, a status, and reference range +
interpretation. This is the validation contract for lab intake; full FHIR resource
import/export is a later increment.
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class LabStatus(enum.StrEnum):
    """Subset of FHIR Observation.status relevant to lab results."""

    preliminary = "preliminary"  # e.g. OCR-extracted, not yet confirmed
    final = "final"  # confirmed
    amended = "amended"
    corrected = "corrected"
    entered_in_error = "entered_in_error"


class Interpretation(enum.StrEnum):
    """FHIR-style result interpretation (v3 ObservationInterpretation)."""

    normal = "N"
    high = "H"
    low = "L"
    abnormal = "A"


class ReferenceRange(BaseModel):
    low: float | None = None
    high: float | None = None
    unit: str | None = Field(default=None, description="UCUM unit for the range bounds")


class LabResultIn(BaseModel):
    """One lab analyte result on intake (FHIR Observation, category = laboratory)."""

    loinc_code: str = Field(..., description="LOINC code (FHIR Observation.code)")
    source_record_id: str | None = Field(
        default=None, description="The source system's own record id (FHIR Observation.id)"
    )
    display: str = Field(..., description="Human-readable analyte name, e.g. 'Hemoglobin A1c'")

    value: float | None = Field(default=None, description="Quantity value (valueQuantity.value)")
    value_text: str | None = Field(default=None, description="Qualitative result (valueString)")
    unit: str | None = Field(default=None, description="UCUM unit (valueQuantity.code/unit)")

    effective_at: datetime = Field(
        ..., description="When the result applies (FHIR effectiveDateTime)"
    )
    issued_at: datetime | None = Field(
        default=None, description="When made available (FHIR issued)"
    )

    status: LabStatus = LabStatus.final
    reference_range: ReferenceRange | None = None
    interpretation: Interpretation | None = None

    # UCUM coding system is fixed for lab quantities; LOINC for the code.
    code_system: str = "LOINC"
    unit_system: str = "UCUM"

    @model_validator(mode="after")
    def _require_a_value(self) -> LabResultIn:
        if self.value is None and self.value_text is None:
            raise ValueError("a lab result must have either a numeric value or a text value")
        if self.value is not None and self.unit is None:
            raise ValueError("a numeric lab value must carry a UCUM unit")
        return self
