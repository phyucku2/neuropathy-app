"""Engine-level tests proving ADL check-in series flow through compute_trajectory:
the new registry codes are judged (higher = better), reach the summary in plain
language, and combine with lab signals. All data is synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.trajectory.directionality import Polarity, polarity_for, signal_info
from app.trajectory.engine import compute_trajectory
from app.trajectory.points import ObservationPoint

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _adl_point(code: str, value: float, days_ago: float) -> ObservationPoint:
    return ObservationPoint(
        code=code,
        source="adl",
        value=value,
        effective_at=NOW - timedelta(days=days_ago),
        status="final",
    )


def _series(code: str, values: list[float], step_days: float = 7.0) -> list[ObservationPoint]:
    """Oldest-first series, one point every `step_days`, ending yesterday."""
    n = len(values)
    return [
        _adl_point(code, value, days_ago=1 + (n - 1 - i) * step_days)
        for i, value in enumerate(values)
    ]


def test_adl_codes_are_registered_higher_is_better() -> None:
    for code in ("adl_walking", "adl_stairs", "adl_balance_confidence", "adl_daily_score"):
        assert polarity_for(code) is Polarity.higher_is_better
    # Plain-language labels, never raw codes.
    assert signal_info("adl_daily_score").label == "daily function"
    assert signal_info("adl_balance_confidence").label == "balance confidence"


def test_rising_adl_daily_score_is_judged_improving() -> None:
    trajectory = compute_trajectory(_series("adl_daily_score", [4, 6, 8, 10, 12]), now=NOW)
    assert trajectory.direction.value == "improving"
    assert trajectory.confidence > 0.05
    signal = trajectory.signals[0]
    assert signal.code == "adl_daily_score"
    assert signal.source == "adl"
    assert signal.direction.value == "improving"
    assert "daily function" in trajectory.summary.lower()
    assert "adl_daily_score" not in trajectory.summary  # plain language only


def test_falling_adl_answers_are_judged_declining() -> None:
    points = _series("adl_walking", [4, 3, 2, 1]) + _series("adl_balance_confidence", [4, 3, 2, 0])
    trajectory = compute_trajectory(points, now=NOW)
    assert trajectory.direction.value == "declining"
    assert {s.code for s in trajectory.signals} == {"adl_walking", "adl_balance_confidence"}
    assert all(s.direction.value == "declining" for s in trajectory.signals)
    assert "balance confidence" in trajectory.summary or "walking" in trajectory.summary


def test_flat_adl_series_is_stable_and_lab_gap_is_named() -> None:
    trajectory = compute_trajectory(_series("adl_stairs", [2, 2, 2, 2]), now=NOW)
    assert trajectory.direction.value == "stable"
    # With only ADL data on file, the missing lab source is an explicit gap.
    assert "No lab results yet." in trajectory.data_gaps


def test_adl_and_lab_signals_vote_together() -> None:
    hba1c = [
        ObservationPoint(
            code="4548-4",
            source="lab",
            value=value,
            effective_at=NOW - timedelta(days=days_ago),
            status="final",
        )
        for value, days_ago in [(9.0, 90), (8.2, 60), (7.4, 30), (7.0, 2)]
    ]
    points = hba1c + _series("adl_daily_score", [5, 7, 9, 11])
    trajectory = compute_trajectory(points, now=NOW)
    assert trajectory.direction.value == "improving"
    assert {s.source for s in trajectory.signals} == {"lab", "adl"}
    # Two judged signals raise confidence above a single-signal answer.
    single = compute_trajectory(_series("adl_daily_score", [5, 7, 9, 11]), now=NOW)
    assert trajectory.confidence > single.confidence


def test_short_adl_series_stays_honest() -> None:
    # Two check-ins over one week: below the evidence bar -> reported, not judged.
    trajectory = compute_trajectory(_series("adl_daily_score", [6, 8], step_days=6.0), now=NOW)
    assert trajectory.direction.value == "insufficient_data"
    assert any("daily function" in gap for gap in trajectory.data_gaps)
