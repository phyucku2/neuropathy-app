"""API schema for the Visit-Ready Summary — the clinician handout (ADR-0045 Phase 1).

The Summary **re-presents the patient's own recorded data** over a selectable window,
each datum labeled with its `source`, `origin`, and date so a clinician can
independently review the basis. It makes **no clinical claim**: it does not diagnose,
interpret, recommend, or prioritize. The "questions to ask" are change-surfacing
prompts about the patient's own data — deterministic template constants, never advice
(the FDA-sensitive edge; the interpretive ones are feature-gated OFF, ADR-0041 D2).

It rides the ADR-0031 export assembly's read semantics: the analyzable current record
only (errored/superseded rows excluded), PHI-safe and secrets-absent-by-construction —
there is no token/hash field to leak.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.trajectory import Direction, Trajectory

# Bump on any breaking shape change so a printed/rendered Summary stays interpretable
# by later tooling (forward-compat, mirrors ADR-0031's export envelope).
VISIT_SUMMARY_SCHEMA_VERSION: str = "1.0"

# The window is validated against this fixed set in-handler (mirrors the ingestion
# validation style); anything else is a 422. 60 is the default (owner, 2026-07-19).
ALLOWED_WINDOW_DAYS: tuple[int, ...] = (30, 60, 90, 120, 365)
DEFAULT_WINDOW_DAYS = 60
# Short windows lead with "what changed"; the long windows (120/365) lead with the
# trajectory over time — the diff loses meaning when everything changed (ADR-0045).
SHORT_WINDOWS = frozenset({30, 60, 90})

# A check-in gap this many days or longer surfaces the (clearly-safe, P1) adherence
# prompt — "please confirm how they have been doing".
ADHERENCE_GAP_DAYS = 14

# The non-diagnostic guardrail, co-located with the data on every surface (CLAUDE.md).
NON_DIAGNOSTIC_NOTE: str = (
    "This is a wellness summary of your own recorded data, not a diagnosis. "
    "Each item shows its source and date. Share it with your care team to discuss "
    "what it means."
)
# Printed, the paper leaves the app's control — say what it is (ADR-0031/0045 honesty).
SHEET_LABEL = "current record, not a complete medical record"

# ---- "Questions to ask" templates — the SINGLE SOURCE OF TRUTH (ADR-0045). Every
# emitted prompt is one of these formatted with data; a BAA-gated narrator (out of P1
# scope) may only warmth-rephrase them, never add a question, number, dose, or
# assessment. GUARDRAIL: each points only at WHAT CHANGED and asks the clinician to
# look — never a diagnosis, treatment, or priority.
#
# data_completeness (clearly safe — always rendered when applicable):
ADHERENCE_GAP_QUESTION = (
    "No check-ins in the last {days} days — please confirm how they have been doing."
)
NEW_LAB_QUESTION = (
    "A new {label} result was recorded in this window since the last value — review in context."
)
COVERAGE_GAP_QUESTION = (
    "Function or symptom check-ins are missing for {missing} of the last {window} days "
    "— the between-visit picture is partial."
)
# change_pointed (edges toward decision support — HELD FOR D2, feature-gated OFF via
# settings.include_change_questions default False, ADR-0045 open question #2):
SYMPTOM_DIRECTION_CHANGE_QUESTION = (
    "The {label} trend direction changed over the last {window} days — ask the patient about it."
)
BIOMECH_DIFFERS_QUESTION = (
    "The latest balance and gait result differs from the prior value — please review."
)


class LeadSection(StrEnum):
    """Which section leads the page — computed from the window, never branched in UI."""

    what_changed = "what_changed"
    trajectory = "trajectory"


class SparkPoint(BaseModel):
    """One plotted datum for a dependency-free sparkline (value at a time)."""

    at: datetime
    value: float


class TrendSeries(BaseModel):
    """A windowed series for one signal — sparkline points plus start→now, sourced.

    `direction` is the trajectory engine's per-signal judgment (reused, not a new stat).
    """

    code: str
    label: str
    source: str
    origin: str
    points: list[SparkPoint] = Field(default_factory=list)
    start_value: float | None
    start_at: datetime | None
    latest_value: float | None
    latest_at: datetime | None
    direction: Direction


class PriorDelta(BaseModel):
    """Latest-in-window vs latest-before-window for one signal (e.g. BioMech).

    `direction` is the polarity-judged step from prior→latest (`insufficient_data`
    when there is no prior value).
    """

    code: str
    label: str
    source: str
    origin: str
    latest_value: float | None
    latest_at: datetime | None
    prior_value: float | None
    prior_at: datetime | None
    direction: Direction


class LabDelta(BaseModel):
    """Most-recent-per-analyte vs the prior value, UNIT-SAFE (ADR-0015).

    `delta` is None whenever the prior is absent OR its unit differs from the current
    unit — no cross-unit subtraction ever. `unit_changed` flags the latter so the UI
    can say so instead of silently dropping the number.
    """

    code: str
    label: str
    source: str
    origin: str
    unit: str | None
    latest_value: float | None
    latest_at: datetime | None
    prior_value: float | None
    prior_at: datetime | None
    prior_unit: str | None
    delta: float | None
    unit_changed: bool


class ActivityStat(BaseModel):
    """Wearable / CGM summary statistics only — count + mean/min/max over the window."""

    code: str
    label: str
    source: str
    origin: str
    count: int
    mean: float | None
    min: float | None
    max: float | None
    latest_at: datetime | None


class AdherenceGap(BaseModel):
    """Check-in adherence facts: recency of the last ADL check-in and per-window counts."""

    last_checkin_at: datetime | None
    days_since_last_checkin: int | None
    checkins_in_window: int
    checkins_in_prior_window: int


class SymptomTrendChange(BaseModel):
    """A symptom's current-window trend direction vs the prior window's (engine reuse)."""

    code: str
    label: str
    source: str
    origin: str
    current_direction: Direction
    prior_direction: Direction
    changed: bool


class WhatChanged(BaseModel):
    """The window's deterministic diff against the prior window — the diff, not the dump."""

    new_labs: list[LabDelta] = Field(default_factory=list)
    symptom_trend: list[SymptomTrendChange] = Field(default_factory=list)
    adherence: AdherenceGap
    latest_biomech: list[PriorDelta] = Field(default_factory=list)


class QuestionsToAsk(BaseModel):
    """Change-surfacing prompts about the patient's own data — templates, never advice.

    `change_pointed` is EMPTY unless `include_change_questions` is on (FDA D2 gate,
    ADR-0045 open question #2); `data_completeness` always renders when applicable.
    """

    data_completeness: list[str] = Field(default_factory=list)
    change_pointed: list[str] = Field(default_factory=list)


class PlaceholderRow(BaseModel):
    """A forward-stable layout row for a section not yet captured (render-only, P1)."""

    key: str
    label: str
    status: Literal["not_yet_tracked"] = "not_yet_tracked"
    phase: str


# The placeholder sections (ADR-0045): render-only in P1 — NO SourceType, model, enum,
# or migration until the capture phases land. Constants keep the layout stable.
PLACEHOLDER_ROWS: tuple[PlaceholderRow, ...] = (
    PlaceholderRow(key="medications", label="Medications & supplements", phase="Phase 2"),
    PlaceholderRow(key="emr_notes", label="EMR clinician notes", phase="Phase 2"),
    PlaceholderRow(key="patient_notes", label="Patient notes & events", phase="Phase 2"),
    PlaceholderRow(key="nutrition", label="Nutrition", phase="Phase 3"),
)


class VisitSummary(BaseModel):
    """The Visit-Ready Summary envelope for one patient over one window (ADR-0045 P1)."""

    generated_at: datetime
    schema_version: str = VISIT_SUMMARY_SCHEMA_VERSION
    subject_id: uuid.UUID
    window_days: int
    # The diff boundaries, surfaced for transparency of what "current" vs "prior" mean.
    window_end: datetime
    current_window_start: datetime
    prior_window_start: datetime
    # Which section leads — computed from the window, never branched in the UI.
    lead_section: LeadSection
    # The windowed NSI + direction/confidence + signals + data_gaps (engine reuse).
    status: Trajectory
    what_changed: WhatChanged
    symptoms: list[TrendSeries] = Field(default_factory=list)
    function: list[TrendSeries] = Field(default_factory=list)
    balance_gait: list[PriorDelta] = Field(default_factory=list)
    labs: list[LabDelta] = Field(default_factory=list)
    activity: list[ActivityStat] = Field(default_factory=list)
    placeholders: list[PlaceholderRow] = Field(default_factory=list)
    questions: QuestionsToAsk
    disclaimer: str = NON_DIAGNOSTIC_NOTE
    sheet_label: str = SHEET_LABEL
