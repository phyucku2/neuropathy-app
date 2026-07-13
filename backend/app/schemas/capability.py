"""API contracts for the feature-toggles surface (ADR-0013)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel


class CapabilityStateOut(BaseModel):
    key: str
    name: str
    active: bool
    # Who currently holds toggle authority for this patient (ADR-0013): 'clinic'
    # while any consented clinic connection is live, 'patient' otherwise (B2C).
    managed_by: Literal["patient", "clinic"]
    expires_at: datetime | None


class CapabilitiesOut(BaseModel):
    capabilities: list[CapabilityStateOut]


class CapabilitySetIn(BaseModel):
    # Patients set on/off only — expiry is clinician authority (order-style renewal),
    # so the patient contract simply has no such field.
    active: bool


class ClinicianCapabilitySetIn(BaseModel):
    active: bool
    # Optional order-style expiry; must be timezone-aware so expiry comparisons are
    # unambiguous. None = no expiry (stands until changed).
    expires_at: AwareDatetime | None = None
