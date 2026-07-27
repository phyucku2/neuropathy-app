"""Patient food & nutrition log endpoints (ADR-0042 V2, Phase 1).

Rides the existing Observation model (no new tables) exactly like the medications/events
capture routes. Postures identical to the rest of the capture surface:
- Patient role ONLY (`PatientUserDep`).
- Capability-gated WRITES (`log_food`, 409 when off); the GET list is NEVER gated (the toggle
  stops new capture, it must not block the patient's read of their own record).
- Every read is `Cache-Control: no-store` (PHI); every call emits ONE counts-only audit event
  (never the description or the estimate values).
- Idempotent per `client_entry_id` via the shared `import_key` + `add_if_absent` invariant.

NON-DIAGNOSTIC, NON-DOSING: food logs are RANGED self-tracking estimates. They are stored with
`origin=patient_estimated` and a `source=food` that is deliberately excluded from the NSI
(services/trajectory.TRAJECTORY_SOURCES), so they never carry lab-grade weight, and they are
NEVER an input to insulin or medication dosing. The confirm-before-store guardrail is enforced
in the schema (`FoodLogIn.confirmed`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import EmrServiceDep, NutritionSourceDep, PatientUserDep, require_capability
from app.ingestion.food import (
    FOOD_LOG_CODE,
    food_import_key,
    food_log_to_observation,
    food_observation_carbs,
    food_observation_energy,
)
from app.models.audit import AuditEvent
from app.models.observation import SourceType
from app.schemas.food import (
    FoodEstimateDraft,
    FoodEstimateIn,
    FoodEstimateOut,
    FoodLogIn,
    FoodLogList,
    FoodLogOut,
    FoodRange,
)

router = APIRouter(tags=["food"])

# Shown when no automated estimate is available (Phase 1 always; Phase 2+ only when the source
# can't identify the item). Keeps the framing honest — a rough range for self-tracking.
_MANUAL_ENTRY_NOTE = (
    "We can't estimate this automatically yet — enter your best guess as a range below. "
    "Food logs are rough estimates for self-tracking, never exact and never for dosing."
)


def _reject_future(day: date, *, now: datetime) -> None:
    """Reject a future date (422). The date is the patient's LOCAL calendar day, so accept up
    to UTC+14 — the furthest-ahead local date on Earth (mirrors the ADL check-in / meds)."""
    if day > (now + timedelta(hours=14)).date():
        raise HTTPException(status_code=422, detail="date cannot be in the future")


@router.post(
    "/food/estimate",
    response_model=FoodEstimateOut,
    dependencies=[Depends(require_capability("log_food"))],
)
async def estimate_food(
    body: FoodEstimateIn, current: PatientUserDep, source: NutritionSourceDep
) -> FoodEstimateOut:
    """Ask for a draft ranged estimate of a described item. Phase 1 returns none (manual
    entry). No write, no PHI stored — the description is not persisted here."""
    assert current.patient_id is not None  # guaranteed by require_patient
    draft = await source.estimate(description=body.description, portion=body.portion)
    if draft is None:
        return FoodEstimateOut(estimate=None, note=_MANUAL_ENTRY_NOTE)
    energy = (
        None
        if draft.energy_low_kcal is None or draft.energy_high_kcal is None
        else FoodRange(low=draft.energy_low_kcal, high=draft.energy_high_kcal)
    )
    return FoodEstimateOut(
        estimate=FoodEstimateDraft(
            carbs_g=FoodRange(low=draft.carbs_low_g, high=draft.carbs_high_g),
            energy_kcal=energy,
            basis=draft.basis,
        ),
        note="A rough range for self-tracking — review and adjust before you save.",
    )


@router.post(
    "/food",
    response_model=FoodLogOut,
    status_code=201,
    dependencies=[Depends(require_capability("log_food"))],
)
async def record_food(
    body: FoodLogIn, current: PatientUserDep, service: EmrServiceDep
) -> FoodLogOut:
    """Record one confirmed, ranged food log as an append-only row. Idempotent per
    client_entry_id: a retry of one save skips; two genuine logs (distinct ids) both persist.
    The confirm-before-store guardrail is enforced by the schema."""
    assert current.patient_id is not None  # guaranteed by require_patient
    now = datetime.now(UTC)
    _reject_future(body.effective_date, now=now)
    import_key = food_import_key(body.client_entry_id)
    row = food_log_to_observation(
        body, patient_id=current.patient_id, import_key=import_key, recorded_at=now
    )
    inserted = await service.observations.add_if_absent(row)
    food_id = row.id
    if not inserted:
        rows = await service.observations.list_for_patient(
            current.patient_id, source=SourceType.food
        )
        existing = next((r for r in rows if r.import_key == import_key), None)
        if existing is not None and existing.id is not None:
            food_id = existing.id
    assert food_id is not None  # add_if_absent mints the id on insert; skip resolves above
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="record_food",
            patient_id=current.patient_id,
            # Counts/refs only — never the description or the estimate values.
            detail={"has_energy": body.energy_kcal is not None, "skipped": not inserted},
        )
    )
    return FoodLogOut(
        food_id=food_id,
        description=body.description,
        portion=body.portion,
        carbs_g=body.carbs_g,
        energy_kcal=body.energy_kcal,
        effective_at=row.effective_at,
        skipped=not inserted,
    )


# Deliberately NO capability gate — same read-path posture as GET /medications & /events.
@router.get("/food", response_model=FoodLogList)
async def list_food(
    current: PatientUserDep, service: EmrServiceDep, response: Response
) -> FoodLogList:
    """The patient's food logs, newest-first. PHI: `no-store`."""
    assert current.patient_id is not None  # guaranteed by require_patient
    response.headers["Cache-Control"] = "no-store"
    rows = await service.observations.list_for_patient(
        current.patient_id, source=SourceType.food, newest_first=True
    )
    items: list[FoodLogOut] = []
    for row in rows:
        if row.code != FOOD_LOG_CODE:  # pragma: no cover - defensive: source-scoped read
            continue
        payload = row.payload if isinstance(row.payload, dict) else {}
        assert row.id is not None  # persisted rows always carry an id
        items.append(
            FoodLogOut(
                food_id=row.id,
                description=str(payload.get("description") or row.value_text or ""),
                portion=str(payload.get("portion") or ""),
                carbs_g=food_observation_carbs(payload),
                energy_kcal=food_observation_energy(payload),
                effective_at=row.effective_at,
                skipped=False,
            )
        )
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="read_food",
            patient_id=current.patient_id,
            detail={"logs": len(items)},
        )
    )
    return FoodLogList(items=items)
