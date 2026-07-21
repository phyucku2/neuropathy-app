"""End-to-end tests for the medication + event capture endpoints (ADR-0045 P2).

Patient-role only, capability-gated, idempotent per client_entry_id, PHI-safe audit
(counts/refs only). Both surfaces ride the shared in-memory Observation store. All data
synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    CurrentUser,
    get_capability_service,
    get_current_user,
    get_emr_service,
)
from app.emr.service import EmrService
from app.main import app
from app.models.observation import SourceType
from app.models.user import UserRole
from app.services.capability import CapabilityService

NOW = datetime.now(UTC)

PATIENT = CurrentUser(
    user_id=uuid4(),
    role=UserRole.patient,
    patient_id=uuid4(),
    email="pat@example.test",
    display_name="Pat",
)


class _NoNetwork:
    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        raise AssertionError("capture must not touch the network")

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        raise AssertionError("capture must not touch the network")


@pytest.fixture()
def service() -> EmrService:
    return EmrService(transport=_NoNetwork(), client_id="c", redirect_uri="https://a/cb")


@pytest.fixture()
def cap_service() -> CapabilityService:
    return CapabilityService()


@pytest.fixture()
def client(service: EmrService, cap_service: CapabilityService) -> Iterator[TestClient]:
    app.dependency_overrides[get_emr_service] = lambda: service
    app.dependency_overrides[get_capability_service] = lambda: cap_service
    app.dependency_overrides[get_current_user] = lambda: PATIENT
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _register_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "name": "Gabapentin",
        "kind": "prescription",
        "dose_amount": 300.0,
        "dose_unit": "mg",
        "dose_text": None,
        "prescriber": "Dr Synthetic",
        "reason": "nerve pain",
        "started_on": "2026-05-01",
        "client_entry_id": str(uuid4()),
    }
    body.update(overrides)
    return body


def _event_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "type": "fall",
        "effective_date": "2026-07-10",
        "note": None,
        "client_entry_id": str(uuid4()),
    }
    body.update(overrides)
    return body


# --- medications: happy path -----------------------------------------------------------


def test_register_mints_id_and_appends_added(client: TestClient) -> None:
    resp = client.post("/medications", json=_register_body())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["medication_id"].startswith("med:")
    assert body["change_type"] == "added"
    assert body["skipped"] is False


def test_register_change_and_fold_roundtrip(client: TestClient) -> None:
    med_id = client.post("/medications", json=_register_body()).json()["medication_id"]
    change = client.post(
        f"/medications/{med_id}/changes",
        json={
            "change_type": "dose_changed",
            "dose_amount": 600.0,
            "dose_unit": "mg",
            "effective_date": "2026-06-15",
            "client_entry_id": str(uuid4()),
        },
    )
    assert change.status_code == 201, change.text
    assert change.json()["change_type"] == "dose_changed"

    listed = client.get("/medications")
    assert listed.status_code == 200
    assert listed.headers.get("cache-control") == "no-store"
    items = listed.json()["items"]
    assert len(items) == 1
    med = items[0]
    assert med["name"] == "Gabapentin"
    assert med["status"] == "active"
    assert med["current_dose_amount"] == 600.0  # latest dose wins
    assert len(med["changes"]) == 2  # the full append-only log


def test_stop_marks_stopped_but_still_listed(client: TestClient) -> None:
    med_id = client.post("/medications", json=_register_body()).json()["medication_id"]
    stop = client.post(
        f"/medications/{med_id}/changes",
        json={
            "change_type": "stopped",
            "effective_date": "2026-07-01",
            "client_entry_id": str(uuid4()),
        },
    )
    assert stop.status_code == 201, stop.text
    med = client.get("/medications").json()["items"][0]
    assert med["status"] == "stopped"  # a stopped med still renders


def test_duplicate_client_entry_id_is_a_graceful_skip(client: TestClient) -> None:
    body = _register_body()
    first = client.post("/medications", json=body).json()
    second = client.post("/medications", json=body).json()
    assert second["skipped"] is True
    assert second["medication_id"] == first["medication_id"]  # same identity, no dup row
    # Only ONE medication on file (the retry did not create a second).
    assert len(client.get("/medications").json()["items"]) == 1


# --- medications: guards ---------------------------------------------------------------


def test_change_on_unknown_medication_is_404_not_403(client: TestClient) -> None:
    resp = client.post(
        "/medications/med:does-not-exist/changes",
        json={
            "change_type": "stopped",
            "effective_date": "2026-07-01",
            "client_entry_id": str(uuid4()),
        },
    )
    assert resp.status_code == 404  # no existence leak — never 403


def test_dose_changed_without_dose_is_422(client: TestClient) -> None:
    med_id = client.post("/medications", json=_register_body()).json()["medication_id"]
    resp = client.post(
        f"/medications/{med_id}/changes",
        json={
            "change_type": "dose_changed",
            "effective_date": "2026-06-15",
            "client_entry_id": str(uuid4()),
        },
    )
    assert resp.status_code == 422


def test_future_started_on_is_422(client: TestClient) -> None:
    future = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    resp = client.post("/medications", json=_register_body(started_on=future))
    assert resp.status_code == 422


async def test_medication_capability_off_gates_the_write_but_never_the_read(
    client: TestClient, cap_service: CapabilityService
) -> None:
    """ingest_medications governs the WRITE only (capability.py contract): with the
    toggle off — which a managing clinician or the ops kill switch can flip — the
    patient's READ of their own already-captured medication log must keep answering 200
    (the same rows still render in /me/visit-summary and /me/export; a 409 here would be
    a third-party-controllable block on right-of-access)."""
    med_id = client.post("/medications", json=_register_body()).json()["medication_id"]
    await cap_service.set_for_patient(
        patient_id=PATIENT.patient_id,
        actor_id=PATIENT.user_id,
        key="ingest_medications",
        active=False,
        now=NOW,
    )
    # Writes refuse — the register AND the append-change path.
    assert client.post("/medications", json=_register_body()).status_code == 409
    change = {
        "change_type": "stopped",
        "effective_date": "2026-07-01",
        "client_entry_id": str(uuid4()),
    }
    assert client.post(f"/medications/{med_id}/changes", json=change).status_code == 409
    # The read of the already-captured record still works.
    listed = client.get("/medications")
    assert listed.status_code == 200
    assert [m["medication_id"] for m in listed.json()["items"]] == [med_id]


def test_clinician_cannot_register(client: TestClient) -> None:
    clinician = CurrentUser(
        user_id=uuid4(),
        role=UserRole.clinician,
        patient_id=None,
        email="dr@example.test",
        display_name="Dr",
        clinic_id=uuid4(),
    )
    app.dependency_overrides[get_current_user] = lambda: clinician
    assert client.post("/medications", json=_register_body()).status_code == 403


def test_register_requires_auth() -> None:
    with TestClient(app) as anon:
        assert anon.post("/medications", json=_register_body()).status_code == 401


# --- medications: audit ----------------------------------------------------------------


async def test_medication_audit_is_counts_only(client: TestClient, service: EmrService) -> None:
    client.post("/medications", json=_register_body(name="Secret Drug Name"))
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert [e.action for e in events] == ["set_medication"]
    # The free-text name/dose never reaches the audit log (PHI contract, CLAUDE.md §5).
    assert "Secret Drug Name" not in str(events[0].detail)
    assert "300" not in str(events[0].detail)


# --- events ----------------------------------------------------------------------------


def test_event_roundtrip_newest_first(client: TestClient) -> None:
    client.post("/events", json=_event_body(type="fall", effective_date="2026-07-01"))
    client.post(
        "/events",
        json=_event_body(type="note", note="Feeling steadier", effective_date="2026-07-15"),
    )
    listed = client.get("/events")
    assert listed.status_code == 200
    assert listed.headers.get("cache-control") == "no-store"
    items = listed.json()["items"]
    assert [i["type"] for i in items] == ["note", "fall"]  # newest first
    assert items[0]["note"] == "Feeling steadier"  # verbatim
    assert items[0]["reviewed"] is False


def test_two_same_day_falls_both_persist(client: TestClient) -> None:
    day = "2026-07-10"
    client.post("/events", json=_event_body(type="fall", effective_date=day))
    client.post("/events", json=_event_body(type="fall", effective_date=day))
    # Distinct client_entry_ids -> two genuine falls, both on file.
    assert len(client.get("/events").json()["items"]) == 2


def test_event_retry_with_same_id_skips(client: TestClient) -> None:
    body = _event_body(type="fall", effective_date="2026-07-10")
    first = client.post("/events", json=body).json()
    second = client.post("/events", json=body).json()
    assert second["skipped"] is True
    assert second["event_id"] == first["event_id"]
    assert len(client.get("/events").json()["items"]) == 1


def test_note_event_without_note_is_422(client: TestClient) -> None:
    assert client.post("/events", json=_event_body(type="note", note=None)).status_code == 422


def test_future_event_date_is_422(client: TestClient) -> None:
    future = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    assert client.post("/events", json=_event_body(effective_date=future)).status_code == 422


async def test_event_capability_off_gates_the_write_but_never_the_read(
    client: TestClient, cap_service: CapabilityService
) -> None:
    """Mirror of the medications posture: ingest_events off refuses NEW events (409) but
    the patient's read of already-recorded events keeps answering 200."""
    recorded = client.post("/events", json=_event_body())
    assert recorded.status_code == 201
    await cap_service.set_for_patient(
        patient_id=PATIENT.patient_id,
        actor_id=PATIENT.user_id,
        key="ingest_events",
        active=False,
        now=NOW,
    )
    assert client.post("/events", json=_event_body()).status_code == 409
    listed = client.get("/events")
    assert listed.status_code == 200
    assert [e["event_id"] for e in listed.json()["items"]] == [recorded.json()["event_id"]]


def test_event_requires_auth() -> None:
    with TestClient(app) as anon:
        assert anon.post("/events", json=_event_body()).status_code == 401


async def test_event_audit_is_counts_only(client: TestClient, service: EmrService) -> None:
    client.post("/events", json=_event_body(type="note", note="private words here"))
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert [e.action for e in events] == ["record_event"]
    # The note text never reaches the audit log (PHI contract).
    assert "private words here" not in str(events[0].detail)


async def test_rows_carry_expected_sources(client: TestClient, service: EmrService) -> None:
    client.post("/medications", json=_register_body())
    client.post("/events", json=_event_body())
    rows = await service.observations.list_for_patient(PATIENT.patient_id)
    sources = {r.source for r in rows}
    assert sources == {SourceType.medication, SourceType.event}
