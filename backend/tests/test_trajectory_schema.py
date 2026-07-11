"""Tests for the trajectory API contract — the product's centerpiece output.

The contract exists to keep AI output explainable and honest: a bounded confidence,
sourced signals, and explicit data gaps. These tests lock that contract.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.trajectory import Direction, SignalTrend, Trajectory


def _signal(direction: Direction = Direction.improving) -> SignalTrend:
    return SignalTrend(
        code="balance_score",
        source="biomech",
        direction=direction,
        detail="balance up 8 pts over 30 days",
    )


def test_trajectory_roundtrips_with_sourced_signals() -> None:
    traj = Trajectory(
        direction=Direction.improving,
        confidence=0.72,
        summary="Balance and daily function are trending up.",
        signals=[_signal()],
        data_gaps=["No labs in the last 60 days"],
    )
    assert traj.direction is Direction.improving
    assert traj.signals[0].source == "biomech"
    # Every driver must carry a source so nothing is an unsourced verdict.
    assert all(s.source for s in traj.signals)


def test_confidence_is_bounded_zero_to_one() -> None:
    with pytest.raises(ValidationError):
        Trajectory(direction=Direction.stable, confidence=1.5, summary="x")
    with pytest.raises(ValidationError):
        Trajectory(direction=Direction.stable, confidence=-0.1, summary="x")


def test_insufficient_data_is_a_first_class_direction() -> None:
    # Honesty under sparse data: the model can say it doesn't know.
    traj = Trajectory(
        direction=Direction.insufficient_data,
        confidence=0.1,
        summary="Not enough data yet to call a trend.",
        data_gaps=["Only one source active"],
    )
    assert traj.direction is Direction.insufficient_data
    assert traj.signals == []
