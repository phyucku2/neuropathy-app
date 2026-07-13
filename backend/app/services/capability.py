"""Capability service — server-enforced feature toggles (ADR-0013).

Every feature is a Capability; whether it is on for a patient is judged here, never
by a client-side flag. Three invariants are enforced in this service, not in routes:

- **Effective state.** effective = capability.available AND (row.active if a row
  exists, else the registry default) AND (row not expired). Absence of a row means
  the DEFAULT — every feature that works today keeps working — and the ops kill
  switch (available=False) overrides everything.
- **Authority.** A patient is clinically managed iff at least one of their clinic
  connections passes `may_transmit_to_clinic` (app/services/connection.py — reused,
  never re-derived). Clinically managed -> only a clinician (or ops) may change
  toggles and the patient's own writes are refused; B2C -> the patient controls their
  own toggles. `expires_at` is settable only by clinicians (order-style renewal).
- **Audit.** Every toggle change writes an AuditEvent (config change, CLAUDE.md §5) —
  actor, action=set_capability, key/active/expires_at/set_by, never health data.

The registry (CAPABILITIES) is the canonical seed list in code; rows are created
lazily by key so both storage modes work without seeds.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.models.audit import AuditEvent
from app.models.capability import Actor, Capability, PatientCapability
from app.models.connection import ClinicConnection
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.capability import (
    CapabilityRepository,
    DuplicateCapabilityKeyError,
    InMemoryCapabilityRepository,
)
from app.repositories.clinic_connection import (
    ClinicConnectionRepository,
    InMemoryClinicConnectionRepository,
)
from app.repositories.patient_capability import (
    InMemoryPatientCapabilityRepository,
    PatientCapabilityRepository,
)
from app.services.connection import may_transmit_to_clinic

__all__ = [
    "CAPABILITIES",
    "CapabilityApiError",
    "CapabilityService",
    "CapabilitySpec",
    "CapabilityNotEnforcedError",
    "CapabilityUnavailableError",
    "ClinicallyManagedError",
    "EffectiveCapability",
    "ManagedBy",
    "UnknownCapabilityError",
    "is_effectively_active",
]

ManagedBy = Literal["patient", "clinic"]


@dataclass(frozen=True)
class CapabilitySpec:
    """One registry entry: the stable key, display name, no-row default, and whether
    the toggle is actually wired to its feature yet (`enforced`)."""

    key: str
    name: str
    default: bool
    enforced: bool


# The canonical registry — every feature the app ships today. Defaults are all True:
# absence of a PatientCapability row means "works exactly as before toggles existed"
# (back-compat, ADR-0013). The DB row's `available` flag is the ops kill switch; the
# default lives here in code because it is a product decision, not per-deployment state.
# `enforced=False` keys are visible but NOT yet settable: a stored "off" the feature
# ignores would be a false promise about what is processed/disclosed (review finding);
# each key flips to enforced=True in the PR that wires its consumer.
CAPABILITIES: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(key="ingest_labs", name="Lab result upload", default=True, enforced=True),
    CapabilitySpec(key="ingest_adl", name="Daily function check-in", default=True, enforced=True),
    CapabilitySpec(
        key="emr_connect", name="Medical record connection", default=True, enforced=False
    ),
    CapabilitySpec(
        key="ai_narrative", name="AI trajectory narration", default=True, enforced=False
    ),
    CapabilitySpec(
        key="share_with_clinic", name="Share data with my clinic", default=True, enforced=False
    ),
)

_SPEC_BY_KEY: dict[str, CapabilitySpec] = {spec.key: spec for spec in CAPABILITIES}


class CapabilityApiError(Exception):
    """Capability flow error the route layer maps to an HTTP response."""

    def __init__(self, reason: str, status_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


class UnknownCapabilityError(CapabilityApiError):
    def __init__(self, key: str) -> None:
        super().__init__(f"Unknown capability: {key}", status_code=404)


class CapabilityUnavailableError(CapabilityApiError):
    def __init__(self, key: str) -> None:
        super().__init__(f"Capability is not currently available: {key}", status_code=409)


class ClinicallyManagedError(CapabilityApiError):
    def __init__(self) -> None:
        super().__init__(
            "Your features are managed by your connected clinic; "
            "ask your care team to change them, or revoke the clinic connection.",
            status_code=409,
        )


class CapabilityNotEnforcedError(CapabilityApiError):
    """Writes to a not-yet-wired toggle are refused: storing an "off" the feature
    would ignore misleads the patient about what is actually processed or disclosed
    (review finding). The key becomes settable when its consumer is wired."""

    def __init__(self, key: str) -> None:
        super().__init__(f"This setting is not changeable yet: {key}", status_code=409)


@dataclass(frozen=True)
class EffectiveCapability:
    """One capability's server-judged state for one patient."""

    key: str
    name: str
    active: bool
    managed_by: ManagedBy
    expires_at: datetime | None
    enforced: bool


def is_effectively_active(
    capability: Capability,
    row: PatientCapability | None,
    *,
    default: bool,
    now: datetime,
) -> bool:
    """THE effective-state predicate (ADR-0013), pure and unit-locked.

    Kill switch first (available=False overrides everything), then the row's state
    (absence means the registry default), then expiry (an expired clinician grant is
    off until renewed — order-style).
    """
    if not capability.available:
        return False
    if row is None:
        return default
    if not row.active:
        return False
    return row.expires_at is None or row.expires_at > now


@dataclass
class CapabilityService:
    capabilities: CapabilityRepository = field(default_factory=InMemoryCapabilityRepository)
    patient_capabilities: PatientCapabilityRepository = field(
        default_factory=InMemoryPatientCapabilityRepository
    )
    connections: ClinicConnectionRepository = field(
        default_factory=InMemoryClinicConnectionRepository
    )
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)

    async def _ensure(self, key: str) -> tuple[Capability, CapabilitySpec]:
        """Get-or-create the registry row for a known key (lazy seeding, ADR-0013).

        Raises UnknownCapabilityError for keys outside the code registry. Race-safe:
        a concurrent first-touch is absorbed via DuplicateCapabilityKeyError and the
        winner's row is re-fetched, mirroring the invite flow's duplicate absorption.
        """
        spec = _SPEC_BY_KEY.get(key)
        if spec is None:
            raise UnknownCapabilityError(key)
        row = await self.capabilities.get_by_key(key)
        if row is None:
            try:
                row = await self.capabilities.add(Capability(key=spec.key, name=spec.name))
            except DuplicateCapabilityKeyError:
                row = await self.capabilities.get_by_key(key)
                assert row is not None  # the duplicate error guarantees the winner's row
        return row, spec

    async def is_clinically_managed(self, patient_id: uuid.UUID, *, lock: bool = False) -> bool:
        """THE authority rule (ADR-0013): clinically managed iff at least one clinic
        connection currently permits transmission — judged per connection by
        `may_transmit_to_clinic`, never re-derived. Revocation flips authority back
        to the patient instantly.

        `lock=True` (write flows) takes a FOR SHARE read in Postgres so the check
        cannot race a concurrent consent grant — the patient's toggle write either
        commits strictly before consent or sees it and is refused (review finding).
        """
        connections = await self.connections.list_for_patient(patient_id, for_share=lock)
        return any(may_transmit_to_clinic(connection) for connection in connections)

    async def effective_states(
        self, patient_id: uuid.UUID, *, now: datetime
    ) -> list[EffectiveCapability]:
        """Every registry capability's effective state for one patient, in registry
        order. This is what clients render — toggles in the app are UI hints only."""
        managed_by: ManagedBy = (
            "clinic" if await self.is_clinically_managed(patient_id) else "patient"
        )
        rows = {
            row.capability_id: row
            for row in await self.patient_capabilities.list_for_patient(patient_id)
        }
        states: list[EffectiveCapability] = []
        for spec in CAPABILITIES:
            capability, _ = await self._ensure(spec.key)
            row = rows.get(capability.id)
            states.append(
                EffectiveCapability(
                    key=spec.key,
                    name=capability.name,
                    active=is_effectively_active(capability, row, default=spec.default, now=now),
                    managed_by=managed_by,
                    expires_at=row.expires_at if row is not None else None,
                    enforced=spec.enforced,
                )
            )
        return states

    async def is_active(self, patient_id: uuid.UUID, key: str, *, now: datetime) -> bool:
        """One capability's effective on/off — the enforcement seam's question.

        Raises UnknownCapabilityError for keys outside the registry (a programming
        error at the call site, not a user input)."""
        capability, spec = await self._ensure(key)
        row = await self.patient_capabilities.get(patient_id, capability.id)
        return is_effectively_active(capability, row, default=spec.default, now=now)

    async def set_for_patient(
        self,
        *,
        patient_id: uuid.UUID,
        actor_id: uuid.UUID,
        key: str,
        active: bool,
        now: datetime,
    ) -> EffectiveCapability:
        """Patient sets their OWN toggle — B2C authority only (ADR-0013).

        Refused (409) while clinically managed: a consented clinic owns the toggles,
        order-like. Patients can never set expiry; their write clears any stale
        clinician expiry along with the row it rode in on."""
        capability, spec = await self._ensure(key)
        if not spec.enforced:
            raise CapabilityNotEnforcedError(key)
        if not capability.available:
            raise CapabilityUnavailableError(key)
        if await self.is_clinically_managed(patient_id, lock=True):
            raise ClinicallyManagedError()
        row = await self.patient_capabilities.upsert(
            patient_id=patient_id,
            capability_id=capability.id,
            active=active,
            set_by=Actor.patient,
            expires_at=None,
        )
        await self._audit_change(
            actor_id=actor_id, actor_role=Actor.patient, patient_id=patient_id, key=key, row=row
        )
        return EffectiveCapability(
            key=spec.key,
            name=capability.name,
            active=is_effectively_active(capability, row, default=spec.default, now=now),
            managed_by="patient",
            expires_at=None,
            enforced=spec.enforced,
        )

    async def set_for_clinician(
        self,
        *,
        connection: ClinicConnection,
        actor_id: uuid.UUID,
        key: str,
        active: bool,
        expires_at: datetime | None,
        now: datetime,
    ) -> EffectiveCapability | None:
        """Clinician sets a consented patient's toggle, optionally with expiry —
        renewable like an order (ADR-0013).

        `connection` is the consented connection the route's access gate resolved;
        defense in depth re-judges it with `may_transmit_to_clinic` and answers None
        (-> 404) if it does not currently permit transmission, so a stale or revoked
        connection can never change toggles even if a route bug hands one in."""
        if not may_transmit_to_clinic(connection):
            return None
        capability, spec = await self._ensure(key)
        if not spec.enforced:
            raise CapabilityNotEnforcedError(key)
        if not capability.available:
            raise CapabilityUnavailableError(key)
        row = await self.patient_capabilities.upsert(
            patient_id=connection.patient_id,
            capability_id=capability.id,
            active=active,
            set_by=Actor.clinician,
            expires_at=expires_at,
        )
        await self._audit_change(
            actor_id=actor_id,
            actor_role=Actor.clinician,
            patient_id=connection.patient_id,
            key=key,
            row=row,
            connection_id=connection.id,
        )
        return EffectiveCapability(
            key=spec.key,
            name=capability.name,
            active=is_effectively_active(capability, row, default=spec.default, now=now),
            managed_by="clinic",
            expires_at=row.expires_at,
            enforced=spec.enforced,
        )

    async def _audit_change(
        self,
        *,
        actor_id: uuid.UUID,
        actor_role: Actor,
        patient_id: uuid.UUID,
        key: str,
        row: PatientCapability,
        connection_id: uuid.UUID | None = None,
    ) -> None:
        """Config-change audit (CLAUDE.md §5): who set which toggle to what, with
        expiry — references and flags only, never health-data values."""
        detail: dict[str, object] = {
            "key": key,
            "active": row.active,
            "expires_at": row.expires_at.isoformat() if row.expires_at is not None else None,
            "set_by": row.set_by.value,
        }
        if connection_id is not None:
            detail["connection_id"] = str(connection_id)
        await self.audit.add(
            AuditEvent(
                actor_id=actor_id,
                actor_role=actor_role.value,
                action="set_capability",
                patient_id=patient_id,
                detail=detail,
            )
        )
