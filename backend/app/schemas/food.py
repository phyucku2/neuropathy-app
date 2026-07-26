"""API schemas for the patient food & nutrition log (ADR-0042 V2, Phase 1).

Each food log is one APPEND-ONLY Observation row (source=food, origin=patient_estimated):
a short, dated, RANGED self-tracking estimate of a meal — never lab-grade, excluded from the
NSI, and never an input to insulin/medication dosing.

The guardrails from ADR-0042 are STRUCTURAL here, not just copy:
- **Ranged, not point.** Every nutrient is a `FoodRange` (low..high); there is no single-value
  field, so the schema cannot express false precision.
- **Human-confirmed.** `FoodLogIn.confirmed` must be True — the client sends a draft the patient
  has reviewed and accepted; an unconfirmed body is rejected (422), so nothing is stored until
  the human confirms (ADR-0042 "nothing is stored as an Observation until confirmed").
- Phase 1 is MANUAL entry: the patient supplies the ranges. The automated-estimate endpoint
  (`/food/estimate`) exists but returns no estimate yet (Phase 2 wires barcode/text/photo behind
  the `NutritionSource` seam), degrading gracefully to manual entry.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.base import ApiModel

DESCRIPTION_MAX = 120
PORTION_MAX = 60
# Generous sanity caps — a food log is an estimate, not a measurement, but absurd input
# (a typo of thousands of grams) should not persist. Well above any real single meal.
CARBS_MAX_G = 1000.0
ENERGY_MAX_KCAL = 10000.0


class FoodRange(ApiModel):
    """A ranged nutrient estimate (low..high) — the ONLY way a nutrient is expressed, so a
    point/false-precision value is unrepresentable (ADR-0042)."""

    low: float = Field(..., ge=0, description="Low end of the estimate")
    high: float = Field(..., ge=0, description="High end of the estimate")

    @model_validator(mode="after")
    def _low_not_above_high(self) -> FoodRange:
        if self.low > self.high:
            raise ValueError("range low cannot exceed high")
        return self


class FoodEstimateIn(ApiModel):
    """Ask for a draft estimate of a described item (Phase 1: returns none — manual entry)."""

    description: str = Field(..., min_length=1, max_length=DESCRIPTION_MAX)
    portion: str = Field(..., min_length=1, max_length=PORTION_MAX, description="e.g. '1 cup'")


class FoodEstimateDraft(ApiModel):
    """A draft ranged estimate the patient then edits and confirms."""

    carbs_g: FoodRange
    energy_kcal: FoodRange | None = None
    basis: str = Field(..., description="Where the estimate came from (plain language)")


class FoodEstimateOut(ApiModel):
    """The estimate draft, or none when no automated source is available (Phase 1)."""

    estimate: FoodEstimateDraft | None = None
    # A plain-language line the UI shows — always framing this as a rough range, and in Phase 1
    # telling the patient to enter their own estimate.
    note: str


class FoodLogIn(ApiModel):
    """Record one confirmed, ranged food log (ADR-0042)."""

    description: str = Field(..., min_length=1, max_length=DESCRIPTION_MAX)
    portion: str = Field(..., min_length=1, max_length=PORTION_MAX, description="e.g. '1 cup'")
    carbs_g: FoodRange = Field(..., description="Estimated carbohydrate range")
    energy_kcal: FoodRange | None = Field(default=None, description="Optional energy range")
    effective_date: date = Field(..., description="The day the food was eaten")
    client_entry_id: UUID = Field(
        ..., description="Client-minted idempotency id — a retry of one save skips"
    )
    confirmed: bool = Field(
        ..., description="Must be true: the patient has reviewed and accepted this estimate"
    )

    @model_validator(mode="after")
    def _enforce_guardrails(self) -> FoodLogIn:
        # Human-confirm is structural: an unconfirmed draft is never stored (ADR-0042).
        if not self.confirmed:
            raise ValueError("a food log must be confirmed before it is saved")
        if self.carbs_g.high > CARBS_MAX_G:
            raise ValueError(f"carbohydrate estimate exceeds the {CARBS_MAX_G:g} g sanity cap")
        if self.energy_kcal is not None and self.energy_kcal.high > ENERGY_MAX_KCAL:
            raise ValueError(f"energy estimate exceeds the {ENERGY_MAX_KCAL:g} kcal sanity cap")
        return self


class FoodLogOut(ApiModel):
    """One recorded food log. `skipped` is True on an idempotent retry (client_entry_id
    already on file), so no new row was written."""

    food_id: UUID
    description: str
    portion: str
    carbs_g: FoodRange
    energy_kcal: FoodRange | None
    effective_at: datetime
    skipped: bool


class FoodLogList(ApiModel):
    """The patient's food logs, newest-first."""

    items: list[FoodLogOut] = Field(default_factory=list)
