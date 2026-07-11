"""API schemas for the health-trajectory view (the product's centerpiece).

The trajectory is deliberately *explainable*: a direction, a confidence, the computed
signals that drove it, and any data gaps — never an unsourced verdict (Brainstorm #3,
AI-Safety lens). Numbers are computed in code; narrative only synthesizes over them.
"""
from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class Direction(str, enum.Enum):
    improving = "improving"
    stable = "stable"
    declining = "declining"
    insufficient_data = "insufficient_data"


class SignalTrend(BaseModel):
    code: str = Field(..., examples=["balance_score", "hba1c", "adl_katz"])
    source: str = Field(..., examples=["biomech", "lab", "adl"])
    direction: Direction
    detail: str = Field(..., description="Plain-language, computed-from-data, e.g. 'balance up 8 pts over 30 days'")


class Trajectory(BaseModel):
    direction: Direction
    confidence: float = Field(..., ge=0, le=1, description="Lower when sources are sparse or toggled off")
    summary: str = Field(..., description="Plain-language synthesis, 6th-8th grade reading level")
    signals: list[SignalTrend] = Field(default_factory=list, description="Every driver, sourced")
    data_gaps: list[str] = Field(default_factory=list, description="What's missing/inactive that limits confidence")
