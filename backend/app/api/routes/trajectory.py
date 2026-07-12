"""Trajectory endpoint — the product's centerpiece view (ADR-0003).

Reads the caller's own analyzable observations (repository excludes errored and
superseded records), converts them to points, and computes the deterministic,
explainable trajectory. No AI call in this increment; the engine is pure code.

State posture: the shared in-memory store behind EmrServiceDep is per-process until
DATABASE_URL wiring lands (deps._default_emr_service) — fine for tests/dev, not for
multi-worker serving.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from app.api.deps import EmrServiceDep, PatientUserDep
from app.models.audit import AuditEvent
from app.schemas.trajectory import Trajectory
from app.trajectory.engine import compute_trajectory
from app.trajectory.points import points_from_observations

router = APIRouter(prefix="/trajectory", tags=["trajectory"])

# Hot-path bound (standards.md read budget): the engine's confidence math saturates at
# 90-day coverage and 6 points per signal, so a bounded lookback loses no judgment
# quality while keeping the query small on multi-year histories.
LOOKBACK = timedelta(days=400)


@router.get("", response_model=Trajectory)
async def get_trajectory(current: PatientUserDep, service: EmrServiceDep) -> Trajectory:
    """The patient's own health trajectory: direction, confidence, sourced signals,
    and explicit data gaps. Always scoped to the authenticated patient."""
    assert current.patient_id is not None  # guaranteed by require_patient
    now = datetime.now(UTC)
    observations = await service.observations.list_for_patient(
        current.patient_id, since=now - LOOKBACK
    )
    # PHI read — audit-logged like every other health-data access (CLAUDE.md 5).
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="read_trajectory",
            patient_id=current.patient_id,
            detail={"observations": len(observations)},  # counts only, never values
        )
    )
    return compute_trajectory(points_from_observations(observations), now=now)
