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
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.emr_clinical_note import EmrClinicalNote
from app.models.observation import Observation
from app.models.user import UserRole
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.caregiver import (
    CaregiverLinkRepository,
    InMemoryCaregiverLinkRepository,
)
from app.repositories.emr_clinical_note import (
    EmrClinicalNoteRepository,
    InMemoryEmrClinicalNoteRepository,
)
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
    ExportCaregiverLink,
    ExportEmrClinicalNote,
    ExportObservation,
    ExportOut,
    ExportPatient,
)
from app.services.capability import CapabilityService
from app.services.clinic import ClinicService
from app.services.rate_limit import SlidingWindowRateLimiter
from app.services.trajectory import compute_patient_trajectory

__all__ = [
    "RATE_LIMITED_DETAIL",
    "ExportError",
    "PatientDataExportService",
    "export_rate_limiter",
]

# Over the export budget (ADR-0031, ADR-0017 pattern): friendly, PHI-free, and honest —
# nothing was disclosed, come back when the window has slid. Surfaced verbatim by the UI.
RATE_LIMITED_DETAIL = "Too many export requests right now — please try again in a little while."


def export_rate_limiter(counter: AuditEventRepository) -> SlidingWindowRateLimiter:
    """The settings-driven throttle on GET /me/export (ADR-0031), counting the
    'export_account' audit events every successful export writes — one per disclosure.
    Mirrors the invite limiter: each accepted export is exactly one audited event, so
    the window count IS the disclosure count. Over-budget requests are refused BEFORE
    the O(n) assembly and write nothing, so the cap bounds the work and the audited
    disclosure volume alike (at most the window budget per actor)."""
    return SlidingWindowRateLimiter(
        counter=counter,
        action="export_account",
        max_events=settings.export_rate_limit_max,
        window=timedelta(seconds=settings.export_rate_limit_window_seconds),
    )


class ExportError(Exception):
    """Export refusal the route layer maps to an HTTP response.

    Raised only on nothing-written paths (the account is gone, the principal is not a
    patient — defense in depth behind `require_patient` — or the actor is over the
    export budget), so the resulting HTTPException has no audit write to roll back.
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


def _clinical_note_out(note: EmrClinicalNote) -> ExportEmrClinicalNote:
    # Metadata only — there is NO body field, so the note text is structurally absent.
    return ExportEmrClinicalNote(
        id=note.id,
        connection_id=note.connection_id,
        source_system=note.source_system,
        document_fhir_id=note.document_fhir_id,
        type_code=note.type_code,
        type_display=note.type_display,
        # category/has_inline_data carry model-level defaults that only fire on a DB flush;
        # coerce here so an in-memory row (no flush) projects the same shape as a DB row.
        category=note.category or "clinical-note",
        authored_at=note.authored_at,
        author_display=note.author_display,
        encounter_fhir_id=note.encounter_fhir_id,
        content_type=note.content_type,
        attachment_url=note.attachment_url,
        has_inline_data=bool(note.has_inline_data),
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
    """Assembles one patient's current record as an ExportOut (ADR-0031).

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
    clinical_notes: EmrClinicalNoteRepository = field(
        default_factory=InMemoryEmrClinicalNoteRepository
    )
    # Caregiver-sharing metadata (ADR-0047): the export names who the patient shares
    # with and at what scope — links only, never invite codes or hashes.
    caregiver_links: CaregiverLinkRepository = field(
        default_factory=InMemoryCaregiverLinkRepository
    )
    clinic: ClinicService = field(default_factory=ClinicService)
    capabilities: CapabilityService = field(default_factory=CapabilityService)
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)

    async def export_patient_data(self, *, user_id: uuid.UUID) -> ExportOut:
        """Build the current export for the authenticated patient, auditing the read.

        Raises ExportError on the nothing-written paths: 401 when the account is gone
        (the token outlived it), 403 for a non-patient principal (defense in depth), and
        429 over the export budget — the throttle fires BEFORE any assembly, so nothing
        is read or written and the raise rolls nothing back.
        """
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise ExportError("Account no longer exists", status_code=401)
        if user.role is not UserRole.patient or user.patient_id is None:
            raise ExportError("Patient account required", status_code=403)

        patient_id = user.patient_id
        now = datetime.now(UTC)

        # Throttle BEFORE the O(n) assembly (ADR-0031): over the budget of audited
        # exports in the window the answer is 429 regardless, so an export flood is
        # capped in both work AND disclosure volume. Nothing has been read or written
        # yet, so raising (-> HTTPException) rolls back nothing.
        if not await export_rate_limiter(self.audit).allow(user.id, now=now):
            raise ExportError(RATE_LIMITED_DETAIL, status_code=429)

        patient = await self.users.get_patient(patient_id)
        observations = await self.observations.list_for_patient(patient_id)
        # The same shared, explainable engine the patient's own /trajectory answers
        # from (services/trajectory.py) — a snapshot of the current judgment. The engine
        # exposes no separate stored history, so the export carries the snapshot only.
        trajectory, _ = await compute_patient_trajectory(self.observations, patient_id, now=now)
        capabilities = await self.capabilities.effective_states(patient_id, now=now)
        clinic_connections = await self.clinic.list_connections(patient_id)
        emr_connections = await self.emr_connections.list_for_patient(patient_id)
        clinical_notes = await self.clinical_notes.list_for_patient(patient_id)
        caregiver_links = await self.caregiver_links.list_for_patient(patient_id)
        caregiver_names: dict[uuid.UUID, str] = {}
        for link in caregiver_links:
            caregiver = await self.users.get_by_id(link.caregiver_user_id)
            # A deleted caregiver account leaves no name behind — export stays honest.
            caregiver_names[link.id] = (
                caregiver.display_name if caregiver is not None else "Unknown caregiver"
            )

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
                    "emr_clinical_notes": len(clinical_notes),
                    "clinic_connections": len(clinic_connections),
                    "capabilities": len(capabilities),
                    "caregiver_links": len(caregiver_links),
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
            emr_clinical_notes=[_clinical_note_out(row) for row in clinical_notes],
            caregiver_links=[
                ExportCaregiverLink(
                    id=link.id,
                    caregiver_display_name=caregiver_names[link.id],
                    scope=link.scope.value,
                    status=link.status.value,
                    accepted_at=link.accepted_at,
                    revoked_at=link.revoked_at,
                    created_at=link.created_at,
                )
                for link in caregiver_links
            ],
        )
