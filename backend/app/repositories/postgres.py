"""Postgres repository implementations — async SQLAlchemy against app/models.

Each class satisfies the corresponding Protocol in this package using an
``AsyncSession`` (app/db/session.py). Methods flush (so constraints fire and
defaults populate) but do not commit: the unit of work — request handler or test —
owns the transaction boundary.

Covered by the integration tests in tests/integration/ against a real Postgres
(CI provides one); excluded from the unit-coverage gate for that reason.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.audit import AuditEvent
from app.models.clinic import Clinic
from app.models.connection import ClinicConnection, ConnectionStatus
from app.models.emr_connection import EmrConnection
from app.models.observation import Observation, ObservationStatus
from app.models.patient import Patient
from app.models.user import User
from app.repositories.clinic_connection import DuplicateLiveConnectionError
from app.repositories.emr_connection import ConnectionRecord
from app.repositories.user import DuplicateEmailError, UserRecord
from app.services.observation import counts_toward_analysis

# The SQL twin of the unit-tested analyzable-status predicate: derived from it, so the
# two can never drift apart.
_ANALYZABLE_STATUSES = tuple(s for s in ObservationStatus if counts_toward_analysis(s))


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

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[ClinicConnection]:
        stmt = (
            select(ClinicConnection)
            .where(ClinicConnection.patient_id == patient_id)
            .order_by(ClinicConnection.created_at)
        )
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


class PostgresObservationRepository:
    """ObservationRepository over the observation table (append-only)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, observation: Observation) -> Observation:
        self._session.add(observation)
        await self._session.flush()
        return observation

    async def list_for_patient(
        self,
        patient_id: uuid.UUID,
        code: str | None = None,
        since: datetime | None = None,
        limit: int | None = None,
        offset: int = 0,
        newest_first: bool = False,
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


def _user_to_record(row: User) -> UserRecord:
    return UserRecord(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        display_name=row.display_name,
        role=row.role,
        patient_id=row.patient_id,
        clinic_id=row.clinic_id,
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
