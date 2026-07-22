"""End-to-end tests for the Caregiver Companion Phase B1 alert surfaces (ADR-0047):
the compute-on-read feed, the idempotent acknowledge, the 404-over-403 posture, the
scope+preference gate, ``Cache-Control: no-store``, the DEFAULT-OFF preference gate, and
the PHI-free one-audit-per-transition contract.

All data is synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_auth_service,
    get_caregiver_alert_service,
    get_caregiver_service,
)
from app.main import app
from app.models.emr_clinical_note import EmrClinicalNote
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.repositories.caregiver_alert import InMemoryCaregiverAlertRepository
from app.services.auth import AuthService
from app.services.caregiver import CaregiverService
from app.services.caregiver_alert import CaregiverAlertService

NOW = datetime.now(UTC)
SYNTHETIC_PASSWORD = "a-strong-password"


@pytest.fixture()
def caregiver_service() -> CaregiverService:
    return CaregiverService()


@pytest.fixture()
def alert_service(caregiver_service: CaregiverService) -> CaregiverAlertService:
    # Share the caregiver service (consent), users, observations, notes, audit — exactly
    # like the deps wiring shares the process singletons.
    return CaregiverAlertService(
        caregivers=caregiver_service,
        alerts=InMemoryCaregiverAlertRepository(links=caregiver_service.links),
        observations=caregiver_service.observations,
        clinical_notes=caregiver_service.clinical_notes,
        audit=caregiver_service.audit,
    )


@pytest.fixture()
def client(
    caregiver_service: CaregiverService, alert_service: CaregiverAlertService
) -> Iterator[TestClient]:
    auth = AuthService(secret="endpoint-test-secret", users=caregiver_service.users)
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_caregiver_service] = lambda: caregiver_service
    app.dependency_overrides[get_caregiver_alert_service] = lambda: alert_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_patient(
    client: TestClient, email: str = "pat@example.com", name: str = "Pat"
) -> tuple[dict[str, str], uuid.UUID]:
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": SYNTHETIC_PASSWORD, "display_name": name},
    )
    assert resp.status_code == 201
    headers = _auth(resp.json()["access_token"])
    me = client.get("/auth/me", headers=headers)
    return headers, uuid.UUID(me.json()["patient_id"])


def _create_code(client: TestClient, patient: dict[str, str]) -> str:
    resp = client.post("/me/caregiver-invites", headers=patient)
    assert resp.status_code == 201, resp.text
    return resp.json()["code"]


def _register_caregiver(
    client: TestClient, code: str, email: str = "care@example.com", name: str = "Cam Caregiver"
) -> dict[str, str]:
    resp = client.post(
        "/caregiver/register",
        json={"code": code, "email": email, "password": SYNTHETIC_PASSWORD, "display_name": name},
    )
    assert resp.status_code == 201, resp.text
    return _auth(resp.json()["access_token"])


def _accept_first_pending(client: TestClient, patient: dict[str, str]) -> str:
    links = client.get("/me/caregivers", headers=patient).json()
    link_id: str = next(row["id"] for row in links if row["status"] == "pending")
    assert client.post(f"/me/caregivers/{link_id}/accept", headers=patient).status_code == 200
    return link_id


def _linked_caregiver(
    client: TestClient, *, scope: str = "full"
) -> tuple[dict[str, str], uuid.UUID, dict[str, str], str]:
    patient, patient_id = _register_patient(client)
    code = _create_code(client, patient)
    caregiver = _register_caregiver(client, code)
    link_id = _accept_first_pending(client, patient)
    if scope != "trends":
        resp = client.patch(f"/me/caregivers/{link_id}", headers=patient, json={"scope": scope})
        assert resp.status_code == 200
    return patient, patient_id, caregiver, link_id


async def _seed_med(service: CaregiverService, patient_id: uuid.UUID) -> None:
    await service.observations.add(
        Observation(
            id=uuid.uuid4(),
            patient_id=patient_id,
            source=SourceType.medication,
            origin=DataOrigin.patient_reported,
            code=f"med:{uuid.uuid4()}",
            value_num=1.0,
            effective_at=NOW - timedelta(days=1),
            recorded_at=NOW - timedelta(days=1),
            status=ObservationStatus.final,
            quality={},
            payload={},
        )
    )


async def _seed_note(service: CaregiverService, patient_id: uuid.UUID, import_key: str) -> None:
    await service.clinical_notes.add_if_absent(
        EmrClinicalNote(
            patient_id=patient_id,
            connection_id=uuid.uuid4(),
            authored_at=NOW - timedelta(days=1),
            import_key=import_key,
        )
    )


def _set_pref(client: TestClient, patient: dict[str, str], alert_type: str, enabled: bool) -> None:
    resp = client.put(
        f"/me/caregiver-alert-preferences/{alert_type}",
        headers=patient,
        json={"enabled": enabled},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"alert_type": alert_type, "enabled": enabled}


# ---------------------------------------------------------------- preferences default OFF


def test_preferences_default_off_and_toggle(client: TestClient) -> None:
    patient, _ = _register_patient(client)
    resp = client.get("/me/caregiver-alert-preferences", headers=patient)
    assert resp.status_code == 200
    prefs = {p["alert_type"]: p["enabled"] for p in resp.json()["preferences"]}
    assert prefs == {
        "missed_checkin": False,
        "med_change": False,
        "trend_shift": False,
        "new_chart_note": False,
    }
    _set_pref(client, patient, "missed_checkin", True)
    prefs2 = {
        p["alert_type"]: p["enabled"]
        for p in client.get("/me/caregiver-alert-preferences", headers=patient).json()[
            "preferences"
        ]
    }
    assert prefs2["missed_checkin"] is True


def test_unknown_preference_type_is_422(client: TestClient) -> None:
    patient, _ = _register_patient(client)
    resp = client.put(
        "/me/caregiver-alert-preferences/not_a_type", headers=patient, json={"enabled": True}
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------- feed


async def test_feed_default_off_shows_no_alerts(
    client: TestClient, caregiver_service: CaregiverService
) -> None:
    _, patient_id, caregiver, _ = _linked_caregiver(client)
    await _seed_med(caregiver_service, patient_id)
    # No preference opted in -> DEFAULT OFF -> empty feed even with data present.
    resp = client.get("/caregiver/alerts", headers=caregiver)
    assert resp.status_code == 200
    assert resp.json()["alerts"] == []
    assert resp.headers.get("cache-control") == "no-store"


async def test_feed_is_idempotent_and_carries_the_emergency_notice(
    client: TestClient, caregiver_service: CaregiverService
) -> None:
    patient, patient_id, caregiver, _ = _linked_caregiver(client)
    _set_pref(client, patient, "med_change", True)
    await _seed_med(caregiver_service, patient_id)

    first = client.get("/caregiver/alerts", headers=caregiver).json()
    med = [a for a in first["alerts"] if a["alert_type"] == "med_change"]
    assert len(med) == 1
    assert med[0]["patient_display_name"] == "Pat"
    assert "911" in first["emergency_notice"]
    assert med[0]["acknowledged_at"] is None
    # A second read persists nothing new (add_if_absent dedupe).
    second = client.get("/caregiver/alerts", headers=caregiver).json()
    med2 = [a for a in second["alerts"] if a["alert_type"] == "med_change"]
    assert len(med2) == 1
    assert med2[0]["id"] == med[0]["id"]


async def test_trends_scope_never_shows_or_acks_med_alerts(
    client: TestClient, caregiver_service: CaregiverService
) -> None:
    # A trends-only caregiver, every type opted in, med + note data present.
    patient, patient_id, caregiver, _ = _linked_caregiver(client, scope="trends")
    for atype in ("missed_checkin", "med_change", "trend_shift", "new_chart_note"):
        _set_pref(client, patient, atype, True)
    await _seed_med(caregiver_service, patient_id)
    await _seed_note(caregiver_service, patient_id, "doc-1")

    feed = client.get("/caregiver/alerts", headers=caregiver).json()["alerts"]
    types = {a["alert_type"] for a in feed}
    assert "med_change" not in types
    assert "new_chart_note" not in types


# ---------------------------------------------------------------- acknowledge


async def test_ack_is_idempotent_with_a_single_audit(
    client: TestClient, caregiver_service: CaregiverService
) -> None:
    patient, patient_id, caregiver, _ = _linked_caregiver(client)
    _set_pref(client, patient, "med_change", True)
    await _seed_med(caregiver_service, patient_id)
    alert = client.get("/caregiver/alerts", headers=caregiver).json()["alerts"][0]

    first = client.post(f"/caregiver/alerts/{alert['id']}/ack", headers=caregiver)
    assert first.status_code == 204
    # Double-ack: quiet 204 again.
    second = client.post(f"/caregiver/alerts/{alert['id']}/ack", headers=caregiver)
    assert second.status_code == 204

    ack_events = [
        e
        for e in caregiver_service.audit._events  # type: ignore[attr-defined]
        if e.action == "caregiver_alert_ack"
    ]
    assert len(ack_events) == 1
    # The alert now reads acknowledged.
    feed = client.get("/caregiver/alerts", headers=caregiver).json()["alerts"]
    acked = next(a for a in feed if a["id"] == alert["id"])
    assert acked["acknowledged_at"] is not None


def test_ack_unknown_alert_is_404(client: TestClient) -> None:
    _, _, caregiver, _ = _linked_caregiver(client)
    resp = client.post(f"/caregiver/alerts/{uuid.uuid4()}/ack", headers=caregiver)
    assert resp.status_code == 404


def test_ack_requires_caregiver_role(client: TestClient) -> None:
    patient, _ = _register_patient(client, email="solo@example.com")
    resp = client.post(f"/caregiver/alerts/{uuid.uuid4()}/ack", headers=patient)
    assert resp.status_code == 403


def test_feed_requires_caregiver_role(client: TestClient) -> None:
    patient, _ = _register_patient(client, email="solo2@example.com")
    assert client.get("/caregiver/alerts", headers=patient).status_code == 403


# ---------------------------------------------------------------- audit + push counts


async def test_one_feed_audit_per_read_and_push_on_new_alert(
    client: TestClient,
    caregiver_service: CaregiverService,
    alert_service: CaregiverAlertService,
) -> None:
    patient, patient_id, caregiver, _ = _linked_caregiver(client)
    _set_pref(client, patient, "med_change", True)
    await _seed_med(caregiver_service, patient_id)

    client.get("/caregiver/alerts", headers=caregiver)
    # The push seam accrued exactly one message — only the newly-inserted alert (the
    # route schedules the post-commit fan-out from these; PHI-free body).
    assert len(alert_service.pending_pushes) == 1
    message = alert_service.pending_pushes[0]
    assert message.alert_type == "med_change"
    assert "911" in message.body

    # Second read: the alert is a duplicate (add_if_absent False) — nothing accrues.
    client.get("/caregiver/alerts", headers=caregiver)
    assert alert_service.pending_pushes == []

    feed_events = [
        e
        for e in caregiver_service.audit._events  # type: ignore[attr-defined]
        if e.action == "caregiver_alert_feed"
    ]
    assert len(feed_events) == 2  # one per read
    assert all("patients" in e.detail and "alerts" in e.detail for e in feed_events)


def test_one_pref_audit_per_change(client: TestClient, caregiver_service: CaregiverService) -> None:
    patient, _ = _register_patient(client)
    _set_pref(client, patient, "trend_shift", True)
    # No-change PUT: quiet success, no second audit.
    _set_pref(client, patient, "trend_shift", True)
    pref_events = [
        e
        for e in caregiver_service.audit._events  # type: ignore[attr-defined]
        if e.action == "set_caregiver_alert_preference"
    ]
    assert len(pref_events) == 1
