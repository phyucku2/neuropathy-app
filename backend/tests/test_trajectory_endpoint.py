"""End-to-end tests for GET /trajectory: the engine wired to the observation store
behind auth (patient-scoped, honest when data is thin).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, get_current_user, get_emr_service
from app.emr.service import EmrService
from app.main import app
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.models.user import UserRole

NOW = datetime.now(UTC)

PATIENT = CurrentUser(
    user_id=uuid4(),
    role=UserRole.patient,
    patient_id=uuid4(),
    email="pat@example.com",
    display_name="Pat",
)


class _NoNetwork:
    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        raise AssertionError("trajectory must not touch the network")

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        raise AssertionError("trajectory must not touch the network")


@pytest.fixture()
def service() -> EmrService:
    return EmrService(transport=_NoNetwork(), client_id="c", redirect_uri="https://a/cb")


@pytest.fixture()
def client(service: EmrService) -> Iterator[TestClient]:
    app.dependency_overrides[get_emr_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: PATIENT
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _hba1c(value: float, days_ago: float, patient_id: UUID | None = None) -> Observation:
    return Observation(
        patient_id=PATIENT.patient_id if patient_id is None else patient_id,
        source=SourceType.lab,
        origin=DataOrigin.ehr_imported,
        code="4548-4",
        value_num=value,
        effective_at=NOW - timedelta(days=days_ago),
        recorded_at=NOW - timedelta(days=days_ago),
        status=ObservationStatus.final,
        quality={},
        payload={},
    )


async def _seed(service: EmrService, observations: list[Observation]) -> None:
    for row in observations:
        await service.observations.add(row)


async def test_improving_labs_produce_an_improving_trajectory(
    client: TestClient, service: EmrService
) -> None:
    await _seed(service, [_hba1c(9.0, 90), _hba1c(8.3, 60), _hba1c(7.6, 30), _hba1c(7.0, 5)])
    resp = client.get("/trajectory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["direction"] == "improving"  # HbA1c falling = better (lower-is-better)
    assert 0 < body["confidence"] <= 1
    assert body["signals"][0]["source"] == "lab"
    assert "4548-4" not in body["summary"]  # plain language, no raw codes


def test_no_data_is_honest_insufficient(client: TestClient) -> None:
    resp = client.get("/trajectory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["direction"] == "insufficient_data"
    assert body["data_gaps"]  # names what's missing


async def test_only_own_observations_are_used(client: TestClient, service: EmrService) -> None:
    other_patient = uuid4()
    await _seed(
        service,
        [
            _hba1c(9.0, 90, other_patient),
            _hba1c(8.0, 45, other_patient),
            _hba1c(7.0, 5, other_patient),
        ],
    )
    resp = client.get("/trajectory")
    # The other patient's rich series must not leak into this patient's answer.
    assert resp.json()["direction"] == "insufficient_data"


def test_trajectory_requires_auth() -> None:
    with TestClient(app) as anon:
        assert anon.get("/trajectory").status_code == 401


def test_clinician_cannot_use_patient_trajectory(client: TestClient) -> None:
    # Reuse the fixture's overrides/cleanup; only the signed-in user changes.
    clinician = CurrentUser(
        user_id=uuid4(),
        role=UserRole.clinician,
        patient_id=None,
        email="dr@example.com",
        display_name="Dr",
    )
    app.dependency_overrides[get_current_user] = lambda: clinician
    assert client.get("/trajectory").status_code == 403


async def test_naive_fhir_datetime_does_not_crash_trajectory(
    client: TestClient, service: EmrService
) -> None:
    """FHIR allows date-only effectiveDateTime (parses tz-naive). A naive stored
    timestamp must never 500 the trajectory (review finding, dual-confirmed)."""
    naive = _hba1c(7.5, 0)
    # Strip the tz off the (already-recent, 0-days-ago) timestamp so it stays the latest
    # point regardless of wall clock — deliberately NAIVE to exercise date-only FHIR parsing.
    # (An earlier hardcoded absolute date drifted with the calendar and flipped the result.)
    naive.effective_at = naive.effective_at.replace(tzinfo=None)  # noqa: DTZ901 — deliberately naive
    naive.recorded_at = naive.recorded_at.replace(tzinfo=None)  # noqa: DTZ901
    await _seed(service, [_hba1c(9.0, 90), _hba1c(8.3, 60), _hba1c(7.9, 30), naive])
    resp = client.get("/trajectory")
    assert resp.status_code == 200
    assert resp.json()["direction"] == "improving"


async def test_trajectory_read_is_audit_logged(client: TestClient, service: EmrService) -> None:
    """PHI reads are audit-logged (CLAUDE.md 5) with counts only, never values."""
    await _seed(service, [_hba1c(7.0, 5)])
    assert client.get("/trajectory").status_code == 200
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert [e.action for e in events] == ["read_trajectory"]
    assert events[0].actor_id == PATIENT.user_id
    assert events[0].detail == {"observations": 1}
    assert "7.0" not in str(events[0].detail)


async def test_lookback_bounds_the_series(client: TestClient, service: EmrService) -> None:
    """Ancient rows beyond the lookback window do not reach the engine."""
    await _seed(service, [_hba1c(12.0, 5000), _hba1c(7.0, 5)])
    resp = client.get("/trajectory")
    # Only the recent point survives -> not enough evidence for a judged trend.
    assert resp.json()["direction"] == "insufficient_data"


async def test_medication_and_event_rows_never_reach_the_engine_or_narrator_facts(
    client: TestClient, service: EmrService
) -> None:
    """Medication/event capture rows (ADR-0045 P2) are record data, not signals: a med
    row's numeric DOSE under an unknown `med:{uuid}` code must not mint a spurious
    unknown-polarity signal on the trajectory surfaces, and the dose magnitude must
    never enter the facts serialized into the AI narrator prompt (the same shared
    computation feeds both — services/trajectory.py TRAJECTORY_SOURCES)."""
    from app.ai.narrative import _facts_for
    from app.services.trajectory import compute_patient_trajectory

    med = Observation(
        patient_id=PATIENT.patient_id,
        source=SourceType.medication,
        origin=DataOrigin.patient_reported,
        code="med:11111111-2222-3333-4444-555555555555",
        code_system="neuropathy-app/medication",
        value_num=613.0,  # a distinctive dose magnitude — must appear NOWHERE downstream
        value_text="Gabapentin",
        unit="mg",
        effective_at=NOW - timedelta(days=10),
        recorded_at=NOW - timedelta(days=10),
        status=ObservationStatus.final,
        quality={"human_confirmed": True, "source_mode": "manual"},
        payload={"change_type": "added", "kind": "prescription"},
    )
    fall = Observation(
        patient_id=PATIENT.patient_id,
        source=SourceType.event,
        origin=DataOrigin.patient_reported,
        code="event_fall",
        value_text="fell in the hall",
        effective_at=NOW - timedelta(days=8),
        recorded_at=NOW - timedelta(days=8),
        status=ObservationStatus.final,
        quality={"human_confirmed": True},
        payload={"type": "fall", "display": "Fall", "reviewed": False},
    )
    await _seed(service, [med, fall, _hba1c(8.0, 30), _hba1c(7.0, 5)])

    resp = client.get("/trajectory")
    assert resp.status_code == 200
    body = resp.json()
    codes = {s["code"] for s in body["signals"]}
    assert not any(code.startswith("med:") for code in codes)
    assert "event_fall" not in codes
    assert "613" not in resp.text  # the dose magnitude reaches no field of the payload
    assert "fell in the hall" not in resp.text  # nor the patient's own note text

    # The narrator prompt facts are built from the SAME trajectory: med/event rows can
    # never leak into the text POSTed to the external LLM.
    trajectory, count = await compute_patient_trajectory(
        service.observations, PATIENT.patient_id, now=NOW
    )
    facts = _facts_for(trajectory)
    assert "med:" not in facts
    assert "613" not in facts
    assert "fell in the hall" not in facts
    assert count == 2  # only the two lab rows are counted as analyzable for the engine

    # The audited read count matches the engine's analyzable set, not the raw row count.
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert events[0].detail == {"observations": 2}
