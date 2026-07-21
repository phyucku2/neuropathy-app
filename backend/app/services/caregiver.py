"""Caregiver service — invite, claim, double opt-in, scope, revoke (ADR-0047).

Phase A of the Caregiver Companion: relationship & consent plus read surfaces only.
Storage lives behind the injected repositories (in-memory defaults for unit tests
and DB-less development; Postgres in deployment). The invariants live here, not in
routes, mirroring services/clinic.py:

- **Acceptance gates every caregiver read.** `_may_caregiver_read` is the single
  predicate behind the caregiver's patient list and both per-patient views: the link
  must be active AND carry the patient's explicit acceptance (`accepted_at`), and
  full-scope surfaces additionally require scope == full. Callers translate a
  failing predicate to a 404 so unlinked, non-accepted, revoked, and
  insufficient-scope records are all indistinguishable from nonexistent ones.
- **Claims never enumerate codes.** The rate limiter fires FIRST (before the code is
  even hashed and looked up), the lookup runs for valid and invalid codes alike, and
  the authenticated-claim response is byte-identical whether or not the code
  matched. Audited refusals that must commit are RETURNED, never raised
  (docs/lessons.md "return don't raise").
- **Revocation is never blockable.** No capability toggle or kill switch gates any
  path here (the AccountDeletionService posture); revoke is instant and idempotent.

Invite codes are high-entropy, patient-generated, 7-day, single-use. Only the sha256
hex is stored (the stdlib-hash idiom services/auth.py uses for throttle sentinels);
the plaintext is returned exactly once at creation. Every lifecycle transition is
audited with refs/counts only — never emails or codes (CLAUDE.md §5).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.caregiver import (
    CaregiverInvite,
    CaregiverLink,
    CaregiverLinkStatus,
    CaregiverScope,
)
from app.models.connection import Initiator
from app.models.user import UserRole
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.caregiver import (
    CaregiverInviteRepository,
    CaregiverLinkRepository,
    DuplicateLiveCaregiverLinkError,
    InMemoryCaregiverInviteRepository,
    InMemoryCaregiverLinkRepository,
)
from app.repositories.emr_clinical_note import (
    EmrClinicalNoteRepository,
    InMemoryEmrClinicalNoteRepository,
)
from app.repositories.observation import InMemoryObservationRepository, ObservationRepository
from app.repositories.user import InMemoryUserRepository, UserRecord, UserRepository
from app.services.rate_limit import RateLimitExceededError, SlidingWindowRateLimiter

__all__ = [
    "CLAIM_ACCEPTED_DETAIL",
    "CLAIM_RATE_LIMITED_DETAIL",
    "CODE_INVALID_DETAIL",
    "INVITE_TTL",
    "CaregiverClaimError",
    "CaregiverService",
    "ClaimDenied",
    "caregiver_claim_rate_limiter",
    "format_invite_code",
    "hash_invite_code",
    "registration_throttle_actor_id",
]

# Patient-generated invite codes live this long (ADR-0047); expired codes are dead.
INVITE_TTL = timedelta(days=7)

# Read-aloud-friendly alphabet: no 0/O, 1/I/L ambiguity. 12 chars ≈ 59 bits — far
# beyond guessable under the claim throttle, short enough to relay over the phone.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 12
_CODE_GROUP = 4

# One fixed sentence for EVERY authenticated-claim outcome — the response must never
# reveal whether the code matched anything (no code enumeration).
CLAIM_ACCEPTED_DETAIL = (
    "If this code is valid, your request is now waiting for the patient's approval."
)

# One message for unknown, expired, consumed, and cancelled codes alike — the
# registration path must refuse without revealing WHICH way the code was dead.
CODE_INVALID_DETAIL = "That code didn't work. Check it, or ask for a new code."

# Over the claim budget: friendly, PHI-free, and deliberately the SAME for a valid
# and an invalid code — a 429 carries zero information about the code probed.
CLAIM_RATE_LIMITED_DETAIL = "Too many attempts right now — please try again in a little while."

# Registration-claim throttle sentinels (the login-throttle pattern, §1B C5): the
# unauthenticated registration path keys its budget on a uuid5 of the normalized-email
# hash — deterministic per email, one-way, never the raw address.
_CLAIM_THROTTLE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "urn:neuropathy-app:caregiver-claim-throttle"
)


def registration_throttle_actor_id(email: str) -> uuid.UUID:
    """The non-enumerating registration-claim sentinel: uuid5 of the normalized-email
    hash, mirroring login_throttle_actor_id (services/auth.py)."""
    digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    return uuid.uuid5(_CLAIM_THROTTLE_NAMESPACE, digest)


def normalize_invite_code(code: str) -> str:
    """Case/format-insensitive: what the patient reads aloud must claim regardless of
    how the caregiver types it (dashes, spaces, lowercase)."""
    return code.strip().upper().replace("-", "").replace(" ", "")


def hash_invite_code(code: str) -> str:
    """sha256 hex of the normalized code — the ONLY form ever stored (ADR-0047)."""
    return hashlib.sha256(normalize_invite_code(code).encode()).hexdigest()


def generate_invite_code() -> str:
    """A fresh high-entropy code from the read-aloud alphabet (unformatted)."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def format_invite_code(code: str) -> str:
    """Group the code for reading aloud: XXXX-XXXX-XXXX."""
    normalized = normalize_invite_code(code)
    groups = [normalized[i : i + _CODE_GROUP] for i in range(0, len(normalized), _CODE_GROUP)]
    return "-".join(groups)


def caregiver_claim_rate_limiter(counter: AuditEventRepository) -> SlidingWindowRateLimiter:
    """The settings-driven claim limiter (ADR-0047, the ADR-0017 sliding-window
    pattern), counting 'caregiver_claim' audit events — one per attempt that reached
    the code lookup, matched or not. Over-budget attempts are refused BEFORE the code
    is hashed or looked up, so a refusal can never depend on — or reveal — whether
    the probed code matches an invite."""
    return SlidingWindowRateLimiter(
        counter=counter,
        action="caregiver_claim",
        max_events=settings.caregiver_claim_rate_limit_max,
        window=timedelta(seconds=settings.caregiver_claim_rate_limit_window_seconds),
    )


class CaregiverClaimError(Exception):
    """Claim-flow refusal the route layer maps to an HTTP response.

    Raised ONLY on paths that have written nothing (e.g. the registration finalize
    losing the single-use race after the account insert — the raise rolls the whole
    request transaction back in Postgres mode), so the resulting HTTPException has
    no audit write to lose.
    """

    def __init__(self, reason: str, status_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


@dataclass(frozen=True)
class ClaimDenied:
    """Audited claim refusal the route must RETURN as a response, never raise: its
    'caregiver_claim' audit event — the very row the claim throttle counts — has to
    commit with the request transaction, and a raised HTTPException would roll it
    back (docs/lessons.md "return don't raise")."""

    reason: str
    status_code: int


@dataclass
class CaregiverService:
    invites: CaregiverInviteRepository = field(default_factory=InMemoryCaregiverInviteRepository)
    links: CaregiverLinkRepository = field(default_factory=InMemoryCaregiverLinkRepository)
    users: UserRepository = field(default_factory=InMemoryUserRepository)
    observations: ObservationRepository = field(default_factory=InMemoryObservationRepository)
    # The full-scope caregiver visit-summary renders the patient's EMR clinical-note
    # metadata section too — the SAME assembly the clinic surface uses (ADR-0045).
    clinical_notes: EmrClinicalNoteRepository = field(
        default_factory=InMemoryEmrClinicalNoteRepository
    )
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)

    # ---------------------------------------------------------------- read predicate

    def _may_caregiver_read(
        self, link: CaregiverLink, *, now: datetime, require_full: bool = False
    ) -> bool:
        """THE caregiver-read predicate (ADR-0047): the link must be active AND carry
        the patient's explicit acceptance (double opt-in); full-scope surfaces
        additionally require scope == full. One predicate feeds the caregiver's
        patient list and both per-patient views, so they can never diverge — revoking
        drops the patient from every caregiver surface at once.

        DELIBERATE divergence from `_may_read_patient` (services/clinic.py): the
        clinician predicate additionally ANDs the patient's `share_with_clinic`
        capability toggle (ADR-0020), which is CLINIC-grantee-specific. For a
        caregiver the link acceptance IS the consent — the ADR's "same server-side
        access predicate" means the same primitive and discipline, not the clinic
        toggle — so this predicate gates on the link alone and never reads
        share_with_clinic. `now` is injected for parity/testability (links carry no
        expiry today)."""
        del now  # no time-based term yet; kept for signature parity with the clinic gate
        if link.status is not CaregiverLinkStatus.active or link.accepted_at is None:
            return False
        return not require_full or link.scope is CaregiverScope.full

    # ---------------------------------------------------------------- patient: invites

    async def create_invite(
        self, *, patient_id: uuid.UUID, actor_id: uuid.UUID
    ) -> tuple[CaregiverInvite, str]:
        """Generate a fresh single-use invite code for this patient (ADR-0047).

        Only the sha256 hex is stored; the formatted plaintext is returned exactly
        once — there is no re-read path. Audited with references only, never the code.
        """
        now = datetime.now(UTC)
        code = generate_invite_code()
        invite = await self.invites.add(
            CaregiverInvite(
                patient_id=patient_id,
                code_hash=hash_invite_code(code),
                expires_at=now + INVITE_TTL,
            )
        )
        await self.audit.add(
            AuditEvent(
                actor_id=actor_id,
                actor_role=UserRole.patient.value,
                action="create_caregiver_invite",
                patient_id=patient_id,
                # Reference only — NEVER the code or its hash (the hash verifies claims).
                detail={"invite_id": str(invite.id)},
            )
        )
        return invite, format_invite_code(code)

    async def list_open_invites(self, patient_id: uuid.UUID) -> list[CaregiverInvite]:
        """The patient's still-claimable invites: not consumed, cancelled, or expired."""
        now = datetime.now(UTC)
        return [
            invite
            for invite in await self.invites.list_for_patient(patient_id)
            if self._invite_open(invite, now=now)
        ]

    @staticmethod
    def _invite_open(invite: CaregiverInvite, *, now: datetime) -> bool:
        return (
            invite.consumed_at is None and invite.cancelled_at is None and invite.expires_at > now
        )

    async def cancel_invite(
        self, *, patient_id: uuid.UUID, actor_id: uuid.UUID, invite_id: uuid.UUID
    ) -> CaregiverInvite | None:
        """Cancel the patient's own invite: the code can never be claimed again.

        Idempotent-safe — cancelling an already-dead (cancelled or consumed) invite
        is a quiet success (no second audit event). None (-> 404) for other
        patients' invites, mirroring revoke_connection's ownership posture.
        """
        invite = await self.invites.get(invite_id)
        if invite is None or invite.patient_id != patient_id:
            return None
        if invite.cancelled_at is not None or invite.consumed_at is not None:
            return invite
        invite.cancelled_at = datetime.now(UTC)
        await self.invites.update(invite)
        await self.audit.add(
            AuditEvent(
                actor_id=actor_id,
                actor_role=UserRole.patient.value,
                action="cancel_caregiver_invite",
                patient_id=patient_id,
                detail={"invite_id": str(invite_id)},
            )
        )
        return invite

    # ---------------------------------------------------------------- caregiver: claims

    async def claim_invite(self, *, caregiver_user_id: uuid.UUID, code: str) -> None:
        """An AUTHENTICATED caregiver claims a code (their second, third, ... patient).

        Deliberately returns nothing: the route answers 202 with a byte-identical
        body whether or not the code matched — the caregiver learns the outcome only
        when (and if) the patient accepts and the link appears in their patient
        list, so a claim probe reveals nothing about any code (non-enumeration,
        the invite_patient posture). Rate limiting fires FIRST, before the code is
        hashed or looked up; the refusal is audited with counts only, never the code.
        """
        now = datetime.now(UTC)
        if not await caregiver_claim_rate_limiter(self.audit).allow(caregiver_user_id, now=now):
            await self.audit.add(
                AuditEvent(
                    actor_id=caregiver_user_id,
                    actor_role=UserRole.caregiver.value,
                    action="rate_limited",
                    patient_id=None,
                    # Counts/config only — the probed code was never even hashed.
                    detail={
                        "surface": "caregiver_claim",
                        "limit": settings.caregiver_claim_rate_limit_max,
                        "window_seconds": settings.caregiver_claim_rate_limit_window_seconds,
                    },
                )
            )
            raise RateLimitExceededError
        invite = await self.invites.get_by_code_hash(hash_invite_code(code))
        matched = invite is not None and self._invite_open(invite, now=now)
        created = False
        patient_id: uuid.UUID | None = None
        if matched:
            assert invite is not None  # narrowed by `matched`
            consumed, created = await self._consume_and_link(
                invite=invite, caregiver_user_id=caregiver_user_id, now=now
            )
            matched = consumed
            patient_id = invite.patient_id if consumed else None
        await self.audit.add(
            AuditEvent(
                actor_id=caregiver_user_id,
                actor_role=UserRole.caregiver.value,
                action="caregiver_claim",
                patient_id=patient_id,
                # References/flags only — never the code (audit contract).
                detail={"matched": matched, "created": created, "registration": False},
            )
        )

    async def registration_claim_check(
        self, *, email: str, code: str
    ) -> ClaimDenied | CaregiverInvite:
        """Phase 1 of caregiver self-registration: throttle, then judge the code —
        BEFORE any account is created (self-registration ONLY with a valid code).

        Over the budget raises RateLimitExceededError with nothing written (the
        route maps it to a 429 that reveals nothing about the code). A dead code —
        unknown, expired, consumed, cancelled, all indistinguishable — writes the
        audited 'caregiver_claim' refusal (the throttle's counter) and RETURNS a
        ClaimDenied the route must render, never raise. A valid code returns the
        invite untouched; the caller creates the account and then finalizes.
        """
        now = datetime.now(UTC)
        actor = registration_throttle_actor_id(email)
        if not await caregiver_claim_rate_limiter(self.audit).allow(actor, now=now):
            raise RateLimitExceededError
        invite = await self.invites.get_by_code_hash(hash_invite_code(code))
        if invite is None or not self._invite_open(invite, now=now):
            # The audited refusal IS the throttle counter (sentinel actor, counts
            # only): failed guesses spend the email's budget; successes never count.
            await self.audit.add(
                AuditEvent(
                    actor_id=actor,
                    actor_role="system",
                    action="caregiver_claim",
                    patient_id=None,
                    detail={"matched": False, "created": False, "registration": True},
                )
            )
            return ClaimDenied(CODE_INVALID_DETAIL, status_code=404)
        return invite

    async def finalize_registration_claim(
        self, *, invite: CaregiverInvite, caregiver_user_id: uuid.UUID
    ) -> None:
        """Phase 2: the account exists — consume the code, create the pending link,
        audit. Raises CaregiverClaimError if the single-use consume was lost to a
        concurrent claim between check and finalize (the raise rolls the just-created
        account back with the request transaction in Postgres mode)."""
        now = datetime.now(UTC)
        consumed, created = await self._consume_and_link(
            invite=invite, caregiver_user_id=caregiver_user_id, now=now
        )
        if not consumed:
            raise CaregiverClaimError(CODE_INVALID_DETAIL, status_code=404)
        await self.audit.add(
            AuditEvent(
                actor_id=caregiver_user_id,
                actor_role=UserRole.caregiver.value,
                action="caregiver_claim",
                patient_id=invite.patient_id,
                detail={"matched": True, "created": created, "registration": True},
            )
        )

    async def _consume_and_link(
        self, *, invite: CaregiverInvite, caregiver_user_id: uuid.UUID, now: datetime
    ) -> tuple[bool, bool]:
        """Single-use consume + pending-link insert; (consumed, link_created).

        The consume is atomic in storage (conditional UPDATE / no-await check-set),
        so of two racing claims exactly one proceeds. A pre-existing live link for
        the pair is absorbed exactly like invite_patient absorbs its duplicate: the
        code is still spent, no second link appears, and the audit records
        created=False."""
        if not await self.invites.consume(invite.id, now=now):
            return False, False
        existing = await self.links.list_for_caregiver(caregiver_user_id)
        created = False
        if not any(
            link.patient_id == invite.patient_id and link.status is not CaregiverLinkStatus.revoked
            for link in existing
        ):
            try:
                await self.links.add(
                    CaregiverLink(
                        patient_id=invite.patient_id,
                        caregiver_user_id=caregiver_user_id,
                        scope=CaregiverScope.trends,
                        status=CaregiverLinkStatus.pending,
                        initiated_by=Initiator.patient,
                    )
                )
                created = True
            except DuplicateLiveCaregiverLinkError:
                # A concurrent claim won the race; absorbing it keeps the response
                # identical and the audit trail truthful.
                created = False
        return True, created

    # ---------------------------------------------------------------- patient: links

    async def list_links_for_patient(
        self, patient_id: uuid.UUID
    ) -> list[tuple[CaregiverLink, UserRecord | None]]:
        """One patient's caregiver links with the caregiver accounts, oldest first."""
        rows = await self.links.list_for_patient(patient_id)
        return [(link, await self.users.get_by_id(link.caregiver_user_id)) for link in rows]

    async def accept_link(
        self, *, patient_id: uuid.UUID, actor_id: uuid.UUID, link_id: uuid.UUID
    ) -> CaregiverLink | None:
        """The PATIENT accepts a pending claim — the double opt-in's second step;
        only now may data become visible (ADR-0047).

        None (-> 404) unless the link exists, belongs to THIS patient, and is still
        pending — acceptance can never resurrect a revoked link or double-fire.
        """
        link = await self.links.get(link_id)
        if (
            link is None
            or link.patient_id != patient_id
            or link.status is not CaregiverLinkStatus.pending
        ):
            return None
        link.accepted_at = datetime.now(UTC)
        link.status = CaregiverLinkStatus.active
        await self.links.update(link)
        await self.audit.add(
            AuditEvent(
                actor_id=actor_id,
                actor_role=UserRole.patient.value,
                action="accept_caregiver_link",
                patient_id=patient_id,
                detail={"link_id": str(link_id), "scope": link.scope.value},
            )
        )
        return link

    async def decline_link(
        self, *, patient_id: uuid.UUID, actor_id: uuid.UUID, link_id: uuid.UUID
    ) -> CaregiverLink | None:
        """The PATIENT declines a pending claim: the link dies (revoked) without ever
        having been readable. None (-> 404) unless pending and theirs."""
        link = await self.links.get(link_id)
        if (
            link is None
            or link.patient_id != patient_id
            or link.status is not CaregiverLinkStatus.pending
        ):
            return None
        link.revoked_at = datetime.now(UTC)
        link.status = CaregiverLinkStatus.revoked
        await self.links.update(link)
        await self.audit.add(
            AuditEvent(
                actor_id=actor_id,
                actor_role=UserRole.patient.value,
                action="decline_caregiver_link",
                patient_id=patient_id,
                detail={"link_id": str(link_id)},
            )
        )
        return link

    async def change_scope(
        self,
        *,
        patient_id: uuid.UUID,
        actor_id: uuid.UUID,
        link_id: uuid.UUID,
        scope: CaregiverScope,
    ) -> CaregiverLink | None:
        """The PATIENT retargets a live link's scope (trends <-> full) — a patient
        action, effective on the caregiver's very next read. Works on pending links
        too (choose the scope before accepting); never on revoked ones. A no-change
        PATCH is a quiet success (no audit event). None (-> 404) otherwise."""
        link = await self.links.get(link_id)
        if (
            link is None
            or link.patient_id != patient_id
            or link.status is CaregiverLinkStatus.revoked
        ):
            return None
        if link.scope is scope:
            return link
        previous = link.scope
        link.scope = scope
        await self.links.update(link)
        await self.audit.add(
            AuditEvent(
                actor_id=actor_id,
                actor_role=UserRole.patient.value,
                action="change_caregiver_scope",
                patient_id=patient_id,
                detail={
                    "link_id": str(link_id),
                    "from": previous.value,
                    "to": scope.value,
                },
            )
        )
        return link

    async def revoke_link(
        self, *, patient_id: uuid.UUID, actor_id: uuid.UUID, link_id: uuid.UUID
    ) -> CaregiverLink | None:
        """The PATIENT revokes a link: data flow stops immediately (ADR-0047 —
        "revocation is never blockable"; deliberately NO capability/kill-switch gate
        anywhere in this path, the AccountDeletionService posture).

        Idempotent-safe — revoking an already-revoked link is a quiet success (no
        second audit event). None (-> 404) for other patients' links.
        """
        link = await self.links.get(link_id)
        if link is None or link.patient_id != patient_id:
            return None
        if link.status is CaregiverLinkStatus.revoked:
            return link
        link.revoked_at = datetime.now(UTC)
        link.status = CaregiverLinkStatus.revoked
        await self.links.update(link)
        await self.audit.add(
            AuditEvent(
                actor_id=actor_id,
                actor_role=UserRole.patient.value,
                action="revoke_caregiver_link",
                patient_id=patient_id,
                detail={"link_id": str(link_id)},
            )
        )
        return link

    # ---------------------------------------------------------------- caregiver: reads

    async def patients_for_caregiver(
        self, caregiver_user_id: uuid.UUID
    ) -> list[tuple[CaregiverLink, UserRecord]]:
        """The caregiver's readable patients: ONLY accepted, non-revoked links —
        judged by the one `_may_caregiver_read` predicate, never re-derived here. A
        patient revoking (or never accepting) simply never appears."""
        now = datetime.now(UTC)
        entries: list[tuple[CaregiverLink, UserRecord]] = []
        for link in await self.links.list_for_caregiver(caregiver_user_id):
            if not self._may_caregiver_read(link, now=now):
                continue
            user = await self.users.get_by_patient_id(link.patient_id)
            if user is not None:
                entries.append((link, user))
        return entries

    async def link_for_caregiver(
        self, *, caregiver_user_id: uuid.UUID, patient_id: uuid.UUID, require_full: bool = False
    ) -> CaregiverLink | None:
        """THE access gate for /caregiver/patients/{id}/*: the accepted link that
        permits this caregiver to read this patient at the required scope, or None
        (routes answer 404 — unknown, unlinked, non-accepted, revoked, and
        insufficient-scope must ALL be indistinguishable from nonexistent)."""
        now = datetime.now(UTC)
        for link in await self.links.list_for_caregiver(caregiver_user_id):
            if link.patient_id == patient_id and self._may_caregiver_read(
                link, now=now, require_full=require_full
            ):
                return link
        return None
