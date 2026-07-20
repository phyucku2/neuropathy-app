"""Clinician surface endpoints: provisioning, invitations, panel, patient views
(ADR-0012).

Routes are thin: validation + HTTP mapping only; the flows and the consent gate live
in ClinicService. Two postures are absolute here:

- **404 over 403.** Every /patients/{patient_id}/* answer for a patient this clinic
  may not read is 404 — cross-clinic and non-consented access must be
  indistinguishable from a nonexistent record (no existence leak).
- **Deterministic only.** The clinician trajectory NEVER touches the AI narrator;
  `narrative_source` stays "deterministic" (ADR-0011 scopes narration to the
  patient's own view).

Every clinician read of patient data is audit-logged with the clinician as actor and
the patient as subject, counts only, never values (CLAUDE.md §5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from app.api.deps import (
    AuthDep,
    ClinicianUserDep,
    ClinicServiceDep,
    CurrentUser,
    OpsUserDep,
)
from app.api.routes.ingestion import observation_to_item
from app.api.routes.me import _validate_window
from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.connection import ClinicConnection
from app.schemas.clinic import (
    ClinicianCreateIn,
    ClinicianOut,
    InvitationIn,
    InvitationOut,
    PanelOut,
    PanelPatientOut,
)
from app.schemas.ingestion import ObservationPage
from app.schemas.trajectory import Trajectory
from app.schemas.visit_summary import DEFAULT_WINDOW_DAYS, VisitSummary
from app.services.auth import AuthApiError
from app.services.clinic import ClinicService
from app.services.rate_limit import RateLimitExceededError
from app.services.trajectory import compute_patient_trajectory
from app.services.visit_summary import build_visit_summary

router = APIRouter(prefix="/clinic", tags=["clinic"])


@router.post("/clinicians", response_model=ClinicianOut, status_code=201)
async def create_clinician(
    body: ClinicianCreateIn,
    service: ClinicServiceDep,
    auth: AuthDep,
    current: OpsUserDep,
) -> ClinicianOut:
    """Provision a clinician account (an authenticated ops action, ADR-0019): join an
    existing clinic by id or found a new one by name. The gate is now a real ops bearer
    token (require_ops), not the shared OPS_BOOTSTRAP_TOKEN, so the provisioning audit
    below records the actual operator as actor — genuine per-operator attribution."""
    founded = body.clinic_id is None
    if body.clinic_id is not None:
        clinic = await service.clinics.get(body.clinic_id)
        if clinic is None:
            raise HTTPException(status_code=422, detail="Unknown clinic_id")
    else:
        assert body.clinic_name is not None  # guaranteed by the schema validator
        clinic = await service.create_clinic(name=body.clinic_name)
    try:
        user = await auth.create_clinician(
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            clinic_id=clinic.id,
        )
    except AuthApiError as exc:
        if founded:
            # Provisioning failed (e.g. duplicate email): a clinic founded in this
            # request must not survive it, or retries accumulate same-name orphans.
            # Postgres mode also rolls back via the request transaction; this keeps
            # in-memory mode equally clean (review finding).
            await service.clinics.delete(clinic.id)
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    # Provisioning is a privileged config change — audited like any other (CLAUDE.md §5).
    # The actor is now the REAL ops operator (ADR-0019), not the anonymous sentinel the
    # shared-token gate could only record.
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role="ops",
            action="create_clinician",
            patient_id=None,
            detail={"user_id": str(user.id), "clinic_id": str(clinic.id)},
        )
    )
    return ClinicianOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        clinic_id=clinic.id,
        clinic_name=clinic.name,
    )


@router.post("/invitations", response_model=InvitationOut, status_code=202)
async def invite_patient(
    body: InvitationIn, current: ClinicianUserDep, service: ClinicServiceDep
) -> InvitationOut | JSONResponse:
    """Invite a patient by email to connect to this clinician's clinic.

    NON-ENUMERATING: the 202 response is byte-identical whether or not the email
    matches a patient account. A match creates a pending, clinic-initiated
    connection the patient must consent to before any data flows (ADR-0005). Over
    the per-clinician budget the answer is 429 (ADR-0017) — the limiter fires before
    the email lookup, so the refusal reveals nothing about the address either. The
    429 is returned rather than raised so the refusal's audit event commits with the
    request transaction instead of rolling back with an HTTPException."""
    assert current.clinic_id is not None  # guaranteed by require_clinician
    try:
        await service.invite_patient(
            clinic_id=current.clinic_id, actor_id=current.user_id, email=body.email
        )
    except RateLimitExceededError:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Too many invitations from this account right now — "
                "please try again in a little while"
            },
        )
    return InvitationOut()


@router.get("/patients", response_model=PanelOut)
async def patient_panel(current: ClinicianUserDep, service: ClinicServiceDep) -> PanelOut:
    """The clinician's panel: ONLY patients with an active, consented connection to
    this clinician's clinic (`may_transmit_to_clinic` is the gate)."""
    assert current.clinic_id is not None  # guaranteed by require_clinician
    entries = await service.panel(clinic_id=current.clinic_id)
    patients: list[PanelPatientOut] = []
    for entry in entries:
        assert entry.patient_user.patient_id is not None  # panel entries are patients
        assert entry.connection.consent_granted_at is not None  # guaranteed by the gate
        # PHI read — one event per patient surfaced, clinician as actor (CLAUDE.md §5).
        await service.audit.add(
            AuditEvent(
                actor_id=current.user_id,
                actor_role=current.role.value,
                action="read_panel",
                patient_id=entry.patient_user.patient_id,
                detail={"connection_id": str(entry.connection.id)},
            )
        )
        patients.append(
            PanelPatientOut(
                patient_id=entry.patient_user.patient_id,
                display_name=entry.patient_user.display_name,
                connection_id=entry.connection.id,
                consent_granted_at=entry.connection.consent_granted_at,
            )
        )
    return PanelOut(patients=patients)


async def _consented_connection(
    service: ClinicService, current: CurrentUser, patient_id: uuid.UUID
) -> ClinicConnection:
    """THE access gate for /patients/{patient_id}/*: 404 — never 403 — when this
    clinic holds no consented connection, so an existence probe learns nothing."""
    assert current.clinic_id is not None  # guaranteed by require_clinician
    connection = await service.connection_for_clinician(
        clinic_id=current.clinic_id, patient_id=patient_id
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return connection


@router.get("/patients/{patient_id}/trajectory", response_model=Trajectory)
async def patient_trajectory(
    patient_id: uuid.UUID, current: ClinicianUserDep, service: ClinicServiceDep
) -> Trajectory:
    """The consented patient's deterministic trajectory — the SAME computation the
    patient sees (services/trajectory.py), never the AI narrative (ADR-0012)."""
    connection = await _consented_connection(service, current, patient_id)
    now = datetime.now(UTC)
    trajectory, observation_count = await compute_patient_trajectory(
        service.observations, patient_id, now=now
    )
    # PHI read — clinician as actor, patient as subject, counts only (CLAUDE.md §5).
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="read_trajectory",
            patient_id=patient_id,
            detail={"observations": observation_count, "connection_id": str(connection.id)},
        )
    )
    return trajectory


@router.get("/patients/{patient_id}/visit-summary", response_model=VisitSummary)
async def patient_visit_summary(
    patient_id: uuid.UUID,
    current: ClinicianUserDep,
    service: ClinicServiceDep,
    response: Response,
    window: Annotated[int, Query()] = DEFAULT_WINDOW_DAYS,
) -> VisitSummary:
    """The consented patient's Visit-Ready Summary — the SAME assembly and data the
    patient's own print answers from (services/visit_summary.py), never the AI narrator
    (ADR-0012: `narrative_source` stays "deterministic"). 404 — never 403 — without a
    consented connection. `now` is resolved once here; the body is PHI, so `no-store`."""
    connection = await _consented_connection(service, current, patient_id)
    _validate_window(window)
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(UTC)
    summary, observation_count = await build_visit_summary(
        service.observations,
        patient_id,
        window=window,
        now=now,
        include_change_questions=settings.include_change_questions,
        clinical_notes=service.clinical_notes,
    )
    # PHI read — clinician as actor, patient as subject, counts only + the connection ref.
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="read_visit_summary",
            patient_id=patient_id,
            detail={
                "observations": observation_count,
                "window_days": window,
                "connection_id": str(connection.id),
            },
        )
    )
    return summary


@router.get("/patients/{patient_id}/observations", response_model=ObservationPage)
async def patient_observations(
    patient_id: uuid.UUID,
    current: ClinicianUserDep,
    service: ClinicServiceDep,
    code: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ObservationPage:
    """The consented patient's raw analyzable records, newest first — the same page
    shape and pagination contract as the patient's own GET /observations."""
    connection = await _consented_connection(service, current, patient_id)
    page = await service.observations.list_for_patient(
        patient_id, code=code, limit=limit, offset=offset, newest_first=True
    )
    total = await service.observations.count_for_patient(patient_id, code=code)
    # PHI read — clinician as actor, patient as subject, counts only (CLAUDE.md §5).
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="read_observations",
            patient_id=patient_id,
            detail={
                "returned": len(page),
                "total": total,
                "connection_id": str(connection.id),
            },
        )
    )
    return ObservationPage(
        items=[observation_to_item(row) for row in page], total=total, limit=limit, offset=offset
    )
