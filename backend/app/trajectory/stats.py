"""Pure trend statistics — every number the trajectory reports is computed here.

Deterministic, dependency-free math (Brainstorm #3, data-science + AI-safety lenses):
per-code series extraction, a hand-rolled least-squares slope, a meaningful-change
threshold relative to the series' own scale (so noise is never called a trend), a
minimum-evidence rule, and a most-recent-value vs reference-range check when range
metadata exists in the series.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from app.trajectory.points import ObservationPoint

SECONDS_PER_DAY = 86_400.0

# Minimum evidence for a judged trend: fewer points or a shorter window can't
# separate a real change from day-to-day variation, so the signal is honestly
# reported as insufficient instead.
MIN_POINTS = 3
MIN_SPAN_DAYS = 14.0

# A fitted change smaller than this fraction of the series' scale is treated as
# noise (flat), not a trend.
MEANINGFUL_RELATIVE_CHANGE = 0.05


class Movement(enum.StrEnum):
    """The raw numeric direction of a series, before any better/worse judgment."""

    rising = "rising"
    falling = "falling"
    flat = "flat"
    insufficient = "insufficient"


class RangePosition(enum.StrEnum):
    """Where the most recent value sits relative to the reference range."""

    below = "below"
    within = "within"
    above = "above"


@dataclass(frozen=True, slots=True)
class SeriesStats:
    """Computed trend facts for one signal's time series."""

    n_points: int
    span_days: float
    slope_per_day: float
    fitted_change: float  # slope * span: the change the fit attributes to the window
    relative_change: float  # fitted_change / series scale (signed)
    first_at: datetime
    latest_at: datetime
    latest_value: float
    movement: Movement


def series_by_code(points: Iterable[ObservationPoint]) -> dict[str, list[ObservationPoint]]:
    """Group points into per-code series, each ordered oldest-first."""
    series: dict[str, list[ObservationPoint]] = {}
    for point in points:
        series.setdefault(point.code, []).append(point)
    for values in series.values():
        values.sort(key=lambda point: point.effective_at)
    return series


def least_squares_slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Ordinary least-squares slope of y on x; 0.0 when x carries no spread."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0.0:
        return 0.0
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return sxy / sxx


def _series_scale(values: Sequence[float]) -> float:
    """The magnitude changes are compared against: the larger of |mean| and spread.

    Taking the max is deliberately conservative — the bigger the yardstick, the
    harder it is for small wobble to register as a meaningful trend.
    """
    mean = sum(values) / len(values)
    spread = max(values) - min(values)
    return max(abs(mean), spread, 1e-9)


def compute_series_stats(series: Sequence[ObservationPoint]) -> SeriesStats:
    """Fit one signal's series and classify its movement.

    The movement is `insufficient` below the minimum-evidence bar; otherwise the
    fitted change over the window is compared to the series' scale, and only a
    change beyond `MEANINGFUL_RELATIVE_CHANGE` counts as rising/falling.
    """
    ordered = sorted(series, key=lambda point: point.effective_at)
    first_at = ordered[0].effective_at
    latest_at = ordered[-1].effective_at
    span_days = (latest_at - first_at).total_seconds() / SECONDS_PER_DAY
    values = [point.value for point in ordered]

    xs = [(point.effective_at - first_at).total_seconds() / SECONDS_PER_DAY for point in ordered]
    slope = least_squares_slope(xs, values)
    fitted_change = slope * span_days
    relative_change = fitted_change / _series_scale(values)

    if len(ordered) < MIN_POINTS or span_days < MIN_SPAN_DAYS:
        movement = Movement.insufficient
    elif relative_change > MEANINGFUL_RELATIVE_CHANGE:
        movement = Movement.rising
    elif relative_change < -MEANINGFUL_RELATIVE_CHANGE:
        movement = Movement.falling
    else:
        movement = Movement.flat

    return SeriesStats(
        n_points=len(ordered),
        span_days=span_days,
        slope_per_day=slope,
        fitted_change=fitted_change,
        relative_change=relative_change,
        first_at=first_at,
        latest_at=latest_at,
        latest_value=ordered[-1].value,
        movement=movement,
    )


def latest_range_position(series: Sequence[ObservationPoint]) -> RangePosition | None:
    """Compare the most recent value against the series' reference range, if any.

    The range comes from the most recent point that carries one (labs may update
    their ranges over time; the newest is the relevant yardstick). Returns None
    when no point in the series has range metadata.
    """
    ordered = sorted(series, key=lambda point: point.effective_at)
    latest_value = ordered[-1].value
    for point in reversed(ordered):
        if point.reference_low is None and point.reference_high is None:
            continue
        if point.reference_low is not None and latest_value < point.reference_low:
            return RangePosition.below
        if point.reference_high is not None and latest_value > point.reference_high:
            return RangePosition.above
        return RangePosition.within
    return None
