"""Caregiver Companion Phase A endpoints (ADR-0047): the patient's invite/consent
lifecycle and the caregiver's read-only surfaces.

Routes are thin: validation + HTTP mapping only; the flows and the acceptance gate
live in CaregiverService. Three postures are absolute here:

- **404 over 403.** Every /caregiver/patients/{patient_id}/* answer for a patient
  this caregiver may not read — unknown, unlinked, non-accepted, revoked, OR at
  insufficient scope — is 404, indistinguishable from a nonexistent record. The
  patient-side lifecycle endpoints answer 404 for other patients' rows the same way
  (the routes/connections.py posture).
- **Deterministic only.** The caregiver trajectory NEVER touches the AI narrator;
  `narrative_source` stays "deterministic" (ADR-0011 scopes narration to the
  patient's own view; a caregiver is not the patient).
- **Non-enumeration.** Claim responses are byte-identical whether or not the code
  matched, the rate limiter fires before any code lookup, and audited refusals are
  RETURNED as responses so their events commit (docs/lessons.md).

Every caregiver read of patient data is audit-logged with action='caregiver_read'
(the surface disambiguated in detail — a deliberate divergence from the clinic
routes' per-surface actions, per the Phase A spec), caregiver as actor, patient as
subject, counts/refs only (CLAUDE.md §5). PHI bodies are served Cache-Control:
no-store.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from app.api.deps import (
    AuthDep,
    CaregiverServiceDep,
    CaregiverUserDep,
    CurrentUser,
    PatientUserDep,
)
from app.api.routes.me import _validate_window
from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.caregiver import CaregiverLink, CaregiverScope
from app.schemas.auth import TokenOut
from app.schemas.caregiver import (
    CaregiverPatientOut,
    CaregiverPatientsOut,
    CaregiverRegisterIn,
    ClaimIn,
    ClaimOut,
    InviteCreateOut,
    InviteOut,
    PatientLinkOut,
    ScopeIn,
)
from app.schemas.trajectory import Trajectory
from app.schemas.visit_summary import DEFAULT_WINDOW_DAYS, VisitSummary
from app.services.auth import AuthApiError, LoginDenied
from app.services.caregiver import (
    CLAIM_RATE_LIMITED_DETAIL,
    CaregiverClaimError,
    CaregiverService,
    ClaimDenied,
)
from app.services.rate_limit import RateLimitExceededError
from app.services.trajectory import compute_patient_trajectory
from app.services.visit_summary import build_visit_summary

router = APIRouter(tags=["caregiver"])


def _rate_limited() -> JSONResponse:
    """The claim throttle's 429 — byte-identical for every code, valid or not."""
    return JSONResponse(status_code=429, content={"detail": CLAIM_RATE_LIMITED_DETAIL})


# ---------------------------------------------------------------- registration / claims


@router.post("/caregiver/register", response_model=TokenOut, status_code=201)
async def register_caregiver(
    body: CaregiverRegisterIn, service: CaregiverServiceDep, auth: AuthDep
) -> TokenOut | JSONResponse:
    """Create a caregiver account WITH a valid invite code (ADR-0047): caregiver
    self-registration exists only inside the invite-claim flow. The code is judged
    BEFORE the account is created; a dead code — unknown, expired, consumed,
    cancelled, all indistinguishable — refuses with one fixed message (returned, so
    its audited refusal commits). The resulting link is PENDING: nothing is visible
    until the patient explicitly accepts (double opt-in)."""
    try:
        outcome = await service.registration_claim_check(email=body.email, code=body.code)
    except RateLimitExceededError:
        # Refused before the code was hashed or looked up; nothing was written.
        return _rate_limited()
    if isinstance(outcome, ClaimDenied):
        return JSONResponse(status_code=outcome.status_code, content={"detail": outcome.reason})
    try:
        user = await auth.create_caregiver(
            email=body.email, password=body.password, display_name=body.display_name
        )
    except AuthApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    try:
        await service.finalize_registration_claim(invite=outcome, caregiver_user_id=user.id)
    except CaregiverClaimError as exc:
        # Lost the single-use race after the insert: the raise rolls the account back
        # with the request transaction (Postgres mode); nothing audited to lose.
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    login = await auth.login(email=body.email, password=body.password)
    if isinstance(login, LoginDenied):
        # Only the login throttle can fire here (the credentials were just created).
        return JSONResponse(status_code=login.status_code, content={"detail": login.reason})
    _, tokens = login
    return TokenOut(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/caregiver/claims", response_model=ClaimOut, status_code=202)
async def claim_invite(
    body: ClaimIn, current: CaregiverUserDep, service: CaregiverServiceDep
) -> ClaimOut | JSONResponse:
    """An existing caregiver claims another patient's code.

    NON-ENUMERATING: the 202 body is byte-identical whether or not the code matched.
    A match creates a PENDING link the patient must accept before anything is
    visible (double opt-in). Over the per-caregiver budget the answer is 429 — the
    limiter fires before the code lookup, so the refusal reveals nothing either; it
    is returned rather than raised so its audit event commits with the request."""
    try:
        await service.claim_invite(caregiver_user_id=current.user_id, code=body.code)
    except RateLimitExceededError:
        return _rate_limited()
    return ClaimOut()


# ---------------------------------------------------------------- caregiver reads


async def _linked_for_caregiver(
    service: CaregiverService,
    current: CurrentUser,
    patient_id: uuid.UUID,
    *,
    require_full: bool = False,
) -> CaregiverLink:
    """THE access gate for /caregiver/patients/{patient_id}/*: 404 — never 403 —
    when no accepted link at the required scope exists, so an existence (or scope)
    probe learns nothing. Insufficient scope is deliberately indistinguishable from
    a nonexistent patient (the non-enumeration posture)."""
    link = await service.link_for_caregiver(
        caregiver_user_id=current.user_id, patient_id=patient_id, require_full=require_full
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return link


@router.get("/caregiver/patients", response_model=CaregiverPatientsOut)
async def caregiver_patients(
    current: CaregiverUserDep, service: CaregiverServiceDep, response: Response
) -> CaregiverPatientsOut:
    """The caregiver's shared patients: ONLY accepted, non-revoked links, judged by
    the one `_may_caregiver_read` predicate. Names are PHI — `no-store`."""
    response.headers["Cache-Control"] = "no-store"
    entries = await service.patients_for_caregiver(current.user_id)
    patients: list[CaregiverPatientOut] = []
    for link, patient_user in entries:
        assert patient_user.patient_id is not None  # linked rows always name a patient
        assert link.accepted_at is not None  # guaranteed by the predicate
        # PHI read — one event per patient surfaced, caregiver as actor (CLAUDE.md §5).
        await service.audit.add(
            AuditEvent(
                actor_id=current.user_id,
                actor_role=current.role.value,
                action="caregiver_read",
                patient_id=patient_user.patient_id,
                detail={"surface": "patients", "link_id": str(link.id)},
            )
        )
        patients.append(
            CaregiverPatientOut(
                patient_id=patient_user.patient_id,
                display_name=patient_user.display_name,
                link_id=link.id,
                scope=link.scope.value,
                accepted_at=link.accepted_at,
            )
        )
    return CaregiverPatientsOut(patients=patients)


@router.get("/caregiver/patients/{patient_id}/trajectory", response_model=Trajectory)
async def caregiver_patient_trajectory(
    patient_id: uuid.UUID,
    current: CaregiverUserDep,
    service: CaregiverServiceDep,
    response: Response,
) -> Trajectory:
    """The shared patient's deterministic trajectory — the SAME computation the
    patient and clinician see (services/trajectory.py), never the AI narrative.
    Trends scope suffices; the body is PHI, so `no-store`."""
    link = await _linked_for_caregiver(service, current, patient_id)
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(UTC)
    trajectory, observation_count = await compute_patient_trajectory(
        service.observations, patient_id, now=now
    )
    # PHI read — caregiver as actor, patient as subject, counts only (CLAUDE.md §5).
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="caregiver_read",
            patient_id=patient_id,
            detail={
                "surface": "trajectory",
                "observations": observation_count,
                "link_id": str(link.id),
            },
        )
    )
    return trajectory


@router.get("/caregiver/patients/{patient_id}/visit-summary", response_model=VisitSummary)
async def caregiver_patient_visit_summary(
    patient_id: uuid.UUID,
    current: CaregiverUserDep,
    service: CaregiverServiceDep,
    response: Response,
    window: Annotated[int, Query()] = DEFAULT_WINDOW_DAYS,
) -> VisitSummary:
    """The shared patient's Visit-Ready Summary — FULL scope only; a trends-scope
    caller gets the same 404 as a nonexistent patient (non-enumeration). The SAME
    assembly the patient's own print answers from (services/visit_summary.py), never
    the AI narrator. The body is PHI, so `no-store`."""
    link = await _linked_for_caregiver(service, current, patient_id, require_full=True)
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
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="caregiver_read",
            patient_id=patient_id,
            detail={
                "surface": "visit_summary",
                "observations": observation_count,
                "window_days": window,
                "link_id": str(link.id),
            },
        )
    )
    return summary


# ---------------------------------------------------------------- patient lifecycle


def _link_out(link: CaregiverLink, caregiver_display_name: str) -> PatientLinkOut:
    return PatientLinkOut(
        id=link.id,
        caregiver_display_name=caregiver_display_name,
        scope=link.scope.value,
        status=link.status.value,
        accepted_at=link.accepted_at,
        revoked_at=link.revoked_at,
        created_at=link.created_at,
    )


async def _caregiver_name(service: CaregiverService, link: CaregiverLink) -> str:
    user = await service.users.get_by_id(link.caregiver_user_id)
    return user.display_name if user is not None else "Unknown caregiver"


@router.post("/me/caregiver-invites", response_model=InviteCreateOut, status_code=201)
async def create_caregiver_invite(
    current: PatientUserDep, service: CaregiverServiceDep, response: Response
) -> InviteCreateOut:
    """Generate a share code for a loved one (ADR-0047). The plaintext code appears
    in THIS response only — it is stored hashed and can never be re-read."""
    assert current.patient_id is not None  # guaranteed by require_patient
    # The one-time code must never land in a shared or browser cache.
    response.headers["Cache-Control"] = "no-store"
    invite, code = await service.create_invite(
        patient_id=current.patient_id, actor_id=current.user_id
    )
    return InviteCreateOut(id=invite.id, code=code, expires_at=invite.expires_at)


@router.get("/me/caregiver-invites", response_model=list[InviteOut])
async def list_caregiver_invites(
    current: PatientUserDep, service: CaregiverServiceDep
) -> list[InviteOut]:
    """The patient's still-claimable invites (codes themselves are unrecoverable)."""
    assert current.patient_id is not None  # guaranteed by require_patient
    rows = await service.list_open_invites(current.patient_id)
    return [
        InviteOut(id=row.id, created_at=row.created_at, expires_at=row.expires_at) for row in rows
    ]


@router.delete("/me/caregiver-invites/{invite_id}", status_code=204)
async def cancel_caregiver_invite(
    invite_id: uuid.UUID, current: PatientUserDep, service: CaregiverServiceDep
) -> None:
    """Cancel the patient's own invite: the code dies immediately. Idempotent —
    re-cancelling answers 204 again; 404 only for invites that aren't theirs."""
    assert current.patient_id is not None  # guaranteed by require_patient
    invite = await service.cancel_invite(
        patient_id=current.patient_id, actor_id=current.user_id, invite_id=invite_id
    )
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")


@router.get("/me/caregivers", response_model=list[PatientLinkOut])
async def list_caregivers(
    current: PatientUserDep, service: CaregiverServiceDep
) -> list[PatientLinkOut]:
    """The patient's caregiver links — pending requests to accept or decline, active
    caregivers with their scope, and revoked history."""
    assert current.patient_id is not None  # guaranteed by require_patient
    rows = await service.list_links_for_patient(current.patient_id)
    return [
        _link_out(link, user.display_name if user is not None else "Unknown caregiver")
        for link, user in rows
    ]


@router.post("/me/caregivers/{link_id}/accept", response_model=PatientLinkOut)
async def accept_caregiver(
    link_id: uuid.UUID, current: PatientUserDep, service: CaregiverServiceDep
) -> PatientLinkOut:
    """Accept a pending caregiver request — the double opt-in's second step; only
    now does anything become visible (ADR-0047). 404 for anything else (someone
    else's link, unknown id, not pending)."""
    assert current.patient_id is not None  # guaranteed by require_patient
    link = await service.accept_link(
        patient_id=current.patient_id, actor_id=current.user_id, link_id=link_id
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Caregiver request not found")
    return _link_out(link, await _caregiver_name(service, link))


@router.post("/me/caregivers/{link_id}/decline", status_code=204)
async def decline_caregiver(
    link_id: uuid.UUID, current: PatientUserDep, service: CaregiverServiceDep
) -> None:
    """Decline a pending caregiver request: the link dies without ever having been
    readable. 404 unless pending and theirs."""
    assert current.patient_id is not None  # guaranteed by require_patient
    link = await service.decline_link(
        patient_id=current.patient_id, actor_id=current.user_id, link_id=link_id
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Caregiver request not found")


@router.patch("/me/caregivers/{link_id}", response_model=PatientLinkOut)
async def change_caregiver_scope(
    link_id: uuid.UUID, body: ScopeIn, current: PatientUserDep, service: CaregiverServiceDep
) -> PatientLinkOut:
    """Change what THIS caregiver can see (trends <-> full) — effective on their
    very next read. 404 for revoked links and links that aren't theirs."""
    assert current.patient_id is not None  # guaranteed by require_patient
    link = await service.change_scope(
        patient_id=current.patient_id,
        actor_id=current.user_id,
        link_id=link_id,
        scope=CaregiverScope(body.scope),
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Caregiver not found")
    return _link_out(link, await _caregiver_name(service, link))


@router.delete("/me/caregivers/{link_id}", status_code=204)
async def revoke_caregiver(
    link_id: uuid.UUID, current: PatientUserDep, service: CaregiverServiceDep
) -> None:
    """Revoke a caregiver's access: it stops immediately and nothing can block it
    (ADR-0047 — no capability or kill-switch gate exists on this path). Idempotent —
    re-revoking answers 204 again; 404 only for links that aren't theirs."""
    assert current.patient_id is not None  # guaranteed by require_patient
    link = await service.revoke_link(
        patient_id=current.patient_id, actor_id=current.user_id, link_id=link_id
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Caregiver not found")
