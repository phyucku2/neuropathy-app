"""Unit tests for the pure trend-statistics layer of the trajectory engine.

These lock the math itself — the least-squares fit, the noise threshold, the
minimum-evidence rule, and the reference-range check — independent of judgment
and narration. Everything is synthetic and deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.trajectory.points import ObservationPoint
from app.trajectory.stats import (
    Movement,
    RangePosition,
    compute_series_stats,
    latest_range_position,
    least_squares_slope,
    series_by_code,
)

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def _pt(
    code: str,
    value: float,
    days_ago: float,
    *,
    low: float | None = None,
    high: float | None = None,
) -> ObservationPoint:
    return ObservationPoint(
        code=code,
        source="lab",
        value=value,
        effective_at=NOW - timedelta(days=days_ago),
        status="final",
        reference_low=low,
        reference_high=high,
    )


# ---------------------------------------------------------------------------
# Least-squares slope
# ---------------------------------------------------------------------------


def test_slope_is_exact_on_perfectly_linear_data() -> None:
    assert least_squares_slope([0, 1, 2, 3], [1, 3, 5, 7]) == 2.0


def test_slope_is_zero_on_constant_values() -> None:
    assert least_squares_slope([0, 10, 20], [5, 5, 5]) == 0.0


def test_slope_is_zero_when_x_has_no_spread() -> None:
    # Degenerate but must not divide by zero.
    assert least_squares_slope([3, 3, 3], [1, 2, 3]) == 0.0


def test_slope_is_negative_on_falling_data() -> None:
    assert least_squares_slope([0, 1, 2], [6, 4, 2]) == -2.0


# ---------------------------------------------------------------------------
# Series extraction
# ---------------------------------------------------------------------------


def test_series_by_code_groups_and_orders_oldest_first() -> None:
    points = [
        _pt("a", 1, 5),
        _pt("b", 9, 1),
        _pt("a", 2, 30),
        _pt("a", 3, 15),
    ]
    series = series_by_code(points)

    assert set(series) == {"a", "b"}
    assert [p.value for p in series["a"]] == [2.0, 3.0, 1.0]
    assert len(series["b"]) == 1


# ---------------------------------------------------------------------------
# Series stats and the meaningful-change threshold
# ---------------------------------------------------------------------------


def test_stats_classify_a_clear_rise() -> None:
    stats = compute_series_stats([_pt("a", 50, 40), _pt("a", 60, 20), _pt("a", 70, 0)])

    assert stats.movement is Movement.rising
    assert stats.n_points == 3
    assert round(stats.span_days) == 40
    assert round(stats.slope_per_day, 3) == 0.5
    assert round(stats.fitted_change) == 20


def test_stats_tolerate_unsorted_input() -> None:
    stats = compute_series_stats([_pt("a", 70, 0), _pt("a", 50, 40), _pt("a", 60, 20)])
    assert stats.movement is Movement.rising
    assert stats.latest_value == 70.0


def test_small_wobble_is_flat() -> None:
    # ~0.5% fitted change against the series scale: noise, not a trend.
    stats = compute_series_stats(
        [_pt("a", 100.0, 30), _pt("a", 100.4, 20), _pt("a", 99.9, 10), _pt("a", 100.3, 0)]
    )
    assert stats.movement is Movement.flat


def test_fewer_than_three_points_is_insufficient() -> None:
    stats = compute_series_stats([_pt("a", 1, 30), _pt("a", 9, 0)])
    assert stats.movement is Movement.insufficient


def test_span_under_fourteen_days_is_insufficient() -> None:
    stats = compute_series_stats([_pt("a", 1, 10), _pt("a", 5, 5), _pt("a", 9, 0)])
    assert stats.movement is Movement.insufficient


def test_clear_fall_is_falling() -> None:
    stats = compute_series_stats([_pt("a", 70, 40), _pt("a", 60, 20), _pt("a", 50, 0)])
    assert stats.movement is Movement.falling


def test_scale_uses_spread_when_mean_is_near_zero() -> None:
    # Values centered on zero: the spread, not the tiny mean, is the yardstick.
    stats = compute_series_stats([_pt("a", -5, 40), _pt("a", 0, 20), _pt("a", 5, 0)])
    assert stats.movement is Movement.rising


# ---------------------------------------------------------------------------
# Reference-range position
# ---------------------------------------------------------------------------


def test_range_position_is_none_without_range_metadata() -> None:
    assert latest_range_position([_pt("a", 500, 10), _pt("a", 510, 0)]) is None


def test_range_position_below_within_above() -> None:
    def at(value: float) -> ObservationPoint:
        return _pt("a", value, 0, low=200, high=900)

    assert latest_range_position([at(150)]) is RangePosition.below
    assert latest_range_position([at(500)]) is RangePosition.within
    assert latest_range_position([at(950)]) is RangePosition.above


def test_range_position_uses_most_recent_range_for_latest_value() -> None:
    points = [_pt("a", 150, 20, low=200, high=900), _pt("a", 250, 0)]
    # Latest value (250) judged against the most recent known range (200-900).
    assert latest_range_position(points) is RangePosition.within


def test_range_with_only_a_low_bound() -> None:
    assert latest_range_position([_pt("a", 150, 0, low=200)]) is RangePosition.below
    assert latest_range_position([_pt("a", 250, 0, low=200)]) is RangePosition.within


def test_range_with_only_a_high_bound() -> None:
    assert latest_range_position([_pt("a", 950, 0, high=900)]) is RangePosition.above
    assert latest_range_position([_pt("a", 250, 0, high=900)]) is RangePosition.within
