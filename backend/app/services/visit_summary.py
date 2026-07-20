"""Visit-Ready Summary assembly — the clinician handout (ADR-0045 Phase 1).

One windowed, curated projection over the patient's own analyzable record, shared by
the patient print (`GET /me/visit-summary`) and the clinician view
(`GET /clinic/patients/{id}/visit-summary`) so the two surfaces can never drift
(mirrors services/trajectory.py, ADR-0012).

The heavy lifting is a PURE function (`assemble_visit_summary`) that takes rows + a
fixed `now` and returns the typed `VisitSummary` — deterministic and unit-testable
with no repository or wall-clock. `build_visit_summary` is the thin repository-reading
wrapper the routes call; it reads a 2×window lookback and partitions in Python (the
repository exposes only a `since` lower bound — an `until` Protocol change would be a
broad blast radius, deferred).

Every number is computed in code and re-presents the patient's own data; the trajectory
engine is REUSED for all directions (no new stat). Nothing here interprets or judges —
the "questions to ask" are deterministic template constants, and the interpretive
(change-pointed) ones are feature-gated OFF (ADR-0041 D2, ADR-0045 open question #2).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.ingestion.medications import FoldedMedication, fold_medications
from app.models.observation import Observation, SourceType
from app.repositories.observation import ObservationRepository
from app.schemas.trajectory import Direction, Trajectory
from app.schemas.visit_summary import (
    ADHERENCE_GAP_DAYS,
    ADHERENCE_GAP_QUESTION,
    BIOMECH_DIFFERS_QUESTION,
    COVERAGE_GAP_QUESTION,
    EVENT_RECORDED_QUESTION,
    MED_CHANGE_QUESTION,
    NEW_LAB_QUESTION,
    PLACEHOLDER_ROWS,
    SHORT_WINDOWS,
    SYMPTOM_DIRECTION_CHANGE_QUESTION,
    ActivityStat,
    AdherenceGap,
    LabDelta,
    LeadSection,
    MedicationChangeDelta,
    MedicationItem,
    PatientEventItem,
    PriorDelta,
    QuestionsToAsk,
    SparkPoint,
    SymptomTrendChange,
    TrendSeries,
    VisitSummary,
    WhatChanged,
)
from app.services.observation import counts_toward_analysis
from app.trajectory.directionality import Polarity, polarity_for, signal_info
from app.trajectory.engine import compute_trajectory
from app.trajectory.points import points_from_observations

# The self-reported symptom + function series the handout sparklines (ADR-0034/0045).
_SYMPTOM_CODES = ("symptom_pain", "symptom_numbness")
_FUNCTION_CODES = ("adl_walking", "adl_stairs", "adl_balance_confidence")

# The sources the trajectory engine judges. Medication/event rows carry a numeric dose and
# unknown codes, so feeding them to compute_trajectory would mint a spurious
# "unknown-polarity" signal under "What's driving it" — they are excluded (ADR-0045 P2).
_TRAJECTORY_SOURCES = frozenset(
    {SourceType.lab, SourceType.adl, SourceType.biomech, SourceType.wearable}
)

# A row/timestamp pair, effective_at coerced tz-aware once at the window filter.
_Row = tuple[Observation, datetime]


def _aware(value: datetime) -> datetime:
    """Treat a naive stored timestamp as UTC (mirrors the repository read path)."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _analyzable_in_window(
    rows: list[Observation], *, lower: datetime, upper: datetime
) -> list[_Row]:
    """Current, non-errored, non-superseded rows whose effective_at is in [lower, upper].

    Re-applies the integrity filter (defense in depth — the repository already does,
    but the pure function must stand alone) and coerces naive timestamps to UTC so a
    tz-naive row never crashes the window comparison (regression mirrors trajectory).
    """
    superseded = {r.revises_id for r in rows if r.revises_id is not None}
    kept: list[_Row] = []
    for row in rows:
        if row.id is not None and row.id in superseded:
            continue
        if not counts_toward_analysis(row.status):
            continue
        effective_at = _aware(row.effective_at)
        if effective_at < lower or effective_at > upper:
            continue
        kept.append((row, effective_at))
    return kept


def _group_by_code(pairs: list[_Row]) -> dict[str, list[_Row]]:
    """Group (row, at) pairs into per-code lists, each ordered oldest-first."""
    grouped: dict[str, list[_Row]] = {}
    for row, at in pairs:
        grouped.setdefault(row.code, []).append((row, at))
    for series in grouped.values():
        series.sort(key=lambda pair: pair[1])
    return grouped


def _numeric(series: list[_Row]) -> list[_Row]:
    """Only the points that carry a numeric value (qualitative results can't be plotted)."""
    return [(row, at) for row, at in series if row.value_num is not None]


def _signal_directions(trajectory: Trajectory) -> dict[str, Direction]:
    """The engine's per-signal direction by code — reused, never recomputed."""
    return {signal.code: signal.direction for signal in trajectory.signals}


def _step_direction(code: str, prior: float | None, latest: float | None) -> Direction:
    """Judge a single prior→latest step via the signal's polarity (no new stat).

    Unjudgeable (no prior, or a polarity a single step can't classify — in-range or
    unknown) reports `insufficient_data`, never a guessed better/worse.
    """
    if prior is None or latest is None:
        return Direction.insufficient_data
    if latest == prior:
        return Direction.stable
    higher = latest > prior
    polarity = polarity_for(code)
    if polarity is Polarity.higher_is_better:
        return Direction.improving if higher else Direction.declining
    if polarity is Polarity.lower_is_better:
        return Direction.declining if higher else Direction.improving
    return Direction.insufficient_data


def _trend_section(
    codes: tuple[str, ...], current_by_code: dict[str, list[_Row]], directions: dict[str, Direction]
) -> list[TrendSeries]:
    """Build the sparkline series for a fixed set of codes present in the current window."""
    section: list[TrendSeries] = []
    for code in codes:
        series = _numeric(current_by_code.get(code, []))
        if series:
            direction = directions.get(code, Direction.insufficient_data)
            section.append(_trend_series(code, series, direction))
    return section


def _trend_series(code: str, series: list[_Row], direction: Direction) -> TrendSeries:
    first_row, first_at = series[0]
    latest_row, latest_at = series[-1]
    info = signal_info(code)
    return TrendSeries(
        code=code,
        label=info.label,
        source=latest_row.source.value,
        origin=latest_row.origin.value,
        points=[SparkPoint(at=at, value=float(row.value_num)) for row, at in series],  # type: ignore[arg-type]
        start_value=float(first_row.value_num),  # type: ignore[arg-type]
        start_at=first_at,
        latest_value=float(latest_row.value_num),  # type: ignore[arg-type]
        latest_at=latest_at,
        direction=direction,
    )


def _prior_delta(code: str, current: list[_Row], prior: list[_Row]) -> PriorDelta:
    latest_row, latest_at = current[-1] if current else (None, None)
    prior_row, prior_at = prior[-1] if prior else (None, None)
    reference = latest_row or prior_row
    assert reference is not None  # only called for codes present in one of the windows
    latest_value = (
        float(latest_row.value_num)
        if latest_row is not None and latest_row.value_num is not None
        else None
    )
    prior_value = (
        float(prior_row.value_num)
        if prior_row is not None and prior_row.value_num is not None
        else None
    )
    info = signal_info(code)
    return PriorDelta(
        code=code,
        label=info.label,
        source=reference.source.value,
        origin=reference.origin.value,
        latest_value=latest_value,
        latest_at=latest_at,
        prior_value=prior_value,
        prior_at=prior_at,
        direction=_step_direction(code, prior_value, latest_value),
    )


def _lab_delta(code: str, current: list[_Row], prior: list[_Row]) -> LabDelta:
    latest_row, latest_at = current[-1]  # current is non-empty by construction
    prior_row, prior_at = prior[-1] if prior else (None, None)
    info = signal_info(code)
    unit = latest_row.unit
    latest_value = float(latest_row.value_num) if latest_row.value_num is not None else None
    prior_value = (
        float(prior_row.value_num)
        if prior_row is not None and prior_row.value_num is not None
        else None
    )
    prior_unit = prior_row.unit if prior_row is not None else None
    # UNIT-SAFE (ADR-0015): a changed unit means NO cross-unit subtraction — flag it and
    # withhold the delta rather than silently subtracting incomparable magnitudes.
    unit_changed = prior_row is not None and prior_unit != unit
    delta = (
        latest_value - prior_value
        if latest_value is not None and prior_value is not None and not unit_changed
        else None
    )
    return LabDelta(
        code=code,
        label=info.label,
        source=latest_row.source.value,
        origin=latest_row.origin.value,
        unit=unit,
        latest_value=latest_value,
        latest_at=latest_at,
        prior_value=prior_value,
        prior_at=prior_at,
        prior_unit=prior_unit,
        delta=delta,
        unit_changed=unit_changed,
    )


def _activity_stat(code: str, current: list[_Row]) -> ActivityStat:
    latest_row, latest_at = current[-1]
    values = [float(row.value_num) for row, _ in current if row.value_num is not None]
    info = signal_info(code)
    return ActivityStat(
        code=code,
        label=info.label,
        source=latest_row.source.value,
        origin=latest_row.origin.value,
        count=len(values),
        mean=(sum(values) / len(values)) if values else None,
        min=min(values) if values else None,
        max=max(values) if values else None,
        latest_at=latest_at,
    )


def _adherence_gap(current: list[_Row], prior: list[_Row], *, now: datetime) -> AdherenceGap:
    current_adl = [(r, at) for r, at in current if r.source is SourceType.adl]
    prior_adl = [(r, at) for r, at in prior if r.source is SourceType.adl]
    all_adl = current_adl + prior_adl
    last_at = max((at for _, at in all_adl), default=None)
    return AdherenceGap(
        last_checkin_at=last_at,
        days_since_last_checkin=(now - last_at).days if last_at is not None else None,
        # Distinct calendar days with a check-in — many entries in one day count once.
        checkins_in_window=len({at.date() for _, at in current_adl}),
        checkins_in_prior_window=len({at.date() for _, at in prior_adl}),
    )


def _medication_item(folded: FoldedMedication) -> MedicationItem:
    return MedicationItem(
        medication_id=folded.medication_id,
        name=folded.name,
        kind=folded.kind,
        status=folded.status,
        current_dose_amount=folded.current_dose_amount,
        current_dose_unit=folded.current_dose_unit,
        current_dose_text=folded.current_dose_text,
        prescriber=folded.prescriber,
        started_on=folded.started_on,
        last_change_at=folded.last_change_at,
    )


def _medication_changes_in_window(
    medication_rows: list[Observation], *, lower: datetime, upper: datetime
) -> list[MedicationChangeDelta]:
    """Every medication CHANGE ROW whose effective_at is in the current window (ADR-0045 P2).

    Descriptive only — names what the patient recorded (drug, kind, change_type, dose,
    date). Ordered newest-first. NO reconciliation or recommendation.
    """
    deltas: list[MedicationChangeDelta] = []
    for row in _analyzable_in_window(medication_rows, lower=lower, upper=upper):
        obs, at = row
        payload = obs.payload if isinstance(obs.payload, dict) else {}
        deltas.append(
            MedicationChangeDelta(
                medication_id=obs.code,
                name=obs.value_text or "",
                kind=str(payload.get("kind") or ""),
                change_type=str(payload.get("change_type") or "added"),
                dose_amount=obs.value_num,
                dose_unit=obs.unit,
                dose_text=(
                    str(payload["dose_text"]) if isinstance(payload.get("dose_text"), str) else None
                ),
                effective_at=at,
            )
        )
    deltas.sort(key=lambda d: d.effective_at, reverse=True)
    return deltas


def _patient_notes(windowed: list[_Row]) -> list[PatientEventItem]:
    """The between-visit events/notes in the window, newest-first (ADR-0045 P2)."""
    notes: list[PatientEventItem] = []
    for row, at in windowed:
        if row.source is not SourceType.event:
            continue
        payload = row.payload if isinstance(row.payload, dict) else {}
        notes.append(
            PatientEventItem(
                type=str(payload.get("type") or ""),
                display=str(payload.get("display") or ""),
                effective_at=at,
                note=row.value_text,
                reviewed=bool(payload.get("reviewed", False)),
            )
        )
    notes.sort(key=lambda n: n.effective_at, reverse=True)
    return notes


def assemble_visit_summary(
    rows: list[Observation],
    *,
    subject_id: uuid.UUID,
    window: int,
    now: datetime,
    include_change_questions: bool,
    medication_rows: list[Observation] | None = None,
) -> VisitSummary:
    """Build the windowed VisitSummary over one patient's rows (pure, deterministic).

    Same rows + same `now` + same window always yield the same VisitSummary. `now` is
    threaded in (never wall-clock here) so results are reproducible and testable.

    `medication_rows` is the patient's FULL (unbounded) medication history — the
    current-medications fold needs a med's `added` row even when it was started before the
    2×window lookback (ADR-0045 P2). When omitted (older callers/tests), the medications
    section is empty.
    """
    medication_rows = medication_rows or []
    window_end = now
    current_window_start = now - timedelta(days=window)
    prior_window_start = now - timedelta(days=2 * window)

    windowed = _analyzable_in_window(rows, lower=prior_window_start, upper=window_end)
    current = [(r, at) for r, at in windowed if at >= current_window_start]
    prior = [(r, at) for r, at in windowed if at < current_window_start]

    # Engine reuse: the status hero is compute_trajectory over the CURRENT window; the
    # prior trajectory is anchored at now-window and used ONLY for the symptom-direction
    # diff (its recency/confidence baseline is intentionally shifted — see ADR-0045).
    # Medication/event rows are EXCLUDED from the engine (they carry a dose + unknown code
    # and would mint a spurious signal) — every real section filters by explicit code/source.
    current_traj_rows = [r for r, _ in current if r.source in _TRAJECTORY_SOURCES]
    prior_traj_rows = [r for r, _ in prior if r.source in _TRAJECTORY_SOURCES]
    status = compute_trajectory(points_from_observations(current_traj_rows), now=now)
    prior_traj = compute_trajectory(
        points_from_observations(prior_traj_rows), now=current_window_start
    )
    current_dirs = _signal_directions(status)
    prior_dirs = _signal_directions(prior_traj)

    current_by_code = _group_by_code(current)
    prior_by_code = _group_by_code(prior)

    # --- Symptoms + function sparklines (current window, engine direction) ---
    symptoms = _trend_section(_SYMPTOM_CODES, current_by_code, current_dirs)
    function = _trend_section(_FUNCTION_CODES, current_by_code, current_dirs)

    # --- Balance & gait (BioMech): latest-in-window vs latest-before-window ---
    biomech_codes = sorted(
        {r.code for r, _ in windowed if r.source is SourceType.biomech and r.value_num is not None}
    )
    balance_gait: list[PriorDelta] = [
        _prior_delta(
            code,
            _numeric(current_by_code.get(code, [])),
            _numeric(prior_by_code.get(code, [])),
        )
        for code in biomech_codes
    ]

    # --- Labs: most-recent-per-analyte in the window + prior, unit-safe ---
    lab_codes = sorted(
        {r.code for r, _ in current if r.source is SourceType.lab and r.value_num is not None}
    )
    labs: list[LabDelta] = [
        _lab_delta(code, _numeric(current_by_code[code]), _numeric(prior_by_code.get(code, [])))
        for code in lab_codes
    ]

    # --- Activity / glucose (wearable/CGM): summary stats only ---
    activity_codes = sorted(
        {r.code for r, _ in current if r.source is SourceType.wearable and r.value_num is not None}
    )
    activity = [_activity_stat(code, _numeric(current_by_code[code])) for code in activity_codes]

    # --- What changed (deterministic diff) ---
    adherence = _adherence_gap(current, prior, now=now)
    symptom_trend: list[SymptomTrendChange] = []
    for code in _SYMPTOM_CODES:
        if code not in current_by_code and code not in prior_by_code:
            continue
        current_direction = current_dirs.get(code, Direction.insufficient_data)
        prior_direction = prior_dirs.get(code, Direction.insufficient_data)
        symptom_trend.append(
            SymptomTrendChange(
                code=code,
                label=signal_info(code).label,
                source=SourceType.adl.value,
                origin="patient_reported",
                current_direction=current_direction,
                prior_direction=prior_direction,
                changed=current_direction != prior_direction,
            )
        )
    # --- Medications (full-history fold) + patient notes/events (windowed) ---
    medications = [_medication_item(folded) for folded in fold_medications(medication_rows)]
    patient_notes = _patient_notes(windowed)
    medication_changes = _medication_changes_in_window(
        medication_rows, lower=current_window_start, upper=window_end
    )

    what_changed = WhatChanged(
        new_labs=labs,
        symptom_trend=symptom_trend,
        adherence=adherence,
        latest_biomech=balance_gait,
        medication_changes=medication_changes,
    )

    questions = _build_questions(
        window=window,
        has_data=bool(windowed),
        adherence=adherence,
        labs=labs,
        symptom_trend=symptom_trend,
        balance_gait=balance_gait,
        include_change_questions=include_change_questions,
        has_medication_changes=bool(medication_changes),
        has_events=bool(patient_notes),
    )

    return VisitSummary(
        generated_at=now,
        subject_id=subject_id,
        window_days=window,
        window_end=window_end,
        current_window_start=current_window_start,
        prior_window_start=prior_window_start,
        lead_section=(
            LeadSection.what_changed if window in SHORT_WINDOWS else LeadSection.trajectory
        ),
        status=status,
        what_changed=what_changed,
        symptoms=symptoms,
        function=function,
        balance_gait=balance_gait,
        labs=labs,
        activity=activity,
        medications=medications,
        patient_notes=patient_notes,
        placeholders=list(PLACEHOLDER_ROWS),
        questions=questions,
    )


_JUDGED = frozenset({Direction.improving, Direction.stable, Direction.declining})


def _build_questions(
    *,
    window: int,
    has_data: bool,
    adherence: AdherenceGap,
    labs: list[LabDelta],
    symptom_trend: list[SymptomTrendChange],
    balance_gait: list[PriorDelta],
    include_change_questions: bool,
    has_medication_changes: bool,
    has_events: bool,
) -> QuestionsToAsk:
    """Assemble the change-surfacing prompts from the template constants only.

    data_completeness is clearly safe and always renders when applicable; change_pointed
    edges toward decision support and stays EMPTY unless the feature flag is on (D2 gate).
    """
    data_completeness: list[str] = []
    change_pointed: list[str] = []

    # An empty account has nothing honest to prompt about — keep it minimal.
    if has_data:
        days_since = adherence.days_since_last_checkin
        if days_since is None or days_since >= ADHERENCE_GAP_DAYS:
            data_completeness.append(
                ADHERENCE_GAP_QUESTION.format(days=days_since if days_since is not None else window)
            )
        # Presence of new lab data, per analyte, since the last recorded value (no
        # interpretation of the value itself).
        for lab in labs:
            if lab.prior_value is not None:
                data_completeness.append(NEW_LAB_QUESTION.format(label=lab.label))
        # Partial between-visit coverage (some check-ins, but not every day).
        covered = adherence.checkins_in_window
        if 0 < covered < window:
            data_completeness.append(
                COVERAGE_GAP_QUESTION.format(missing=window - covered, window=window)
            )

    # Medication/event completeness prompts (ADR-0045 P2): clearly-safe, point only at what
    # the patient recorded in the window — no interpretation. Independent of has_data since a
    # medication change or event is itself the recorded data.
    if has_medication_changes:
        data_completeness.append(MED_CHANGE_QUESTION)
    if has_events:
        data_completeness.append(EVENT_RECORDED_QUESTION)

    if include_change_questions:
        for change in symptom_trend:
            if (
                change.changed
                and change.current_direction in _JUDGED
                and change.prior_direction in _JUDGED
            ):
                change_pointed.append(
                    SYMPTOM_DIRECTION_CHANGE_QUESTION.format(label=change.label, window=window)
                )
        if any(
            delta.prior_value is not None
            and delta.direction in (Direction.improving, Direction.declining)
            for delta in balance_gait
        ):
            change_pointed.append(BIOMECH_DIFFERS_QUESTION)

    return QuestionsToAsk(data_completeness=data_completeness, change_pointed=change_pointed)


async def build_visit_summary(
    observations: ObservationRepository,
    subject_id: uuid.UUID,
    *,
    window: int,
    now: datetime,
    include_change_questions: bool,
) -> tuple[VisitSummary, int]:
    """Read a 2×window lookback and assemble the VisitSummary (partition in Python).

    Returns the summary plus the observation count it was computed from (callers audit
    the read with counts only, never values — CLAUDE.md §5).
    """
    rows = await observations.list_for_patient(subject_id, since=now - timedelta(days=2 * window))
    # The current-medications fold needs a med's `added` row even when it predates the
    # window, so read the FULL medication history (source-scoped, unbounded) — meds are
    # low-volume and the (patient_id, source, effective_at) index keeps it in budget.
    medication_rows = await observations.list_for_patient(subject_id, source=SourceType.medication)
    summary = assemble_visit_summary(
        rows,
        subject_id=subject_id,
        window=window,
        now=now,
        include_change_questions=include_change_questions,
        medication_rows=medication_rows,
    )
    return summary, len(rows) + len(medication_rows)
