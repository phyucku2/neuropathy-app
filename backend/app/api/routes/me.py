"""Patient self-service data endpoints — the "Download my data" export (ADR-0031) and
the patient-held Visit-Ready Summary print (ADR-0045).

GET /me/export returns the authenticated patient's CURRENT record as one typed JSON
envelope (the right-of-access sibling to DELETE /auth/me, ADR-0027). GET
/me/visit-summary returns the windowed, curated handout projection over the SAME read
paths. Both are patient role only — `require_patient` answers 403 for clinician/ops and
401 for the unauthenticated caller before the service runs. Every read writes one
PHI-free audit event and is served `Cache-Control: no-store` so the PHI payload is never
cached by a proxy or the browser.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response

from app.api.deps import EmrServiceDep, PatientDataExportDep, PatientUserDep
from app.core.config import settings
from app.models.audit import AuditEvent
from app.schemas.export import ExportOut
from app.schemas.visit_summary import ALLOWED_WINDOW_DAYS, DEFAULT_WINDOW_DAYS, VisitSummary
from app.services.export import ExportError
from app.services.visit_summary import build_visit_summary

router = APIRouter(prefix="/me", tags=["me"])


def _validate_window(window: int) -> None:
    """Reject any window outside the fixed allowed set (422 — mirrors ingestion validation)."""
    if window not in ALLOWED_WINDOW_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"window must be one of {list(ALLOWED_WINDOW_DAYS)} days",
        )


@router.get("/export", response_model=ExportOut)
async def export_my_data(
    current: PatientUserDep, service: PatientDataExportDep, response: Response
) -> ExportOut:
    """Export the authenticated PATIENT's current record (ADR-0031).

    A read plus one PHI-free `export_account` audit event; NO token, secret, or
    password hash is ever part of the payload (the sub-models have no field for them).
    The response carries `Cache-Control: no-store` — the body is the patient's whole
    record, which must never be written to a shared/browser cache. The nothing-written
    refusals (account gone, non-patient, over the export budget) raise and map to
    401/403/429 — safe to raise since nothing has been written.
    """
    # PHI payload: never cache it (set on the success response; the error paths below
    # raise their own PHI-free HTTPException).
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.export_patient_data(user_id=current.user_id)
    except ExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc


@router.get("/visit-summary", response_model=VisitSummary)
async def my_visit_summary(
    current: PatientUserDep,
    service: EmrServiceDep,
    response: Response,
    window: Annotated[int, Query()] = DEFAULT_WINDOW_DAYS,
) -> VisitSummary:
    """The authenticated PATIENT's Visit-Ready Summary over a selectable window (ADR-0045).

    A windowed, curated re-presentation of the patient's own analyzable record — the
    SAME assembly the clinician view answers from (services/visit_summary.py), so the two
    surfaces can never drift. Deterministic; no AI narrator in P1. `now` is resolved once
    here and threaded into the pure assembly. The response is `Cache-Control: no-store`
    (the body is PHI) and the read is audit-logged with counts only, never values.
    """
    assert current.patient_id is not None  # guaranteed by require_patient
    _validate_window(window)
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(UTC)
    summary, observation_count = await build_visit_summary(
        service.observations,
        current.patient_id,
        window=window,
        now=now,
        include_change_questions=settings.include_change_questions,
    )
    # PHI read — audit-logged like every health-data access (CLAUDE.md §5), counts only.
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="read_visit_summary",
            patient_id=current.patient_id,
            detail={"observations": observation_count, "window_days": window},
        )
    )
    return summary
