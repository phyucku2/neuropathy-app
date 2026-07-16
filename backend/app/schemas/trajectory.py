"""API schemas for the health-trajectory view (the product's centerpiece).

The trajectory is deliberately *explainable*: a direction, a confidence, the computed
signals that drove it, and any data gaps — never an unsourced verdict (Brainstorm #3,
AI-Safety lens). Numbers are computed in code; narrative only synthesizes over them.
"""

from __future__ import annotations

import enum
from datetime import date

from pydantic import BaseModel, Field


class Direction(enum.StrEnum):
    improving = "improving"
    stable = "stable"
    declining = "declining"
    insufficient_data = "insufficient_data"


class ConfidenceLevel(enum.StrEnum):
    """How much to trust the Index (coverage + recency) — NOT a health signal (ADR-0034)."""

    high = "high"
    medium = "medium"
    low = "low"


class SignalTrend(BaseModel):
    code: str = Field(..., examples=["balance_score", "hba1c", "adl_katz"])
    source: str = Field(..., examples=["biomech", "lab", "adl"])
    direction: Direction
    detail: str = Field(
        ..., description="Plain-language, computed-from-data, e.g. 'balance up 8 pts over 30 days'"
    )


class Trajectory(BaseModel):
    direction: Direction
    confidence: float = Field(
        ..., ge=0, le=1, description="Lower when sources are sparse or toggled off"
    )
    summary: str = Field(..., description="Plain-language synthesis, 6th-8th grade reading level")
    signals: list[SignalTrend] = Field(default_factory=list, description="Every driver, sourced")
    data_gaps: list[str] = Field(
        default_factory=list, description="What's missing/inactive that limits confidence"
    )
    narrative_source: str = Field(
        default="deterministic",
        description="'deterministic' (template) or 'ai' (validated model rephrasing, ADR-0011)",
    )
    # ---- Neuropathy Status Index (ADR-0034) — a non-diagnostic 0-100 composite. The
    # card's single source of truth: score + its OWN 30-day delta + Confidence, anchored
    # to a real as_of date. PHI-free (fixed vocabulary + rounded ints, never raw values).
    score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Neuropathy Status Index, 0-100, higher = better. None when no domain present.",
    )
    score_delta_30d: int | None = Field(
        default=None,
        description="Composite now minus ~30 days prior; sign drives the card's direction.",
    )
    as_of: date | None = Field(
        default=None,
        description="Effective date of the newest contributing observation (never wall-clock).",
    )
    confidence_level: ConfidenceLevel | None = Field(
        default=None, description="High/Medium/Low from domain coverage + data recency."
    )
    # Direction is derived SOLELY from `score_delta_30d` (its sign) on every surface —
    # the composite delta is the single source of truth (ADR-0034 §4). No separate
    # direction field ships on the contract: a second "direction" could only ever
    # contradict the delta for some future client.
    data_is_stale: bool = Field(
        default=False,
        description="True when a contributing domain is materially old — the UI says so.",
    )
