"""API contracts for the EMR endpoints (ADR-0009). Token material never appears here."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.lab import LabResultIn


class ProviderOut(BaseModel):
    key: str
    name: str
    vendor: str
    sandbox_fhir_base: str | None
    note: str


class ConnectStartIn(BaseModel):
    """Start an EMR connection: pick a registry provider OR supply a custom FHIR base.

    patient_id is explicit until app auth lands (ADR-0009 placeholder).
    """

    patient_id: uuid.UUID
    provider_key: str | None = Field(default=None, description="Key from GET /emr/providers")
    fhir_base: str | None = Field(default=None, description="Custom SMART FHIR base URL")

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
    results: list[LabResultIn]
