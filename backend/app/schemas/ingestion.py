"""API schemas for the patient data-entry surface: lab upload, ADL daily check-in, and
the observations list (ADR-0003, ADR-0006, ADR-0007).

The lab upload receives results the patient has ALREADY confirmed on-device (the mobile
app OCRs and human-confirms locally per ADR-0003) — structured values only, never raw
documents. The observations list paginates by limit/offset (documented contract:
`limit` 1-100 default 50, `offset` >= 0, newest first by `effective_at`).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.lab import LabResultIn

# One upload maps to one confirmed document/panel; anything larger is not a plausible
# single human-confirmed panel and is rejected at the boundary (422).
MAX_LAB_BATCH = 100

# The ADL daily check-in: three 0-4 answers and their 0-12 derived composite.
ADL_ANSWER_MAX = 4
ADL_COMPOSITE_MAX = 12

# Symptom check-in (ADR-0034 Phase 1): pain + numbness/paresthesia, each a 0-10 severity
# item where HIGHER = WORSE (the opposite polarity of the function answers above). These
# are validated-measure-ALIGNED, not the instruments themselves: pain uses a 0-10 Numeric
# Rating Scale (NRS, public-domain); numbness/tingling is an NTSS-6-aligned severity item.
# Exact NTSS-6 wording/scoring and licensing are NOT confirmed (ADR-0034 "confirm against
# source"), so nothing here claims to BE NTSS-6 or a validated instrument. Phase 1 only
# CAPTURES and STORES — no normalization/scoring (Phase 2 inverts the polarity).
SYMPTOM_NRS_MAX = 10


class LabImportIn(BaseModel):
    """A panel of lab results the patient confirmed on-device (ADR-0003)."""

    results: list[LabResultIn] = Field(..., min_length=1, max_length=MAX_LAB_BATCH)


class LabImportOut(BaseModel):
    """Import outcome: how many rows were persisted vs already on file (idempotent)."""

    imported: int = Field(..., ge=0)
    skipped: int = Field(..., ge=0, description="Already imported (same content identity)")


class AdlCheckInIn(BaseModel):
    """One daily function check-in — the three questions from the mockups, each 0-4
    (higher = better). `check_in_date` defaults to today (UTC) when omitted."""

    walking: int = Field(..., ge=0, le=ADL_ANSWER_MAX, description="How walking felt today")
    stairs: int = Field(..., ge=0, le=ADL_ANSWER_MAX, description="How stairs felt today")
    balance_confidence: int = Field(
        ..., ge=0, le=ADL_ANSWER_MAX, description="Confidence in balance today"
    )
    # Symptom items (ADR-0034 Phase 1) — OPTIONAL so the base function check-in stays
    # back-compatible, and gated by the `ingest_symptoms` capability: when that toggle is
    # off the route ignores these entirely (enforced-flag honesty, ADR-0013). Higher =
    # worse (inverse polarity of the function answers), persisted per-observation.
    pain: int | None = Field(
        default=None,
        ge=0,
        le=SYMPTOM_NRS_MAX,
        description="Worst pain today, 0-10 NRS (0 = none, 10 = worst imaginable)",
    )
    numbness: int | None = Field(
        default=None,
        ge=0,
        le=SYMPTOM_NRS_MAX,
        description="Numbness/tingling severity today, 0-10 (0 = none, 10 = most severe); "
        "NTSS-6-aligned symptom item",
    )
    check_in_date: date | None = Field(
        default=None, description="Calendar day the answers are about (default: today, UTC)"
    )


class AdlCheckInOut(BaseModel):
    check_in_date: date
    daily_score: int = Field(..., ge=0, le=ADL_COMPOSITE_MAX)
    superseded: bool = Field(
        ..., description="True when this check-in replaced an earlier one for the same day"
    )


class ObservationItem(BaseModel):
    """One of the patient's own analyzable records — display fields only, no internals."""

    code: str
    display: str | None
    value: float | None
    value_text: str | None
    unit: str | None
    effective_at: datetime
    source: str
    status: str


class ObservationPage(BaseModel):
    """Offset-paginated page of the patient's analyzable records, newest first."""

    items: list[ObservationItem]
    total: int = Field(..., ge=0, description="All analyzable records matching the filter")
    limit: int
    offset: int
