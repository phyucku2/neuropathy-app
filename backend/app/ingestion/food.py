"""Food-log ingestion — append-only Observation rows + the NutritionSource seam (ADR-0042).

A pure mapping module (mirrors ingestion/events.py): one Observation row per confirmed food
log, no repository or wall clock. Food rides the existing Observation model with its OWN
`source=food`, which is deliberately absent from `services.trajectory.TRAJECTORY_SOURCES` — so
a food log NEVER reaches the trajectory engine, mints no signal, and is excluded from the NSI
(the same structural exclusion `medication`/`event` already get). `origin=patient_estimated`
marks it as a ranged self-tracking estimate that can never be mistaken for lab-grade data.

The `NutritionSource` Protocol is the extension seam for the automated-estimate paths ADR-0042
describes (barcode -> Open Food Facts, text -> USDA, photo -> GPT-4o under the BAA gate). Phase
1 ships `NullNutritionSource` (no automated estimate — manual entry), so the whole feature is
deterministic and testable with no external dependency; later phases swap in the real source
behind this same interface.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Protocol

from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.schemas.food import FoodLogIn, FoodRange

# Stable code for a food-log row (the log is one item; nutrients live in the ranged payload).
FOOD_LOG_CODE = "food_log"


@dataclass(frozen=True)
class RangedNutritionEstimate:
    """A draft ranged estimate a NutritionSource returns — never a point value (ADR-0042)."""

    carbs_low_g: float
    carbs_high_g: float
    basis: str
    energy_low_kcal: float | None = None
    energy_high_kcal: float | None = None


class NutritionSource(Protocol):
    """The seam for turning a described item into a ranged draft estimate.

    Phase 2/3 implementations: barcode -> Open Food Facts, text -> USDA FoodData Central,
    photo -> GPT-4o-vision grounded in those DBs (behind the ADR-0011/0040 BAA gate). Each
    returns a RANGED draft the patient then edits and confirms — never a stored value, never a
    dosing input. Returns None when it cannot estimate (the flow falls back to manual entry).
    """

    async def estimate(
        self, *, description: str, portion: str
    ) -> RangedNutritionEstimate | None: ...


class NullNutritionSource:
    """Phase-1 source: no automated estimate yet — the patient enters their own range.

    Kept as a real object (not None) so the route + frontend already speak the estimate ->
    confirm shape; Phase 2 swaps in a DB-backed source with no route change.
    """

    async def estimate(self, *, description: str, portion: str) -> RangedNutritionEstimate | None:
        return None


def food_import_key(client_entry_id: uuid.UUID) -> str:
    """Fold the client-minted entry id into the import key (ALCOA sweep #3): a retry of one
    save skips gracefully; two genuine same-day logs (distinct ids) both persist."""
    return f"{SourceType.food.value}:{client_entry_id}"


def _date_to_datetime(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def food_log_to_observation(
    body: FoodLogIn,
    *,
    patient_id: uuid.UUID,
    import_key: str,
    recorded_at: datetime,
) -> Observation:
    """Map one confirmed, ranged food log to its append-only Observation row.

    value_num is deliberately left NULL — a food log has no single point value; the ranged
    nutrients live in the payload so the record can never be read as lab-grade precision.
    """
    energy = body.energy_kcal
    return Observation(
        patient_id=patient_id,
        source=SourceType.food,
        origin=DataOrigin.patient_estimated,
        code=FOOD_LOG_CODE,
        code_system=None,
        value_num=None,
        value_text=body.description,
        unit=None,
        effective_at=_date_to_datetime(body.effective_date),
        recorded_at=recorded_at,
        status=ObservationStatus.final,
        revises_id=None,
        recorded_by_role="patient",
        import_key=import_key,
        quality={"human_confirmed": True, "estimate": True, "method": "manual"},
        payload={
            "description": body.description,
            "portion": body.portion,
            "carbs_low_g": body.carbs_g.low,
            "carbs_high_g": body.carbs_g.high,
            "energy_low_kcal": None if energy is None else energy.low,
            "energy_high_kcal": None if energy is None else energy.high,
            "modality": "manual",
        },
    )


def _range_from_payload(
    payload: dict[str, object], low_key: str, high_key: str
) -> FoodRange | None:
    """Reconstruct a FoodRange from two payload keys, or None if either is absent/null."""
    low = payload.get(low_key)
    high = payload.get(high_key)
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        return FoodRange(low=float(low), high=float(high))
    return None


def food_observation_carbs(payload: dict[str, object]) -> FoodRange:
    """The carbohydrate range from a stored food-log payload (carbs are always present)."""
    carbs = _range_from_payload(payload, "carbs_low_g", "carbs_high_g")
    # A stored food log always carries a carb range (schema-required on write); fall back to a
    # zero range only for a defensively-malformed row so the read never 500s.
    return carbs if carbs is not None else FoodRange(low=0.0, high=0.0)


def food_observation_energy(payload: dict[str, object]) -> FoodRange | None:
    """The optional energy range from a stored food-log payload."""
    return _range_from_payload(payload, "energy_low_kcal", "energy_high_kcal")
