"""The engine's input: a minimal, source-agnostic time-series point.

`ObservationPoint` deliberately carries only what trend math needs, so the engine
stays pure and testable — no ORM session, no request context. The converter applies
the integrity rules from `app.services.observation` (ADR-0006): `entered_in_error`
rows are retained for the record but never analyzed, and only numeric values can
be trended.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from app.models.observation import ObservationStatus
from app.services.observation import counts_toward_analysis

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.models.observation import Observation


@dataclass(frozen=True, slots=True)
class ObservationPoint:
    """One analyzable datum: what was measured, by which source, when, and its value.

    `reference_low`/`reference_high` are optional series metadata (from the lab's
    reference range when one was ingested) used to judge in-range-is-better signals.
    """

    code: str
    source: str
    value: float
    effective_at: datetime
    status: str
    reference_low: float | None = field(default=None)
    reference_high: float | None = field(default=None)


def _reference_bounds(payload: object) -> tuple[float | None, float | None]:
    """Pull numeric reference-range bounds out of an Observation payload, if present."""
    if not isinstance(payload, dict):
        return None, None
    reference = payload.get("reference_range")
    if not isinstance(reference, dict):
        return None, None
    low = reference.get("low")
    high = reference.get("high")
    return (
        float(low) if isinstance(low, int | float) else None,
        float(high) if isinstance(high, int | float) else None,
    )


def points_from_observations(observations: Iterable[Observation]) -> list[ObservationPoint]:
    """Convert Observation rows into analyzable points, oldest first.

    Filters to statuses that count toward analysis (`entered_in_error` is excluded —
    ALCOA: Accurate) and to numeric values (qualitative results cannot be trended).
    """
    points: list[ObservationPoint] = []
    for row in observations:
        if not counts_toward_analysis(ObservationStatus(row.status)):
            continue
        if row.value_num is None:
            continue
        low, high = _reference_bounds(row.payload)
        points.append(
            ObservationPoint(
                code=row.code,
                source=str(row.source.value),
                value=float(row.value_num),
                effective_at=row.effective_at,
                status=str(row.status.value),
                reference_low=low,
                reference_high=high,
            )
        )
    points.sort(key=lambda point: point.effective_at)
    return points
