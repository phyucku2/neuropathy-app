"""API contracts for the Caregiver Companion Phase B1 alert surfaces (ADR-0047).

PHI-minimal by construction: an alert carries only fixed template copy (title/body) +
references + the patient's display name (already surfaced on the Phase A patient list)
— never a value, a code label, or note text. The non-urgent 911 framing rides the feed
envelope (``EMERGENCY_NOTICE``), co-located with the data as Phase A does.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.base import ApiModel
from app.schemas.caregiver import EMERGENCY_NOTICE

AlertTypeLiteral = Literal["missed_checkin", "med_change", "trend_shift", "new_chart_note"]


class CaregiverAlertOut(BaseModel):
    """One alert as the CAREGIVER sees it — template copy + refs only, never a value."""

    id: uuid.UUID
    alert_type: AlertTypeLiteral
    patient_id: uuid.UUID
    patient_display_name: str
    title: str
    body: str
    created_at: datetime
    acknowledged_at: datetime | None


class CaregiverAlertsOut(BaseModel):
    alerts: list[CaregiverAlertOut]
    # Non-urgent framing rides with the data (ADR-0047): co-located, not implied.
    emergency_notice: str = EMERGENCY_NOTICE


class AlertPreferenceOut(BaseModel):
    """One per-type opt-in flag as the PATIENT sees it (DEFAULT OFF)."""

    alert_type: AlertTypeLiteral
    enabled: bool


class AlertPreferencesOut(BaseModel):
    preferences: list[AlertPreferenceOut]


class AlertPreferenceIn(ApiModel):
    enabled: bool
