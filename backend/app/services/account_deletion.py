"""Patient account & data deletion (ADR-0027) — the DELETE /auth/me flow.

One transactional, storage-agnostic pass: fresh password re-authentication (a stolen
bearer token alone must never be able to destroy an account), ONE PHI-free audit
event written BEFORE the destructive statements, then every table's rows for the
patient in FK-safe order, the patient row last. Vaulted EMR secrets are purged
through the same `SecretStore.delete` seam revocation uses (ADR-0017) — never a
second crypto path.

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

from app.core.security import verify_password
from app.emr.service import InMemorySecretStore, SecretStore
from app.models.audit import AuditEvent
from app.models.user import UserRole
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.clinic_connection import (
    ClinicConnectionRepository,
    InMemoryClinicConnectionRepository,
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

__all__ = ["WRONG_PASSWORD_DETAIL", "AccountDeletionError", "AccountDeletionService"]

# The caller is already authenticated, so plain wording is fine — but it must never
# hint at anything beyond the password mismatch, and it must reassure that nothing
# was destroyed. Surfaced verbatim by the UI (role=alert).
WRONG_PASSWORD_DETAIL = "That password didn't match. Nothing was deleted."


class AccountDeletionError(Exception):
    """Deletion refusal the route layer maps to an HTTP response."""

    def __init__(self, reason: str, status_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


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
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)

    async def delete_patient_account(self, *, user_id: uuid.UUID, password: str) -> None:
        """Verify the password, then destroy the account and every datum it owns.

        Raises AccountDeletionError: 401 when the account is already gone (the token
        outlived it), 403 for a non-patient principal or a wrong password. Nothing is
        written before the password verifies, so a refusal has nothing to roll back.
        """
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise AccountDeletionError("Account no longer exists", status_code=401)
        if user.role is not UserRole.patient or user.patient_id is None:
            # Defense in depth behind the route's require_patient gate.
            raise AccountDeletionError("Patient account required", status_code=403)
        # Fresh re-authentication (ADR-0027): the bearer token proves possession of a
        # session; only the password proves the account owner is asking. Argon2id
        # verify — the same primitive login uses.
        if not verify_password(user.password_hash, password):
            raise AccountDeletionError(WRONG_PASSWORD_DETAIL, status_code=403)

        patient_id = user.patient_id
        emr = await self.emr_connections.list_for_patient(patient_id)
        clinic_rows = await self.clinic_connections.list_for_patient(patient_id)
        capability_rows = await self.patient_capabilities.list_for_patient(patient_id)
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
                    "vault_secrets": len(token_refs),
                    "clinic_connections": len(clinic_rows),
                    "patient_capabilities": len(capability_rows),
                },
            )
        )

        # FK-safe destruction order. Each step only removes rows that nothing
        # remaining references; the patient row goes last.
        await self.pending_auth.delete_for_connections([c.id for c in emr])
        for ref in token_refs:
            # The ADR-0017 deletion-on-revoke seam — the exact code path EMR revoke
            # uses to purge vaulted tokens; no second crypto/deletion implementation.
            await self.secret_store.delete(ref)
        await self.emr_connections.delete_for_patient(patient_id)
        await self.clinic_connections.delete_for_patient(patient_id)
        await self.patient_capabilities.delete_for_patient(patient_id)
        await self.observations.delete_for_patient(patient_id)
        await self.users.delete_with_patient(user_id=user.id, patient_id=patient_id)
        # Postgres: the FK already detached the retained audit rows with the patient
        # delete above; this is the in-memory mirror (and a Postgres no-op backstop).
        await self.audit.detach_patient(patient_id)
