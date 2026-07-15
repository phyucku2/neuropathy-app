"""Patient self-service data endpoints — the "Download my data" export (ADR-0031).

GET /me/export returns the authenticated patient's CURRENT record as one typed JSON
envelope (the right-of-access sibling to DELETE /auth/me, ADR-0027). Patient role only
— `require_patient` answers 403 for clinician/ops and 401 for the unauthenticated
caller before the service runs. Every export writes one PHI-free audit event, is capped
per actor by a sliding window (429 over budget), and is served `Cache-Control: no-store`
so the PHI payload is never cached by a proxy or the browser.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.api.deps import PatientDataExportDep, PatientUserDep
from app.schemas.export import ExportOut
from app.services.export import ExportError

router = APIRouter(prefix="/me", tags=["me"])


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
