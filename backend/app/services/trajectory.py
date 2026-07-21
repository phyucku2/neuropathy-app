"""Shared trajectory computation — one lookback, one engine call, every surface.

The patient endpoint (routes/trajectory.py) and the clinician endpoint
(routes/clinic.py) both answer from THIS helper, so the deterministic judgment can
never drift between the two views of the same record (ADR-0012).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from app.models.observation import SourceType
from app.repositories.observation import ObservationRepository
from app.schemas.trajectory import Trajectory
from app.trajectory.engine import compute_trajectory
from app.trajectory.points import points_from_observations

# Hot-path bound (standards.md read budget): the engine's confidence math saturates at
# 90-day coverage and 6 points per signal, so a bounded lookback loses no judgment
# quality while keeping the query small on multi-year histories.
LOOKBACK = timedelta(days=400)

# The ONLY sources the trajectory engine judges (shared with the visit summary so the
# surfaces can never drift). Medication/event capture rows (ADR-0045 P2) are record
# data, not signals: a medication row carries a numeric DOSE under an unknown
# `med:{uuid}` code, so feeding it to compute_trajectory would mint a spurious
# unknown-polarity signal whose detail embeds the dose — and that detail would then
# leave the deterministic boundary via the AI narrator prompt. They are filtered out
# BEFORE the engine ever sees them.
TRAJECTORY_SOURCES = frozenset(
    {SourceType.lab, SourceType.adl, SourceType.biomech, SourceType.wearable}
)


async def compute_patient_trajectory(
    observations: ObservationRepository, patient_id: uuid.UUID, *, now: datetime
) -> tuple[Trajectory, int]:
    """Deterministic trajectory over one patient's analyzable lookback window.

    Returns the trajectory plus the observation count it was computed from (callers
    audit the read with counts only, never values — CLAUDE.md §5). Medication/event
    rows never enter the engine (TRAJECTORY_SOURCES) and are excluded from the count.
    """
    rows = await observations.list_for_patient(patient_id, since=now - LOOKBACK)
    analyzable = [row for row in rows if row.source in TRAJECTORY_SOURCES]
    return compute_trajectory(points_from_observations(analyzable), now=now), len(analyzable)
