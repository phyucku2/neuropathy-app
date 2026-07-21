"""Caregiver-alert repositories — interfaces + in-memory implementations (ADR-0047
Phase B1), mirroring repositories/caregiver.py + repositories/patient_capability.py.

Both work directly with ``models.CaregiverAlert`` / ``models.CaregiverAlertPreference``
— the rows the compute-on-read engine (services/caregiver_alert.py) persists and the
feed/ack/preference flows judge, so the scope+preference gate is applied to exactly
what storage holds, never a diverging copy.

``add_if_absent`` mirrors the observation/emr-note idempotent-write contract: the
DB-level UNIQUE index ``uq_caregiver_alert_link_type_dedupe`` is the real invariant, so
a re-read of the feed (or a concurrent evaluator run) never duplicates a row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from app.models.caregiver import CaregiverAlert, CaregiverAlertPreference, CaregiverAlertType
from app.repositories.caregiver import (
    CaregiverLinkRepository,
    InMemoryCaregiverLinkRepository,
)


class CaregiverAlertRepository(Protocol):
    """Persistence contract for the append-only caregiver-alert fact."""

    async def add_if_absent(self, alert: CaregiverAlert) -> bool:
        """Idempotent insert keyed on (caregiver_link_id, alert_type, dedupe_key): persist
        unless an alert with the same logical identity already exists. Returns True if this
        call inserted, False if a matching alert was already on file.

        The compute-on-read engine calls this per candidate on every feed read; the DB
        UNIQUE index makes the duplicate impossible and this returns False rather than
        raising under a concurrent evaluator run (mirrors EmrClinicalNote.add_if_absent)."""
        ...

    async def get(self, alert_id: uuid.UUID) -> CaregiverAlert | None:
        """Fetch an alert by id (the ack flow's ownership/scope re-check reads it)."""
        ...

    async def list_for_link(
        self, caregiver_link_id: uuid.UUID, *, newest_first: bool = True
    ) -> list[CaregiverAlert]:
        """All alerts for one link, newest first by default (the per-patient feed)."""
        ...

    async def list_for_links(self, link_ids: list[uuid.UUID]) -> list[CaregiverAlert]:
        """All alerts across a caregiver's links, newest first (the whole-feed read)."""
        ...

    async def acknowledge(
        self, alert_id: uuid.UUID, caregiver_link_id: uuid.UUID, *, at: datetime
    ) -> bool:
        """Conditional acknowledge: set acknowledged_at only WHERE id=? AND
        caregiver_link_id=? AND acknowledged_at IS NULL. Returns True when this call made
        the transition, False when it was already acked or not owned by this link (drives
        the quiet double-ack — no second audit). Single conditional UPDATE, never
        check-then-write (docs/lessons.md)."""
        ...

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        """Destroy every alert row for one patient (ADR-0027 account deletion). Callers
        own the FK order: this runs BEFORE caregiver_links.delete_for_patient (alerts FK
        the caregiver_link row)."""
        ...

    async def delete_for_caregiver(self, caregiver_user_id: uuid.UUID) -> None:
        """Destroy every alert row for one caregiver account's links (its deletion).
        Runs BEFORE caregiver_links.delete_for_caregiver (alerts FK the caregiver_link)."""
        ...


class CaregiverAlertPreferenceRepository(Protocol):
    """Persistence contract for per-patient, per-type caregiver-alert opt-in (DEFAULT OFF)."""

    async def get(
        self, patient_id: uuid.UUID, alert_type: CaregiverAlertType
    ) -> CaregiverAlertPreference | None:
        """The one preference row for a (patient, type) pair, or None (= OFF)."""
        ...

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[CaregiverAlertPreference]:
        """All of one patient's preference rows, oldest first."""
        ...

    async def upsert(
        self, *, patient_id: uuid.UUID, alert_type: CaregiverAlertType, enabled: bool
    ) -> CaregiverAlertPreference:
        """Create or replace the opt-in state for a (patient, type) pair. Race-safe:
        ``uq_caregiver_alert_preference_patient_type`` guarantees one row per pair even
        under concurrent requests (Postgres absorbs the losing insert and updates)."""
        ...

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        """Destroy every preference row for one patient (ADR-0027 account deletion)."""
        ...


class InMemoryCaregiverAlertRepository:
    """List-backed store for unit tests and DB-less development.

    ``delete_for_caregiver`` resolves the caregiver's link ids through the SAME
    in-memory link repository the caregiver/deletion services share (the Postgres twin
    uses a subquery instead), so the erasure sweep matches storage exactly. The default
    is a fresh empty link store for the bare ``CaregiverAlertService()`` unit-test
    construction — deps wire the shared singleton (app/api/deps.py)."""

    def __init__(self, links: CaregiverLinkRepository | None = None) -> None:
        self._alerts: list[CaregiverAlert] = []
        self._links: CaregiverLinkRepository = links or InMemoryCaregiverLinkRepository()

    async def add_if_absent(self, alert: CaregiverAlert) -> bool:
        # Mirror uq_caregiver_alert_link_type_dedupe: uniqueness on
        # (caregiver_link_id, alert_type, dedupe_key).
        if any(
            a.caregiver_link_id == alert.caregiver_link_id
            and a.alert_type == alert.alert_type
            and a.dedupe_key == alert.dedupe_key
            for a in self._alerts
        ):
            return False
        # Column defaults (id, created_at) only apply on DB flush; mirror them here.
        if alert.id is None:
            alert.id = uuid.uuid4()
        if alert.created_at is None:
            alert.created_at = datetime.now(UTC)
        self._alerts.append(alert)
        return True

    async def get(self, alert_id: uuid.UUID) -> CaregiverAlert | None:
        return next((a for a in self._alerts if a.id == alert_id), None)

    async def list_for_link(
        self, caregiver_link_id: uuid.UUID, *, newest_first: bool = True
    ) -> list[CaregiverAlert]:
        rows = [a for a in self._alerts if a.caregiver_link_id == caregiver_link_id]
        rows.sort(key=lambda a: a.created_at, reverse=newest_first)
        return rows

    async def list_for_links(self, link_ids: list[uuid.UUID]) -> list[CaregiverAlert]:
        wanted = set(link_ids)
        rows = [a for a in self._alerts if a.caregiver_link_id in wanted]
        rows.sort(key=lambda a: a.created_at, reverse=True)
        return rows

    async def acknowledge(
        self, alert_id: uuid.UUID, caregiver_link_id: uuid.UUID, *, at: datetime
    ) -> bool:
        # No await between the check and the set -> atomic in the single event loop
        # (the Postgres twin gets the same guarantee from one conditional UPDATE).
        alert = next((a for a in self._alerts if a.id == alert_id), None)
        if (
            alert is None
            or alert.caregiver_link_id != caregiver_link_id
            or alert.acknowledged_at is not None
        ):
            return False
        alert.acknowledged_at = at
        return True

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        self._alerts = [a for a in self._alerts if a.patient_id != patient_id]

    async def delete_for_caregiver(self, caregiver_user_id: uuid.UUID) -> None:
        links = await self._links.list_for_caregiver(caregiver_user_id)
        wanted = {link.id for link in links}
        self._alerts = [a for a in self._alerts if a.caregiver_link_id not in wanted]


class InMemoryCaregiverAlertPreferenceRepository:
    """Dict-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._rows: dict[tuple[uuid.UUID, CaregiverAlertType], CaregiverAlertPreference] = {}

    async def get(
        self, patient_id: uuid.UUID, alert_type: CaregiverAlertType
    ) -> CaregiverAlertPreference | None:
        return self._rows.get((patient_id, alert_type))

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[CaregiverAlertPreference]:
        rows = [r for r in self._rows.values() if r.patient_id == patient_id]
        return sorted(rows, key=lambda r: r.created_at)

    async def upsert(
        self, *, patient_id: uuid.UUID, alert_type: CaregiverAlertType, enabled: bool
    ) -> CaregiverAlertPreference:
        # Mirror uq_caregiver_alert_preference_patient_type: one row per pair, updated
        # in place.
        row = self._rows.get((patient_id, alert_type))
        if row is None:
            row = CaregiverAlertPreference(
                id=uuid.uuid4(),
                patient_id=patient_id,
                alert_type=alert_type,
                enabled=enabled,
            )
            # Column defaults only apply on DB flush; mirror them here.
            row.created_at = datetime.now(UTC)
            self._rows[(patient_id, alert_type)] = row
        else:
            row.enabled = enabled
        return row

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        self._rows = {key: row for key, row in self._rows.items() if key[0] != patient_id}
