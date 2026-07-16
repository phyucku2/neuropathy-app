"""Unit tests for the capability domain rules (ADR-0013): the pure effective-state
predicate, the lazy registry get-or-create (incl. race absorption), the repository
invariants, and the service-level defense-in-depth branches no route can reach.

All timestamps are fixed and injected — never derived from the wall clock at assert
time (a time-of-day-dependent expiry test is a CI flake waiting to happen).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.capability import Actor, Capability, PatientCapability
from app.models.connection import ClinicConnection, ConnectionStatus, Initiator
from app.repositories.capability import DuplicateCapabilityKeyError, InMemoryCapabilityRepository
from app.repositories.patient_capability import InMemoryPatientCapabilityRepository
from app.services import capability as capability_module
from app.services.capability import (
    CAPABILITIES,
    SHARE_WITH_CLINIC_KEY,
    CapabilityNotEnforcedError,
    CapabilityService,
    CapabilitySpec,
    CapabilityUnavailableError,
    PatientHeldCapabilityError,
    UnknownCapabilityError,
    is_effectively_active,
    managed_by_for,
    share_with_clinic_effective,
)

FIXED_NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _capability(*, available: bool = True) -> Capability:
    return Capability(id=uuid.uuid4(), key="ingest_adl", name="ADL", available=available)


def _row(
    *, active: bool = True, expires_at: datetime | None = None, set_by: Actor = Actor.clinician
) -> PatientCapability:
    return PatientCapability(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        capability_id=uuid.uuid4(),
        active=active,
        set_by=set_by,
        expires_at=expires_at,
    )


def _consented_connection(patient_id: uuid.UUID) -> ClinicConnection:
    return ClinicConnection(
        id=uuid.uuid4(),
        patient_id=patient_id,
        clinic_id=uuid.uuid4(),
        status=ConnectionStatus.active,
        initiated_by=Initiator.clinic,
        consent_granted_at=FIXED_NOW - timedelta(days=1),
    )


# ------------------------------------------------------ the effective-state predicate


def test_no_row_means_the_registry_default() -> None:
    capability = _capability()
    assert is_effectively_active(capability, None, default=True, now=FIXED_NOW) is True
    assert is_effectively_active(capability, None, default=False, now=FIXED_NOW) is False


def test_kill_switch_overrides_everything() -> None:
    dead = _capability(available=False)
    on_forever = _row(active=True, expires_at=None)
    assert is_effectively_active(dead, on_forever, default=True, now=FIXED_NOW) is False
    assert is_effectively_active(dead, None, default=True, now=FIXED_NOW) is False


def test_row_state_beats_the_default() -> None:
    capability = _capability()
    assert is_effectively_active(capability, _row(active=False), default=True, now=FIXED_NOW) is (
        False
    )
    assert is_effectively_active(capability, _row(active=True), default=False, now=FIXED_NOW) is (
        True
    )


def test_expiry_is_judged_against_the_injected_now() -> None:
    capability = _capability()
    expired = _row(active=True, expires_at=FIXED_NOW - timedelta(seconds=1))
    live = _row(active=True, expires_at=FIXED_NOW + timedelta(days=30))
    assert is_effectively_active(capability, expired, default=True, now=FIXED_NOW) is False
    assert is_effectively_active(capability, live, default=True, now=FIXED_NOW) is True
    # The same rows judged at a later now: the live grant lapses too (renewable order).
    later = FIXED_NOW + timedelta(days=31)
    assert is_effectively_active(capability, live, default=True, now=later) is False


# ------------------------------------------------------ registry lazy get-or-create


async def test_registry_rows_are_created_lazily_once() -> None:
    service = CapabilityService()
    assert await service.capabilities.list() == []
    assert await service.is_active(uuid.uuid4(), "ingest_adl", now=FIXED_NOW) is True
    (row,) = await service.capabilities.list()
    assert row.key == "ingest_adl" and row.available is True
    # A second touch reuses the row instead of re-creating it.
    await service.is_active(uuid.uuid4(), "ingest_adl", now=FIXED_NOW)
    assert len(await service.capabilities.list()) == 1


async def test_registry_covers_every_shipped_feature() -> None:
    service = CapabilityService()
    states = await service.effective_states(uuid.uuid4(), now=FIXED_NOW)
    assert [s.key for s in states] == [spec.key for spec in CAPABILITIES]
    assert {s.key for s in states} == {
        "ingest_labs",
        "ingest_adl",
        "ingest_biomech",
        "ingest_symptoms",
        "emr_connect",
        "ai_narrative",
        "share_with_clinic",
    }
    by_key = {s.key: s for s in states}
    # Back-compat: with no rows, every pre-existing feature keeps working. The one opt-in
    # key (ingest_symptoms, ADR-0034 Phase 1) is default OFF until the owner enables it.
    assert all(s.active for s in states if s.key != "ingest_symptoms")
    assert by_key["ingest_symptoms"].active is False
    assert all(s.managed_by == "patient" for s in states)


async def test_registry_absorbs_a_lost_creation_race() -> None:
    """When a concurrent request wins the get-or-create race, storage raises
    DuplicateCapabilityKeyError and the ensure re-fetches the winner's row — no error
    escapes (mirrors the invite flow's duplicate absorption)."""

    class RacedRepository(InMemoryCapabilityRepository):
        async def add(self, capability: Capability) -> Capability:
            await super().add(capability)  # the concurrent winner's insert...
            raise DuplicateCapabilityKeyError(capability.key)  # ...then our loss

    service = CapabilityService(capabilities=RacedRepository())
    assert await service.is_active(uuid.uuid4(), "ingest_labs", now=FIXED_NOW) is True
    (row,) = await service.capabilities.list()
    assert row.key == "ingest_labs"


async def test_unknown_key_raises_at_the_seam() -> None:
    service = CapabilityService()
    with pytest.raises(UnknownCapabilityError):
        await service.is_active(uuid.uuid4(), "not_a_feature", now=FIXED_NOW)


# ------------------------------------------------------ repository invariants


async def test_in_memory_registry_rejects_duplicate_keys() -> None:
    """The in-memory twin of the unique constraint on capability.key."""
    repo = InMemoryCapabilityRepository()
    await repo.add(Capability(key="ingest_adl", name="ADL"))
    with pytest.raises(DuplicateCapabilityKeyError):
        await repo.add(Capability(key="ingest_adl", name="ADL again"))
    assert [c.key for c in await repo.list()] == ["ingest_adl"]


async def test_in_memory_registry_mirrors_column_defaults_only_when_absent() -> None:
    """Pre-populated id/created_at/available survive `add` untouched — the in-memory
    store only mirrors the DB column defaults for values a flush would fill in."""
    repo = InMemoryCapabilityRepository()
    given_id = uuid.uuid4()
    row = await repo.add(
        Capability(id=given_id, key="synthetic_key", name="Synthetic", available=False)
    )
    row.created_at = FIXED_NOW  # would come from the DB; fix it before re-checking
    assert row.id == given_id
    assert row.available is False
    stored = await repo.add(
        Capability(id=uuid.uuid4(), created_at=FIXED_NOW, key="other_key", name="Other")
    )
    assert stored.created_at == FIXED_NOW
    assert stored.available is True  # the one default a flush would have applied


async def test_in_memory_upsert_keeps_one_row_per_pair() -> None:
    """The in-memory twin of uq_patient_capability: repeated upserts update the one
    row in place — active, set_by, and expires_at all follow the latest write."""
    repo = InMemoryPatientCapabilityRepository()
    patient_id, capability_id = uuid.uuid4(), uuid.uuid4()
    first = await repo.upsert(
        patient_id=patient_id,
        capability_id=capability_id,
        active=True,
        set_by=Actor.patient,
        expires_at=None,
    )
    expiry = FIXED_NOW + timedelta(days=30)
    second = await repo.upsert(
        patient_id=patient_id,
        capability_id=capability_id,
        active=False,
        set_by=Actor.clinician,
        expires_at=expiry,
    )
    assert second.id == first.id  # updated in place, never a second row
    assert [r.id for r in await repo.list_for_patient(patient_id)] == [first.id]
    assert await repo.get(patient_id, capability_id) is second
    assert second.active is False
    assert second.set_by is Actor.clinician
    assert second.expires_at == expiry
    assert await repo.get(patient_id, uuid.uuid4()) is None
    assert await repo.list_for_patient(uuid.uuid4()) == []


# ------------------------------------------------------ service defense in depth


async def test_clinician_set_rejudges_the_connection() -> None:
    """`set_for_clinician` re-applies may_transmit_to_clinic to the connection the
    route hands in: a revoked or never-consented one answers None (-> 404) and writes
    nothing — even though no route can produce that call today (defense in depth,
    like the panel's re-judging)."""
    service = CapabilityService()
    patient_id = uuid.uuid4()
    connection = _consented_connection(patient_id)
    connection.revoked_at = FIXED_NOW
    connection.status = ConnectionStatus.revoked
    result = await service.set_for_clinician(
        connection=connection,
        actor_id=uuid.uuid4(),
        key="ingest_adl",
        active=False,
        expires_at=None,
        now=FIXED_NOW,
    )
    assert result is None
    assert await service.patient_capabilities.list_for_patient(patient_id) == []
    assert await service.audit.list_for_patient(patient_id) == []


async def test_clinician_set_respects_the_kill_switch() -> None:
    service = CapabilityService()
    dead = await service.capabilities.add(Capability(key="ingest_adl", name="ADL", available=False))
    assert dead.available is False
    with pytest.raises(CapabilityUnavailableError):
        await service.set_for_clinician(
            connection=_consented_connection(uuid.uuid4()),
            actor_id=uuid.uuid4(),
            key="ingest_adl",
            active=True,
            expires_at=None,
            now=FIXED_NOW,
        )


# ------------------------------------------------------ ADR-0020: enforced + carve-outs


def test_every_shipped_key_is_enforced() -> None:
    """After ADR-0020 wired the last three consumers, no shipped key is un-wired."""
    assert all(spec.enforced for spec in CAPABILITIES)


def test_managed_by_carves_out_share_with_clinic() -> None:
    """The patient-held consent control always reads 'patient' (ADR-0020); every other
    key follows the connection."""
    assert managed_by_for("ingest_adl", clinically_managed=True) == "clinic"
    assert managed_by_for("ingest_adl", clinically_managed=False) == "patient"
    assert managed_by_for(SHARE_WITH_CLINIC_KEY, clinically_managed=True) == "patient"
    assert managed_by_for(SHARE_WITH_CLINIC_KEY, clinically_managed=False) == "patient"


async def test_share_with_clinic_effective_defaults_on_then_follows_the_row() -> None:
    """The clinician-read gate's toggle half (ADR-0020): default-on with no registry
    row (back-compat), then tracks the stored state once the patient sets it."""
    caps = InMemoryCapabilityRepository()
    patient_caps = InMemoryPatientCapabilityRepository()
    patient_id = uuid.uuid4()
    # No registry row yet -> the default (sharing on), so consented flows keep working.
    assert await share_with_clinic_effective(caps, patient_caps, patient_id, now=FIXED_NOW) is True
    capability = await caps.add(Capability(key=SHARE_WITH_CLINIC_KEY, name="Share"))
    await patient_caps.upsert(
        patient_id=patient_id,
        capability_id=capability.id,
        active=False,
        set_by=Actor.patient,
        expires_at=None,
    )
    assert await share_with_clinic_effective(caps, patient_caps, patient_id, now=FIXED_NOW) is False


async def test_managed_patient_may_set_share_with_clinic_but_not_other_keys() -> None:
    """The service-level carve-out (ADR-0020): while clinically managed the patient's
    own write to any key 409s — EXCEPT share_with_clinic, their consent control."""
    service = CapabilityService()
    patient_id = uuid.uuid4()
    await service.connections.add(_consented_connection(patient_id))  # makes them managed
    from app.services.capability import ClinicallyManagedError

    with pytest.raises(ClinicallyManagedError):
        await service.set_for_patient(
            patient_id=patient_id,
            actor_id=uuid.uuid4(),
            key="ingest_adl",
            active=False,
            now=FIXED_NOW,
        )
    state = await service.set_for_patient(
        patient_id=patient_id,
        actor_id=uuid.uuid4(),
        key=SHARE_WITH_CLINIC_KEY,
        active=False,
        now=FIXED_NOW,
    )
    assert state.active is False
    assert state.managed_by == "patient"


async def test_clinician_cannot_set_the_patient_held_share_control() -> None:
    """A clinic can never set share_with_clinic — it is patient-held (ADR-0020)."""
    service = CapabilityService()
    with pytest.raises(PatientHeldCapabilityError):
        await service.set_for_clinician(
            connection=_consented_connection(uuid.uuid4()),
            actor_id=uuid.uuid4(),
            key=SHARE_WITH_CLINIC_KEY,
            active=False,
            expires_at=None,
            now=FIXED_NOW,
        )


async def test_unwired_future_key_refuses_writes_for_both_actors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `enforced` guard still protects a FUTURE key introduced un-wired (ADR-0013):
    a stored 'off' the feature would ignore is a false promise, so both the patient and
    clinician write paths refuse it (409 'not changeable yet')."""
    synthetic = CapabilitySpec(key="future_unwired", name="Future", default=True, enforced=False)
    monkeypatch.setitem(capability_module._SPEC_BY_KEY, "future_unwired", synthetic)
    service = CapabilityService()
    with pytest.raises(CapabilityNotEnforcedError):
        await service.set_for_patient(
            patient_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            key="future_unwired",
            active=False,
            now=FIXED_NOW,
        )
    with pytest.raises(CapabilityNotEnforcedError):
        await service.set_for_clinician(
            connection=_consented_connection(uuid.uuid4()),
            actor_id=uuid.uuid4(),
            key="future_unwired",
            active=False,
            expires_at=None,
            now=FIXED_NOW,
        )
