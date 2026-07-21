"""Unit tests for the caregiver service rules (ADR-0047): the single read
predicate, invite-code hygiene, single-use/expiry, the duplicate-live-link
backstop, lifecycle transitions, and the non-enumerating claim throttle ordering.

All data is synthetic (CLAUDE.md §5); time-sensitive assertions use injected fixed
timestamps, never the wall clock (docs/lessons.md).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.models.caregiver import (
    CaregiverInvite,
    CaregiverLink,
    CaregiverLinkStatus,
    CaregiverScope,
)
from app.models.connection import Initiator
from app.models.user import UserRole
from app.repositories.caregiver import (
    DuplicateLiveCaregiverLinkError,
    InMemoryCaregiverInviteRepository,
    InMemoryCaregiverLinkRepository,
)
from app.repositories.user import UserRecord
from app.services.caregiver import (
    CODE_INVALID_DETAIL,
    INVITE_TTL,
    CaregiverClaimError,
    CaregiverService,
    ClaimDenied,
    format_invite_code,
    generate_invite_code,
    hash_invite_code,
    normalize_invite_code,
)
from app.services.rate_limit import RateLimitExceededError

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def _link(
    *,
    status: CaregiverLinkStatus = CaregiverLinkStatus.active,
    accepted: bool = True,
    scope: CaregiverScope = CaregiverScope.trends,
) -> CaregiverLink:
    return CaregiverLink(
        patient_id=uuid.uuid4(),
        caregiver_user_id=uuid.uuid4(),
        scope=scope,
        status=status,
        initiated_by=Initiator.patient,
        accepted_at=NOW if accepted else None,
    )


async def _caregiver_user(service: CaregiverService, email: str = "care@example.com") -> UserRecord:
    user = UserRecord(
        id=uuid.uuid4(),
        email=email,
        password_hash="synthetic-hash",
        display_name="Cam Caregiver",
        role=UserRole.caregiver,
        patient_id=None,
    )
    await service.users.add(user)
    return user


# ---------------------------------------------------------------- code hygiene


def test_generated_codes_use_the_read_aloud_alphabet() -> None:
    code = generate_invite_code()
    assert len(code) == 12
    assert set(code) <= set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")  # no 0/O 1/I/L ambiguity


def test_code_normalization_forgives_case_dashes_and_spaces() -> None:
    assert normalize_invite_code(" abcd-2345 EFGH ") == "ABCD2345EFGH"
    assert hash_invite_code("abcd-2345-efgh") == hash_invite_code("ABCD2345EFGH")


def test_format_groups_for_reading_aloud() -> None:
    assert format_invite_code("ABCD2345EFGH") == "ABCD-2345-EFGH"


async def test_create_invite_stores_only_the_hash_and_audits_a_reference() -> None:
    service = CaregiverService()
    patient_id, actor_id = uuid.uuid4(), uuid.uuid4()
    invite, code = await service.create_invite(patient_id=patient_id, actor_id=actor_id)
    assert invite.code_hash == hash_invite_code(code)
    assert normalize_invite_code(code) not in invite.code_hash  # hashed, never plaintext
    # created_at is stamped by the store a beat after `now` was read; the TTL holds
    # to within that beat.
    assert abs((invite.expires_at - invite.created_at) - INVITE_TTL) < timedelta(seconds=5)
    (event,) = await service.audit.list_for_patient(patient_id)
    assert event.action == "create_caregiver_invite"
    assert event.detail == {"invite_id": str(invite.id)}
    assert normalize_invite_code(code) not in str(event.detail)  # never the code


# ---------------------------------------------------------------- read predicate


def test_predicate_requires_active_and_accepted() -> None:
    service = CaregiverService()
    assert service._may_caregiver_read(_link(), now=NOW) is True
    assert (
        service._may_caregiver_read(
            _link(status=CaregiverLinkStatus.pending, accepted=False), now=NOW
        )
        is False
    )
    assert (
        service._may_caregiver_read(
            _link(status=CaregiverLinkStatus.revoked, accepted=True), now=NOW
        )
        is False
    )
    # Defense in depth: active but never accepted (a state the API cannot produce)
    # must still never pass — acceptance IS the consent (ADR-0047 double opt-in).
    assert service._may_caregiver_read(_link(accepted=False), now=NOW) is False


def test_predicate_full_scope_requirement() -> None:
    service = CaregiverService()
    trends = _link(scope=CaregiverScope.trends)
    full = _link(scope=CaregiverScope.full)
    assert service._may_caregiver_read(trends, now=NOW, require_full=True) is False
    assert service._may_caregiver_read(full, now=NOW, require_full=True) is True
    # Trends surfaces accept both scopes.
    assert service._may_caregiver_read(trends, now=NOW) is True
    assert service._may_caregiver_read(full, now=NOW) is True


# ---------------------------------------------------------------- storage invariants


async def test_storage_rejects_second_live_link_per_pair() -> None:
    """The in-memory twin of the uq_caregiver_link_live partial unique index: one
    live link per patient-caregiver pair; a fresh link is allowed after revocation,
    and other pairs are unaffected — unlimited caregivers per patient hold."""
    repo = InMemoryCaregiverLinkRepository()
    patient_id, caregiver_id = uuid.uuid4(), uuid.uuid4()

    def fresh() -> CaregiverLink:
        return CaregiverLink(
            patient_id=patient_id,
            caregiver_user_id=caregiver_id,
            status=CaregiverLinkStatus.pending,
            initiated_by=Initiator.patient,
        )

    first = await repo.add(fresh())
    with pytest.raises(DuplicateLiveCaregiverLinkError):
        await repo.add(fresh())
    # A different caregiver is a different pair — allowed (unlimited caregivers).
    await repo.add(
        CaregiverLink(
            patient_id=patient_id,
            caregiver_user_id=uuid.uuid4(),
            status=CaregiverLinkStatus.pending,
            initiated_by=Initiator.patient,
        )
    )
    # Revoked rows leave the index: the pair may re-link later.
    first.status = CaregiverLinkStatus.revoked
    await repo.update(first)
    await repo.add(fresh())


async def test_invite_consume_is_single_use() -> None:
    repo = InMemoryCaregiverInviteRepository()
    invite = await repo.add(
        CaregiverInvite(
            patient_id=uuid.uuid4(), code_hash="synthetic-hash", expires_at=NOW + INVITE_TTL
        )
    )
    assert await repo.consume(invite.id, now=NOW) is True
    assert await repo.consume(invite.id, now=NOW) is False  # spent
    cancelled = await repo.add(
        CaregiverInvite(
            patient_id=uuid.uuid4(),
            code_hash="synthetic-hash-2",
            expires_at=NOW + INVITE_TTL,
            cancelled_at=NOW,
        )
    )
    assert await repo.consume(cancelled.id, now=NOW) is False  # dead on arrival


# ---------------------------------------------------------------- claim flow


async def test_authenticated_claim_creates_a_pending_link_and_spends_the_code() -> None:
    service = CaregiverService()
    caregiver = await _caregiver_user(service)
    patient_id = uuid.uuid4()
    invite, code = await service.create_invite(patient_id=patient_id, actor_id=uuid.uuid4())

    await service.claim_invite(caregiver_user_id=caregiver.id, code=code.lower())

    (link,) = await service.links.list_for_patient(patient_id)
    assert link.status is CaregiverLinkStatus.pending  # double opt-in: NOT active
    assert link.accepted_at is None
    assert link.scope is CaregiverScope.trends
    assert link.initiated_by is Initiator.patient
    refreshed = await service.invites.get(invite.id)
    assert refreshed is not None and refreshed.consumed_at is not None  # single-use spent
    events = await service.audit.list_for_patient(patient_id)
    claim = next(e for e in events if e.action == "caregiver_claim")
    assert claim.detail == {"matched": True, "created": True, "registration": False}


async def test_claim_with_expired_or_dead_code_matches_nothing() -> None:
    service = CaregiverService()
    caregiver = await _caregiver_user(service)
    patient_id = uuid.uuid4()
    invite, code = await service.create_invite(patient_id=patient_id, actor_id=uuid.uuid4())
    invite.expires_at = datetime.now(UTC) - timedelta(seconds=1)  # expired
    await service.invites.update(invite)

    await service.claim_invite(caregiver_user_id=caregiver.id, code=code)

    assert await service.links.list_for_patient(patient_id) == []
    unmatched = [
        e
        for e in service.audit._events  # type: ignore[attr-defined]
        if e.action == "caregiver_claim"
    ]
    assert len(unmatched) == 1
    assert unmatched[0].detail == {"matched": False, "created": False, "registration": False}
    assert unmatched[0].patient_id is None  # the code was never resolved to a patient


async def test_claim_absorbs_an_existing_live_link_but_still_spends_the_code() -> None:
    """A second code claimed for the SAME pair: the code is consumed (single-use
    holds) but no duplicate link appears, and the audit records created=False."""
    service = CaregiverService()
    caregiver = await _caregiver_user(service)
    patient_id = uuid.uuid4()
    _, first_code = await service.create_invite(patient_id=patient_id, actor_id=uuid.uuid4())
    await service.claim_invite(caregiver_user_id=caregiver.id, code=first_code)
    second_invite, second_code = await service.create_invite(
        patient_id=patient_id, actor_id=uuid.uuid4()
    )

    await service.claim_invite(caregiver_user_id=caregiver.id, code=second_code)

    assert len(await service.links.list_for_patient(patient_id)) == 1
    refreshed = await service.invites.get(second_invite.id)
    assert refreshed is not None and refreshed.consumed_at is not None
    claims = [
        e
        for e in service.audit._events  # type: ignore[attr-defined]
        if e.action == "caregiver_claim"
    ]
    assert claims[-1].detail == {"matched": True, "created": False, "registration": False}


async def test_rate_limited_claim_never_looks_up_the_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE non-enumeration ordering (the invite_patient mirror): the limiter fires
    BEFORE the code lookup, so a refusal cannot depend on — or leak — whether the
    probed code matches an invite."""

    class LookupCountingInvites(InMemoryCaregiverInviteRepository):
        def __init__(self) -> None:
            super().__init__()
            self.code_lookups = 0

        async def get_by_code_hash(self, code_hash: str) -> CaregiverInvite | None:
            self.code_lookups += 1
            return await super().get_by_code_hash(code_hash)

    monkeypatch.setattr(settings, "caregiver_claim_rate_limit_max", 0)  # every attempt refused
    invites = LookupCountingInvites()
    service = CaregiverService(invites=invites)
    with pytest.raises(RateLimitExceededError):
        await service.claim_invite(caregiver_user_id=uuid.uuid4(), code="PROBE-CODE-1")
    with pytest.raises(RateLimitExceededError):
        await service.registration_claim_check(email="probe@example.com", code="PROBE-CODE-2")
    assert invites.code_lookups == 0  # refused before any code was ever resolved
    actions = [e.action for e in service.audit._events]  # type: ignore[attr-defined]
    # The authenticated path audits its refusal; the anonymous registration path
    # writes nothing (no log-flood primitive for an unauthenticated client).
    assert actions == ["rate_limited"]
    assert "PROBE" not in str(service.audit._events[0].detail)  # type: ignore[attr-defined]


async def test_registration_check_denies_dead_codes_identically_and_audits() -> None:
    service = CaregiverService()
    patient_id = uuid.uuid4()
    invite, code = await service.create_invite(patient_id=patient_id, actor_id=uuid.uuid4())
    await service.invites.consume(invite.id, now=datetime.now(UTC))  # consumed -> dead

    unknown = await service.registration_claim_check(email="a@example.com", code="NOPE-NOPE-NOPE")
    consumed = await service.registration_claim_check(email="a@example.com", code=code)

    assert isinstance(unknown, ClaimDenied) and isinstance(consumed, ClaimDenied)
    assert unknown == consumed  # byte-identical refusal: unknown vs consumed vs expired
    assert unknown.reason == CODE_INVALID_DETAIL
    denials = [
        e
        for e in service.audit._events  # type: ignore[attr-defined]
        if e.action == "caregiver_claim"
    ]
    assert len(denials) == 2  # each failed guess counts against the email's budget
    for event in denials:
        assert event.detail == {"matched": False, "created": False, "registration": True}
        assert event.patient_id is None


async def test_registration_check_returns_the_invite_without_consuming_it() -> None:
    """The code is judged BEFORE the account insert but spent only at finalize — a
    409 on the email must not burn the patient's code."""
    service = CaregiverService()
    _, code = await service.create_invite(patient_id=uuid.uuid4(), actor_id=uuid.uuid4())
    outcome = await service.registration_claim_check(email="new@example.com", code=code)
    assert isinstance(outcome, CaregiverInvite)
    assert outcome.consumed_at is None  # still claimable


async def test_finalize_raises_when_the_single_use_race_was_lost() -> None:
    service = CaregiverService()
    caregiver = await _caregiver_user(service)
    invite, _code = await service.create_invite(patient_id=uuid.uuid4(), actor_id=uuid.uuid4())
    await service.invites.consume(invite.id, now=datetime.now(UTC))  # a rival claimed it
    with pytest.raises(CaregiverClaimError) as excinfo:
        await service.finalize_registration_claim(invite=invite, caregiver_user_id=caregiver.id)
    assert excinfo.value.status_code == 404
    assert excinfo.value.reason == CODE_INVALID_DETAIL


# ---------------------------------------------------------------- lifecycle rules


async def _pending_link(service: CaregiverService) -> tuple[uuid.UUID, uuid.UUID, CaregiverLink]:
    caregiver = await _caregiver_user(service, email=f"{uuid.uuid4().hex[:8]}@example.com")
    patient_id = uuid.uuid4()
    _, code = await service.create_invite(patient_id=patient_id, actor_id=uuid.uuid4())
    await service.claim_invite(caregiver_user_id=caregiver.id, code=code)
    (link,) = await service.links.list_for_patient(patient_id)
    return patient_id, caregiver.id, link


async def test_accept_activates_only_pending_links_of_this_patient() -> None:
    service = CaregiverService()
    patient_id, _, link = await _pending_link(service)
    assert (
        await service.accept_link(patient_id=uuid.uuid4(), actor_id=uuid.uuid4(), link_id=link.id)
        is None
    )  # foreign patient: 404-shaped
    accepted = await service.accept_link(
        patient_id=patient_id, actor_id=uuid.uuid4(), link_id=link.id
    )
    assert accepted is not None and accepted.status is CaregiverLinkStatus.active
    assert accepted.accepted_at is not None
    # Already active: a second accept is 404-shaped (single-fire).
    assert (
        await service.accept_link(patient_id=patient_id, actor_id=uuid.uuid4(), link_id=link.id)
        is None
    )


async def test_decline_kills_a_pending_link_for_good() -> None:
    service = CaregiverService()
    patient_id, _, link = await _pending_link(service)
    declined = await service.decline_link(
        patient_id=patient_id, actor_id=uuid.uuid4(), link_id=link.id
    )
    assert declined is not None and declined.status is CaregiverLinkStatus.revoked
    # Neither accept nor a second decline can touch it now.
    assert (
        await service.accept_link(patient_id=patient_id, actor_id=uuid.uuid4(), link_id=link.id)
        is None
    )
    assert (
        await service.decline_link(patient_id=patient_id, actor_id=uuid.uuid4(), link_id=link.id)
        is None
    )


async def test_revoke_is_idempotent_and_scoped_to_the_owner() -> None:
    service = CaregiverService()
    patient_id, _, link = await _pending_link(service)
    await service.accept_link(patient_id=patient_id, actor_id=uuid.uuid4(), link_id=link.id)
    assert (
        await service.revoke_link(patient_id=uuid.uuid4(), actor_id=uuid.uuid4(), link_id=link.id)
        is None
    )  # not theirs: 404-shaped
    first = await service.revoke_link(patient_id=patient_id, actor_id=uuid.uuid4(), link_id=link.id)
    assert first is not None and first.status is CaregiverLinkStatus.revoked
    again = await service.revoke_link(patient_id=patient_id, actor_id=uuid.uuid4(), link_id=link.id)
    assert again is not None  # quiet success
    revokes = [
        e
        for e in service.audit._events  # type: ignore[attr-defined]
        if e.action == "revoke_caregiver_link"
    ]
    assert len(revokes) == 1  # no second audit event on the idempotent re-revoke


async def test_change_scope_audits_the_transition_and_skips_noops() -> None:
    service = CaregiverService()
    patient_id, _, link = await _pending_link(service)
    changed = await service.change_scope(
        patient_id=patient_id,
        actor_id=uuid.uuid4(),
        link_id=link.id,
        scope=CaregiverScope.full,
    )
    assert changed is not None and changed.scope is CaregiverScope.full
    # A no-change PATCH is a quiet success with no audit event.
    await service.change_scope(
        patient_id=patient_id, actor_id=uuid.uuid4(), link_id=link.id, scope=CaregiverScope.full
    )
    events = [
        e
        for e in service.audit._events  # type: ignore[attr-defined]
        if e.action == "change_caregiver_scope"
    ]
    assert len(events) == 1
    assert events[0].detail == {"link_id": str(link.id), "from": "trends", "to": "full"}
    # Revoked links cannot be re-scoped.
    await service.revoke_link(patient_id=patient_id, actor_id=uuid.uuid4(), link_id=link.id)
    assert (
        await service.change_scope(
            patient_id=patient_id,
            actor_id=uuid.uuid4(),
            link_id=link.id,
            scope=CaregiverScope.trends,
        )
        is None
    )


async def test_patients_for_caregiver_skips_unaccepted_and_userless_rows() -> None:
    """The list re-judges every row through the predicate, and a link whose patient
    user vanished is skipped: rows the API cannot produce today must still never
    leak if storage ever holds them."""
    service = CaregiverService()
    caregiver = await _caregiver_user(service)
    # Pending (claimed, never accepted) — must not appear.
    await service.links.add(
        CaregiverLink(
            patient_id=uuid.uuid4(),
            caregiver_user_id=caregiver.id,
            status=CaregiverLinkStatus.pending,
            initiated_by=Initiator.patient,
        )
    )
    # Active + accepted, but no user record owns the patient id.
    await service.links.add(
        CaregiverLink(
            patient_id=uuid.uuid4(),
            caregiver_user_id=caregiver.id,
            status=CaregiverLinkStatus.active,
            accepted_at=NOW,
            initiated_by=Initiator.patient,
        )
    )
    assert await service.patients_for_caregiver(caregiver.id) == []
