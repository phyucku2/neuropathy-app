"""Unit tests for the repository layer: in-memory implementations, the sync bridge,
and the EMR pull -> Observation persistence path (all synthetic data).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.emr.service import EmrService, InMemorySecretStore
from app.ingestion.labs import lab_result_to_observation
from app.models.audit import AuditEvent
from app.models.emr_connection import EmrConnectionStatus
from app.models.observation import DataOrigin
from app.repositories.audit import InMemoryAuditEventRepository
from app.repositories.emr_connection import ConnectionRecord, InMemoryEmrConnectionRepository
from app.repositories.observation import InMemoryObservationRepository
from app.schemas.lab import LabResultIn, LabStatus

PATIENT_ID = uuid.uuid4()


def _lab(
    code: str, value: float, *, status: LabStatus = LabStatus.final, day: int = 1
) -> LabResultIn:
    return LabResultIn(
        loinc_code=code,
        display="Synthetic analyte",
        value=value,
        unit="%",
        effective_at=datetime(2026, 6, day, 8, 0, tzinfo=UTC),
        status=status,
    )


def _observation(result: LabResultIn, patient_id: uuid.UUID = PATIENT_ID) -> Any:
    return lab_result_to_observation(
        result,
        patient_id=patient_id,
        origin=DataOrigin.ehr_imported,
        recorded_by_role="system",
        quality={"source_system": "Synthetic Health"},
    )


async def test_observation_repository_lists_analyzable_records_only() -> None:
    repo = InMemoryObservationRepository()
    later = await repo.add(_observation(_lab("4548-4", 7.4, day=20)))
    early = await repo.add(_observation(_lab("4548-4", 7.1, day=5)))
    errored = await repo.add(_observation(_lab("4548-4", 99.9, status=LabStatus.entered_in_error)))
    glucose = await repo.add(_observation(_lab("2345-7", 5.6, day=8)))
    await repo.add(_observation(_lab("4548-4", 6.0), uuid.uuid4()))  # another patient

    rows = await repo.list_for_patient(PATIENT_ID)
    assert [r.id for r in rows] == [early.id, glucose.id, later.id]  # oldest first
    assert errored.id not in {r.id for r in rows}  # retained, never analyzed

    assert [r.id for r in await repo.list_for_patient(PATIENT_ID, code="4548-4")] == [
        early.id,
        later.id,
    ]


async def test_audit_repository_is_append_only_and_fills_defaults() -> None:
    repo = InMemoryAuditEventRepository()
    event = await repo.add(
        AuditEvent(actor_role="system", action="import_labs", patient_id=PATIENT_ID, detail={})
    )
    assert event.id is not None
    assert event.occurred_at is not None

    events = await repo.list_for_patient(PATIENT_ID)
    assert events == [event]
    assert await repo.list_for_patient(uuid.uuid4()) == []


async def test_emr_connection_repository_round_trip() -> None:
    repo = InMemoryEmrConnectionRepository()
    record = ConnectionRecord(
        id=uuid.uuid4(), patient_id=PATIENT_ID, fhir_base="https://ehr.example", provider_name=None
    )
    await repo.add(record)
    assert await repo.get(record.id) == record
    record.status = EmrConnectionStatus.active
    await repo.update(record)
    loaded = await repo.get(record.id)
    assert loaded is not None and loaded.status is EmrConnectionStatus.active
    assert await repo.get(uuid.uuid4()) is None


class _PullOnlyEmr:
    """Transport fake: just enough FHIR for pull_labs (no network, synthetic data)."""

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        assert access_token == "the-access-token"
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4"}]},
                        "effectiveDateTime": "2026-06-15T08:30:00+00:00",
                        "valueQuantity": {
                            "value": 7.2,
                            "unit": "%",
                            "system": "http://unitsofmeasure.org",
                            "code": "%",
                        },
                    }
                }
            ],
        }

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        raise AssertionError("pull_labs must not hit the token endpoint")


async def test_pull_labs_persists_research_grade_observations_and_audits() -> None:
    secret_store = InMemorySecretStore()
    service = EmrService(
        transport=_PullOnlyEmr(),
        client_id="c",
        redirect_uri="https://a/cb",
        secret_store=secret_store,
    )
    record = ConnectionRecord(
        id=uuid.uuid4(),
        patient_id=PATIENT_ID,
        fhir_base="https://ehr.example/fhir",
        provider_name="Synthetic Health",
        status=EmrConnectionStatus.active,
        patient_fhir_id="fhir-patient-9",
        token_ref=secret_store.put({"access_token": "the-access-token"}),
    )
    await service.connections.add(record)

    results, imported = await service.pull_labs(record.id)
    assert len(results) == 1
    assert imported == 1

    observations = await service.observations.list_for_patient(PATIENT_ID)
    assert len(observations) == 1
    stored = observations[0]
    assert stored.origin is DataOrigin.ehr_imported
    assert stored.recorded_by_role == "system"
    assert stored.quality == {"source_system": "Synthetic Health"}
    assert stored.code == "4548-4"
    assert stored.value_num == 7.2

    events = await service.audit.list_for_patient(PATIENT_ID)
    assert [e.action for e in events] == ["import_labs"]
    assert events[0].detail == {"connection_id": str(record.id), "fetched": 1, "imported": 1}
    # References only in the audit trail — never lab values (PHI).
    assert "7.2" not in str(events[0].detail)


async def test_pull_labs_names_fhir_base_when_provider_unknown() -> None:
    secret_store = InMemorySecretStore()
    service = EmrService(
        transport=_PullOnlyEmr(),
        client_id="c",
        redirect_uri="https://a/cb",
        secret_store=secret_store,
    )
    record = ConnectionRecord(
        id=uuid.uuid4(),
        patient_id=PATIENT_ID,
        fhir_base="https://ehr.example/fhir",
        provider_name=None,
        status=EmrConnectionStatus.active,
        patient_fhir_id="fhir-patient-9",
        token_ref=secret_store.put({"access_token": "the-access-token"}),
    )
    await service.connections.add(record)
    await service.pull_labs(record.id)
    observations = await service.observations.list_for_patient(PATIENT_ID)
    assert observations[0].quality == {"source_system": "https://ehr.example/fhir"}


async def test_repeated_pulls_do_not_duplicate_observations() -> None:
    """Re-syncing the same EMR records must never double-count the dataset (review
    finding: duplicate labs on repeated pulls)."""
    secret_store = InMemorySecretStore()
    service = EmrService(
        transport=_PullOnlyEmr(),
        client_id="c",
        redirect_uri="https://a/cb",
        secret_store=secret_store,
    )
    record = ConnectionRecord(
        id=uuid.uuid4(),
        patient_id=PATIENT_ID,
        fhir_base="https://ehr.example/fhir",
        provider_name="Synthetic Health",
        status=EmrConnectionStatus.active,
        patient_fhir_id="fhir-patient-9",
        token_ref=secret_store.put({"access_token": "the-access-token"}),
    )
    await service.connections.add(record)

    _, first = await service.pull_labs(record.id)
    results, second = await service.pull_labs(record.id)
    assert (first, second) == (1, 0)  # second sync fetches but persists nothing new
    assert len(results) == 1
    assert len(await service.observations.list_for_patient(PATIENT_ID)) == 1


async def test_superseded_observations_are_excluded_from_the_analyzable_dataset() -> None:
    """A corrected-away original must not be returned (review finding: revises_id
    chains double-counted)."""
    from datetime import UTC, datetime

    from app.models.observation import Observation, ObservationStatus, SourceType
    from app.repositories.observation import InMemoryObservationRepository

    repo = InMemoryObservationRepository()
    wrong = await repo.add(
        Observation(
            patient_id=PATIENT_ID,
            source=SourceType.lab,
            origin=DataOrigin.ehr_imported,
            code="4548-4",
            value_num=9.2,  # mis-OCR'd value
            effective_at=datetime(2026, 6, 1, tzinfo=UTC),
            recorded_at=datetime(2026, 6, 1, tzinfo=UTC),
            status=ObservationStatus.final,
            quality={},
            payload={},
        )
    )
    await repo.add(
        Observation(
            patient_id=PATIENT_ID,
            source=SourceType.lab,
            origin=DataOrigin.ehr_imported,
            code="4548-4",
            value_num=7.0,
            effective_at=datetime(2026, 6, 1, tzinfo=UTC),
            recorded_at=datetime(2026, 6, 2, tzinfo=UTC),
            status=ObservationStatus.corrected,
            revises_id=wrong.id,
            quality={},
            payload={},
        )
    )
    rows = await repo.list_for_patient(PATIENT_ID)
    assert [r.value_num for r in rows] == [7.0]  # only the current record survives


async def test_duplicate_email_raises_domain_error_at_the_repository() -> None:
    """The repository owns email uniqueness (review finding: check-then-insert race)."""
    from app.models.user import UserRole
    from app.repositories.user import DuplicateEmailError, InMemoryUserRepository, UserRecord

    repo = InMemoryUserRepository()
    user = UserRecord(
        id=uuid.uuid4(),
        email="dup@example.com",
        password_hash="x",
        display_name="Dup",
        role=UserRole.patient,
        patient_id=uuid.uuid4(),
    )
    await repo.add(user)
    assert repo.patients  # the linked patient record is created with the user
    with pytest.raises(DuplicateEmailError):
        await repo.add(user)


async def test_callback_for_vanished_connection_is_404() -> None:
    """Defensive: a pending state whose connection was removed fails cleanly."""
    from app.emr.service import EmrError, _PendingAuth

    service = EmrService(transport=_PullOnlyEmr(), client_id="c", redirect_uri="https://a/cb")
    service._pending["s"] = _PendingAuth(  # noqa: SLF001 — contrived state
        connection_id=uuid.uuid4(), code_verifier="v", token_endpoint="https://t"
    )

    class _TokenOnly(_PullOnlyEmr):
        async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
            return {"access_token": "the-access-token"}

    service.transport = _TokenOnly()
    with pytest.raises(EmrError) as exc_info:
        await service.complete_callback(state="s", code="c")
    assert exc_info.value.status_code == 404


def test_import_key_prefers_source_record_id() -> None:
    """The EMR's own FHIR id wins; content identity is the fallback (dedup design)."""
    from datetime import UTC, datetime

    from app.ingestion.labs import lab_import_key
    from app.schemas.lab import LabResultIn

    fhir_base = "https://ehr.example/fhir"
    with_id = LabResultIn(
        loinc_code="4548-4",
        source_record_id="obs-123",
        display="Hemoglobin A1c",
        value=7.2,
        unit="%",
        effective_at=datetime(2026, 6, 15, tzinfo=UTC),
    )
    without_id = with_id.model_copy(update={"source_record_id": None})
    assert lab_import_key(with_id, fhir_base=fhir_base) == "fhir:https://ehr.example/fhir:obs-123"
    assert lab_import_key(without_id, fhir_base=fhir_base).startswith("content:4548-4:2026-06-15")
    # Patient uploads pass no fhir_base: content identity keys the whole panel.
    assert lab_import_key(with_id).startswith("content:4548-4:2026-06-15")
