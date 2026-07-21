"""Caregiver-alert copy (ADR-0047 Phase B1) — non-urgent, non-diagnostic templates.

Every alert surface carries the SAME framing the Phase A surfaces do
(``EMERGENCY_NOTICE`` from schemas/caregiver.py): a caregiver alert is a non-urgent
wellness nudge, never monitoring and never an emergency channel. The copy is fixed and
PHI-free — a template constant per type, never a patient name, value, or note text — so
the push payload and the feed body can reuse it verbatim.

The banned-word test (tests/test_caregiver_alert_copy.py) asserts none of the
alarming/diagnostic vocabulary appears and that the 911 framing is co-located on every
body. Plain 60+ language, AA-friendly, non-diagnostic by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.caregiver import CaregiverAlertType
from app.schemas.caregiver import EMERGENCY_NOTICE


@dataclass(frozen=True)
class AlertCopy:
    """One alert's fixed, non-diagnostic title + body (the 911 framing rides the body)."""

    title: str
    body: str


def _body(lead: str) -> str:
    """Co-locate the non-urgent 911 framing on every alert body (ADR-0047)."""
    return f"{lead} {EMERGENCY_NOTICE}"


ALERT_TEMPLATES: dict[CaregiverAlertType, AlertCopy] = {
    CaregiverAlertType.missed_checkin: AlertCopy(
        title="A check-in was missed",
        body=_body(
            "It's been a little while since the last daily check-in. "
            "You might want to check in the next time you talk."
        ),
    ),
    CaregiverAlertType.med_change: AlertCopy(
        title="A medication update",
        body=_body(
            "There's been an update to the medication list. "
            "You can see the details in the app when you have a moment."
        ),
    ),
    CaregiverAlertType.trend_shift: AlertCopy(
        title="A shift in the wellness trend",
        body=_body(
            "The weekly wellness trend has shifted. Take a look in the app when you get a chance."
        ),
    ),
    CaregiverAlertType.new_chart_note: AlertCopy(
        title="A new note from the care team",
        body=_body(
            "A new note from the care team is now on file. "
            "You can find it in the app when you have a moment."
        ),
    ),
}
