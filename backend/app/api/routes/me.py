"""Patient self-service data endpoints — the "Download my data" export (ADR-0031).

GET /me/export returns the authenticated patient's COMPLETE record as one typed JSON
envelope (the right-of-access sibling to DELETE /auth/me, ADR-0027). Patient role only
— `require_patient` answers 403 for clinician/ops and 401 for the unauthenticated
caller before the service runs. Every export writes one PHI-free audit event.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import PatientDataExportDep, PatientUserDep
from app.schemas.export import ExportOut
from app.services.export import ExportError

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/export", response_model=ExportOut)
async def export_my_data(current: PatientUserDep, service: PatientDataExportDep) -> ExportOut:
    """Export the authenticated PATIENT's complete record (ADR-0031).

    A read plus one PHI-free `export_account` audit event; NO token, secret, or
    password hash is ever part of the payload (the sub-models have no field for them).
    The nothing-written defense-in-depth refusals (account gone, non-patient) raise and
    map to 401/403 — safe to raise since nothing has been written.
    """
    try:
        return await service.export_patient_data(user_id=current.user_id)
    except ExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
