"""Postgres repository implementations — async SQLAlchemy against app/models.

Each class satisfies the corresponding Protocol in this package using an
``AsyncSession`` (app/db/session.py). Methods flush (so constraints fire and
defaults populate) but do not commit: the unit of work — request handler or test —
owns the transaction boundary.

Covered by the integration tests in tests/integration/ against a real Postgres
(CI provides one); excluded from the unit-coverage gate for that reason.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.audit import AuditEvent
from app.models.capability import Actor, Capability, PatientCapability
from app.models.clinic import Clinic
from app.models.connection import ClinicConnection, ConnectionStatus
from app.models.emr_connection import EmrConnection
from app.models.observation import Observation, ObservationStatus, SourceType
from app.models.patient import Patient
from app.models.pending_auth import PendingAuthState
from app.models.secret import StoredSecret
from app.models.user import User, UserRole
from app.repositories.capability import DuplicateCapabilityKeyError
from app.repositories.clinic_connection import DuplicateLiveConnectionError
from app.repositories.emr_connection import ConnectionRecord
from app.repositories.pending_auth import PendingAuth, pending_auth_ttl
from app.repositories.user import (
    DuplicateEmailError,
    OpsAlreadyExistsError,
    OpsDeactivateOutcome,
    OpsDeactivateResult,
    PatientRecord,
    UserRecord,
)
from app.services.observation import counts_toward_analysis

# The SQL twin of the unit-tested analyzable-status predicate: derived from it, so the
# two can never drift apart.
_ANALYZABLE_STATUSES = tuple(s for s in ObservationStatus if counts_toward_analysis(s))

# One fixed bigint key for the first-ops bootstrap advisory lock (ADR-0019): with zero
# ops rows to row-lock, this transaction-scoped lock is the serialization point that
# keeps concurrent first-ops bootstraps from both inserting a "first" operator.
_OPS_BOOTSTRAP_LOCK_KEY = 190_019


class PostgresUserRepository:
    """UserRepository over the app_user table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: UserRecord) -> None:
        # One flush: the user row and its linked Patient clinical record are created
        # atomically, and the unique email index enforces uniqueness without a
        # check-then-insert race (translated to the domain error).
        if user.patient_id is not None:
            self._session.add(Patient(id=user.patient_id, display_name=user.display_name))
        self._session.add(
            User(
                id=user.id,
                email=user.email,
                password_hash=user.password_hash,
                display_name=user.display_name,
                role=user.role,
                patient_id=user.patient_id,
                clinic_id=user.clinic_id,
                active=user.active,
                disabled_at=user.disabled_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if "app_user" in str(exc.orig) and "email" in str(exc.orig):
                raise DuplicateEmailError(user.email) from exc
            raise

    async def get_by_email(self, email: str) -> UserRecord | None:
        row = await self._session.scalar(select(User).where(User.email == email))
        return None if row is None else _user_to_record(row)

    async def get_by_id(self, user_id: uuid.UUID) -> UserRecord | None:
        row = await self._session.get(User, user_id)
        return None if row is None else _user_to_record(row)

    async def get_by_patient_id(self, patient_id: uuid.UUID) -> UserRecord | None:
        row = await self._session.scalar(select(User).where(User.patient_id == patient_id))
        return None if row is None else _user_to_record(row)

    async def get_patient(self, patient_id: uuid.UUID) -> PatientRecord | None:
        row = await self._session.get(Patient, patient_id)
        if row is None:
            return None
        return PatientRecord(
            id=row.id,
            display_name=row.display_name,
            connection_mode=row.connection_mode,
            created_at=row.created_at,
        )

    async def count_with_role(self, role: UserRole, *, active_only: bool = False) -> int:
        stmt = select(func.count()).select_from(User).where(User.role == role)
        if active_only:
            stmt = stmt.where(User.active.is_(True))
        return int(await self._session.scalar(stmt) or 0)

    async def set_active(
        self, user_id: uuid.UUID, *, active: bool, disabled_at: datetime | None
    ) -> UserRecord | None:
        row = await self._session.get(User, user_id)
        if row is None:
            return None
        row.active = active
        row.disabled_at = disabled_at
        await self._session.flush()
        return _user_to_record(row)

    async def add_first_ops(self, user: UserRecord) -> None:
        # Serialize concurrent first-ops bootstraps on a transaction-scoped advisory
        # lock (there are no ops rows to row-lock yet): the loser waits here, then
        # re-reads a now-nonzero ops count and is refused. The lock releases with the
        # request transaction.
        await self._session.execute(select(func.pg_advisory_xact_lock(_OPS_BOOTSTRAP_LOCK_KEY)))
        existing = await self._session.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.ops)
        )
        if existing:
            raise OpsAlreadyExistsError(str(user.id))
        await self.add(user)

    async def deactivate_ops_guarded(
        self, user_id: uuid.UUID, *, disabled_at: datetime
    ) -> OpsDeactivateResult:
        # Lock the active-ops set FOR UPDATE so concurrent deactivations serialize: the
        # second waiter re-reads the just-committed flip (EvalPlanQual) and sees the
        # reduced set, so it cannot also remove what is now the last active operator.
        # Aggregates can't carry FOR UPDATE, so we lock the rows and count them here.
        locked = (
            await self._session.scalars(
                select(User.id)
                .where(User.role == UserRole.ops, User.active.is_(True))
                .order_by(User.id)  # deterministic lock-acquisition order (no deadlock)
                .with_for_update()
            )
        ).all()
        row = await self._session.get(User, user_id)
        if row is None or row.role is not UserRole.ops:
            return OpsDeactivateResult(OpsDeactivateOutcome.not_found, None)
        if not row.active:
            return OpsDeactivateResult(OpsDeactivateOutcome.already_inactive, _user_to_record(row))
        if len(locked) <= 1:
            return OpsDeactivateResult(OpsDeactivateOutcome.refused_last_active, None)
        row.active = False
        row.disabled_at = disabled_at
        await self._session.flush()
        return OpsDeactivateResult(OpsDeactivateOutcome.deactivated, _user_to_record(row))

    async def delete_with_patient(self, *, user_id: uuid.UUID, patient_id: uuid.UUID) -> None:
        # The mirror of add(): the auth identity and its Patient clinical record fall
        # together. The patient row goes LAST — its deletion is the statement that
        # fires audit_event's ON DELETE SET NULL (migration 0006), so the retained
        # audit history detaches in the same flush (ADR-0027).
        await self._session.execute(delete(User).where(User.id == user_id))
        await self._session.execute(delete(Patient).where(Patient.id == patient_id))
        await self._session.flush()


class PostgresClinicRepository:
    """ClinicRepository over the clinic table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, clinic: Clinic) -> Clinic:
        self._session.add(clinic)
        await self._session.flush()
        # created_at is a server default; load it so callers see the same shape the
        # in-memory implementation returns.
        await self._session.refresh(clinic)
        return clinic

    async def get(self, clinic_id: uuid.UUID) -> Clinic | None:
        return await self._session.get(Clinic, clinic_id)

    async def delete(self, clinic_id: uuid.UUID) -> None:
        row = await self._session.get(Clinic, clinic_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


class PostgresClinicConnectionRepository:
    """ClinicConnectionRepository over the clinic_connection table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, connection: ClinicConnection) -> ClinicConnection:
        # A savepoint scopes the flush: when uq_clinic_connection_live fires, only
        # this insert rolls back and the caller's transaction stays usable (the
        # invite flow still writes its audit event after absorbing the duplicate).
        try:
            async with self._session.begin_nested():
                self._session.add(connection)
                await self._session.flush()
        except IntegrityError as exc:
            if "uq_clinic_connection_live" in str(exc.orig):
                raise DuplicateLiveConnectionError(
                    connection.patient_id, connection.clinic_id
                ) from exc
            raise
        await self._session.refresh(connection)
        return connection

    async def get(self, connection_id: uuid.UUID) -> ClinicConnection | None:
        return await self._session.get(ClinicConnection, connection_id)

    async def list_for_patient(
        self, patient_id: uuid.UUID, *, for_share: bool = False
    ) -> list[ClinicConnection]:
        stmt = (
            select(ClinicConnection)
            .where(ClinicConnection.patient_id == patient_id)
            .order_by(ClinicConnection.created_at)
        )
        if for_share:
            # FOR SHARE: blocks a concurrent consent grant's row UPDATE until this
            # transaction ends, closing the authority-check TOCTOU (ADR-0013).
            stmt = stmt.with_for_update(read=True)
        return list((await self._session.scalars(stmt)).all())

    async def list_active_for_clinic(self, clinic_id: uuid.UUID) -> list[ClinicConnection]:
        stmt = (
            select(ClinicConnection)
            .where(
                ClinicConnection.clinic_id == clinic_id,
                ClinicConnection.status == ConnectionStatus.active,
            )
            .order_by(ClinicConnection.created_at)
        )
        return list((await self._session.scalars(stmt)).all())

    async def update(self, connection: ClinicConnection) -> None:
        row = await self._session.get(ClinicConnection, connection.id)
        if row is None:
            raise LookupError(f"clinic_connection {connection.id} does not exist")
        row.status = connection.status
        row.consent_granted_at = connection.consent_granted_at
        row.revoked_at = connection.revoked_at
        await self._session.flush()

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(ClinicConnection).where(ClinicConnection.patient_id == patient_id)
        )
        await self._session.flush()


class PostgresEmrConnectionRepository:
    """EmrConnectionRepository over the emr_connection table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, connection: ConnectionRecord) -> None:
        self._session.add(
            EmrConnection(
                id=connection.id,
                patient_id=connection.patient_id,
                fhir_base=connection.fhir_base,
                provider_name=connection.provider_name,
                status=connection.status,
                granted_scope=connection.granted_scope,
                patient_fhir_id=connection.patient_fhir_id,
                token_ref=connection.token_ref,
                token_expires_at=connection.token_expires_at,
                revoked_at=connection.revoked_at,
            )
        )
        await self._session.flush()

    async def get(self, connection_id: uuid.UUID) -> ConnectionRecord | None:
        row = await self._session.get(EmrConnection, connection_id)
        return None if row is None else _connection_to_record(row)

    async def update(self, connection: ConnectionRecord) -> None:
        row = await self._session.get(EmrConnection, connection.id)
        if row is None:
            raise LookupError(f"emr_connection {connection.id} does not exist")
        row.status = connection.status
        row.granted_scope = connection.granted_scope
        row.patient_fhir_id = connection.patient_fhir_id
        row.token_ref = connection.token_ref
        row.token_expires_at = connection.token_expires_at
        row.revoked_at = connection.revoked_at
        await self._session.flush()

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[ConnectionRecord]:
        stmt = (
            select(EmrConnection)
            .where(EmrConnection.patient_id == patient_id)
            .order_by(EmrConnection.created_at)
        )
        return [_connection_to_record(row) for row in (await self._session.scalars(stmt)).all()]

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        # Callers (ADR-0027) have already removed the pending_auth rows referencing
        # these connections and purged their vaulted secrets via SecretStore.delete.
        await self._session.execute(
            delete(EmrConnection).where(EmrConnection.patient_id == patient_id)
        )
        await self._session.flush()


class PostgresObservationRepository:
    """ObservationRepository over the observation table (append-only)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, observation: Observation) -> Observation:
        self._session.add(observation)
        await self._session.flush()
        return observation

    async def add_if_absent(self, observation: Observation) -> bool:
        # A savepoint scopes the flush: when uq_observation_patient_import_key fires (a
        # concurrent pull already imported this source record), only THIS insert rolls
        # back and the caller's transaction stays usable — the ingest handler still writes
        # its batch audit event and returns a clean skip instead of a 500 (sweep #3). Any
        # other IntegrityError (e.g. an FK violation) is a real fault and re-raises.
        try:
            async with self._session.begin_nested():
                self._session.add(observation)
                await self._session.flush()
        except IntegrityError as exc:
            if "uq_observation_patient_import_key" in str(exc.orig):
                return False
            raise
        return True

    async def list_for_patient(
        self,
        patient_id: uuid.UUID,
        code: str | None = None,
        since: datetime | None = None,
        limit: int | None = None,
        offset: int = 0,
        newest_first: bool = False,
        source: SourceType | None = None,
    ) -> list[Observation]:
        # "Current" records only: exclude rows superseded by a newer row's revises_id
        # (corrections replace their target in the analyzable dataset).
        newer = aliased(Observation)
        order = Observation.effective_at.desc() if newest_first else Observation.effective_at
        stmt = (
            select(Observation)
            .where(
                Observation.patient_id == patient_id,
                Observation.status.in_(_ANALYZABLE_STATUSES),
                ~exists(
                    select(newer.id).where(
                        newer.patient_id == patient_id, newer.revises_id == Observation.id
                    )
                ),
            )
            .order_by(order)
        )
        if code is not None:
            stmt = stmt.where(Observation.code == code)
        if source is not None:
            # Backed by ix_observation_patient_source_time — the medication full-history
            # fold's source-scoped read (ADR-0045 P2).
            stmt = stmt.where(Observation.source == source)
        if since is not None:
            stmt = stmt.where(Observation.effective_at >= since)
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list((await self._session.scalars(stmt)).all())

    async def existing_import_keys(self, patient_id: uuid.UUID, import_keys: list[str]) -> set[str]:
        if not import_keys:
            return set()
        stmt = select(Observation.import_key).where(
            Observation.patient_id == patient_id,
            Observation.import_key.in_(import_keys),
        )
        return {key for key in (await self._session.scalars(stmt)).all() if key is not None}

    async def count_for_patient(self, patient_id: uuid.UUID, code: str | None = None) -> int:
        newer = aliased(Observation)
        stmt = select(func.count(Observation.id)).where(
            Observation.patient_id == patient_id,
            Observation.status.in_(_ANALYZABLE_STATUSES),
            ~exists(
                select(newer.id).where(
                    newer.patient_id == patient_id, newer.revises_id == Observation.id
                )
            ),
        )
        if code is not None:
            stmt = stmt.where(Observation.code == code)
        return int(await self._session.scalar(stmt) or 0)

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        # Clear the self-referencing supersede FK first: a correction row and its
        # target both belong to this patient (cross-patient supersession does not
        # exist), so nulling revises_id lets one DELETE take the whole chain without
        # ordering rows parent-before-child (ADR-0027).
        await self._session.execute(
            update(Observation).where(Observation.patient_id == patient_id).values(revises_id=None)
        )
        await self._session.execute(delete(Observation).where(Observation.patient_id == patient_id))
        await self._session.flush()


class PostgresAuditEventRepository:
    """AuditEventRepository over the audit_event table (append-only)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: AuditEvent) -> AuditEvent:
        self._session.add(event)
        await self._session.flush()
        # occurred_at is a server default; load it so callers see the same shape the
        # in-memory implementation returns.
        await self._session.refresh(event)
        return event

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.patient_id == patient_id)
            .order_by(AuditEvent.occurred_at)
        )
        return list((await self._session.scalars(stmt)).all())

    async def count_actor_events_since(
        self, *, actor_id: uuid.UUID, action: str, since: datetime
    ) -> int:
        # The sliding-window rate-limit counter (ADR-0017); indexed point-range read
        # via ix_audit_event_actor_action_time.
        stmt = select(func.count(AuditEvent.id)).where(
            AuditEvent.actor_id == actor_id,
            AuditEvent.action == action,
            AuditEvent.occurred_at >= since,
        )
        return int(await self._session.scalar(stmt) or 0)

    async def detach_patient(self, patient_id: uuid.UUID) -> None:
        # Defense in depth only: the ON DELETE SET NULL FK (migration 0006) has
        # already detached every retained row when the patient row was deleted, so
        # this UPDATE matches nothing in Postgres. The in-memory twin is where the
        # detach actually happens (no FK to do it there).
        await self._session.execute(
            update(AuditEvent).where(AuditEvent.patient_id == patient_id).values(patient_id=None)
        )
        await self._session.flush()


def encrypt_tokens(fernet: Fernet, tokens: dict[str, str]) -> bytes:
    """Serialize + encrypt token material for the `secret` table (ADR-0017)."""
    return fernet.encrypt(json.dumps(tokens).encode())


def decrypt_tokens(fernet: Fernet, ciphertext: bytes) -> dict[str, str] | None:
    """Invert encrypt_tokens; None when the key cannot open the ciphertext (rotated
    or wrong key) — the caller treats that exactly like a missing secret, fail closed."""
    try:
        raw = fernet.decrypt(ciphertext)
    except InvalidToken:
        return None
    loaded: dict[str, str] = json.loads(raw.decode())
    return loaded


class PostgresSecretStore:
    """SecretStore over the `secret` table — Fernet-encrypted at rest (ADR-0017).

    Constructed per request (deps wiring) ONLY when settings.secret_store_key is
    configured; plaintext secret material never reaches the database.
    """

    def __init__(self, session: AsyncSession, fernet: Fernet) -> None:
        self._session = session
        self._fernet = fernet

    async def put(self, tokens: dict[str, str]) -> str:
        ref = f"secret::{uuid.uuid4()}"
        self._session.add(StoredSecret(ref=ref, ciphertext=encrypt_tokens(self._fernet, tokens)))
        await self._session.flush()
        return ref

    async def get(self, ref: str) -> dict[str, str] | None:
        row = await self._session.get(StoredSecret, ref)
        if row is None:
            return None
        return decrypt_tokens(self._fernet, row.ciphertext)

    async def delete(self, ref: str) -> None:
        # Revocation/re-link removes the ciphertext row itself (ADR-0017): a revoked
        # or superseded grant must not stay recoverable from a DB dump plus the key.
        await self._session.execute(delete(StoredSecret).where(StoredSecret.ref == ref))
        await self._session.flush()


class PostgresPendingAuthStore:
    """PendingAuthStore over the `pending_auth` table (ADR-0017).

    Single-use is enforced by the database, not by check-then-delete: `consume` is
    one DELETE ... RETURNING, so of two callbacks racing on the same state the second
    waits on the row lock and then deletes nothing — exactly one wins.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def put(self, state: str, pending: PendingAuth, *, now: datetime) -> None:
        # Opportunistic purge: expired handshakes are dead weight and must never be
        # honored anyway; each put sweeps them (indexed by ix_pending_auth_expires_at).
        await self._session.execute(
            delete(PendingAuthState).where(PendingAuthState.expires_at <= now)
        )
        self._session.add(
            PendingAuthState(
                state=state,
                connection_id=pending.connection_id,
                code_verifier=pending.code_verifier,
                token_endpoint=pending.token_endpoint,
                expires_at=now + pending_auth_ttl(),
            )
        )
        await self._session.flush()

    async def consume(self, state: str, *, now: datetime) -> PendingAuth | None:
        stmt = (
            delete(PendingAuthState)
            .where(PendingAuthState.state == state)
            .returning(
                PendingAuthState.connection_id,
                PendingAuthState.code_verifier,
                PendingAuthState.token_endpoint,
                PendingAuthState.expires_at,
            )
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None or row.expires_at <= now:
            # Unknown, already consumed, or expired (the expired row is now purged —
            # deleting before judging expiry keeps replays of stale states silent).
            return None
        return PendingAuth(
            connection_id=row.connection_id,
            code_verifier=row.code_verifier,
            token_endpoint=row.token_endpoint,
        )

    async def delete_for_connections(self, connection_ids: list[uuid.UUID]) -> None:
        if not connection_ids:
            return
        await self._session.execute(
            delete(PendingAuthState).where(PendingAuthState.connection_id.in_(connection_ids))
        )
        await self._session.flush()


class PostgresCapabilityRepository:
    """CapabilityRepository over the capability table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_key(self, key: str) -> Capability | None:
        stmt = select(Capability).where(Capability.key == key)
        return (await self._session.scalars(stmt)).first()

    async def add(self, capability: Capability) -> Capability:
        # A savepoint scopes the flush: when the unique key constraint fires, only
        # this insert rolls back and the caller's transaction stays usable (the lazy
        # get-or-create in CapabilityService re-fetches the winner's row).
        try:
            async with self._session.begin_nested():
                self._session.add(capability)
                await self._session.flush()
        except IntegrityError as exc:
            if "capability_key_key" in str(exc.orig):
                raise DuplicateCapabilityKeyError(capability.key) from exc
            raise
        await self._session.refresh(capability)
        return capability

    async def list(self) -> list[Capability]:
        stmt = select(Capability).order_by(Capability.key)
        return list((await self._session.scalars(stmt)).all())


class PostgresPatientCapabilityRepository:
    """PatientCapabilityRepository over the patient_capability table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, patient_id: uuid.UUID, capability_id: uuid.UUID
    ) -> PatientCapability | None:
        stmt = select(PatientCapability).where(
            PatientCapability.patient_id == patient_id,
            PatientCapability.capability_id == capability_id,
        )
        return (await self._session.scalars(stmt)).first()

    async def upsert(
        self,
        *,
        patient_id: uuid.UUID,
        capability_id: uuid.UUID,
        active: bool,
        set_by: Actor,
        expires_at: datetime | None,
    ) -> PatientCapability:
        # Insert-first, mirroring PostgresClinicConnectionRepository.add: the
        # savepoint absorbs uq_patient_capability (whether the row pre-existed or a
        # concurrent upsert won the race) and the update path takes over, so exactly
        # one row per pair survives and the caller's transaction stays usable.
        row = PatientCapability(
            patient_id=patient_id,
            capability_id=capability_id,
            active=active,
            set_by=set_by,
            expires_at=expires_at,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
        except IntegrityError as exc:
            if "uq_patient_capability" not in str(exc.orig):
                raise
            existing = await self.get(patient_id, capability_id)
            assert existing is not None  # the fired constraint guarantees the row
            existing.active = active
            existing.set_by = set_by
            existing.expires_at = expires_at
            await self._session.flush()
            return existing
        await self._session.refresh(row)
        return row

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[PatientCapability]:
        stmt = (
            select(PatientCapability)
            .where(PatientCapability.patient_id == patient_id)
            .order_by(PatientCapability.created_at)
        )
        return list((await self._session.scalars(stmt)).all())

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(PatientCapability).where(PatientCapability.patient_id == patient_id)
        )
        await self._session.flush()


def _user_to_record(row: User) -> UserRecord:
    return UserRecord(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        display_name=row.display_name,
        role=row.role,
        patient_id=row.patient_id,
        clinic_id=row.clinic_id,
        active=row.active,
        disabled_at=row.disabled_at,
        created_at=row.created_at,
    )


def _connection_to_record(row: EmrConnection) -> ConnectionRecord:
    return ConnectionRecord(
        id=row.id,
        patient_id=row.patient_id,
        fhir_base=row.fhir_base,
        provider_name=row.provider_name,
        status=row.status,
        granted_scope=row.granted_scope,
        patient_fhir_id=row.patient_fhir_id,
        token_ref=row.token_ref,
        token_expires_at=row.token_expires_at,
        revoked_at=row.revoked_at,
    )
