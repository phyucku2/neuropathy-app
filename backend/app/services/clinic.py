"""Clinic service — the clinician surface's flows: invite, consent, panel (ADR-0012).

Storage lives behind the injected repositories (in-memory defaults for unit tests and
DB-less development; Postgres in deployment). Two invariants are enforced here, not
in routes:

- **Consent gates every clinician read.** `connection_for_clinician` answers only via
  `may_transmit_to_clinic` (app/services/connection.py) — the single, unit-locked
  predicate from ADR-0005. No consented connection, no data; callers translate the
  None to a 404 so non-consented records are indistinguishable from nonexistent ones.
- **Invitations never enumerate accounts.** `invite_patient` returns nothing either
  way; a matching patient email creates a pending connection, a non-matching one only
  writes an audit event. The HTTP response is identical in both cases.

Invitations are additionally rate-limited per clinician (ADR-0012 deferral ->
ADR-0017): the sliding-window limiter counts prior 'invite_patient' audit events and
fires BEFORE the email lookup, so a refusal can never depend on — or reveal — whether
the probed email matches an account.

Consent grants/revocations and invitations are audit-logged here so no route can
perform them unaccounted (CLAUDE.md §5).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.clinic import Clinic
from app.models.connection import ClinicConnection, ConnectionStatus, Initiator
from app.models.user import UserRole
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.clinic import ClinicRepository, InMemoryClinicRepository
from app.repositories.clinic_connection import (
    ClinicConnectionRepository,
    DuplicateLiveConnectionError,
    InMemoryClinicConnectionRepository,
)
from app.repositories.observation import InMemoryObservationRepository, ObservationRepository
from app.repositories.user import InMemoryUserRepository, UserRecord, UserRepository
from app.services.connection import may_transmit_to_clinic
from app.services.rate_limit import RateLimitExceededError, SlidingWindowRateLimiter

__all__ = ["ClinicService", "PanelEntry", "invitation_rate_limiter"]


def invitation_rate_limiter(counter: AuditEventRepository) -> SlidingWindowRateLimiter:
    """The settings-driven per-clinician invitation limiter (ADR-0017), counting the
    'invite_patient' audit events the invite flow already writes — one per ACCEPTED
    attempt, matched or not ('rate_limited' refusals deliberately do not count, so a
    refused clinician's budget still frees up as the window slides)."""
    return SlidingWindowRateLimiter(
        counter=counter,
        action="invite_patient",
        max_events=settings.invite_rate_limit_max,
        window=timedelta(seconds=settings.invite_rate_limit_window_seconds),
    )


@dataclass(frozen=True)
class PanelEntry:
    """One panel row: the consented connection plus the patient user behind it."""

    connection: ClinicConnection
    patient_user: UserRecord


@dataclass
class ClinicService:
    clinics: ClinicRepository = field(default_factory=InMemoryClinicRepository)
    connections: ClinicConnectionRepository = field(
        default_factory=InMemoryClinicConnectionRepository
    )
    users: UserRepository = field(default_factory=InMemoryUserRepository)
    observations: ObservationRepository = field(default_factory=InMemoryObservationRepository)
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)

    async def create_clinic(self, *, name: str) -> Clinic:
        return await self.clinics.add(Clinic(name=name))

    async def invite_patient(
        self, *, clinic_id: uuid.UUID, actor_id: uuid.UUID, email: str
    ) -> None:
        """Invite a patient by email; clinic-initiated pending connection on a match.

        Deliberately returns nothing: the route answers 202 with a byte-identical
        body either way, and the connection lookup runs for matched and unmatched
        emails alike so steady-state response timing does not reveal a match (the
        one-time INSERT on a first successful invite remains a residual single-shot
        signal — ADR-0012). Duplicate invitations are absorbed: the check here plus
        the storage-level unique index (DuplicateLiveConnectionError) guarantee one
        live connection per patient-clinic pair even under concurrent requests. The
        attempt is audited whether or not it matched.

        Rate limiting (ADR-0017) runs FIRST — before the email is even looked up —
        so a 429 carries zero information about the probed address and slows an
        enumeration campaign to the window budget. Refusals are audited with counts
        only, never the email.
        """
        now = datetime.now(UTC)
        if not await invitation_rate_limiter(self.audit).allow(actor_id, now=now):
            await self.audit.add(
                AuditEvent(
                    actor_id=actor_id,
                    actor_role=UserRole.clinician.value,
                    action="rate_limited",
                    patient_id=None,
                    # Counts/config only — the probed email was never even looked up.
                    detail={
                        "clinic_id": str(clinic_id),
                        "limit": settings.invite_rate_limit_max,
                        "window_seconds": settings.invite_rate_limit_window_seconds,
                    },
                )
            )
            raise RateLimitExceededError
        user = await self.users.get_by_email(email.strip().lower())
        matched = user is not None and user.role is UserRole.patient and user.patient_id is not None
        created = False
        patient_id: uuid.UUID | None = None
        # Equalized work: unmatched emails look up a connection list too (for a
        # patient id that cannot exist), keeping per-probe query cost branch-free.
        lookup_id = (
            user.patient_id
            if matched and user is not None and user.patient_id is not None
            else uuid.uuid4()
        )
        existing = await self.connections.list_for_patient(lookup_id)
        if matched:
            assert user is not None and user.patient_id is not None  # narrowed by `matched`
            patient_id = user.patient_id
            if not any(
                c.clinic_id == clinic_id and c.status is not ConnectionStatus.revoked
                for c in existing
            ):
                try:
                    await self.connections.add(
                        ClinicConnection(
                            patient_id=patient_id,
                            clinic_id=clinic_id,
                            status=ConnectionStatus.pending,
                            initiated_by=Initiator.clinic,
                        )
                    )
                    created = True
                except DuplicateLiveConnectionError:
                    # A concurrent invitation won the race; absorbing it keeps the
                    # response identical and the audit trail truthful.
                    created = False
        await self.audit.add(
            AuditEvent(
                actor_id=actor_id,
                actor_role=UserRole.clinician.value,
                action="invite_patient",
                patient_id=patient_id,
                # References only — never the probed email address.
                detail={"clinic_id": str(clinic_id), "matched": matched, "created": created},
            )
        )

    async def list_connections(
        self, patient_id: uuid.UUID
    ) -> list[tuple[ClinicConnection, Clinic | None]]:
        """One patient's connections with their clinics, oldest first."""
        rows = await self.connections.list_for_patient(patient_id)
        return [(row, await self.clinics.get(row.clinic_id)) for row in rows]

    async def grant_consent(
        self, *, patient_id: uuid.UUID, actor_id: uuid.UUID, connection_id: uuid.UUID
    ) -> ClinicConnection | None:
        """Patient consents to a pending connection: record the grant, activate.

        None (-> 404) unless the connection exists, belongs to THIS patient, and is
        still pending — a consent can never resurrect a revoked link or double-fire.
        """
        connection = await self.connections.get(connection_id)
        if (
            connection is None
            or connection.patient_id != patient_id
            or connection.status is not ConnectionStatus.pending
        ):
            return None
        connection.consent_granted_at = datetime.now(UTC)
        connection.status = ConnectionStatus.active
        await self.connections.update(connection)
        await self.audit.add(
            AuditEvent(
                actor_id=actor_id,
                actor_role=UserRole.patient.value,
                action="grant_consent",
                patient_id=patient_id,
                detail={
                    "connection_id": str(connection_id),
                    "clinic_id": str(connection.clinic_id),
                },
            )
        )
        return connection

    async def revoke_connection(
        self, *, patient_id: uuid.UUID, actor_id: uuid.UUID, connection_id: uuid.UUID
    ) -> ClinicConnection | None:
        """Patient revokes a connection: data flow stops immediately (ADR-0005).

        Idempotent-safe — revoking an already-revoked connection is a quiet success
        (no second audit event). None (-> 404) for other patients' connections.
        """
        connection = await self.connections.get(connection_id)
        if connection is None or connection.patient_id != patient_id:
            return None
        if connection.status is ConnectionStatus.revoked:
            return connection
        connection.revoked_at = datetime.now(UTC)
        connection.status = ConnectionStatus.revoked
        await self.connections.update(connection)
        await self.audit.add(
            AuditEvent(
                actor_id=actor_id,
                actor_role=UserRole.patient.value,
                action="revoke_connection",
                patient_id=patient_id,
                detail={
                    "connection_id": str(connection_id),
                    "clinic_id": str(connection.clinic_id),
                },
            )
        )
        return connection

    async def panel(self, *, clinic_id: uuid.UUID) -> list[PanelEntry]:
        """The clinic's panel: ONLY patients on active, consented, non-revoked
        connections — judged by `may_transmit_to_clinic`, never re-derived here."""
        entries: list[PanelEntry] = []
        for connection in await self.connections.list_active_for_clinic(clinic_id):
            if not may_transmit_to_clinic(connection):
                continue
            user = await self.users.get_by_patient_id(connection.patient_id)
            if user is not None:
                entries.append(PanelEntry(connection=connection, patient_user=user))
        return entries

    async def connection_for_clinician(
        self, *, clinic_id: uuid.UUID, patient_id: uuid.UUID
    ) -> ClinicConnection | None:
        """THE access gate for /clinic/patients/{id}/*: the consented connection that
        permits this clinic to read this patient, or None (routes answer 404 — a
        non-consented record must be indistinguishable from a nonexistent one)."""
        for connection in await self.connections.list_for_patient(patient_id):
            if connection.clinic_id == clinic_id and may_transmit_to_clinic(connection):
                return connection
        return None
