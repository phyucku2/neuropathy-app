"""API contracts for the Caregiver Companion Phase A surfaces (ADR-0047)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.base import ApiModel

# Every caregiver-facing response body carries this framing (ADR-0047): the product
# is a non-urgent wellness trend, never monitoring, never an emergency channel.
EMERGENCY_NOTICE = "This isn't for emergencies. If something's wrong right now, call 911."


class InviteCreateOut(BaseModel):
    """The one-time answer to creating an invite: the plaintext code appears HERE and
    never again (only its hash is stored)."""

    id: uuid.UUID
    code: str
    expires_at: datetime


class InviteOut(BaseModel):
    """An open invite as the patient lists it — the code itself is unrecoverable."""

    id: uuid.UUID
    created_at: datetime
    expires_at: datetime


class ClaimIn(ApiModel):
    code: str = Field(..., min_length=1, max_length=64)


class ClaimOut(BaseModel):
    # One fixed sentence for every outcome — the response must never reveal whether
    # the code matched an invite (no code enumeration).
    detail: str = "If this code is valid, your request is now waiting for the patient's approval."


class CaregiverRegisterIn(ApiModel):
    """Caregiver self-registration: ONLY with a valid invite code (ADR-0047)."""

    code: str = Field(..., min_length=1, max_length=64)
    email: EmailStr
    # NIST 800-63B: length over composition rules (same bar as patient registration).
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=200)


class PatientLinkOut(BaseModel):
    """One caregiver link as the PATIENT sees it — who, scope, lifecycle."""

    id: uuid.UUID
    caregiver_display_name: str
    scope: str
    status: str
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ScopeIn(ApiModel):
    scope: Literal["trends", "full"]


class CaregiverPatientOut(BaseModel):
    """One shared patient as the CAREGIVER sees it: display name + scope only."""

    patient_id: uuid.UUID
    display_name: str
    link_id: uuid.UUID
    scope: str
    accepted_at: datetime


class CaregiverPatientsOut(BaseModel):
    patients: list[CaregiverPatientOut]
    # Non-urgent framing rides with the data (ADR-0047): co-located, not implied.
    emergency_notice: str = EMERGENCY_NOTICE
