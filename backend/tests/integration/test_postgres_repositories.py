"""Postgres repository round-trips + migration/model parity, against a real database.

Runs only when TEST_DATABASE_URL is set (skips cleanly otherwise). All data is
synthetic — no real patient data (CLAUDE.md §5).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.base import Base
from app.ingestion.labs import lab_result_to_observation
from app.models.audit import AuditEvent
from app.models.clinic import Clinic
from app.models.connection import ClinicConnection, ConnectionStatus, Initiator
from app.models.emr_connection import EmrConnectionStatus
from app.models.observation import DataOrigin
from app.models.patient import Patient
from app.models.user import UserRole
from app.repositories.clinic_connection import DuplicateLiveConnectionError
from app.repositories.emr_connection import ConnectionRecord
from app.repositories.postgres import (
    PostgresAuditEventRepository,
    PostgresClinicConnectionRepository,
    PostgresClinicRepository,
    PostgresEmrConnectionRepository,
    PostgresObservationRepository,
    PostgresUserRepository,
)
from app.repositories.user import UserRecord
from app.schemas.lab import LabResultIn, LabStatus

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Postgres integration tests need TEST_DATABASE_URL (the CI service provides it)",
)


async def _new_patient(session: AsyncSession) -> uuid.UUID:
    patient = Patient(display_name="Synthetic Integration Patient")
    session.add(patient)
    await session.flush()
    return patient.id


def _lab(code: str, value: float, *, status: LabStatus, day: int) -> LabResultIn:
    return LabResultIn(
        loinc_code=code,
        display="Synthetic analyte",
        value=value,
        unit="%",
        effective_at=datetime(2026, 6, day, 8, 0, tzinfo=UTC),
        status=status,
    )


async def test_user_repository_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    record = UserRecord(
        id=uuid.uuid4(),
        email=f"pat-{uuid.uuid4().hex[:12]}@example.com",
        password_hash="argon2-hash-placeholder",
        display_name="Synthetic Pat",
        role=UserRole.patient,
        patient_id=uuid.uuid4(),
    )
    async with session_factory() as session:
        await PostgresUserRepository(session).add(record)
        await session.commit()

    async with session_factory() as session:
        repo = PostgresUserRepository(session)
        assert await repo.get_by_email(record.email) == record
        assert await repo.get_by_id(record.id) == record
        assert await repo.get_by_email("nobody@example.com") is None
        assert await repo.get_by_id(uuid.uuid4()) is None


async def test_emr_connection_repository_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        patient_id = await _new_patient(session)
        record = ConnectionRecord(
            id=uuid.uuid4(),
            patient_id=patient_id,
            fhir_base="https://ehr.example/fhir",
            provider_name="Synthetic Health",
        )
        await PostgresEmrConnectionRepository(session).add(record)
        await session.commit()

    async with session_factory() as session:
        repo = PostgresEmrConnectionRepository(session)
        loaded = await repo.get(record.id)
        assert loaded == record
        assert loaded is not None and loaded.status is EmrConnectionStatus.authorizing

        record.status = EmrConnectionStatus.active
        record.granted_scope = "patient/Observation.read"
        record.patient_fhir_id = "fhir-patient-1"
        record.token_ref = "secret::synthetic-ref"
        await repo.update(record)
        await session.commit()

    async with session_factory() as session:
        repo = PostgresEmrConnectionRepository(session)
        assert await repo.get(record.id) == record
        assert await repo.get(uuid.uuid4()) is None
        missing = ConnectionRecord(
            id=uuid.uuid4(), patient_id=patient_id, fhir_base="https://x", provider_name=None
        )
        with pytest.raises(LookupError):
            await repo.update(missing)


async def test_observation_repository_lists_analyzable_records_only(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        patient_id = await _new_patient(session)
        other_patient_id = await _new_patient(session)
        repo = PostgresObservationRepository(session)

        def _obs(result: LabResultIn, *, pid: uuid.UUID = patient_id) -> object:
            return lab_result_to_observation(
                result,
                patient_id=pid,
                origin=DataOrigin.ehr_imported,
                recorded_by_role="system",
                quality={"source_system": "Synthetic Health"},
            )

        later_a1c = await repo.add(_obs(_lab("4548-4", 7.4, status=LabStatus.final, day=20)))
        early_a1c = await repo.add(_obs(_lab("4548-4", 7.1, status=LabStatus.final, day=5)))
        errored = await repo.add(
            _obs(_lab("4548-4", 99.9, status=LabStatus.entered_in_error, day=10))
        )
        glucose = await repo.add(_obs(_lab("2345-7", 5.6, status=LabStatus.preliminary, day=8)))
        other = _obs(_lab("4548-4", 6.0, status=LabStatus.final, day=9), pid=other_patient_id)
        await repo.add(other)
        await session.commit()

    async with session_factory() as session:
        repo = PostgresObservationRepository(session)
        rows = await repo.list_for_patient(patient_id)
        # entered_in_error is retained in the table but excluded from analysis; the
        # other patient's data never leaks in; order is oldest-first by effective_at.
        assert [r.id for r in rows] == [early_a1c.id, glucose.id, later_a1c.id]
        assert errored.id not in {r.id for r in rows}

        a1c_rows = await repo.list_for_patient(patient_id, code="4548-4")
        assert [r.id for r in a1c_rows] == [early_a1c.id, later_a1c.id]
        assert a1c_rows[0].quality == {"source_system": "Synthetic Health"}
        assert a1c_rows[0].origin is DataOrigin.ehr_imported


async def test_audit_event_repository_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        patient_id = await _new_patient(session)
        repo = PostgresAuditEventRepository(session)
        event = await repo.add(
            AuditEvent(
                actor_role="system",
                action="import_labs",
                patient_id=patient_id,
                detail={"imported": 2},
            )
        )
        assert event.occurred_at is not None  # server default loaded on add
        await session.commit()

    async with session_factory() as session:
        repo = PostgresAuditEventRepository(session)
        events = await repo.list_for_patient(patient_id)
        assert [e.id for e in events] == [event.id]
        assert events[0].action == "import_labs"
        assert events[0].detail == {"imported": 2}
        assert await repo.list_for_patient(uuid.uuid4()) == []


async def test_clinic_repository_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        repo = PostgresClinicRepository(session)
        clinic = await repo.add(Clinic(name="Synthetic Neuropathy Clinic"))
        assert clinic.id is not None and clinic.created_at is not None  # defaults loaded
        await session.commit()

    async with session_factory() as session:
        repo = PostgresClinicRepository(session)
        loaded = await repo.get(clinic.id)
        assert loaded is not None and loaded.name == "Synthetic Neuropathy Clinic"
        assert await repo.get(uuid.uuid4()) is None
        await repo.delete(clinic.id)
        await session.commit()

    async with session_factory() as session:
        repo = PostgresClinicRepository(session)
        assert await repo.get(clinic.id) is None
        await repo.delete(uuid.uuid4())  # unknown id is a quiet no-op


async def test_clinic_connection_repository_consent_lifecycle(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The storage layer under the consent gate: status/consent_granted_at/revoked_at
    must round-trip exactly, list_active_for_clinic must track them, and the live
    unique index must hold (this is what may_transmit_to_clinic judges)."""
    async with session_factory() as session:
        patient_id = await _new_patient(session)
        clinic = await PostgresClinicRepository(session).add(Clinic(name="Synthetic Clinic A"))
        other_clinic = await PostgresClinicRepository(session).add(
            Clinic(name="Synthetic Clinic B")
        )
        repo = PostgresClinicConnectionRepository(session)
        connection = await repo.add(
            ClinicConnection(
                patient_id=patient_id, clinic_id=clinic.id, initiated_by=Initiator.clinic
            )
        )
        assert connection.status is ConnectionStatus.pending  # default loaded on add
        later = await repo.add(
            ClinicConnection(
                patient_id=patient_id, clinic_id=other_clinic.id, initiated_by=Initiator.clinic
            )
        )
        await session.commit()

    async with session_factory() as session:
        repo = PostgresClinicConnectionRepository(session)
        # One live connection per patient-clinic pair — the partial unique index.
        with pytest.raises(DuplicateLiveConnectionError):
            await repo.add(
                ClinicConnection(
                    patient_id=patient_id, clinic_id=clinic.id, initiated_by=Initiator.clinic
                )
            )
        # The savepoint keeps the transaction usable after the absorbed duplicate.
        rows = await repo.list_for_patient(patient_id)
        assert [r.id for r in rows] == [connection.id, later.id]  # oldest first
        assert await repo.list_active_for_clinic(clinic.id) == []  # pending is not active

        loaded = await repo.get(connection.id)
        assert loaded is not None
        loaded.status = ConnectionStatus.active
        loaded.consent_granted_at = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
        await repo.update(loaded)
        await session.commit()

    async with session_factory() as session:
        repo = PostgresClinicConnectionRepository(session)
        active = await repo.list_active_for_clinic(clinic.id)
        assert [r.id for r in active] == [connection.id]
        assert active[0].consent_granted_at == datetime(2026, 7, 13, 12, 0, tzinfo=UTC)

        active[0].status = ConnectionStatus.revoked
        active[0].revoked_at = datetime(2026, 7, 13, 13, 0, tzinfo=UTC)
        await repo.update(active[0])
        await session.commit()

    async with session_factory() as session:
        repo = PostgresClinicConnectionRepository(session)
        revoked = await repo.get(connection.id)
        assert revoked is not None and revoked.status is ConnectionStatus.revoked
        assert revoked.revoked_at == datetime(2026, 7, 13, 13, 0, tzinfo=UTC)
        assert await repo.list_active_for_clinic(clinic.id) == []  # revocation cuts the list
        # The live index only covers non-revoked rows: a fresh invite may follow.
        replacement = await repo.add(
            ClinicConnection(
                patient_id=patient_id, clinic_id=clinic.id, initiated_by=Initiator.clinic
            )
        )
        assert replacement.status is ConnectionStatus.pending
        with pytest.raises(LookupError):
            await repo.update(
                ClinicConnection(
                    id=uuid.uuid4(),
                    patient_id=patient_id,
                    clinic_id=clinic.id,
                    initiated_by=Initiator.clinic,
                )
            )


async def test_user_repository_clinician_fields_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        clinic = await PostgresClinicRepository(session).add(Clinic(name="Synthetic Clinic"))
        patient_record = UserRecord(
            id=uuid.uuid4(),
            email=f"pat-{uuid.uuid4().hex[:12]}@example.com",
            password_hash="argon2-hash-placeholder",
            display_name="Synthetic Pat",
            role=UserRole.patient,
            patient_id=uuid.uuid4(),
        )
        clinician_record = UserRecord(
            id=uuid.uuid4(),
            email=f"doc-{uuid.uuid4().hex[:12]}@example.com",
            password_hash="argon2-hash-placeholder",
            display_name="Synthetic Doc",
            role=UserRole.clinician,
            patient_id=None,
            clinic_id=clinic.id,
        )
        repo = PostgresUserRepository(session)
        await repo.add(patient_record)
        await repo.add(clinician_record)
        await session.commit()

    async with session_factory() as session:
        repo = PostgresUserRepository(session)
        assert patient_record.patient_id is not None
        assert await repo.get_by_patient_id(patient_record.patient_id) == patient_record
        assert await repo.get_by_patient_id(uuid.uuid4()) is None
        loaded = await repo.get_by_id(clinician_record.id)
        assert loaded == clinician_record and loaded.clinic_id == clinic.id


def _autogenerate_diff(connection: Connection) -> list[object]:
    context = MigrationContext.configure(connection)
    return list(compare_metadata(context, Base.metadata))


async def test_migration_and_models_are_in_parity(engine: AsyncEngine) -> None:
    """Autogenerate against the migrated schema must produce an empty diff."""
    async with engine.connect() as connection:
        diff = await connection.run_sync(_autogenerate_diff)
    assert diff == [], f"migration/model drift detected: {diff}"
