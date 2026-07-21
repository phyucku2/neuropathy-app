"""API contracts for the EMR endpoints (ADR-0009). Token material never appears here."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.lab import LabResultIn


class ProviderOut(BaseModel):
    key: str
    name: str
    vendor: str
    sandbox_fhir_base: str | None
    note: str


class ConnectStartIn(ApiModel):
    """Start an EMR connection: pick a registry provider OR supply a custom FHIR base.

    The patient is the authenticated caller (ADR-0010) — never supplied by the client.
    """

    provider_key: str | None = Field(default=None, description="Key from GET /emr/providers")
    fhir_base: str | None = Field(default=None, description="Custom SMART FHIR base URL")
    # Per-connection opt-in to also request clinical-note read on the EHR consent screen
    # (ADR-0045 P2 #27). Default off so a labs-only connection is not forced to ask for
    # patient/DocumentReference.rs — the pull enforces the granted scope at pull time.
    connect_notes: bool = Field(
        default=False, description="Also request clinical-note (DocumentReference) read access"
    )

    @model_validator(mode="after")
    def _require_a_target(self) -> ConnectStartIn:
        if self.provider_key is None and self.fhir_base is None:
            raise ValueError("provide provider_key or fhir_base")
        return self


class ConnectStartOut(BaseModel):
    connection_id: uuid.UUID
    authorize_url: str = Field(..., description="Open this in the patient's browser")
    state: str


class ConnectionOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    fhir_base: str
    provider_name: str | None
    status: str
    granted_scope: str | None
    patient_fhir_id: str | None
    token_expires_at: datetime | None
    revoked_at: datetime | None


class PullOut(BaseModel):
    imported: int
    # Un-mappable EHR search-set entries that were skipped (non-final status, panel with no
    # value, non-LOINC code, missing unit/time, non-Observation) — reported, never fatal.
    skipped: int = 0
    results: list[LabResultIn]


class ClinicalNoteIn(ApiModel):
    """One clinical note parsed from a FHIR DocumentReference — METADATA ONLY (ADR-0045 P2).

    NEVER carries the note body: the text is fetched lazily from the Binary on demand and
    never summarized, scanned, or fed to the AI narrator. `attachment_url` is the opaque
    Binary reference for that lazy fetch, not content.
    """

    document_fhir_id: str | None = None
    type_code: str | None = None
    type_display: str | None = None
    authored_at: datetime
    author_display: str | None = None
    encounter_fhir_id: str | None = None
    content_type: str | None = None
    attachment_url: str | None = None
    has_inline_data: bool = False


class PullNotesOut(BaseModel):
    """Result of a clinical-note pull — COUNTS ONLY (no note text ever leaves here)."""

    imported: int
    # DocumentReference entries skipped as un-mappable (non-DocumentReference, missing
    # type/date/attachment, OperationOutcome) — reported, never fatal.
    skipped: int = 0
    fetched: int = 0
