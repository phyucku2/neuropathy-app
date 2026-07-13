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

from fastapi import APIRouter, BackgroundTasks

from app.ai.narrative import NARRATIVE_CACHE, narrate_into_cache, narrative_cache_key
from app.api.deps import EmrServiceDep, NarratorDep, PatientUserDep
from app.core.config import settings
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
async def get_trajectory(
    current: PatientUserDep,
    service: EmrServiceDep,
    narrator: NarratorDep,
    background: BackgroundTasks,
) -> Trajectory:
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
    trajectory = compute_trajectory(points_from_observations(observations), now=now)
    # Deterministic result stands on its own; the narrator may only rephrase it.
    # The LLM is NEVER in the request path (standards.md: async jobs only): a cached
    # accepted narrative is served immediately; otherwise this response ships the
    # template summary and narration runs as a background task AFTER the response —
    # outside the request's DB transaction (ADR-0011 rev. 2, review findings).
    if narrator is not None:
        key = narrative_cache_key(trajectory, settings.ai_model)
        known, cached = NARRATIVE_CACHE.lookup(key)
        if cached is not None:
            trajectory = trajectory.model_copy(update={"summary": cached, "narrative_source": "ai"})
        elif not known and NARRATIVE_CACHE.begin(key):
            # The scheduled provider call is a PHI-derived disclosure: audit it NOW,
            # within this request's transaction, so error/rejection paths are never
            # unaccounted (review finding: disclosure must not depend on acceptance).
            await service.audit.add(
                AuditEvent(
                    actor_id=current.user_id,
                    actor_role=current.role.value,
                    action="ai_narrative",
                    patient_id=current.patient_id,
                    detail={"model": settings.ai_model, "event": "requested"},  # never content
                )
            )
            background.add_task(narrate_into_cache, narrator, trajectory, key, NARRATIVE_CACHE)
    return trajectory
