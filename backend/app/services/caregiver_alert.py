"""Caregiver-alert service — compute-on-read evaluators, scope gate, feed, ack, and
per-type patient opt-in (ADR-0047 Phase B1).

Phase B1 adds the alert engine on top of Phase A's relationship & consent. There is NO
scheduler: the four evaluators run when the caregiver READS their feed, and every
candidate they find is persisted idempotently via ``add_if_absent`` on
``uq_caregiver_alert_link_type_dedupe`` — so a re-read never duplicates a row.

Three invariants hold the surface together:

- **Single consent predicate.** Every alert access flows through
  ``CaregiverService.patients_for_caregiver`` / ``link_for_caregiver`` — the only
  callers of ``_may_caregiver_read``. No second access path is added here.
- **Scope leakage is a defect.** An alert is emitted, shown, AND ack-able ONLY when the
  link is active+accepted, the patient's per-type preference is ON, AND the type is
  allowed for the link's scope. Feed filtering and ack authorization both re-check
  ``type_allowed_for_scope`` + preference, so a trends-only caregiver gets a 404 even
  for the *existence* of a ``med_change`` / ``new_chart_note`` alert.
- **Audit is PHI-free.** Refs/counts only — one ``caregiver_alert_feed`` per read, one
  ``caregiver_alert_ack`` per real transition (never a double-ack), one
  ``set_caregiver_alert_preference`` per change (CLAUDE.md §5).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.models.audit import AuditEvent
from app.models.caregiver import (
    CaregiverAlert,
    CaregiverAlertType,
    CaregiverLink,
    CaregiverScope,
)
from app.models.observation import SourceType
from app.models.user import UserRole
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.caregiver_alert import (
    CaregiverAlertPreferenceRepository,
    CaregiverAlertRepository,
    InMemoryCaregiverAlertPreferenceRepository,
    InMemoryCaregiverAlertRepository,
)
from app.repositories.emr_clinical_note import (
    EmrClinicalNoteRepository,
    InMemoryEmrClinicalNoteRepository,
)
from app.repositories.observation import InMemoryObservationRepository, ObservationRepository
from app.services.caregiver import CaregiverService
from app.services.caregiver_alert_copy import ALERT_TEMPLATES
from app.services.push import PushMessage
from app.services.trajectory import compute_patient_trajectory

__all__ = [
    "CaregiverAlertService",
    "type_allowed_for_scope",
]

# No ADL check-in within this many days is a "missed check-in" (ADR-0047 B1).
_MISSED_CHECKIN_DAYS = 7

# Compute-on-read lookback for the event-shaped alerts (med_change, new_chart_note):
# only events inside this window become alerts. Idempotent regardless (dedupe on the
# event's stable identity), so the window only bounds which recent events surface.
_EVENT_LOOKBACK = timedelta(days=30)

# The one place scope maps to allowed alert types (ADR-0047 B1). trends: the two
# non-clinical signals only; full: all four. Unit-locked in tests.
_SCOPE_MATRIX: dict[CaregiverScope, set[CaregiverAlertType]] = {
    CaregiverScope.trends: {
        CaregiverAlertType.missed_checkin,
        CaregiverAlertType.trend_shift,
    },
    CaregiverScope.full: set(CaregiverAlertType),
}


def type_allowed_for_scope(alert_type: CaregiverAlertType, scope: CaregiverScope) -> bool:
    """Whether a link at ``scope`` may ever see ``alert_type`` (ADR-0047 B1). The single
    scope gate: a trends-only caregiver never sees (or acks, or learns the existence of)
    ``med_change`` / ``new_chart_note`` — scope leakage is a defect."""
    return alert_type in _SCOPE_MATRIX[scope]


@dataclass
class CaregiverAlertService:
    """Compute-on-read alert engine over the Phase A consent primitive (ADR-0047 B1).

    ``caregivers`` is the SINGLE predicate source — access is never re-derived here.
    In-memory defaults serve unit tests and DB-less development; deps wire the Postgres
    twins and share the process singletons so every feature reads the same rows.
    """

    caregivers: CaregiverService = field(default_factory=CaregiverService)
    alerts: CaregiverAlertRepository = field(default_factory=InMemoryCaregiverAlertRepository)
    preferences: CaregiverAlertPreferenceRepository = field(
        default_factory=InMemoryCaregiverAlertPreferenceRepository
    )
    observations: ObservationRepository = field(default_factory=InMemoryObservationRepository)
    clinical_notes: EmrClinicalNoteRepository = field(
        default_factory=InMemoryEmrClinicalNoteRepository
    )
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)
    # The PHI-free push messages for alerts newly inserted on the LAST feed read
    # (ADR-0047 B2). The route reads these right after ``feed_for_caregiver`` returns and
    # schedules the post-commit fan-out (services/caregiver_push_dispatch.py) — so the
    # real FCM send runs AFTER the request transaction commits, never inside it, and a
    # rolled-back feed read pushes nothing. Reset at the start of every feed read.
    _pending_pushes: list[PushMessage] = field(default_factory=list, repr=False)

    @property
    def pending_pushes(self) -> list[PushMessage]:
        """The push messages accrued on the most recent ``feed_for_caregiver`` — one per
        newly-inserted alert, never a duplicate (``add_if_absent`` False accrues nothing).
        Read by the route to schedule the post-commit fan-out."""
        return self._pending_pushes

    # ---------------------------------------------------------------- evaluators

    async def _eval_missed_checkin(self, patient_id: uuid.UUID, *, now: datetime) -> list[str]:
        """A missed-check-in candidate: no ADL observation in the last N days. dedupe_key
        is the missed-window date key (one per missed-window day), so the same missed day
        never re-alerts. Returns [] when a check-in exists in the window."""
        recent = await self.observations.list_for_patient(
            patient_id, since=now - timedelta(days=_MISSED_CHECKIN_DAYS), source=SourceType.adl
        )
        if recent:
            return []
        return [now.date().isoformat()]

    async def _eval_med_change(
        self, patient_id: uuid.UUID, *, now: datetime, since: datetime
    ) -> list[str]:
        """Med-change candidates: each medication observation in the window is one event,
        dedupe_key = its observation id (the med-change event id)."""
        rows = await self.observations.list_for_patient(
            patient_id, since=since, source=SourceType.medication
        )
        return [str(row.id) for row in rows]

    async def _eval_trend_shift(self, patient_id: uuid.UUID, *, now: datetime) -> list[str]:
        """Trend-shift candidates: a contributing signal that is currently MOVING
        (improving/declining, not stable/insufficient) yields one alert per code per ISO
        week. dedupe_key = f"{code}:{iso_year}-W{iso_week:02d}", so a code re-alerts at
        most once per ISO week (the compute-on-read read of the shared trajectory)."""
        trajectory, _ = await compute_patient_trajectory(self.observations, patient_id, now=now)
        iso = now.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        moving = {"improving", "declining"}
        keys: list[str] = []
        seen: set[str] = set()
        for signal in trajectory.signals:
            if signal.direction.value not in moving:
                continue
            key = f"{signal.code}:{week_key}"
            if key not in seen:
                seen.add(key)
                keys.append(key)
        return keys

    async def _eval_new_chart_note(
        self, patient_id: uuid.UUID, *, now: datetime, since: datetime
    ) -> list[str]:
        """New-chart-note candidates: each pulled clinical note in the window is one
        event, dedupe_key = the note's stable import_key (the same key
        ``NewChartNoteSignal`` carries). Notes without an import_key are skipped — a
        null key has no stable identity to dedupe on."""
        notes = await self.clinical_notes.list_for_patient(patient_id, since=since)
        return [note.import_key for note in notes if note.import_key is not None]

    async def _eval_for_type(
        self,
        alert_type: CaregiverAlertType,
        patient_id: uuid.UUID,
        *,
        now: datetime,
        since: datetime,
    ) -> list[str]:
        if alert_type is CaregiverAlertType.missed_checkin:
            return await self._eval_missed_checkin(patient_id, now=now)
        if alert_type is CaregiverAlertType.med_change:
            return await self._eval_med_change(patient_id, now=now, since=since)
        if alert_type is CaregiverAlertType.trend_shift:
            return await self._eval_trend_shift(patient_id, now=now)
        return await self._eval_new_chart_note(patient_id, now=now, since=since)

    # ---------------------------------------------------------------- persistence

    async def _preference_on(self, patient_id: uuid.UUID, alert_type: CaregiverAlertType) -> bool:
        """The patient's opt-in for this type — DEFAULT OFF when no row exists."""
        pref = await self.preferences.get(patient_id, alert_type)
        return pref is not None and pref.enabled

    async def _persist(
        self,
        link: CaregiverLink,
        alert_type: CaregiverAlertType,
        dedupe_keys: list[str],
        *,
        caregiver_user_id: uuid.UUID,
        now: datetime,
        pending: list[PushMessage],
    ) -> None:
        """Idempotently persist each candidate for a (link, type). Gated by scope AND
        preference (defense in depth — callers gate too). A newly-inserted alert accrues a
        PHI-free push message onto ``pending`` (the route schedules the post-commit
        fan-out); a re-read (add_if_absent -> False) accrues nothing, so a push fires
        exactly once per new alert and never on a duplicate."""
        del now  # kept for signature parity with the other persist-time helpers
        if not type_allowed_for_scope(alert_type, link.scope):
            return
        if not await self._preference_on(link.patient_id, alert_type):
            return
        template = ALERT_TEMPLATES[alert_type]
        for key in dedupe_keys:
            alert = CaregiverAlert(
                patient_id=link.patient_id,
                caregiver_link_id=link.id,
                alert_type=alert_type,
                dedupe_key=key,
            )
            inserted = await self.alerts.add_if_absent(alert)
            if inserted:
                pending.append(
                    PushMessage(
                        caregiver_user_id=caregiver_user_id,
                        alert_type=alert_type.value,
                        alert_id=alert.id,
                        title=template.title,
                        body=template.body,
                    )
                )

    # ---------------------------------------------------------------- caregiver: feed

    async def feed_for_caregiver(
        self, caregiver_user_id: uuid.UUID, *, now: datetime
    ) -> list[tuple[CaregiverAlert, str]]:
        """Run the evaluators for every readable patient, persist new candidates, then
        return the scope+preference-gated alert feed (each alert with its patient's
        display name). A scope or preference change hides prior alerts — no leakage.
        Writes ONE PHI-free ``caregiver_alert_feed`` audit event (counts only)."""
        entries = await self.caregivers.patients_for_caregiver(caregiver_user_id)
        link_by_id: dict[uuid.UUID, tuple[CaregiverLink, str]] = {}
        since = now - _EVENT_LOOKBACK
        # Accrue this read's new-alert pushes into a LOCAL list, published to
        # ``_pending_pushes`` only at the very end (no await between publish and return),
        # so a concurrent feed read on the shared in-memory singleton can never mix its
        # pushes into this one in the cooperative event loop.
        pending: list[PushMessage] = []
        for link, user in entries:
            link_by_id[link.id] = (link, user.display_name)
            for alert_type in CaregiverAlertType:
                if not type_allowed_for_scope(alert_type, link.scope):
                    continue
                if not await self._preference_on(link.patient_id, alert_type):
                    continue
                keys = await self._eval_for_type(alert_type, link.patient_id, now=now, since=since)
                await self._persist(
                    link,
                    alert_type,
                    keys,
                    caregiver_user_id=caregiver_user_id,
                    now=now,
                    pending=pending,
                )

        visible: list[tuple[CaregiverAlert, str]] = []
        for alert in await self.alerts.list_for_links(list(link_by_id)):
            entry = link_by_id.get(alert.caregiver_link_id)
            if entry is None:
                continue
            link, display_name = entry
            # Re-check the gate on the READ path too — a scope/pref change since the row
            # was written must hide it (no scope leakage).
            if not type_allowed_for_scope(alert.alert_type, link.scope):
                continue
            if not await self._preference_on(link.patient_id, alert.alert_type):
                continue
            visible.append((alert, display_name))

        await self.audit.add(
            AuditEvent(
                actor_id=caregiver_user_id,
                actor_role=UserRole.caregiver.value,
                action="caregiver_alert_feed",
                patient_id=None,
                detail={"patients": len(link_by_id), "alerts": len(visible)},
            )
        )
        # Publish atomically (no await between here and return): the route reads
        # ``pending_pushes`` immediately after this call.
        self._pending_pushes = pending
        return visible

    async def acknowledge(
        self, *, caregiver_user_id: uuid.UUID, alert_id: uuid.UUID, now: datetime
    ) -> bool | None:
        """Acknowledge an alert. Returns None (-> 404) when it is unknown, not this
        caregiver's, or hidden by scope/preference (404-over-403 — existence must not
        leak). Returns True when this call made the transition, False for a quiet
        double-ack (already acknowledged). Audits ``caregiver_alert_ack`` ONLY on a real
        transition — a double-ack writes no second event."""
        alert = await self.alerts.get(alert_id)
        if alert is None:
            return None
        link = await self.caregivers.link_for_caregiver(
            caregiver_user_id=caregiver_user_id, patient_id=alert.patient_id
        )
        if (
            link is None
            or alert.caregiver_link_id != link.id
            or not type_allowed_for_scope(alert.alert_type, link.scope)
            or not await self._preference_on(link.patient_id, alert.alert_type)
        ):
            return None
        changed = await self.alerts.acknowledge(alert_id, link.id, at=now)
        if changed:
            await self.audit.add(
                AuditEvent(
                    actor_id=caregiver_user_id,
                    actor_role=UserRole.caregiver.value,
                    action="caregiver_alert_ack",
                    patient_id=alert.patient_id,
                    detail={"alert_id": str(alert_id), "alert_type": alert.alert_type.value},
                )
            )
        return changed

    # ---------------------------------------------------------------- patient: prefs

    async def list_preferences(
        self, patient_id: uuid.UUID
    ) -> list[tuple[CaregiverAlertType, bool]]:
        """Every alert type with its opt-in flag for this patient — DEFAULT OFF when no
        row exists, so the full set always renders (no missing toggles)."""
        rows = {
            row.alert_type: row.enabled
            for row in await self.preferences.list_for_patient(patient_id)
        }
        return [(alert_type, rows.get(alert_type, False)) for alert_type in CaregiverAlertType]

    async def set_preference(
        self,
        *,
        patient_id: uuid.UUID,
        actor_id: uuid.UUID,
        alert_type: CaregiverAlertType,
        enabled: bool,
        now: datetime,
    ) -> bool:
        """Set the patient's opt-in for one type. A no-change write is a quiet success
        (no audit event, mirroring change_scope); a real change upserts and writes one
        PHI-free ``set_caregiver_alert_preference`` event (type + flag only). Returns the
        resulting enabled state."""
        del now  # no time-based term; kept for signature parity with the other setters
        if await self._preference_on(patient_id, alert_type) == enabled:
            return enabled
        await self.preferences.upsert(patient_id=patient_id, alert_type=alert_type, enabled=enabled)
        await self.audit.add(
            AuditEvent(
                actor_id=actor_id,
                actor_role=UserRole.patient.value,
                action="set_caregiver_alert_preference",
                patient_id=patient_id,
                detail={"alert_type": alert_type.value, "enabled": enabled},
            )
        )
        return enabled
