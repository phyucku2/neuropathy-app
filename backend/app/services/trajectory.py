"""Shared trajectory computation — one lookback, one engine call, every surface.

The patient endpoint (routes/trajectory.py) and the clinician endpoint
(routes/clinic.py) both answer from THIS helper, so the deterministic judgment can
never drift between the two views of the same record (ADR-0012).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from app.repositories.observation import ObservationRepository
from app.schemas.trajectory import Trajectory
from app.trajectory.engine import compute_trajectory
from app.trajectory.points import points_from_observations

# Hot-path bound (standards.md read budget): the engine's confidence math saturates at
# 90-day coverage and 6 points per signal, so a bounded lookback loses no judgment
# quality while keeping the query small on multi-year histories.
LOOKBACK = timedelta(days=400)


async def compute_patient_trajectory(
    observations: ObservationRepository, patient_id: uuid.UUID, *, now: datetime
) -> tuple[Trajectory, int]:
    """Deterministic trajectory over one patient's analyzable lookback window.

    Returns the trajectory plus the observation count it was computed from (callers
    audit the read with counts only, never values — CLAUDE.md §5).
    """
    rows = await observations.list_for_patient(patient_id, since=now - LOOKBACK)
    return compute_trajectory(points_from_observations(rows), now=now), len(rows)
