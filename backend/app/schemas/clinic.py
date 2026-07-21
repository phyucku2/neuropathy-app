"""API contracts for the clinician surface and patient consent flow (ADR-0012)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.base import ApiModel


class ClinicianCreateIn(ApiModel):
    email: EmailStr
    # NIST 800-63B: length over composition rules (same bar as patient registration).
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=200)
    # Join an existing clinic by id, or found a new one by name — exactly one path.
    clinic_id: uuid.UUID | None = None
    clinic_name: str | None = Field(None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _one_clinic_reference(self) -> ClinicianCreateIn:
        if (self.clinic_id is None) == (self.clinic_name is None):
            raise ValueError("Provide exactly one of clinic_id or clinic_name")
        return self


class ClinicianOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    clinic_id: uuid.UUID
    clinic_name: str


class InvitationIn(ApiModel):
    email: EmailStr


class InvitationOut(BaseModel):
    # One fixed sentence for every outcome — the response must never reveal whether
    # the email matched a patient account (no enumeration).
    detail: str = "If this email belongs to a patient account, an invitation is now pending."


class ConnectionOut(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    clinic_name: str
    status: str
    initiated_by: str
    consent_granted_at: datetime | None
    revoked_at: datetime | None


class PanelPatientOut(BaseModel):
    patient_id: uuid.UUID
    display_name: str
    connection_id: uuid.UUID
    consent_granted_at: datetime


class PanelOut(BaseModel):
    patients: list[PanelPatientOut]
