"""Tests for the trajectory engine — deterministic, explainable trend analysis.

The engine is the product centerpiece, so these tests lock its honest behavior:
directions come only from computed stats, noise is never called a trend, thin data
is called insufficient (not guessed), ties resolve conservatively, confidence grows
with evidence, and the summary reads plainly with no raw code names. All data is
synthetic; `now` is always passed explicitly so every case is reproducible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.schemas.trajectory import Direction
from app.trajectory.directionality import Polarity, polarity_for, signal_info
from app.trajectory.engine import compute_trajectory
from app.trajectory.points import (
    ObservationPoint,
    _reference_bounds,
    points_from_observations,
)

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def _pt(
    code: str,
    value: float,
    days_ago: float,
    *,
    source: str = "lab",
    status: str = "final",
    low: float | None = None,
    high: float | None = None,
) -> ObservationPoint:
    return ObservationPoint(
        code=code,
        source=source,
        value=value,
        effective_at=NOW - timedelta(days=days_ago),
        status=status,
        reference_low=low,
        reference_high=high,
    )


def _series(
    code: str,
    values: list[float],
    *,
    newest_days_ago: float = 5,
    step_days: float = 10,
    source: str = "lab",
    low: float | None = None,
    high: float | None = None,
) -> list[ObservationPoint]:
    """Evenly spaced points, oldest value first, newest `newest_days_ago` days old."""
    oldest = newest_days_ago + step_days * (len(values) - 1)
    return [
        _pt(code, value, oldest - i * step_days, source=source, low=low, high=high)
        for i, value in enumerate(values)
    ]


def _signal(trajectory: Any, code: str) -> Any:
    return next(s for s in trajectory.signals if s.code == code)


# ---------------------------------------------------------------------------
# Core directions
# ---------------------------------------------------------------------------


def test_improving_series_yields_improving() -> None:
    points = _series("balance_score", [50, 55, 62, 70], source="adl") + _series(
        "adl_katz", [3, 4, 4, 5], source="adl"
    )
    trajectory = compute_trajectory(points, NOW)

    assert trajectory.direction is Direction.improving
    assert _signal(trajectory, "balance_score").direction is Direction.improving
    assert _signal(trajectory, "adl_katz").direction is Direction.improving
    assert 0 < trajectory.confidence <= 1


def test_rising_lower_is_better_lab_yields_declining() -> None:
    # HbA1c rising is worse even though the numbers go up.
    trajectory = compute_trajectory(_series("hba1c", [6.8, 7.0, 7.3, 7.6]), NOW)

    assert trajectory.direction is Direction.declining
    signal = _signal(trajectory, "hba1c")
    assert signal.direction is Direction.declining
    assert "up" in signal.detail  # the raw movement is still reported honestly


def test_falling_lower_is_better_lab_yields_improving() -> None:
    trajectory = compute_trajectory(_series("4548-4", [8.1, 7.7, 7.2, 6.9]), NOW)
    assert trajectory.direction is Direction.improving
    assert "down" in _signal(trajectory, "4548-4").detail


def test_flat_series_yields_stable() -> None:
    trajectory = compute_trajectory(_series("hba1c", [7.0, 7.0, 7.1, 7.0]), NOW)
    assert trajectory.direction is Direction.stable
    assert _signal(trajectory, "hba1c").direction is Direction.stable
    assert "steady" in _signal(trajectory, "hba1c").detail


def test_noise_below_threshold_is_stable_not_a_trend() -> None:
    # ~1% wobble on eGFR must not be called a trend.
    trajectory = compute_trajectory(_series("egfr", [90.0, 90.5, 90.2, 90.8]), NOW)
    assert trajectory.direction is Direction.stable


def test_higher_is_better_falling_yields_declining() -> None:
    trajectory = compute_trajectory(_series("egfr", [90, 82, 74, 65]), NOW)
    assert trajectory.direction is Direction.declining


# ---------------------------------------------------------------------------
# Insufficient data is a first-class honest outcome
# ---------------------------------------------------------------------------


def test_too_few_points_is_insufficient() -> None:
    trajectory = compute_trajectory(_series("hba1c", [7.0, 8.0]), NOW)

    assert trajectory.direction is Direction.insufficient_data
    assert _signal(trajectory, "hba1c").direction is Direction.insufficient_data
    assert any("Not enough" in gap for gap in trajectory.data_gaps)
    assert "enough data" in trajectory.summary


def test_too_short_a_span_is_insufficient_even_with_many_points() -> None:
    points = _series("hba1c", [7.0, 7.4, 7.8, 8.2], newest_days_ago=1, step_days=2)
    trajectory = compute_trajectory(points, NOW)
    assert trajectory.direction is Direction.insufficient_data


def test_single_reading_detail_uses_singular_wording() -> None:
    trajectory = compute_trajectory([_pt("hba1c", 7.0, 10)], NOW)
    assert "only 1 reading over" in _signal(trajectory, "hba1c").detail


def test_empty_input_is_insufficient_with_absent_source_gaps() -> None:
    trajectory = compute_trajectory([], NOW)

    assert trajectory.direction is Direction.insufficient_data
    assert trajectory.signals == []
    assert trajectory.confidence <= 0.1
    assert "No lab results yet." in trajectory.data_gaps
    assert "No daily-activity check-ins yet." in trajectory.data_gaps


def test_absent_adl_source_is_named_as_a_gap() -> None:
    trajectory = compute_trajectory(_series("hba1c", [7.0, 7.0, 7.0, 7.0]), NOW)
    assert "No daily-activity check-ins yet." in trajectory.data_gaps
    assert "No lab results yet." not in trajectory.data_gaps


# ---------------------------------------------------------------------------
# Integrity filtering
# ---------------------------------------------------------------------------


def _observation(
    *,
    code: str = "4548-4",
    value: float | None = 7.0,
    days_ago: float = 10,
    status: ObservationStatus = ObservationStatus.final,
    payload: dict[str, Any] | None = None,
) -> Observation:
    return Observation(
        patient_id=uuid.uuid4(),
        source=SourceType.lab,
        origin=DataOrigin.document_imported,
        code=code,
        value_num=value,
        effective_at=NOW - timedelta(days=days_ago),
        recorded_at=NOW - timedelta(days=days_ago),
        status=status,
        quality={"human_confirmed": True},
        payload=payload or {},
    )


def test_converter_excludes_entered_in_error_and_non_numeric() -> None:
    rows = [
        _observation(days_ago=30),
        _observation(days_ago=20, status=ObservationStatus.entered_in_error),
        _observation(days_ago=10, value=None),
        _observation(days_ago=5, status=ObservationStatus.corrected),
    ]
    points = points_from_observations(rows)

    assert len(points) == 2
    assert all(point.status != "entered_in_error" for point in points)
    # Oldest first, and source carried as a plain string.
    assert points[0].effective_at < points[1].effective_at
    assert points[0].source == "lab"


def test_converter_extracts_reference_range_when_numeric() -> None:
    rows = [
        _observation(payload={"reference_range": {"low": 200, "high": 900.0}}),
        _observation(payload={"reference_range": {"low": "200", "high": None}}),
        _observation(payload={"reference_range": "200-900"}),
        _observation(payload={}),
    ]
    points = points_from_observations(rows)

    assert (points[0].reference_low, points[0].reference_high) == (200.0, 900.0)
    # Non-numeric or missing bounds degrade safely to None, never crash.
    assert all((p.reference_low, p.reference_high) == (None, None) for p in points[1:])


def test_reference_bounds_tolerate_a_malformed_payload() -> None:
    # An Observation payload is JSONB — defend against non-dict shapes end to end.
    assert _reference_bounds(None) == (None, None)
    assert _reference_bounds(["not", "a", "dict"]) == (None, None)


def test_engine_refilters_entered_in_error_and_unknown_statuses() -> None:
    # Even hand-built points can't sneak errored/unknown-status data into analysis.
    points = [
        _pt("hba1c", 7.0, 30, status="entered_in_error"),
        _pt("hba1c", 7.5, 20, status="entered_in_error"),
        _pt("hba1c", 8.0, 10, status="entered_in_error"),
        _pt("hba1c", 9.0, 5, status="not_a_real_status"),
    ]
    trajectory = compute_trajectory(points, NOW)
    assert trajectory.direction is Direction.insufficient_data
    assert trajectory.signals == []


# ---------------------------------------------------------------------------
# Unknown codes: reported, never judged
# ---------------------------------------------------------------------------


def test_unknown_code_is_reported_but_not_judged() -> None:
    points = _series("mystery_metric", [10, 20, 30, 40], source="adl")
    trajectory = compute_trajectory(points, NOW)

    signal = _signal(trajectory, "mystery_metric")
    assert signal.direction is Direction.insufficient_data  # not judged better/worse
    assert "up" in signal.detail  # but the movement itself is reported
    assert trajectory.direction is Direction.insufficient_data  # no judged voters
    assert any("do not judge" in gap for gap in trajectory.data_gaps)


def test_unknown_code_does_not_outvote_judged_signals() -> None:
    points = _series("mystery_metric", [40, 30, 20, 10]) + _series(
        "balance_score", [50, 55, 62, 70], source="adl"
    )
    trajectory = compute_trajectory(points, NOW)
    assert trajectory.direction is Direction.improving


# ---------------------------------------------------------------------------
# In-range-is-better signals
# ---------------------------------------------------------------------------


def test_below_range_rising_is_improving() -> None:
    points = _series("vitamin_b12", [120, 140, 160, 185], low=200, high=900)
    trajectory = compute_trajectory(points, NOW)
    signal = _signal(trajectory, "vitamin_b12")
    assert signal.direction is Direction.improving
    assert "below the typical range" in signal.detail


def test_below_range_falling_is_declining() -> None:
    points = _series("vitamin_b12", [185, 160, 140, 120], low=200, high=900)
    assert _signal(compute_trajectory(points, NOW), "vitamin_b12").direction is Direction.declining


def test_above_range_rising_is_declining() -> None:
    points = _series("vitamin_b12", [950, 1000, 1080, 1150], low=200, high=900)
    assert _signal(compute_trajectory(points, NOW), "vitamin_b12").direction is Direction.declining


def test_above_range_falling_is_improving() -> None:
    points = _series("vitamin_b12", [1150, 1080, 1000, 950], low=200, high=900)
    assert _signal(compute_trajectory(points, NOW), "vitamin_b12").direction is Direction.improving


def test_within_range_is_stable_even_while_drifting() -> None:
    points = _series("vitamin_b12", [300, 400, 500, 600], low=200, high=900)
    trajectory = compute_trajectory(points, NOW)
    signal = _signal(trajectory, "vitamin_b12")
    assert signal.direction is Direction.stable
    assert "in the typical range" in signal.detail


def test_within_range_flat_is_stable() -> None:
    points = _series("vitamin_b12", [500, 505, 500, 502], low=200, high=900)
    assert _signal(compute_trajectory(points, NOW), "vitamin_b12").direction is Direction.stable


def test_in_range_signal_without_a_range_is_not_judged() -> None:
    points = _series("vitamin_b12", [300, 400, 500, 600])
    trajectory = compute_trajectory(points, NOW)
    assert _signal(trajectory, "vitamin_b12").direction is Direction.insufficient_data
    assert any("reference range" in gap for gap in trajectory.data_gaps)


def test_range_from_an_older_point_still_applies_to_the_latest_value() -> None:
    points = [
        _pt("vitamin_b12", 120, 40, low=200, high=900),
        _pt("vitamin_b12", 150, 25),
        _pt("vitamin_b12", 185, 5),
    ]
    assert _signal(compute_trajectory(points, NOW), "vitamin_b12").direction is Direction.improving


# ---------------------------------------------------------------------------
# Conservative tie-break and mixed pictures
# ---------------------------------------------------------------------------


def test_exact_tie_between_improving_and_declining_resolves_to_declining() -> None:
    # Same point count, spacing, and recency → identical vote weights.
    improving = _series("balance_score", [50, 55, 60, 65], source="adl")
    declining = _series("pain_score", [2, 3, 4, 5], source="adl")
    trajectory = compute_trajectory(improving + declining, NOW)

    assert trajectory.direction is Direction.declining  # clinically conservative
    assert "care team" in trajectory.summary


def test_majority_of_judged_signals_wins() -> None:
    points = (
        _series("balance_score", [50, 55, 60, 65], source="adl")
        + _series("adl_katz", [3, 3, 4, 5], source="adl")
        + _series("hba1c", [6.8, 7.0, 7.3, 7.6])
    )
    trajectory = compute_trajectory(points, NOW)

    assert trajectory.direction is Direction.improving
    # The mixed picture is surfaced, not hidden: the decliner is named for a look.
    assert "worth a look" in trajectory.summary
    assert "blood sugar" in trajectory.summary


def test_declining_summary_mentions_bright_side_when_something_improves() -> None:
    points = (
        _series("hba1c", [6.8, 7.0, 7.3, 7.6])
        + _series("egfr", [90, 82, 74, 65])
        + _series("balance_score", [50, 55, 60, 65], source="adl")
    )
    trajectory = compute_trajectory(points, NOW)

    assert trajectory.direction is Direction.declining
    assert "On the bright side" in trajectory.summary
    assert "balance" in trajectory.summary


def test_stable_overall_still_flags_a_decliner_for_a_look() -> None:
    points = (
        _series("hba1c", [7.0, 7.0, 7.1, 7.0])
        + _series("vitamin_b12", [500, 505, 500, 502], low=200, high=900)
        + _series("egfr", [90, 82, 74, 65])
    )
    trajectory = compute_trajectory(points, NOW)

    assert trajectory.direction is Direction.stable
    assert "holding steady" in trajectory.summary
    assert "worth a look" in trajectory.summary


# ---------------------------------------------------------------------------
# Confidence: bounded, honest, monotone in evidence
# ---------------------------------------------------------------------------


def test_confidence_is_bounded() -> None:
    rich = (
        _series("balance_score", [50 + i for i in range(10)], source="adl")
        + _series("adl_katz", [3, 3, 4, 4, 5, 5], source="adl")
        + _series("hba1c", [7.6, 7.4, 7.2, 7.0, 6.9, 6.8])
    )
    trajectory = compute_trajectory(rich, NOW)
    assert 0 < trajectory.confidence <= 0.95


def test_more_judged_signals_do_not_lower_confidence() -> None:
    base = _series("balance_score", [50, 55, 62], step_days=10, source="adl")
    more = base + _series("hba1c", [7.6, 7.3, 7.0, 6.8], step_days=15)

    conf_base = compute_trajectory(base, NOW).confidence
    conf_more = compute_trajectory(more, NOW).confidence
    assert conf_more >= conf_base


def test_more_points_on_the_same_signal_do_not_lower_confidence() -> None:
    base = _series("balance_score", [50, 55, 62], source="adl")
    extended = _series("balance_score", [42, 46, 50, 55, 62], source="adl")

    conf_base = compute_trajectory(base, NOW).confidence
    conf_extended = compute_trajectory(extended, NOW).confidence
    assert conf_extended >= conf_base


def test_fresh_data_scores_higher_confidence_than_stale_data() -> None:
    fresh = _series("balance_score", [50, 55, 62, 70], newest_days_ago=5, source="adl")
    stale = _series("balance_score", [50, 55, 62, 70], newest_days_ago=120, source="adl")

    fresh_conf = compute_trajectory(fresh, NOW).confidence
    stale_conf = compute_trajectory(stale, NOW).confidence
    assert fresh_conf > stale_conf


def test_insufficient_outcome_has_minimal_confidence() -> None:
    trajectory = compute_trajectory(_series("hba1c", [7.0, 8.0]), NOW)
    assert trajectory.confidence <= 0.1


def test_very_old_data_is_still_judged_but_flagged_stale() -> None:
    points = _series("balance_score", [50, 55, 62, 70], newest_days_ago=320, source="adl")
    trajectory = compute_trajectory(points, NOW)

    assert trajectory.direction is Direction.improving  # the trend itself is real
    assert any("days ago" in gap for gap in trajectory.data_gaps)
    assert trajectory.confidence < 0.5


# ---------------------------------------------------------------------------
# Summary readability
# ---------------------------------------------------------------------------


def test_summary_uses_friendly_labels_never_codes() -> None:
    points = _series("adl_katz", [3, 4, 4, 5], source="adl") + _series(
        "4548-4", [7.6, 7.3, 7.0, 6.8]
    )
    trajectory = compute_trajectory(points, NOW)

    assert "4548-4" not in trajectory.summary
    assert "adl_katz" not in trajectory.summary
    assert "hba1c" not in trajectory.summary.lower()
    # The drivers are named in plain language.
    assert "daily function" in trajectory.summary.lower()
    assert "blood sugar" in trajectory.summary.lower()


def test_declining_summary_is_constructive_not_alarmist() -> None:
    trajectory = compute_trajectory(_series("hba1c", [6.8, 7.0, 7.3, 7.6]), NOW)

    assert "care team" in trajectory.summary
    lowered = trajectory.summary.lower()
    assert not any(word in lowered for word in ("danger", "alarm", "urgent", "severe", "warning"))
    assert "!" not in trajectory.summary


def test_summary_joins_three_drivers_readably() -> None:
    points = (
        _series("balance_score", [50, 55, 60, 65], source="adl")
        + _series("gait_speed", [0.8, 0.9, 1.0, 1.1], source="adl")
        + _series("adl_katz", [3, 4, 4, 5], source="adl")
    )
    trajectory = compute_trajectory(points, NOW)
    assert trajectory.direction is Direction.improving
    assert ", and " in trajectory.summary


def test_duplicate_labels_are_deduped_in_the_summary() -> None:
    points = _series("adl_katz", [3, 4, 4, 5], source="adl") + _series(
        "adl_barthel", [60, 70, 80, 90], source="adl"
    )
    trajectory = compute_trajectory(points, NOW)
    assert trajectory.summary.lower().count("daily function") == 1


def test_signal_details_follow_the_computed_facts_format() -> None:
    trajectory = compute_trajectory(_series("balance_score", [50, 55, 62, 70], source="adl"), NOW)
    detail = _signal(trajectory, "balance_score").detail
    assert "balance up" in detail
    assert "over" in detail and "days" in detail


def test_every_signal_is_sourced() -> None:
    points = _series("hba1c", [7.0, 7.0, 7.1, 7.0]) + _series("adl_katz", [3, 4], source="adl")
    trajectory = compute_trajectory(points, NOW)
    assert all(signal.source in {"lab", "adl"} for signal in trajectory.signals)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_inputs_always_produce_the_same_trajectory() -> None:
    points = (
        _series("balance_score", [50, 55, 60, 65], source="adl")
        + _series("hba1c", [6.8, 7.0, 7.3, 7.6])
        + _series("mystery_metric", [1, 2, 3, 4])
    )
    first = compute_trajectory(list(points), NOW)
    second = compute_trajectory(list(reversed(points)), NOW)
    assert first == second


# ---------------------------------------------------------------------------
# Directionality registry
# ---------------------------------------------------------------------------


def test_registry_covers_loinc_codes_and_friendly_keys() -> None:
    assert polarity_for("4548-4") is Polarity.lower_is_better
    assert polarity_for("hba1c") is Polarity.lower_is_better
    assert polarity_for("2132-9") is Polarity.in_range_is_better
    assert polarity_for("vitamin_b12") is Polarity.in_range_is_better
    assert polarity_for("62238-1") is Polarity.higher_is_better
    assert polarity_for("egfr") is Polarity.higher_is_better
    assert polarity_for("balance_score") is Polarity.higher_is_better
    assert polarity_for("pain_score") is Polarity.lower_is_better


def test_registry_lookup_is_case_insensitive() -> None:
    assert polarity_for("HbA1c") is Polarity.lower_is_better
    assert polarity_for("EGFR") is Polarity.higher_is_better


def test_unknown_codes_default_to_unknown_polarity_with_a_readable_label() -> None:
    info = signal_info("grip_strength_test")
    assert info.polarity is Polarity.unknown
    assert info.label == "grip strength test"


def test_loinc_and_friendly_key_share_one_label() -> None:
    assert signal_info("4548-4").label == signal_info("hba1c").label
