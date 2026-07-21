"""API contracts for the feature-toggles surface (ADR-0013)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, model_validator

from app.schemas.base import ApiModel


class CapabilityStateOut(BaseModel):
    key: str
    name: str
    active: bool
    # Who currently holds toggle authority for this patient (ADR-0013): 'clinic'
    # while any consented clinic connection is live, 'patient' otherwise (B2C).
    managed_by: Literal["patient", "clinic"]
    expires_at: datetime | None
    # False = the toggle is not wired to its feature yet, so writes are refused
    # (409) and clients must render it read-only (ADR-0013 review finding).
    enforced: bool


class CapabilitiesOut(BaseModel):
    capabilities: list[CapabilityStateOut]


class CapabilitySetIn(ApiModel):
    # Patients set on/off only — expiry is clinician authority (order-style renewal),
    # so the patient contract simply has no such field.
    active: bool


class ClinicianCapabilitySetIn(ApiModel):
    active: bool
    # Optional order-style expiry; must be timezone-aware so expiry comparisons are
    # unambiguous. None = no expiry (stands until changed).
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _expiry_only_on_enable(self) -> ClinicianCapabilitySetIn:
        """Expiry deactivates, it never re-enables: 'active=false until <date>' would
        read as a scheduled re-activation but silently be permanent-off (review
        finding) — refuse the combination instead of storing a false promise."""
        if not self.active and self.expires_at is not None:
            raise ValueError("expires_at only applies when active=true; omit it when disabling")
        return self
