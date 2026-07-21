"""Patient account & data deletion (ADR-0027) — the DELETE /auth/me flow.

One transactional, storage-agnostic pass: fresh password re-authentication (a stolen
bearer token alone must never be able to destroy an account), ONE PHI-free audit
event written BEFORE the destructive statements, then every table's rows for the
patient in FK-safe order, the patient row last. Vaulted EMR secrets are purged
through the same `SecretStore.delete` seam revocation uses (ADR-0017) — never a
second crypto path — AFTER every DB row deletion (see the ordering note inline).

Failed password attempts are throttled (ADR-0017 sliding-window pattern, keyed on
the authenticated actor): each wrong password writes one bounded, PHI-free
'account_delete_denied' audit event, and over the window budget the flow answers 429
BEFORE the Argon2id verify runs — capping the destruction/password oracle and its
CPU cost, and bounding the denial audit volume by the same budget.

Retention: audit_event rows are RETAINED (regulatory retention; PHI-free by
contract). The patient-row delete fires migration 0006's ON DELETE SET NULL, so the
history — including the deletion event itself — survives as anonymous events; the
in-memory twin mirrors that via `AuditEventRepository.detach_patient`.

Deletion is NEVER blockable: no capability toggle or ops kill switch gates this
flow, mirroring the ADR-0013 "revocation is never toggle-blockable" posture.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.ai.narrative import clear_narrative_cache
from app.core.config import settings
from app.core.security import verify_password
from app.emr.service import InMemorySecretStore, SecretStore
from app.models.audit import AuditEvent
from app.models.user import UserRole
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.caregiver import (
    CaregiverInviteRepository,
    CaregiverLinkRepository,
    InMemoryCaregiverInviteRepository,
    InMemoryCaregiverLinkRepository,
)
from app.repositories.caregiver_alert import (
    CaregiverAlertPreferenceRepository,
    CaregiverAlertRepository,
    InMemoryCaregiverAlertPreferenceRepository,
    InMemoryCaregiverAlertRepository,
)
from app.repositories.clinic_connection import (
    ClinicConnectionRepository,
    InMemoryClinicConnectionRepository,
)
from app.repositories.emr_clinical_note import (
    EmrClinicalNoteRepository,
    InMemoryEmrClinicalNoteRepository,
)
from app.repositories.emr_connection import (
    EmrConnectionRepository,
    InMemoryEmrConnectionRepository,
)
from app.repositories.observation import InMemoryObservationRepository, ObservationRepository
from app.repositories.patient_capability import (
    InMemoryPatientCapabilityRepository,
    PatientCapabilityRepository,
)
from app.repositories.pending_auth import InMemoryPendingAuthStore, PendingAuthStore
from app.repositories.user import InMemoryUserRepository, UserRepository
from app.services.rate_limit import SlidingWindowRateLimiter

__all__ = [
    "RATE_LIMITED_DETAIL",
    "WRONG_PASSWORD_DETAIL",
    "AccountDeletionError",
    "AccountDeletionService",
    "DeletionDenied",
    "deletion_denial_rate_limiter",
]

# The caller is already authenticated, so plain wording is fine — but it must never
# hint at anything beyond the password mismatch, and it must reassure that nothing
# was destroyed. Surfaced verbatim by the UI (role=alert).
WRONG_PASSWORD_DETAIL = "That password didn't match. Nothing was deleted."

# Over the failed-password budget (ADR-0017 pattern): friendly, PHI-free, and just as
# reassuring — nothing was destroyed, come back when the window has slid.
RATE_LIMITED_DETAIL = (
    "Too many attempts right now — please try again in a little while. Nothing was deleted."
)


class AccountDeletionError(Exception):
    """Deletion refusal the route layer maps to an HTTP response.

    Raised ONLY on paths that have written nothing (missing account, wrong role,
    over the attempt budget), so the resulting HTTPException has nothing to roll
    back. The audited wrong-password refusal is `DeletionDenied`, returned instead.
    """

    def __init__(self, reason: str, status_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


@dataclass(frozen=True)
class DeletionDenied:
    """Audited refusal the route must RETURN as a response, never raise: the denial's
    'account_delete_denied' audit event has to commit with the request transaction, and
    a raised HTTPException would roll it back (docs/lessons.md "return don't raise") —
    the throttle that counts those events would then never trip."""

    reason: str
    status_code: int


def deletion_denial_rate_limiter(counter: AuditEventRepository) -> SlidingWindowRateLimiter:
    """The settings-driven throttle on DELETE /auth/me password failures (ADR-0027),
    counting the 'account_delete_denied' audit events the refusal path writes — one per
    wrong password that reached the Argon2id verify. Over-budget attempts are refused
    BEFORE the verify and write nothing, so the cap bounds the denial audit volume too:
    at most the window budget of denial rows per actor (never a log-flood primitive)."""
    return SlidingWindowRateLimiter(
        counter=counter,
        action="account_delete_denied",
        max_events=settings.delete_account_rate_limit_max,
        window=timedelta(seconds=settings.delete_account_rate_limit_window_seconds),
    )


@dataclass
class AccountDeletionService:
    """Deletes a patient account and ALL its data in one unit of work.

    In Postgres mode every repository is bound to the request-scoped transaction
    (app/api/deps.py), so the audit write and every delete commit or roll back
    together; the in-memory twins serve the no-DATABASE_URL mode identically.
    """

    users: UserRepository = field(default_factory=InMemoryUserRepository)
    emr_connections: EmrConnectionRepository = field(
        default_factory=InMemoryEmrConnectionRepository
    )
    pending_auth: PendingAuthStore = field(default_factory=InMemoryPendingAuthStore)
    secret_store: SecretStore = field(default_factory=InMemorySecretStore)
    clinic_connections: ClinicConnectionRepository = field(
        default_factory=InMemoryClinicConnectionRepository
    )
    patient_capabilities: PatientCapabilityRepository = field(
        default_factory=InMemoryPatientCapabilityRepository
    )
    observations: ObservationRepository = field(default_factory=InMemoryObservationRepository)
    # EMR clinical notes are a SEPARATE store that FKs emr_connection, so they must be
    # deleted BEFORE the connections (ADR-0045 P2 #27, FK-safe order below).
    clinical_notes: EmrClinicalNoteRepository = field(
        default_factory=InMemoryEmrClinicalNoteRepository
    )
    # Caregiver invites/links (ADR-0047): a patient deletion purges both (invites FK
    # the patient row; links FK it too), and a caregiver-account deletion removes the
    # links referencing the user row — no dangling consent rows either way.
    caregiver_invites: CaregiverInviteRepository = field(
        default_factory=InMemoryCaregiverInviteRepository
    )
    caregiver_links: CaregiverLinkRepository = field(
        default_factory=InMemoryCaregiverLinkRepository
    )
    # Caregiver alerts + per-type preferences (ADR-0047 B1): alerts FK caregiver_link, so
    # a patient deletion removes them BEFORE the invites/links; a caregiver-account
    # deletion removes the alerts on that caregiver's links first too. Preferences FK the
    # patient row.
    caregiver_alerts: CaregiverAlertRepository = field(
        default_factory=InMemoryCaregiverAlertRepository
    )
    caregiver_alert_preferences: CaregiverAlertPreferenceRepository = field(
        default_factory=InMemoryCaregiverAlertPreferenceRepository
    )
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)

    async def delete_patient_account(
        self, *, user_id: uuid.UUID, password: str
    ) -> DeletionDenied | None:
        """Verify the password, then destroy the account and every datum it owns.

        Returns None on success, or a `DeletionDenied` (403) for a wrong password —
        returned, not raised, because that refusal writes a bounded audit event that
        must commit. Raises AccountDeletionError on the nothing-written paths: 401
        when the account is already gone (the token outlived it), 403 for a
        non-patient principal, 429 over the failed-password budget.
        """
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise AccountDeletionError("Account no longer exists", status_code=401)
        if user.role is not UserRole.patient or user.patient_id is None:
            # Defense in depth behind the route's require_patient gate.
            raise AccountDeletionError("Patient account required", status_code=403)
        # Throttle BEFORE the Argon2id verify (ADR-0017 pattern): over the budget of
        # audited failures the answer is 429 regardless of the password offered, so a
        # guessing campaign is capped in both oracle answers AND hashing CPU. Nothing
        # has been written yet, so raising (-> HTTPException) rolls back nothing.
        now = datetime.now(UTC)
        if not await deletion_denial_rate_limiter(self.audit).allow(user.id, now=now):
            raise AccountDeletionError(RATE_LIMITED_DETAIL, status_code=429)
        # Fresh re-authentication (ADR-0027): the bearer token proves possession of a
        # session; only the password proves the account owner is asking. Argon2id
        # verify — the same primitive login uses.
        if not verify_password(user.password_hash, password):
            # Bounded, PHI-free denial event (config/counts only — audit contract):
            # the throttle above counts exactly these rows, so their volume can never
            # exceed the window budget per actor. Returned, never raised — the event
            # must commit with the request transaction (docs/lessons.md).
            await self.audit.add(
                AuditEvent(
                    actor_id=user.id,
                    actor_role="patient",
                    action="account_delete_denied",
                    patient_id=user.patient_id,
                    detail={
                        "limit": settings.delete_account_rate_limit_max,
                        "window_seconds": settings.delete_account_rate_limit_window_seconds,
                    },
                )
            )
            return DeletionDenied(WRONG_PASSWORD_DETAIL, status_code=403)

        patient_id = user.patient_id
        emr = await self.emr_connections.list_for_patient(patient_id)
        clinic_rows = await self.clinic_connections.list_for_patient(patient_id)
        capability_rows = await self.patient_capabilities.list_for_patient(patient_id)
        note_rows = await self.clinical_notes.list_for_patient(patient_id)
        invite_rows = await self.caregiver_invites.list_for_patient(patient_id)
        caregiver_link_rows = await self.caregiver_links.list_for_patient(patient_id)
        alert_rows = [
            alert
            for link in caregiver_link_rows
            for alert in await self.caregiver_alerts.list_for_link(link.id)
        ]
        alert_pref_rows = await self.caregiver_alert_preferences.list_for_patient(patient_id)
        # Vault refs are collected BEFORE the emr_connection rows die below; the
        # purge itself runs LAST (see the ordering note there).
        token_refs = [c.token_ref for c in emr if c.token_ref is not None]

        # ONE audit event, BEFORE the destructive statements, in the same transaction
        # (ADR-0027). Counts and references only — never values (audit contract). The
        # patient-row delete below detaches it (patient_id -> NULL), so it survives
        # the deletion as an anonymous, PHI-free record that the erasure happened.
        await self.audit.add(
            AuditEvent(
                actor_id=user.id,
                actor_role="patient",
                action="delete_account",
                patient_id=patient_id,
                detail={
                    "emr_connections": len(emr),
                    "emr_clinical_notes": len(note_rows),
                    "vault_secrets": len(token_refs),
                    "clinic_connections": len(clinic_rows),
                    "patient_capabilities": len(capability_rows),
                    "caregiver_invites": len(invite_rows),
                    "caregiver_links": len(caregiver_link_rows),
                    "caregiver_alerts": len(alert_rows),
                    "caregiver_alert_preferences": len(alert_pref_rows),
                },
            )
        )

        # FK-safe destruction order. Each step only removes rows that nothing
        # remaining references; the patient row goes last.
        await self.pending_auth.delete_for_connections([c.id for c in emr])
        # Notes FK emr_connection, so they die BEFORE the connections (ADR-0045 P2 #27).
        await self.clinical_notes.delete_for_patient(patient_id)
        await self.emr_connections.delete_for_patient(patient_id)
        await self.clinic_connections.delete_for_patient(patient_id)
        await self.patient_capabilities.delete_for_patient(patient_id)
        await self.observations.delete_for_patient(patient_id)
        # Caregiver alerts FK caregiver_link, so they die BEFORE the links (ADR-0047 B1);
        # the per-type preferences FK the patient row.
        await self.caregiver_alerts.delete_for_patient(patient_id)
        await self.caregiver_alert_preferences.delete_for_patient(patient_id)
        # Caregiver invites + links FK the patient row (ADR-0047): both die before
        # it. Deleting the links also ends any live caregiver consent — with no link
        # left, _may_caregiver_read can never pass for this patient again.
        await self.caregiver_invites.delete_for_patient(patient_id)
        await self.caregiver_links.delete_for_patient(patient_id)
        await self.users.delete_with_patient(user_id=user.id, patient_id=patient_id)
        # Postgres: the FK already detached the retained audit rows with the patient
        # delete above; this is the in-memory mirror (and a Postgres no-op backstop).
        await self.audit.detach_patient(patient_id)
        # Vault purge LAST, after every DB row deletion (review finding). With the
        # keyed PostgresSecretStore the delete joins the same request transaction as
        # the row deletes above, so this ordering changes nothing about atomicity.
        # With the keyless InMemorySecretStore the delete is process-memory and
        # NON-transactional: had it run before the row deletes, a mid-request DB
        # failure would roll the rows back but leave the vault entry gone — an
        # intact-looking account whose emr_connection.token_ref points at a purged
        # entry. Running it last means such a failure rolls back to a fully intact
        # account instead. Still the ADR-0017 deletion-on-revoke seam — the exact
        # code path EMR revoke uses; no second crypto/deletion implementation.
        for ref in token_refs:
            await self.secret_store.delete(ref)
        # The AI narrative cache is keyed by trajectory content, not patient id, so
        # this patient's entries cannot be purged selectively — clear the whole
        # process-level cache (cheap; it repopulates on demand). An IN-FLIGHT
        # narration scheduled before this request can still finish after it — the
        # accepted seconds-wide residual recorded in ADR-0027.
        clear_narrative_cache()
        return None

    async def delete_caregiver_account(
        self, *, user_id: uuid.UUID, password: str
    ) -> DeletionDenied | None:
        """Delete a CAREGIVER account (ADR-0047): the same fresh password re-auth and
        failed-attempt throttle as patient deletion, but a far smaller footprint — a
        caregiver holds no patient data, so only its links (which FK the user row)
        and the user row itself are destroyed. The patients' records are untouched;
        their audit history keeps the PHI-free lifecycle events.

        Returns None on success, or a `DeletionDenied` (403) for a wrong password —
        returned, not raised (docs/lessons.md). Raises AccountDeletionError on the
        nothing-written paths: 401 gone, 403 non-caregiver, 429 over budget.
        """
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise AccountDeletionError("Account no longer exists", status_code=401)
        if user.role is not UserRole.caregiver:
            # Defense in depth behind the route's role dispatch.
            raise AccountDeletionError("Caregiver account required", status_code=403)
        # The SAME throttle + denial-audit budget the patient flow uses (ADR-0017
        # pattern): one limiter, one action, no second knob to drift.
        now = datetime.now(UTC)
        if not await deletion_denial_rate_limiter(self.audit).allow(user.id, now=now):
            raise AccountDeletionError(RATE_LIMITED_DETAIL, status_code=429)
        if not verify_password(user.password_hash, password):
            await self.audit.add(
                AuditEvent(
                    actor_id=user.id,
                    actor_role=UserRole.caregiver.value,
                    action="account_delete_denied",
                    patient_id=None,
                    detail={
                        "limit": settings.delete_account_rate_limit_max,
                        "window_seconds": settings.delete_account_rate_limit_window_seconds,
                    },
                )
            )
            return DeletionDenied(WRONG_PASSWORD_DETAIL, status_code=403)

        links = await self.caregiver_links.list_for_caregiver(user.id)
        alert_rows = [
            alert for link in links for alert in await self.caregiver_alerts.list_for_link(link.id)
        ]
        # ONE audit event BEFORE the destructive statements (ADR-0027) — counts only.
        # No patient subject: the event records the caregiver identity's erasure.
        await self.audit.add(
            AuditEvent(
                actor_id=user.id,
                actor_role=UserRole.caregiver.value,
                action="delete_account",
                patient_id=None,
                detail={"caregiver_links": len(links), "caregiver_alerts": len(alert_rows)},
            )
        )
        # FK-safe order: alerts FK the caregiver_link, so they die BEFORE the links, which
        # in turn reference the user row and die before it.
        await self.caregiver_alerts.delete_for_caregiver(user.id)
        await self.caregiver_links.delete_for_caregiver(user.id)
        await self.users.delete_user(user.id)
        return None
