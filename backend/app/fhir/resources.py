"""Typed subset of FHIR R4 resources needed for laboratory Observations.

These Pydantic models serialize to / parse from canonical FHIR JSON (camelCase via
aliases). Only the elements we use are modeled; unknown fields are ignored on parse so
we tolerate richer real-world resources.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Canonical FHIR system URIs.
LOINC_SYSTEM = "http://loinc.org"
UCUM_SYSTEM = "http://unitsofmeasure.org"
CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-category"
INTERPRETATION_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"


class _FhirBase(BaseModel):
    # Accept both alias (FHIR camelCase) and field name; ignore unknown FHIR elements.
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class Coding(_FhirBase):
    system: str | None = None
    code: str | None = None
    display: str | None = None


class CodeableConcept(_FhirBase):
    coding: list[Coding] = Field(default_factory=list)
    text: str | None = None


class Quantity(_FhirBase):
    value: float | None = None
    unit: str | None = None
    system: str | None = None
    code: str | None = None


class Reference(_FhirBase):
    reference: str | None = None


class ObservationReferenceRange(_FhirBase):
    low: Quantity | None = None
    high: Quantity | None = None


class Observation(_FhirBase):
    """FHIR R4 Observation — laboratory subset."""

    resource_type: str = Field(default="Observation", alias="resourceType")
    id: str | None = None
    status: str
    category: list[CodeableConcept] = Field(default_factory=list)
    code: CodeableConcept
    subject: Reference | None = None
    effective_date_time: datetime | None = Field(default=None, alias="effectiveDateTime")
    issued: datetime | None = None
    value_quantity: Quantity | None = Field(default=None, alias="valueQuantity")
    value_string: str | None = Field(default=None, alias="valueString")
    reference_range: list[ObservationReferenceRange] = Field(
        default_factory=list, alias="referenceRange"
    )
    interpretation: list[CodeableConcept] = Field(default_factory=list)

    def to_fhir_json(self) -> dict[str, object]:
        """Serialize to canonical FHIR JSON (camelCase, no nulls)."""
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")


class BundleEntry(_FhirBase):
    resource: Observation


class Bundle(_FhirBase):
    resource_type: str = Field(default="Bundle", alias="resourceType")
    type: str = "collection"
    entry: list[BundleEntry] = Field(default_factory=list)

    def to_fhir_json(self) -> dict[str, object]:
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")
