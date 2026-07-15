"""Patient data export — the "Download my data" flow (ADR-0031).

The right-of-access sibling to account deletion (ADR-0027): where deletion destroys
the patient's record, export returns a faithful copy of it. Both are storage-agnostic
services over the same repository Protocols, wired per request in app/api/deps.py so
they read/write exactly the data every other feature does — no hand-rolled SQL, no
second source of truth.

Two invariants, mirrored from deletion:

- **Patient role ONLY.** The route gate (`require_patient`) refuses clinician/ops with
  403 and the unauthenticated caller with 401 before the service runs; the guards here
  are defense in depth and raise on the nothing-written paths.
- **Every export is audited.** ONE PHI-free `export_account` event — counts and
  references only, never values — records that the disclosure happened (CLAUDE.md §5).

NO SECRETS leave here. The export is assembled from token-free projections
(schemas/export.py): the account profile omits the password hash, EMR connections
reuse the vault-reference-free `ConnectionOut`, and the vaulted OAuth tokens are never
read at all. Absence is structural and proven by tests that scan the serialized
payload for the known token/hash fixtures.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.models.audit import AuditEvent
from app.models.observation import Observation
from app.models.user import UserRole
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.emr_connection import (
    ConnectionRecord,
    EmrConnectionRepository,
    InMemoryEmrConnectionRepository,
)
from app.repositories.observation import InMemoryObservationRepository, ObservationRepository
from app.repositories.user import InMemoryUserRepository, UserRepository
from app.schemas.capability import CapabilityStateOut
from app.schemas.clinic import ConnectionOut as ClinicConnectionOut
from app.schemas.emr import ConnectionOut as EmrConnectionOut
from app.schemas.export import (
    EXPORT_SCHEMA_VERSION,
    ExportAccountProfile,
    ExportObservation,
    ExportOut,
    ExportPatient,
)
from app.services.capability import CapabilityService
from app.services.clinic import ClinicService
from app.services.trajectory import compute_patient_trajectory

__all__ = ["ExportError", "PatientDataExportService"]


class ExportError(Exception):
    """Export refusal the route layer maps to an HTTP response.

    Raised only on nothing-written paths (the account is gone, or — defense in depth
    behind `require_patient` — the principal is not a patient), so the resulting
    HTTPException has no audit write to roll back.
    """

    def __init__(self, reason: str, status_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


def _observation_out(observation: Observation) -> ExportObservation:
    return ExportObservation(
        id=observation.id,
        source=observation.source.value,
        origin=observation.origin.value,
        code=observation.code,
        code_system=observation.code_system,
        value_num=observation.value_num,
        value_text=observation.value_text,
        unit=observation.unit,
        unit_system=observation.unit_system,
        effective_at=observation.effective_at,
        recorded_at=observation.recorded_at,
        status=observation.status.value,
        revises_id=observation.revises_id,
        recorded_by_role=observation.recorded_by_role,
        quality=observation.quality,
        payload=observation.payload,
    )


def _emr_connection_out(connection: ConnectionRecord) -> EmrConnectionOut:
    # Token-free by construction: ConnectionOut has no token_ref field, so the vault
    # reference on the record is simply never carried into the export.
    return EmrConnectionOut(
        id=connection.id,
        patient_id=connection.patient_id,
        fhir_base=connection.fhir_base,
        provider_name=connection.provider_name,
        status=connection.status.value,
        granted_scope=connection.granted_scope,
        patient_fhir_id=connection.patient_fhir_id,
        token_expires_at=connection.token_expires_at,
        revoked_at=connection.revoked_at,
    )


@dataclass
class PatientDataExportService:
    """Assembles one patient's complete record as an ExportOut (ADR-0031).

    In Postgres mode every dependency is bound to the request-scoped session
    (app/api/deps.py); the in-memory twins serve the no-DATABASE_URL mode identically,
    sharing the SAME singleton stores every other feature uses — so the export reflects
    exactly the data those features wrote.
    """

    users: UserRepository = field(default_factory=InMemoryUserRepository)
    observations: ObservationRepository = field(default_factory=InMemoryObservationRepository)
    emr_connections: EmrConnectionRepository = field(
        default_factory=InMemoryEmrConnectionRepository
    )
    clinic: ClinicService = field(default_factory=ClinicService)
    capabilities: CapabilityService = field(default_factory=CapabilityService)
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)

    async def export_patient_data(self, *, user_id: uuid.UUID) -> ExportOut:
        """Build the complete export for the authenticated patient, auditing the read.

        Raises ExportError on the nothing-written paths: 401 when the account is gone
        (the token outlived it), 403 for a non-patient principal (defense in depth).
        """
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise ExportError("Account no longer exists", status_code=401)
        if user.role is not UserRole.patient or user.patient_id is None:
            raise ExportError("Patient account required", status_code=403)

        patient_id = user.patient_id
        now = datetime.now(UTC)

        patient = await self.users.get_patient(patient_id)
        observations = await self.observations.list_for_patient(patient_id)
        # The same shared, explainable engine the patient's own /trajectory answers
        # from (services/trajectory.py) — a snapshot of the current judgment. The engine
        # exposes no separate stored history, so the export carries the snapshot only.
        trajectory, _ = await compute_patient_trajectory(self.observations, patient_id, now=now)
        capabilities = await self.capabilities.effective_states(patient_id, now=now)
        clinic_connections = await self.clinic.list_connections(patient_id)
        emr_connections = await self.emr_connections.list_for_patient(patient_id)

        # ONE PHI-free audit event: this is a disclosure of the whole record, so it is
        # logged like every other PHI read (CLAUDE.md §5) — counts only, never values.
        await self.audit.add(
            AuditEvent(
                actor_id=user.id,
                actor_role="patient",
                action="export_account",
                patient_id=patient_id,
                detail={
                    "observations": len(observations),
                    "emr_connections": len(emr_connections),
                    "clinic_connections": len(clinic_connections),
                    "capabilities": len(capabilities),
                },
            )
        )

        return ExportOut(
            exported_at=now,
            schema_version=EXPORT_SCHEMA_VERSION,
            subject_id=patient_id,
            account=ExportAccountProfile(
                display_name=user.display_name,
                email=user.email,
                role=user.role.value,
                created_at=user.created_at,
            ),
            patient=ExportPatient(
                patient_id=patient_id,
                # The linked record is created with the user; a missing row (should not
                # happen) falls back to the account's own display name/none, never a crash.
                display_name=patient.display_name if patient is not None else user.display_name,
                connection_mode=(
                    patient.connection_mode.value if patient is not None else "self_connected"
                ),
                created_at=patient.created_at if patient is not None else None,
            ),
            observations=[_observation_out(row) for row in observations],
            trajectory=trajectory,
            capabilities=[
                CapabilityStateOut(
                    key=state.key,
                    name=state.name,
                    active=state.active,
                    managed_by=state.managed_by,
                    expires_at=state.expires_at,
                    enforced=state.enforced,
                )
                for state in capabilities
            ],
            clinic_connections=[
                ClinicConnectionOut(
                    id=connection.id,
                    clinic_id=connection.clinic_id,
                    clinic_name=clinic.name if clinic is not None else "Unknown clinic",
                    status=connection.status.value,
                    initiated_by=connection.initiated_by.value,
                    consent_granted_at=connection.consent_granted_at,
                    revoked_at=connection.revoked_at,
                )
                for connection, clinic in clinic_connections
            ],
            emr_connections=[_emr_connection_out(row) for row in emr_connections],
        )
