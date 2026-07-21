"""Postgres repository round-trips + migration/model parity, against a real database.

Runs only when TEST_DATABASE_URL is set (skips cleanly otherwise). All data is
synthetic — no real patient data (CLAUDE.md §5).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.base import Base
from app.ingestion.labs import lab_result_to_observation
from app.models.audit import AuditEvent
from app.models.capability import Actor, Capability
from app.models.caregiver import (
    CaregiverInvite,
    CaregiverLink,
    CaregiverLinkStatus,
    CaregiverScope,
)
from app.models.clinic import Clinic
from app.models.connection import ClinicConnection, ConnectionStatus, Initiator
from app.models.emr_connection import EmrConnectionStatus
from app.models.observation import DataOrigin
from app.models.patient import Patient
from app.models.user import UserRole
from app.repositories.capability import DuplicateCapabilityKeyError
from app.repositories.caregiver import DuplicateLiveCaregiverLinkError
from app.repositories.clinic_connection import DuplicateLiveConnectionError
from app.repositories.emr_connection import ConnectionRecord
from app.repositories.postgres import (
    PostgresAuditEventRepository,
    PostgresCapabilityRepository,
    PostgresCaregiverInviteRepository,
    PostgresCaregiverLinkRepository,
    PostgresClinicConnectionRepository,
    PostgresClinicRepository,
    PostgresEmrClinicalNoteRepository,
    PostgresEmrConnectionRepository,
    PostgresMfaFactorRepository,
    PostgresObservationRepository,
    PostgresPatientCapabilityRepository,
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
        loaded = await repo.get_by_email(record.email)
        # The read path now surfaces the server-stamped created_at (ADR-0031); adopt it
        # onto the expected record so the rest of the round-trip compares field-for-field.
        assert loaded is not None and loaded.created_at is not None
        record.created_at = loaded.created_at
        assert loaded == record
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


async def test_add_if_absent_enforces_import_idempotency_across_sessions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The DB-level invariant behind sweep #3: uq_observation_patient_import_key makes a
    second import of the same source record impossible even when it commits from a SEPARATE
    transaction between another pull's existence-probe and its write. add_if_absent absorbs
    the resulting unique-violation as a skip (False), leaving the session usable — never a
    500 and never a duplicate analyzable row."""

    def _obs(key: str | None, *, pid: uuid.UUID) -> object:
        return lab_result_to_observation(
            _lab("4548-4", 7.2, status=LabStatus.final, day=15),
            patient_id=pid,
            origin=DataOrigin.ehr_imported,
            recorded_by_role="system",
            quality={"source_system": "Synthetic Health"},
            import_key=key,
        )

    async with session_factory() as session:
        patient_id = await _new_patient(session)
        other_patient_id = await _new_patient(session)
        await session.commit()

    # First pull imports the row and commits.
    async with session_factory() as session:
        repo = PostgresObservationRepository(session)
        assert await repo.add_if_absent(_obs("labs:abc", pid=patient_id)) is True
        await session.commit()

    # A concurrent second pull that already probed "absent" now tries the same write in a
    # fresh transaction: the unique index rejects it and add_if_absent returns False. The
    # SAME key for a DIFFERENT patient still inserts (uniqueness is per-patient), and after
    # the absorbed conflict the session is still usable for that follow-on write + commit.
    async with session_factory() as session:
        repo = PostgresObservationRepository(session)
        assert await repo.add_if_absent(_obs("labs:abc", pid=patient_id)) is False
        assert await repo.add_if_absent(_obs("labs:abc", pid=other_patient_id)) is True
        await session.commit()

    # Exactly one row for the first patient (the duplicate never landed); one for the other.
    async with session_factory() as session:
        repo = PostgresObservationRepository(session)
        assert await repo.count_for_patient(patient_id) == 1
        assert await repo.count_for_patient(other_patient_id) == 1


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
        loaded_patient = await repo.get_by_patient_id(patient_record.patient_id)
        # Adopt the server-stamped created_at the read path now surfaces (ADR-0031).
        assert loaded_patient is not None and loaded_patient.created_at is not None
        patient_record.created_at = loaded_patient.created_at
        assert loaded_patient == patient_record
        assert await repo.get_by_patient_id(uuid.uuid4()) is None
        loaded = await repo.get_by_id(clinician_record.id)
        assert loaded is not None and loaded.created_at is not None
        clinician_record.created_at = loaded.created_at
        assert loaded == clinician_record and loaded.clinic_id == clinic.id


async def test_capability_repository_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The registry storage under the lazy get-or-create: add/get_by_key/list, the
    unique key constraint (absorbed via savepoint so the transaction stays usable),
    and the loaded column defaults."""
    key = f"synthetic_{uuid.uuid4().hex[:8]}"
    async with session_factory() as session:
        repo = PostgresCapabilityRepository(session)
        capability = await repo.add(Capability(key=key, name="Synthetic capability"))
        assert capability.available is True  # default loaded on add
        assert capability.created_at is not None
        await session.commit()

    async with session_factory() as session:
        repo = PostgresCapabilityRepository(session)
        with pytest.raises(DuplicateCapabilityKeyError):
            await repo.add(Capability(key=key, name="Synthetic capability again"))
        # The savepoint keeps the transaction usable after the absorbed duplicate.
        loaded = await repo.get_by_key(key)
        assert loaded is not None and loaded.id == capability.id
        assert await repo.get_by_key("never_registered") is None
        assert key in [c.key for c in await repo.list()]


async def test_patient_capability_repository_upsert_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """uq_patient_capability under the upsert: the first write inserts, every later
    write is absorbed by the savepoint and updates the ONE row in place — active,
    set_by, and expires_at all follow the latest write (the race-losing insert takes
    exactly this path, mirroring the DuplicateLiveConnectionError absorption)."""
    expiry = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    async with session_factory() as session:
        patient_id = await _new_patient(session)
        capability = await PostgresCapabilityRepository(session).add(
            Capability(key=f"synthetic_{uuid.uuid4().hex[:8]}", name="Synthetic capability")
        )
        repo = PostgresPatientCapabilityRepository(session)
        first = await repo.upsert(
            patient_id=patient_id,
            capability_id=capability.id,
            active=True,
            set_by=Actor.patient,
            expires_at=None,
        )
        assert first.created_at is not None  # defaults loaded on add
        await session.commit()

    async with session_factory() as session:
        repo = PostgresPatientCapabilityRepository(session)
        second = await repo.upsert(
            patient_id=patient_id,
            capability_id=capability.id,
            active=False,
            set_by=Actor.clinician,
            expires_at=expiry,
        )
        assert second.id == first.id  # updated in place, never a second row
        # The savepoint keeps the transaction usable after the absorbed insert.
        rows = await repo.list_for_patient(patient_id)
        assert [r.id for r in rows] == [first.id]
        await session.commit()

    async with session_factory() as session:
        repo = PostgresPatientCapabilityRepository(session)
        loaded = await repo.get(patient_id, capability.id)
        assert loaded is not None
        assert loaded.active is False
        assert loaded.set_by is Actor.clinician
        assert loaded.expires_at == expiry
        assert await repo.get(patient_id, uuid.uuid4()) is None
        assert await repo.list_for_patient(uuid.uuid4()) == []


async def test_medication_and_event_source_scoped_reads_and_append_only(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The source-scoped read (ix_observation_patient_source_time) returns only the named
    source, and the medication change log persists append-only across add_if_absent — a
    retry of the same client_entry_id skips via uq_observation_patient_import_key, while a
    genuine second change (distinct key) endures (ADR-0045 P2)."""
    from datetime import date

    from app.ingestion.events import event_import_key, event_to_observation
    from app.ingestion.medications import (
        medication_change_to_observation,
        medication_import_key,
        medication_register_to_observation,
        mint_medication_id,
    )
    from app.models.observation import SourceType
    from app.schemas.event import EventIn, EventType
    from app.schemas.medication import (
        MedicationChangeIn,
        MedicationChangeType,
        MedicationKind,
        MedicationRegisterIn,
    )

    now = datetime.now(UTC)
    async with session_factory() as session:
        patient_id = await _new_patient(session)
        repo = PostgresObservationRepository(session)
        med_id = mint_medication_id()
        retry_cid = uuid.uuid4()

        added = medication_register_to_observation(
            MedicationRegisterIn(
                name="Gabapentin",
                kind=MedicationKind.prescription,
                dose_amount=300.0,
                dose_unit="mg",
                started_on=date(2026, 5, 1),
                client_entry_id=retry_cid,
            ),
            patient_id=patient_id,
            medication_id=med_id,
            import_key=medication_import_key(retry_cid),
            recorded_at=now,
        )
        assert await repo.add_if_absent(added) is True
        # A dose change is its OWN append-only row (distinct key) — the log, not a correction.
        changed = medication_change_to_observation(
            MedicationChangeIn(
                change_type=MedicationChangeType.dose_changed,
                dose_amount=600.0,
                dose_unit="mg",
                effective_date=date(2026, 6, 15),
                client_entry_id=uuid.uuid4(),
            ),
            patient_id=patient_id,
            medication_id=med_id,
            display="Gabapentin",
            kind="prescription",
            prescriber=None,
            import_key=medication_import_key(uuid.uuid4()),
            recorded_at=now,
        )
        assert await repo.add_if_absent(changed) is True
        # An event row of a different source.
        event = event_to_observation(
            EventIn(
                type=EventType.fall, effective_date=date(2026, 6, 20), client_entry_id=uuid.uuid4()
            ),
            patient_id=patient_id,
            import_key=event_import_key(uuid.uuid4()),
            recorded_at=now,
        )
        assert await repo.add_if_absent(event) is True
        await session.commit()

    async with session_factory() as session:
        repo = PostgresObservationRepository(session)
        # Source-scoped read returns ONLY that source (both med rows, append-only log intact).
        meds = await repo.list_for_patient(patient_id, source=SourceType.medication)
        assert {r.code for r in meds} == {med_id}
        assert len(meds) == 2  # added + dose_changed both endure (the log)
        assert all(r.revises_id is None for r in meds)  # none supersedes another
        events = await repo.list_for_patient(patient_id, source=SourceType.event)
        assert [r.code for r in events] == ["event_fall"]

        # A retry of the `added` entry (same client_entry_id -> same import_key) skips.
        retry = medication_register_to_observation(
            MedicationRegisterIn(
                name="Gabapentin",
                kind=MedicationKind.prescription,
                dose_amount=300.0,
                dose_unit="mg",
                started_on=date(2026, 5, 1),
                client_entry_id=retry_cid,
            ),
            patient_id=patient_id,
            medication_id=mint_medication_id(),
            import_key=medication_import_key(retry_cid),
            recorded_at=now,
        )
        assert await repo.add_if_absent(retry) is False
        await session.commit()

    async with session_factory() as session:
        repo = PostgresObservationRepository(session)
        assert len(await repo.list_for_patient(patient_id, source=SourceType.medication)) == 2


async def test_emr_clinical_note_repository_round_trip_and_idempotency(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The SEPARATE clinical-note store (ADR-0045 P2 #27): metadata round-trips, the
    partial-unique index (uq_emr_note_patient_import_key) makes a re-pull of the same
    DocumentReference a graceful skip (add_if_absent -> False) across transactions, the
    same key for a DIFFERENT patient still inserts, and list/delete are patient-scoped."""
    from app.models.emr_clinical_note import EmrClinicalNote

    def _note(key: str | None, *, pid: uuid.UUID, connection_id: uuid.UUID) -> EmrClinicalNote:
        return EmrClinicalNote(
            patient_id=pid,
            connection_id=connection_id,
            origin=DataOrigin.ehr_imported,
            source_system="Synthetic Health",
            document_fhir_id="DocRef/1",
            type_code="11506-3",
            type_display="Progress note",
            category="clinical-note",
            authored_at=datetime(2026, 6, 15, 8, 30, tzinfo=UTC),
            author_display="Dr Synthetic",
            has_inline_data=False,
            import_key=key,
        )

    async with session_factory() as session:
        patient_id = await _new_patient(session)
        other_patient_id = await _new_patient(session)
        connection_id, other_connection_id = uuid.uuid4(), uuid.uuid4()
        connections = PostgresEmrConnectionRepository(session)
        await connections.add(
            ConnectionRecord(
                id=connection_id,
                patient_id=patient_id,
                fhir_base="https://ehr.example/fhir",
                provider_name="Synthetic Health",
            )
        )
        await connections.add(
            ConnectionRecord(
                id=other_connection_id,
                patient_id=other_patient_id,
                fhir_base="https://ehr.example/fhir",
                provider_name="Synthetic Health",
            )
        )
        await session.commit()

    # First pull imports the note.
    async with session_factory() as session:
        repo = PostgresEmrClinicalNoteRepository(session)
        assert (
            await repo.add_if_absent(_note("docref:1", pid=patient_id, connection_id=connection_id))
            is True
        )
        await session.commit()

    # A second pull that already probed "absent" now hits the unique index and skips;
    # the SAME key for a DIFFERENT patient still inserts (uniqueness is per-patient), and
    # the session stays usable after the absorbed conflict.
    async with session_factory() as session:
        repo = PostgresEmrClinicalNoteRepository(session)
        assert (
            await repo.add_if_absent(_note("docref:1", pid=patient_id, connection_id=connection_id))
            is False
        )
        assert (
            await repo.add_if_absent(
                _note("docref:1", pid=other_patient_id, connection_id=other_connection_id)
            )
            is True
        )
        await session.commit()

    async with session_factory() as session:
        repo = PostgresEmrClinicalNoteRepository(session)
        notes = await repo.list_for_patient(patient_id)
        assert [n.type_display for n in notes] == ["Progress note"]  # exactly one, metadata intact
        assert notes[0].author_display == "Dr Synthetic"
        probe = await repo.existing_import_keys(patient_id, ["docref:1", "docref:absent"])
        assert probe == {"docref:1"}

        await repo.delete_for_patient(patient_id)
        await session.commit()

    async with session_factory() as session:
        repo = PostgresEmrClinicalNoteRepository(session)
        assert await repo.list_for_patient(patient_id) == []  # erased
        assert len(await repo.list_for_patient(other_patient_id)) == 1  # other patient untouched


async def _new_privileged_user(session: AsyncSession) -> uuid.UUID:
    record = UserRecord(
        id=uuid.uuid4(),
        email=f"dr-{uuid.uuid4().hex[:12]}@example.com",
        password_hash="argon2-hash-placeholder",
        display_name="Synthetic Clinician",
        role=UserRole.ops,  # ops needs neither patient nor clinic row
        patient_id=None,
    )
    await PostgresUserRepository(session).add(record)
    return record.id


async def test_mfa_factor_repository_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """§1B C6: get/replace/confirm across sessions, in parity with the in-memory
    twin — one factor per user, re-enrollment replaces it (fresh + unconfirmed) and
    surfaces the superseded vault ref, confirmation is idempotent."""
    async with session_factory() as session:
        user_id = await _new_privileged_user(session)
        repo = PostgresMfaFactorRepository(session)
        assert await repo.get_for_user(user_id) is None
        assert await repo.replace_for_user(user_id, secret_ref="secret::first") is None
        await session.commit()

    async with session_factory() as session:
        repo = PostgresMfaFactorRepository(session)
        factor = await repo.get_for_user(user_id)
        assert factor is not None
        assert factor.user_id == user_id
        assert factor.secret_ref == "secret::first"
        assert factor.confirmed_at is None  # pending until confirmed
        confirmed_at = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
        confirmed = await repo.confirm(user_id, at=confirmed_at)
        assert confirmed is not None and confirmed.confirmed_at == confirmed_at
        # Idempotent: a re-confirm keeps the original timestamp.
        again = await repo.confirm(user_id, at=confirmed_at + timedelta(hours=1))
        assert again is not None and again.confirmed_at == confirmed_at
        assert await repo.confirm(uuid.uuid4(), at=confirmed_at) is None  # nothing to confirm
        await session.commit()

    async with session_factory() as session:
        repo = PostgresMfaFactorRepository(session)
        # Re-enrollment REPLACES: exactly one row survives (the unique user_id
        # index's invariant), unconfirmed, and the superseded ref comes back so the
        # caller can purge the old vault entry.
        assert await repo.replace_for_user(user_id, secret_ref="secret::second") == "secret::first"
        await session.commit()

    async with session_factory() as session:
        repo = PostgresMfaFactorRepository(session)
        replaced = await repo.get_for_user(user_id)
        assert replaced is not None
        assert replaced.secret_ref == "secret::second"
        assert replaced.confirmed_at is None  # back to pending
        assert await repo.get_for_user(uuid.uuid4()) is None


async def test_caregiver_repositories_round_trip_and_live_link_index(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Caregiver invite/link round-trips (ADR-0047): the DB-enforced single-use
    consume, the uq_caregiver_link_live partial unique index (savepoint-absorbed,
    revocation frees the pair), and the deletion sweeps."""
    now = datetime.now(UTC)
    caregiver = UserRecord(
        id=uuid.uuid4(),
        email=f"care-{uuid.uuid4().hex[:12]}@example.com",
        password_hash="argon2-hash-placeholder",
        display_name="Synthetic Caregiver",
        role=UserRole.caregiver,
        patient_id=None,
    )
    code_hash = f"synthetic-hash-{uuid.uuid4().hex}"[:64]

    async with session_factory() as session:
        patient_id = await _new_patient(session)
        await PostgresUserRepository(session).add(caregiver)
        invites = PostgresCaregiverInviteRepository(session)
        invite = await invites.add(
            CaregiverInvite(
                patient_id=patient_id, code_hash=code_hash, expires_at=now + timedelta(days=7)
            )
        )
        await session.commit()

    async with session_factory() as session:
        invites = PostgresCaregiverInviteRepository(session)
        loaded = await invites.get_by_code_hash(code_hash)
        assert loaded is not None and loaded.id == invite.id
        assert await invites.get_by_code_hash("no-such-hash") is None
        assert (await invites.list_for_patient(patient_id))[0].id == invite.id
        # Single-use is ONE conditional UPDATE: the second consume matches nothing.
        assert await invites.consume(invite.id, now=now) is True
        assert await invites.consume(invite.id, now=now) is False
        await session.commit()

    async with session_factory() as session:
        links = PostgresCaregiverLinkRepository(session)
        link = await links.add(
            CaregiverLink(
                patient_id=patient_id,
                caregiver_user_id=caregiver.id,
                status=CaregiverLinkStatus.pending,
                initiated_by=Initiator.patient,
            )
        )
        # The partial unique index refuses a second live link for the pair — and the
        # savepoint keeps the transaction usable afterwards.
        with pytest.raises(DuplicateLiveCaregiverLinkError):
            await links.add(
                CaregiverLink(
                    patient_id=patient_id,
                    caregiver_user_id=caregiver.id,
                    status=CaregiverLinkStatus.pending,
                    initiated_by=Initiator.patient,
                )
            )
        link.status = CaregiverLinkStatus.active
        link.accepted_at = now
        link.scope = CaregiverScope.full
        await links.update(link)
        await session.commit()

    async with session_factory() as session:
        links = PostgresCaregiverLinkRepository(session)
        reloaded = await links.get(link.id)
        assert reloaded is not None
        assert reloaded.status is CaregiverLinkStatus.active
        assert reloaded.scope is CaregiverScope.full
        assert reloaded.accepted_at is not None
        assert [row.id for row in await links.list_for_caregiver(caregiver.id)] == [link.id]
        assert [row.id for row in await links.list_for_patient(patient_id)] == [link.id]
        # Revocation frees the pair: a fresh link inserts cleanly under the index.
        reloaded.status = CaregiverLinkStatus.revoked
        reloaded.revoked_at = now
        await links.update(reloaded)
        await links.add(
            CaregiverLink(
                patient_id=patient_id,
                caregiver_user_id=caregiver.id,
                status=CaregiverLinkStatus.pending,
                initiated_by=Initiator.patient,
            )
        )
        await session.commit()

    async with session_factory() as session:
        # Deletion sweeps (ADR-0027/0047): by caregiver, then by patient.
        links = PostgresCaregiverLinkRepository(session)
        invites = PostgresCaregiverInviteRepository(session)
        await links.delete_for_caregiver(caregiver.id)
        assert await links.list_for_patient(patient_id) == []
        await invites.delete_for_patient(patient_id)
        assert await invites.list_for_patient(patient_id) == []
        await session.commit()


def _autogenerate_diff(connection: Connection) -> list[object]:
    context = MigrationContext.configure(connection)
    return list(compare_metadata(context, Base.metadata))


async def test_migration_and_models_are_in_parity(engine: AsyncEngine) -> None:
    """Autogenerate against the migrated schema must produce an empty diff."""
    async with engine.connect() as connection:
        diff = await connection.run_sync(_autogenerate_diff)
    assert diff == [], f"migration/model drift detected: {diff}"
