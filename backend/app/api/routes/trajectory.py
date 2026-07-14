"""Trajectory endpoint — the product's centerpiece view (ADR-0003).

Reads the caller's own analyzable observations (repository excludes errored and
superseded records), converts them to points, and computes the deterministic,
explainable trajectory. No AI call in this increment; the engine is pure code.

State posture: the shared in-memory store behind EmrServiceDep is per-process until
DATABASE_URL wiring lands (deps._default_emr_service) — fine for tests/dev, not for
multi-worker serving.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks

from app.ai.narrative import NARRATIVE_CACHE, narrate_into_cache, narrative_cache_key
from app.api.deps import CapabilityServiceDep, EmrServiceDep, NarratorDep, PatientUserDep
from app.core.config import settings
from app.core.metrics import record_ai_narrative_event
from app.models.audit import AuditEvent
from app.schemas.trajectory import Trajectory
from app.services.trajectory import compute_patient_trajectory

router = APIRouter(prefix="/trajectory", tags=["trajectory"])


@router.get("", response_model=Trajectory)
async def get_trajectory(
    current: PatientUserDep,
    service: EmrServiceDep,
    narrator: NarratorDep,
    capabilities: CapabilityServiceDep,
    background: BackgroundTasks,
) -> Trajectory:
    """The patient's own health trajectory: direction, confidence, sourced signals,
    and explicit data gaps. Always scoped to the authenticated patient."""
    assert current.patient_id is not None  # guaranteed by require_patient
    now = datetime.now(UTC)
    # Shared deterministic computation (services/trajectory.py) — the clinician view
    # answers from the same helper, so the two surfaces can never drift (ADR-0012).
    trajectory, observation_count = await compute_patient_trajectory(
        service.observations, current.patient_id, now=now
    )
    # PHI read — audit-logged like every other health-data access (CLAUDE.md 5).
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role=current.role.value,
            action="read_trajectory",
            patient_id=current.patient_id,
            detail={"observations": observation_count},  # counts only, never values
        )
    )
    # Deterministic result stands on its own; the narrator may only rephrase it.
    # The LLM is NEVER in the request path (standards.md: async jobs only): a cached
    # accepted narrative is served immediately; otherwise this response ships the
    # template summary and narration runs as a background task AFTER the response —
    # outside the request's DB transaction (ADR-0011 rev. 2, review findings).
    #
    # ai_narrative toggle ANDs with the BAA gate (ADR-0020): BOTH must be satisfied to
    # narrate. This is an in-handler branch, NOT a require_capability 409 gate — the
    # endpoint always returns 200 with the deterministic summary. With the toggle off
    # the request stays fully deterministic: no cached AI narrative is served, no
    # narration is scheduled, and (since scheduling never happens) no ai_narrative
    # disclosure is audited. The toggle read only runs when a narrator is configured,
    # so the deterministic path costs nothing extra.
    if narrator is not None and await capabilities.is_active(
        current.patient_id, "ai_narrative", now=now
    ):
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
            # Subject-free metric alongside the audit row: counts that a disclosure was
            # requested by TYPE, never by patient (ADR-0021) — feeds the disclosure-rate
            # alert without any subject entering a label.
            record_ai_narrative_event("requested")
            background.add_task(narrate_into_cache, narrator, trajectory, key, NARRATIVE_CACHE)
    return trajectory
