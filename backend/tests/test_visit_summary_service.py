"""Unit tests for the pure Visit-Ready Summary assembly (ADR-0045 Phase 1).

`assemble_visit_summary` is deterministic in (rows, now, window): every test injects a
FIXED `now` (no wall clock — docs/lessons.md) and asserts exact structural facts. The
engine is REUSED for all directions, so these tests also pin the engine-reuse identity
(status == compute_trajectory over the current window) rather than re-deriving stats.
All data is synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.schemas.trajectory import Direction
from app.schemas.visit_summary import (
    BIOMECH_DIFFERS_QUESTION,
    NON_DIAGNOSTIC_NOTE,
    SHEET_LABEL,
    SYMPTOM_DIRECTION_CHANGE_QUESTION,
    LeadSection,
)
from app.services.visit_summary import _step_direction, assemble_visit_summary
from app.trajectory.directionality import signal_info
from app.trajectory.engine import compute_trajectory
from app.trajectory.points import points_from_observations

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
SUBJECT = uuid4()


def _obs(
    code: str,
    value: float | None,
    days_ago: float,
    *,
    source: SourceType = SourceType.adl,
    origin: DataOrigin = DataOrigin.patient_reported,
    unit: str | None = None,
    status: ObservationStatus = ObservationStatus.final,
    revises_id: UUID | None = None,
    obs_id: UUID | None = None,
) -> Observation:
    at = NOW - timedelta(days=days_ago)
    return Observation(
        id=obs_id or uuid4(),
        patient_id=SUBJECT,
        source=source,
        origin=origin,
        code=code,
        value_num=value,
        unit=unit,
        effective_at=at,
        recorded_at=at,
        status=status,
        revises_id=revises_id,
        quality={},
        payload={},
    )


def _assemble(rows: list[Observation], *, window: int = 60, change_questions: bool = False):  # type: ignore[no-untyped-def]
    return assemble_visit_summary(
        rows,
        subject_id=SUBJECT,
        window=window,
        now=NOW,
        include_change_questions=change_questions,
    )


def test_window_boundary_partitions_current_prior_and_excludes_old() -> None:
    """A row at exactly now-window is CURRENT, just before it is PRIOR, older than
    2×window is dropped. Proven via the function series point (current) and the
    adherence per-window distinct-day counts."""
    rows = [
        _obs("adl_walking", 3.0, 60),  # exactly now-window -> current
        _obs("adl_walking", 2.0, 61),  # just before -> prior
        _obs("adl_walking", 1.0, 121),  # older than 2×window -> excluded
    ]
    summary = _assemble(rows, window=60)

    walking = next(s for s in summary.function if s.code == "adl_walking")
    assert [p.value for p in walking.points] == [3.0]  # only the current-window row
    assert walking.start_at == NOW - timedelta(days=60)
    assert summary.what_changed.adherence.checkins_in_window == 1
    assert summary.what_changed.adherence.checkins_in_prior_window == 1  # the 121d row is gone


def test_status_equals_compute_trajectory_over_current_rows() -> None:
    """Engine-reuse identity: the status hero IS compute_trajectory over the current
    window — NSI/signals are never recomputed here."""
    rows = [
        _obs("4548-4", 9.0, 90, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"),
        _obs("4548-4", 8.3, 40, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"),
        _obs("4548-4", 7.6, 30, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"),
        _obs("4548-4", 7.0, 5, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"),
    ]
    summary = _assemble(rows, window=60)
    current_rows = [r for r in rows if (NOW - r.effective_at).days <= 60]
    expected = compute_trajectory(points_from_observations(current_rows), now=NOW)
    assert summary.status == expected


def test_empty_account_is_honest_and_does_not_crash() -> None:
    summary = _assemble([], window=60)
    assert summary.status.score is None
    assert summary.symptoms == []
    assert summary.function == []
    assert summary.balance_gait == []
    assert summary.labs == []
    assert summary.activity == []
    assert summary.what_changed.new_labs == []
    assert summary.what_changed.adherence.days_since_last_checkin is None
    assert summary.questions.data_completeness == []
    assert summary.questions.change_pointed == []


def test_new_labs_delta_same_unit_and_most_recent_selection() -> None:
    """Same-unit current vs latest-prior gives a numeric delta; the CURRENT value is the
    most-recent-in-window reading per analyte."""
    rows = [
        _obs("4548-4", 8.0, 70, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"),
        _obs("4548-4", 7.5, 30, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"),
        _obs("4548-4", 7.0, 10, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"),
    ]
    summary = _assemble(rows, window=60)
    lab = next(x for x in summary.labs if x.code == "4548-4")
    assert lab.latest_value == 7.0  # most recent current-window reading
    assert lab.latest_at == NOW - timedelta(days=10)
    assert lab.prior_value == 8.0  # most recent before the window
    assert lab.delta == 7.0 - 8.0
    assert lab.unit_changed is False
    assert summary.what_changed.new_labs == summary.labs


def test_unit_change_withholds_the_delta() -> None:
    """ADR-0015: an analyte whose unit changed between prior and current -> delta None,
    unit_changed True, no cross-unit subtraction."""
    rows = [
        _obs(
            "4548-4",
            64.0,
            70,
            source=SourceType.lab,
            origin=DataOrigin.ehr_imported,
            unit="mmol/mol",
        ),
        _obs("4548-4", 7.0, 10, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"),
    ]
    summary = _assemble(rows, window=60)
    lab = next(x for x in summary.labs if x.code == "4548-4")
    assert lab.unit == "%"
    assert lab.prior_unit == "mmol/mol"
    assert lab.unit_changed is True
    assert lab.delta is None


def _symptom_change_rows() -> list[Observation]:
    # Prior window [now-120, now-60): numbness rising (raw) -> declining (lower-is-better).
    prior = [
        _obs("symptom_numbness", 2.0, 118),
        _obs("symptom_numbness", 5.0, 105),
        _obs("symptom_numbness", 8.0, 95),
    ]
    # Current window: numbness falling (raw) -> improving.
    current = [
        _obs("symptom_numbness", 8.0, 55),
        _obs("symptom_numbness", 5.0, 40),
        _obs("symptom_numbness", 2.0, 20),
    ]
    return prior + current


def test_symptom_trend_direction_change_reuses_engine_and_anchors_prior() -> None:
    rows = _symptom_change_rows()
    summary = _assemble(rows, window=60)
    change = next(c for c in summary.what_changed.symptom_trend if c.code == "symptom_numbness")
    assert change.current_direction == Direction.improving
    assert change.prior_direction == Direction.declining
    assert change.changed is True

    # prior_traj is anchored at now-window (current_window_start), NOT now — pin it.
    prior_rows = [r for r in rows if (NOW - r.effective_at).days > 60]
    current_start = NOW - timedelta(days=60)
    prior_traj = compute_trajectory(points_from_observations(prior_rows), now=current_start)
    prior_sig = {s.code: s.direction for s in prior_traj.signals}
    assert change.prior_direction == prior_sig["symptom_numbness"]


def test_adherence_gap_counts_and_recency() -> None:
    rows = [
        _obs("adl_walking", 3.0, 5),
        _obs("adl_stairs", 2.0, 5),  # same day -> one distinct check-in day
        _obs("adl_walking", 3.0, 20),
        _obs("adl_walking", 2.0, 70),  # prior window
    ]
    summary = _assemble(rows, window=60)
    gap = summary.what_changed.adherence
    assert gap.last_checkin_at == NOW - timedelta(days=5)
    assert gap.days_since_last_checkin == 5
    assert gap.checkins_in_window == 2  # days 5 and 20, deduped within a day
    assert gap.checkins_in_prior_window == 1


def test_adherence_gap_is_none_without_adl_rows() -> None:
    rows = [
        _obs("4548-4", 7.0, 10, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%")
    ]
    summary = _assemble(rows, window=60)
    gap = summary.what_changed.adherence
    assert gap.last_checkin_at is None
    assert gap.days_since_last_checkin is None
    assert gap.checkins_in_window == 0
    assert gap.checkins_in_prior_window == 0


def test_latest_biomech_vs_prior_direction_via_polarity() -> None:
    rows = [
        _obs(
            "biomech_balance_score",
            60.0,
            70,
            source=SourceType.biomech,
            origin=DataOrigin.device_measured,
        ),
        _obs(
            "biomech_balance_score",
            70.0,
            10,
            source=SourceType.biomech,
            origin=DataOrigin.device_measured,
        ),
    ]
    summary = _assemble(rows, window=60)
    delta = next(d for d in summary.balance_gait if d.code == "biomech_balance_score")
    assert delta.latest_value == 70.0
    assert delta.prior_value == 60.0
    # higher_is_better + latest > prior -> improving.
    assert delta.direction == Direction.improving
    assert summary.what_changed.latest_biomech == summary.balance_gait


def test_lead_section_emphasis_by_window() -> None:
    for window in (30, 60, 90):
        assert _assemble([], window=window).lead_section == LeadSection.what_changed
    for window in (120, 365):
        assert _assemble([], window=window).lead_section == LeadSection.trajectory


def test_questions_default_holds_change_pointed_but_populates_completeness() -> None:
    rows = _symptom_change_rows() + [
        _obs("4548-4", 8.0, 70, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"),
        _obs("4548-4", 7.0, 10, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"),
    ]
    summary = _assemble(rows, window=60, change_questions=False)
    assert summary.questions.change_pointed == []
    assert summary.questions.data_completeness  # adherence + new-lab + coverage prompts


def test_questions_gated_on_populates_change_pointed_from_templates() -> None:
    rows = _symptom_change_rows() + [
        _obs(
            "biomech_balance_score",
            60.0,
            70,
            source=SourceType.biomech,
            origin=DataOrigin.device_measured,
        ),
        _obs(
            "biomech_balance_score",
            70.0,
            10,
            source=SourceType.biomech,
            origin=DataOrigin.device_measured,
        ),
    ]
    summary = _assemble(rows, window=60, change_questions=True)
    numbness_label = signal_info("symptom_numbness").label
    expected_symptom = SYMPTOM_DIRECTION_CHANGE_QUESTION.format(label=numbness_label, window=60)
    assert expected_symptom in summary.questions.change_pointed
    assert BIOMECH_DIFFERS_QUESTION in summary.questions.change_pointed
    # GUARDRAIL: no advice/diagnosis/priority wording in any emitted prompt.
    banned = ("diagnos", "treat", "prescrib", "dose", "should", "recommend", "urgent")
    for prompt in summary.questions.change_pointed + summary.questions.data_completeness:
        assert not any(word in prompt.lower() for word in banned)


def test_non_diagnostic_labeling_every_datum_is_sourced_and_dated() -> None:
    rows = [
        _obs("symptom_pain", 4.0, 20),
        _obs("adl_walking", 3.0, 20),
        _obs(
            "biomech_gait_score",
            55.0,
            10,
            source=SourceType.biomech,
            origin=DataOrigin.device_measured,
        ),
        _obs("4548-4", 7.0, 10, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"),
        _obs(
            "wearable_steps",
            5000.0,
            10,
            source=SourceType.wearable,
            origin=DataOrigin.device_measured,
        ),
    ]
    summary = _assemble(rows, window=60)
    for datum in [*summary.symptoms, *summary.function]:
        assert datum.source and datum.origin and datum.latest_at is not None
    for datum in [*summary.balance_gait, *summary.labs]:
        assert datum.source and datum.origin and datum.latest_at is not None
    for stat in summary.activity:
        assert stat.source and stat.origin and stat.latest_at is not None
    assert summary.disclaimer == NON_DIAGNOSTIC_NOTE
    assert summary.sheet_label == SHEET_LABEL
    assert summary.status.narrative_source == "deterministic"


def test_tz_naive_effective_at_does_not_crash() -> None:
    """A tz-naive stored timestamp must be UTC-coerced, never crash the window compare
    (mirrors the trajectory regression)."""
    naive = _obs("adl_walking", 3.0, 0)
    naive.effective_at = datetime(2026, 6, 1, 12)  # noqa: DTZ001 — deliberately naive
    naive.recorded_at = datetime(2026, 6, 1, 12)  # noqa: DTZ001
    summary = _assemble([naive, _obs("adl_walking", 2.0, 20)], window=60)
    walking = next(s for s in summary.function if s.code == "adl_walking")
    assert len(walking.points) == 2


def test_superseded_and_errored_rows_are_excluded() -> None:
    original = _obs("adl_walking", 1.0, 20, obs_id=uuid4())
    correction = _obs("adl_walking", 3.0, 19, revises_id=original.id)
    errored = _obs("adl_stairs", 4.0, 20, status=ObservationStatus.entered_in_error)
    summary = _assemble([original, correction, errored], window=60)
    walking = next(s for s in summary.function if s.code == "adl_walking")
    assert [p.value for p in walking.points] == [3.0]  # only the current correction
    assert all(s.code != "adl_stairs" for s in summary.function)  # errored row dropped


def test_step_direction_maps_every_polarity() -> None:
    """The prior→latest step judgment reuses the polarity registry (no new stat)."""
    assert _step_direction("biomech_balance_score", None, 5.0) == Direction.insufficient_data
    assert _step_direction("biomech_balance_score", 5.0, 5.0) == Direction.stable
    assert (
        _step_direction("biomech_balance_score", 5.0, 6.0) == Direction.improving
    )  # higher better
    assert _step_direction("symptom_pain", 5.0, 6.0) == Direction.declining  # lower is better, up
    assert _step_direction("symptom_pain", 5.0, 4.0) == Direction.improving  # lower is better, down
    # A single step can't judge an in-range / unknown-polarity measure.
    assert _step_direction("biomech_cadence", 5.0, 6.0) == Direction.insufficient_data


def test_change_questions_skip_unchanged_symptoms() -> None:
    """With the flag on, a symptom whose direction did NOT change contributes no prompt."""
    rows = [
        # Flat in BOTH windows -> stable both -> not changed.
        _obs("symptom_pain", 3.0, 118),
        _obs("symptom_pain", 3.0, 105),
        _obs("symptom_pain", 3.0, 95),
        _obs("symptom_pain", 3.0, 55),
        _obs("symptom_pain", 3.0, 40),
        _obs("symptom_pain", 3.0, 20),
    ]
    summary = _assemble(rows, window=60, change_questions=True)
    change = next(c for c in summary.what_changed.symptom_trend if c.code == "symptom_pain")
    assert change.changed is False
    assert summary.questions.change_pointed == []


def test_placeholder_rows_present_and_not_yet_tracked() -> None:
    summary = _assemble([], window=60)
    keys = {row.key for row in summary.placeholders}
    assert keys == {"medications", "emr_notes", "patient_notes", "nutrition"}
    assert all(row.status == "not_yet_tracked" for row in summary.placeholders)
