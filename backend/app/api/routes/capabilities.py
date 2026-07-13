"""Feature-toggle endpoints: the patient's own toggles and the clinician-managed
variant (ADR-0013).

Routes are thin: validation + HTTP mapping only; the effective-state semantics, the
authority rule, and the change audit live in CapabilityService. Two postures carry
over from the rest of the API:

- **404 over 403** on /clinic/patients/{patient_id}/* — the SAME `_consented_connection`
  gate as the other clinician views (routes/clinic.py), so cross-clinic and
  non-consented patients stay indistinguishable from nonexistent ones.
- **Reads are consent-gated but not audited.** Toggle state is configuration, not
  health data; every CHANGE is audited in the service (ADR-0013 documents the choice).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.api.deps import CapabilityServiceDep, ClinicianUserDep, ClinicServiceDep, PatientUserDep
from app.api.routes.clinic import _consented_connection
from app.schemas.capability import (
    CapabilitiesOut,
    CapabilitySetIn,
    CapabilityStateOut,
    ClinicianCapabilitySetIn,
)
from app.services.capability import CapabilityApiError, EffectiveCapability

router = APIRouter(tags=["capabilities"])


def _to_out(state: EffectiveCapability) -> CapabilityStateOut:
    return CapabilityStateOut(
        key=state.key,
        name=state.name,
        active=state.active,
        managed_by=state.managed_by,
        expires_at=state.expires_at,
        enforced=state.enforced,
    )


@router.get("/capabilities", response_model=CapabilitiesOut)
async def list_capabilities(
    current: PatientUserDep, service: CapabilityServiceDep
) -> CapabilitiesOut:
    """The authenticated patient's effective toggle states — server-judged; client
    toggles are UI hints only (ADR-0013)."""
    assert current.patient_id is not None  # guaranteed by require_patient
    states = await service.effective_states(current.patient_id, now=datetime.now(UTC))
    return CapabilitiesOut(capabilities=[_to_out(state) for state in states])


@router.put("/capabilities/{key}", response_model=CapabilityStateOut)
async def set_own_capability(
    key: str, body: CapabilitySetIn, current: PatientUserDep, service: CapabilityServiceDep
) -> CapabilityStateOut:
    """Patient sets their OWN toggle (B2C authority). 404 for unknown keys; 409 while
    clinically managed (the consented clinic owns the toggles) and while the
    capability is ops-disabled."""
    assert current.patient_id is not None  # guaranteed by require_patient
    try:
        state = await service.set_for_patient(
            patient_id=current.patient_id,
            actor_id=current.user_id,
            key=key,
            active=body.active,
            now=datetime.now(UTC),
        )
    except CapabilityApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    return _to_out(state)


@router.get("/clinic/patients/{patient_id}/capabilities", response_model=CapabilitiesOut)
async def patient_capabilities(
    patient_id: uuid.UUID,
    current: ClinicianUserDep,
    clinic: ClinicServiceDep,
    service: CapabilityServiceDep,
) -> CapabilitiesOut:
    """The consented patient's effective toggle states, for the clinician console."""
    await _consented_connection(clinic, current, patient_id)
    states = await service.effective_states(patient_id, now=datetime.now(UTC))
    return CapabilitiesOut(capabilities=[_to_out(state) for state in states])


@router.put("/clinic/patients/{patient_id}/capabilities/{key}", response_model=CapabilityStateOut)
async def set_patient_capability(
    patient_id: uuid.UUID,
    key: str,
    body: ClinicianCapabilitySetIn,
    current: ClinicianUserDep,
    clinic: ClinicServiceDep,
    service: CapabilityServiceDep,
) -> CapabilityStateOut:
    """Clinician sets a consented patient's toggle, optionally with expiry —
    renewable like an order (ADR-0013). Same 404-over-403 gate as every other
    /clinic/patients/{id}/* route."""
    connection = await _consented_connection(clinic, current, patient_id)
    try:
        state = await service.set_for_clinician(
            connection=connection,
            actor_id=current.user_id,
            key=key,
            active=body.active,
            expires_at=body.expires_at,
            now=datetime.now(UTC),
        )
    except CapabilityApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    if state is None:  # defense in depth in the service re-judged the connection
        raise HTTPException(status_code=404, detail="Patient not found")
    return _to_out(state)
