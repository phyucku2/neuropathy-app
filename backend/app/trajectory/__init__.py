"""Deterministic, explainable trend analysis over a patient's observations.

The trajectory engine is the product centerpiece (ADR-0003, Brainstorm #3). Every
number is computed in code — no model calls in this layer — and the output is the
locked `Trajectory` contract: a direction, a bounded confidence, a plain-language
summary, per-signal sourced details, and explicit data gaps. `insufficient_data`
is a first-class honest outcome, never an error.
"""

from app.trajectory.engine import compute_trajectory
from app.trajectory.points import ObservationPoint, points_from_observations

__all__ = ["ObservationPoint", "compute_trajectory", "points_from_observations"]
