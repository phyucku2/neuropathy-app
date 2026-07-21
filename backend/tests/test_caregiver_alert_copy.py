"""Copy guards for the caregiver-alert templates (ADR-0047 Phase B1).

Every alert body carries the non-urgent "not for emergencies, call 911" framing, and
NONE of the templates use alarming or diagnostic vocabulary — a caregiver alert is a
gentle wellness nudge, never a clinical verdict or an emergency instruction. All copy is
fixed and PHI-free (no interpolation of any value).
"""

from __future__ import annotations

from app.models.caregiver import CaregiverAlertType
from app.schemas.caregiver import EMERGENCY_NOTICE
from app.services.caregiver_alert_copy import ALERT_TEMPLATES

# Alarming / diagnostic / urgency vocabulary that must never appear in alert copy. The
# non-urgent 911 framing (EMERGENCY_NOTICE) is the ONLY place the word "emergencies"
# appears — it says the opposite of an emergency instruction — so "emergency" is not
# banned as a bare substring here; every other alarming term is.
_BANNED = (
    "diagnos",  # diagnosis / diagnostic / diagnose
    "urgent",
    "danger",
    "abnormal",
    "critical",
    "severe",
    "worse",  # also catches "worsen"/"worsening"
    "alarm",
    "warning",
    "immediately",
    "asap",
    "call 911 now",  # 911 appears only as the non-urgent framing, never an instruction
)


def test_every_alert_type_has_a_template() -> None:
    assert set(ALERT_TEMPLATES) == set(CaregiverAlertType)


def test_no_alert_copy_uses_banned_vocabulary() -> None:
    for alert_type, copy in ALERT_TEMPLATES.items():
        haystack = f"{copy.title}\n{copy.body}".lower()
        for word in _BANNED:
            assert word not in haystack, f"{alert_type.value} copy uses banned word '{word}'"


def test_every_body_carries_the_911_framing() -> None:
    for alert_type, copy in ALERT_TEMPLATES.items():
        assert EMERGENCY_NOTICE in copy.body, f"{alert_type.value} body is missing the 911 framing"
        # The framing is the canonical non-urgent sentence — it names 911 and says this
        # ISN'T for emergencies.
        assert "911" in copy.body
        assert "isn't for emergencies" in copy.body.lower()


def test_titles_are_short_and_non_empty() -> None:
    for copy in ALERT_TEMPLATES.values():
        assert copy.title.strip()
        assert len(copy.title) <= 60  # 60+ readable, glanceable
