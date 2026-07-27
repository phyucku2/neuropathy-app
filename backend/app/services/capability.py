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
    "SHARE_WITH_CLINIC_KEY",
    "CapabilityApiError",
    "CapabilityService",
    "CapabilitySpec",
    "CapabilityNotEnforcedError",
    "CapabilityUnavailableError",
    "ClinicallyManagedError",
    "EffectiveCapability",
    "ManagedBy",
    "PatientHeldCapabilityError",
    "UnknownCapabilityError",
    "is_effectively_active",
    "managed_by_for",
    "share_with_clinic_effective",
]

ManagedBy = Literal["patient", "clinic"]

# The one patient-held CONSENT control (ADR-0020): unlike every other key, the patient
# always controls it — even while clinically managed — because it is the mechanism by
# which they stop sharing. A clinic controlling the patient's ability to stop sharing
# would be perverse. Named once so the carve-outs below can never drift on a typo.
SHARE_WITH_CLINIC_KEY = "share_with_clinic"


@dataclass(frozen=True)
class CapabilitySpec:
    """One registry entry: the stable key, display name, no-row default, and whether
    the toggle is actually wired to its feature yet (`enforced`)."""

    key: str
    name: str
    default: bool
    enforced: bool


# The canonical registry — every feature the app ships. Back-compat keys default True:
# absence of a PatientCapability row means "works exactly as before toggles existed"
# (ADR-0013). The DB row's `available` flag is the ops kill switch; the default lives here
# in code because it is a product decision, not per-deployment state.
# `enforced=False` keys are visible but NOT yet settable: a stored "off" the feature
# ignores would be a false promise about what is processed/disclosed (review finding);
# each key flips to enforced=True in the PR that wires its consumer. As of ADR-0020 all
# shipped keys are wired: emr_connect gates the EMR connect flow, ai_narrative gates
# narrator scheduling, share_with_clinic gates clinician reads. The `enforced` flag and
# its read-only rendering stay in place for any FUTURE key introduced un-wired.
# `ingest_symptoms` (pain + numbness) is the CORE of the daily neuropathy instrument and
# defaults ON (ADR-0049 — amends ADR-0034's Phase-1 opt-in); a patient can still turn it
# off to keep a function-only check-in. enforced=True — the /adl route only persists
# symptom rows when it is on.
CAPABILITIES: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(key="ingest_labs", name="Lab result upload", default=True, enforced=True),
    CapabilitySpec(key="ingest_adl", name="Daily function check-in", default=True, enforced=True),
    CapabilitySpec(key="ingest_biomech", name="BioMech report upload", default=True, enforced=True),
    # Symptom items (pain + numbness) are the CORE of the daily neuropathy instrument, so they
    # default ON (ADR-0049 — amends ADR-0034's Phase-1 opt-in). Kept a separable toggle, not
    # merged into ingest_adl, so a patient can decline daily symptom prompts and keep the
    # function check-in (autonomy, ADR-0013). enforced=True — the /adl route only persists
    # symptom rows when it is on.
    CapabilitySpec(
        key="ingest_symptoms",
        name="Symptom check-in (pain & numbness)",
        default=True,
        enforced=True,
    ),
    # Wearable/phone mobility import (ADR-0035 Phase 1). OPT-IN (default off): health-store
    # data is PHI, so nothing is imported until the patient turns it on. enforced=True — the
    # /wearable route only persists rows when it is on (enforced-flag honesty, ADR-0013).
    CapabilitySpec(
        key="ingest_wearable",
        name="Wearable health data (phone & watch)",
        default=False,
        enforced=True,
    ),
    # Patient-entered medication/supplement change log and between-visit events/notes
    # (ADR-0045 P2). Default ON (back-compat posture of the other capture keys); enforced —
    # the medications/events routes refuse the write with 409 when the toggle is off.
    CapabilitySpec(
        key="ingest_medications", name="Medications & supplements", default=True, enforced=True
    ),
    CapabilitySpec(
        key="ingest_events", name="Between-visit notes & events", default=True, enforced=True
    ),
    CapabilitySpec(
        key="emr_connect", name="Medical record connection", default=True, enforced=True
    ),
    # EMR clinical-note pull (ADR-0045 P2 #27). OPT-IN (default off, like ingest_wearable):
    # notes are large sensitive free-text, so nothing is pulled until the patient turns it
    # on. enforced=True — POST /emr/connections/{id}/pull-notes refuses with 409 when off.
    CapabilitySpec(key="ingest_notes", name="EMR clinician notes", default=False, enforced=True),
    CapabilitySpec(key="ai_narrative", name="AI trajectory narration", default=True, enforced=True),
    CapabilitySpec(
        key=SHARE_WITH_CLINIC_KEY, name="Share data with my clinic", default=True, enforced=True
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


class PatientHeldCapabilityError(CapabilityApiError):
    """A clinician tried to set a patient-held consent control (share_with_clinic).
    That key is the patient's own mechanism to stop sharing (ADR-0020) — a clinic
    can never set it, even for a clinically-managed patient. 409: the key exists but
    the actor may not change it."""

    def __init__(self, key: str) -> None:
        super().__init__(
            f"This setting is controlled by the patient and cannot be set here: {key}",
            status_code=409,
        )


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


def managed_by_for(key: str, *, clinically_managed: bool) -> ManagedBy:
    """Who holds toggle authority for one key (ADR-0013, amended by ADR-0020).

    Every key follows the connection: clinic while clinically managed, else patient.
    `share_with_clinic` is the ONE exception — a patient-held consent control the
    patient always owns, so it reads `patient` regardless of managed status (the UI
    must render it interactive, and `set_for_patient` honors that carve-out)."""
    if key == SHARE_WITH_CLINIC_KEY:
        return "patient"
    return "clinic" if clinically_managed else "patient"


async def share_with_clinic_effective(
    capabilities: CapabilityRepository,
    patient_capabilities: PatientCapabilityRepository,
    patient_id: uuid.UUID,
    *,
    now: datetime,
) -> bool:
    """Effective on/off of `share_with_clinic` for one patient — the patient-held
    consent gate the clinician-read predicate ANDs with connection consent (ADR-0020).

    Reuses `is_effectively_active` (the single unit-locked predicate) and the registry
    default. No registry row yet -> the default (True), so existing consented
    connections keep working with no back-fill (back-compat by construction). Reads
    only; it never seeds a row, so a clinician read can't mutate capability state."""
    spec = _SPEC_BY_KEY[SHARE_WITH_CLINIC_KEY]
    capability = await capabilities.get_by_key(SHARE_WITH_CLINIC_KEY)
    if capability is None:
        return spec.default
    row = await patient_capabilities.get(patient_id, capability.id)
    return is_effectively_active(capability, row, default=spec.default, now=now)


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
        clinically_managed = await self.is_clinically_managed(patient_id)
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
                    # share_with_clinic reads 'patient' even while managed (ADR-0020):
                    # it is patient-held consent, so the client must render it settable.
                    managed_by=managed_by_for(spec.key, clinically_managed=clinically_managed),
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
        order-like. The ONE exception is `share_with_clinic` (ADR-0020) — a patient-held
        consent control the patient always owns, even while clinically managed, because
        it is how they stop sharing; the managed-authority refusal is skipped for it.
        Patients can never set expiry; their write clears any stale clinician expiry
        along with the row it rode in on."""
        capability, spec = await self._ensure(key)
        if not spec.enforced:
            raise CapabilityNotEnforcedError(key)
        if not capability.available:
            raise CapabilityUnavailableError(key)
        # Patient-held consent (share_with_clinic) is exempt from clinician authority:
        # the patient may always turn it off — a clinic controlling the patient's ability
        # to stop sharing would be perverse (ADR-0020). Every other key stays clinician-
        # controlled while managed. The FOR SHARE lock still guards the race for those.
        if key != SHARE_WITH_CLINIC_KEY and await self.is_clinically_managed(patient_id, lock=True):
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
        # A clinic can never set the patient's own consent-to-share control (ADR-0020):
        # it is patient-held, so even a consented clinician write to it is refused. (The
        # read gate already 404s clinician access once share is off; this guards the
        # narrow window where share is still on and a clinician tries to flip it.)
        if key == SHARE_WITH_CLINIC_KEY:
            raise PatientHeldCapabilityError(key)
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
