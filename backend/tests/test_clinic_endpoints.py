"""End-to-end tests for the clinician surface (ADR-0012): provisioning, invitations,
the consent lifecycle, the consented-only panel, and the 404-over-403 posture on
every /clinic/patients/{id}/* view.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_service, get_clinic_service
from app.core.config import settings
from app.main import app
from app.models.connection import ClinicConnection, ConnectionStatus, Initiator
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.models.user import UserRole
from app.repositories.clinic_connection import (
    DuplicateLiveConnectionError,
    InMemoryClinicConnectionRepository,
)
from app.repositories.user import UserRecord
from app.services.auth import AuthService
from app.services.clinic import ClinicService

NOW = datetime.now(UTC)
BOOTSTRAP = {"X-Bootstrap-Token": "test-bootstrap-value"}


@pytest.fixture()
def clinic_service() -> ClinicService:
    return ClinicService()


@pytest.fixture()
def client(clinic_service: ClinicService, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Auth and clinic flows share ONE user store, exactly like the deps wiring does.
    auth = AuthService(secret="endpoint-test-secret", users=clinic_service.users)
    monkeypatch.setattr(settings, "ops_bootstrap_token", "test-bootstrap-value")
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_clinic_service] = lambda: clinic_service
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
        json={"email": email, "password": "a-strong-password", "display_name": name},
    )
    assert resp.status_code == 201
    headers = _auth(resp.json()["access_token"])
    me = client.get("/auth/me", headers=headers)
    return headers, uuid.UUID(me.json()["patient_id"])


def _create_clinician(
    client: TestClient,
    email: str = "dr@example.com",
    clinic_name: str = "Advanced Health & Wellness Group",
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    """Provision + log in a clinician; returns (headers, clinic_id, user_id)."""
    resp = client.post(
        "/clinic/clinicians",
        headers=BOOTSTRAP,
        json={
            "email": email,
            "password": "a-strong-password",
            "display_name": "Dr. Rivera",
            "clinic_name": clinic_name,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    login = client.post("/auth/login", json={"email": email, "password": "a-strong-password"})
    return (
        _auth(login.json()["access_token"]),
        uuid.UUID(body["clinic_id"]),
        uuid.UUID(body["user_id"]),
    )


def _connect_consented_patient(
    client: TestClient, clinician: dict[str, str], email: str = "pat@example.com"
) -> tuple[dict[str, str], uuid.UUID, str]:
    """Register + invite + consent; returns (patient headers, patient_id, connection id)."""
    patient, patient_id = _register_patient(client, email=email)
    assert (
        client.post("/clinic/invitations", headers=clinician, json={"email": email}).status_code
        == 202
    )
    connection_id = client.get("/connections", headers=patient).json()[0]["id"]
    assert client.post(f"/connections/{connection_id}/consent", headers=patient).status_code == 200
    return patient, patient_id, connection_id


def _hba1c(value: float, days_ago: float, patient_id: uuid.UUID) -> Observation:
    return Observation(
        patient_id=patient_id,
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


async def _seed_improving_labs(service: ClinicService, patient_id: uuid.UUID) -> None:
    for value, days_ago in ((9.0, 90), (8.3, 60), (7.6, 30), (7.0, 5)):
        await service.observations.add(_hba1c(value, days_ago, patient_id))


# ---------------------------------------------------------------- provisioning


def test_bootstrap_fails_closed_when_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ops_bootstrap_token", None)
    resp = client.post(
        "/clinic/clinicians",
        headers=BOOTSTRAP,
        json={
            "email": "dr@example.com",
            "password": "a-strong-password",
            "display_name": "Dr",
            "clinic_name": "C",
        },
    )
    assert resp.status_code == 403


def test_bootstrap_rejects_wrong_or_missing_token(client: TestClient) -> None:
    body = {
        "email": "dr@example.com",
        "password": "a-strong-password",
        "display_name": "Dr",
        "clinic_name": "C",
    }
    wrong = client.post("/clinic/clinicians", headers={"X-Bootstrap-Token": "nope"}, json=body)
    missing = client.post("/clinic/clinicians", json=body)
    assert wrong.status_code == 403
    assert missing.status_code == 403


def test_bootstrap_creates_clinician_bound_to_new_clinic(client: TestClient) -> None:
    _, clinic_id, _ = _create_clinician(client)
    # A colleague joins the SAME clinic by id.
    resp = client.post(
        "/clinic/clinicians",
        headers=BOOTSTRAP,
        json={
            "email": "dr2@example.com",
            "password": "a-strong-password",
            "display_name": "Dr. Two",
            "clinic_id": str(clinic_id),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["clinic_id"] == str(clinic_id)
    assert resp.json()["clinic_name"] == "Advanced Health & Wellness Group"


def test_bootstrap_unknown_clinic_id_is_422(client: TestClient) -> None:
    resp = client.post(
        "/clinic/clinicians",
        headers=BOOTSTRAP,
        json={
            "email": "dr@example.com",
            "password": "a-strong-password",
            "display_name": "Dr",
            "clinic_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 422


def test_bootstrap_requires_exactly_one_clinic_reference(client: TestClient) -> None:
    base = {"email": "dr@example.com", "password": "a-strong-password", "display_name": "Dr"}
    neither = client.post("/clinic/clinicians", headers=BOOTSTRAP, json=base)
    both = client.post(
        "/clinic/clinicians",
        headers=BOOTSTRAP,
        json={**base, "clinic_id": str(uuid.uuid4()), "clinic_name": "C"},
    )
    assert neither.status_code == 422
    assert both.status_code == 422


def test_bootstrap_duplicate_email_is_409(client: TestClient) -> None:
    _create_clinician(client)
    resp = client.post(
        "/clinic/clinicians",
        headers=BOOTSTRAP,
        json={
            "email": "dr@example.com",
            "password": "another-pass-1",
            "display_name": "Dr Again",
            "clinic_name": "Other Clinic",
        },
    )
    assert resp.status_code == 409


def test_failed_provisioning_leaves_no_orphan_clinic(
    client: TestClient, clinic_service: ClinicService
) -> None:
    """A clinic founded in a provisioning request that 409s must not survive it —
    otherwise retries accumulate same-name duplicates (review finding)."""
    _create_clinician(client)
    resp = client.post(
        "/clinic/clinicians",
        headers=BOOTSTRAP,
        json={
            "email": "dr@example.com",  # duplicate — provisioning fails
            "password": "another-pass-1",
            "display_name": "Dr Again",
            "clinic_name": "Orphan Clinic",
        },
    )
    assert resp.status_code == 409
    assert len(clinic_service.clinics._clinics) == 1  # only the first clinic remains


# ---------------------------------------------------------------- invitations


def test_invitation_response_never_enumerates_accounts(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    _register_patient(client, email="real@example.com")
    matched = client.post(
        "/clinic/invitations", headers=clinician, json={"email": "real@example.com"}
    )
    unmatched = client.post(
        "/clinic/invitations", headers=clinician, json={"email": "nobody@example.com"}
    )
    assert matched.status_code == unmatched.status_code == 202
    assert matched.content == unmatched.content  # byte-identical bodies


def test_invitation_creates_one_pending_connection(client: TestClient) -> None:
    clinician, clinic_id, _ = _create_clinician(client)
    patient, _ = _register_patient(client)
    for _ in range(2):  # a repeated invitation must not duplicate the connection
        client.post("/clinic/invitations", headers=clinician, json={"email": "pat@example.com"})
    rows = client.get("/connections", headers=patient).json()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["initiated_by"] == "clinic"
    assert rows[0]["clinic_id"] == str(clinic_id)
    assert rows[0]["clinic_name"] == "Advanced Health & Wellness Group"
    assert rows[0]["consent_granted_at"] is None


def test_invitation_to_clinician_email_creates_nothing(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    resp = client.post("/clinic/invitations", headers=clinician, json={"email": "dr@example.com"})
    assert resp.status_code == 202  # same non-enumerating answer; no connection appears


def test_invitations_require_clinician(client: TestClient) -> None:
    patient, _ = _register_patient(client)
    resp = client.post("/clinic/invitations", headers=patient, json={"email": "x@example.com"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Clinician account required"


async def test_storage_rejects_second_live_connection_per_patient_clinic_pair() -> None:
    """The in-memory twin of the uq_clinic_connection_live partial unique index:
    one live connection per patient-clinic pair, fresh ones allowed after revocation."""
    repo = InMemoryClinicConnectionRepository()
    patient_id, clinic_id = uuid.uuid4(), uuid.uuid4()
    first = await repo.add(
        ClinicConnection(
            patient_id=patient_id,
            clinic_id=clinic_id,
            status=ConnectionStatus.pending,
            initiated_by=Initiator.clinic,
        )
    )
    with pytest.raises(DuplicateLiveConnectionError):
        await repo.add(
            ClinicConnection(
                patient_id=patient_id,
                clinic_id=clinic_id,
                status=ConnectionStatus.pending,
                initiated_by=Initiator.clinic,
            )
        )
    # A different clinic is a different pair — allowed.
    await repo.add(
        ClinicConnection(
            patient_id=patient_id,
            clinic_id=uuid.uuid4(),
            status=ConnectionStatus.pending,
            initiated_by=Initiator.clinic,
        )
    )
    # Revoked rows leave the index: the patient may reconnect later.
    first.status = ConnectionStatus.revoked
    await repo.update(first)
    await repo.add(
        ClinicConnection(
            patient_id=patient_id,
            clinic_id=clinic_id,
            status=ConnectionStatus.pending,
            initiated_by=Initiator.clinic,
        )
    )


async def test_invitation_absorbs_a_lost_duplicate_race() -> None:
    """When a concurrent invitation wins the check-then-insert race, storage raises
    DuplicateLiveConnectionError and the invite absorbs it: no error escapes (the 202
    stays identical) and the audit trail records created=False."""

    class RacedRepository(InMemoryClinicConnectionRepository):
        async def add(self, connection: ClinicConnection) -> ClinicConnection:
            raise DuplicateLiveConnectionError(connection.patient_id, connection.clinic_id)

    service = ClinicService(connections=RacedRepository())
    patient_id = uuid.uuid4()
    await service.users.add(
        UserRecord(
            id=uuid.uuid4(),
            email="race@example.com",
            password_hash="synthetic-hash",
            display_name="Race",
            role=UserRole.patient,
            patient_id=patient_id,
        )
    )
    await service.invite_patient(
        clinic_id=uuid.uuid4(), actor_id=uuid.uuid4(), email="race@example.com"
    )
    (event,) = await service.audit.list_for_patient(patient_id)
    assert event.detail["matched"] is True
    assert event.detail["created"] is False


# ---------------------------------------------------------------- consent lifecycle


def test_consent_lifecycle_invite_consent_revoke(
    client: TestClient, clinic_service: ClinicService
) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, patient_id, connection_id = _connect_consented_patient(client, clinician)

    active = client.get("/connections", headers=patient).json()[0]
    assert active["status"] == "active"
    assert active["consent_granted_at"] is not None

    panel = client.get("/clinic/patients", headers=clinician).json()["patients"]
    assert [p["patient_id"] for p in panel] == [str(patient_id)]
    assert panel[0]["display_name"] == "Pat"

    assert client.delete(f"/connections/{connection_id}", headers=patient).status_code == 204
    revoked = client.get("/connections", headers=patient).json()[0]
    assert revoked["status"] == "revoked"
    assert revoked["revoked_at"] is not None
    assert client.get("/clinic/patients", headers=clinician).json()["patients"] == []


def test_panel_excludes_pending_connections(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    _register_patient(client)
    client.post("/clinic/invitations", headers=clinician, json={"email": "pat@example.com"})
    assert client.get("/clinic/patients", headers=clinician).json()["patients"] == []


def test_consent_on_foreign_connection_is_404(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    _, _, connection_id = _connect_consented_patient(client, clinician, email="one@example.com")
    other, _ = _register_patient(client, email="two@example.com", name="Two")
    assert client.post(f"/connections/{connection_id}/consent", headers=other).status_code == 404
    assert client.delete(f"/connections/{connection_id}", headers=other).status_code == 404


def test_consent_is_single_fire(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, _, connection_id = _connect_consented_patient(client, clinician)
    # Already active: a second consent (and consent on unknown ids) is 404.
    assert client.post(f"/connections/{connection_id}/consent", headers=patient).status_code == 404
    assert client.post(f"/connections/{uuid.uuid4()}/consent", headers=patient).status_code == 404


def test_revoke_is_idempotent(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, _, connection_id = _connect_consented_patient(client, clinician)
    assert client.delete(f"/connections/{connection_id}", headers=patient).status_code == 204
    assert client.delete(f"/connections/{connection_id}", headers=patient).status_code == 204
    assert client.delete(f"/connections/{uuid.uuid4()}", headers=patient).status_code == 404


def test_revoked_connection_cannot_be_reconsented(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, _, connection_id = _connect_consented_patient(client, clinician)
    client.delete(f"/connections/{connection_id}", headers=patient)
    assert client.post(f"/connections/{connection_id}/consent", headers=patient).status_code == 404


def test_connection_endpoints_require_patient(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    assert client.get("/connections", headers=clinician).status_code == 403
    with TestClient(app) as anon:
        assert anon.get("/connections").status_code == 401


# ---------------------------------------------------------------- clinician reads


async def test_clinician_trajectory_is_deterministic_only(
    client: TestClient, clinic_service: ClinicService
) -> None:
    clinician, _, _ = _create_clinician(client)
    _, patient_id, _ = _connect_consented_patient(client, clinician)
    await _seed_improving_labs(clinic_service, patient_id)
    resp = client.get(f"/clinic/patients/{patient_id}/trajectory", headers=clinician)
    assert resp.status_code == 200
    body = resp.json()
    assert body["direction"] == "improving"
    # NEVER the AI narrative on the clinician surface (ADR-0012).
    assert body["narrative_source"] == "deterministic"
    assert "4548-4" not in body["summary"]  # plain language, no raw codes


async def test_clinician_observations_return_consented_patient_rows(
    client: TestClient, clinic_service: ClinicService
) -> None:
    clinician, _, _ = _create_clinician(client)
    _, patient_id, _ = _connect_consented_patient(client, clinician)
    await _seed_improving_labs(clinic_service, patient_id)
    resp = client.get(f"/clinic/patients/{patient_id}/observations", headers=clinician)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    assert body["items"][0]["code"] == "4548-4"
    assert body["items"][0]["value"] == 7.0  # newest first


def test_cross_clinic_access_is_404_not_403(client: TestClient) -> None:
    clinician_a, _, _ = _create_clinician(client)
    _, patient_id, _ = _connect_consented_patient(client, clinician_a)
    clinician_b, _, _ = _create_clinician(
        client, email="dr-b@example.com", clinic_name="Other Clinic"
    )
    for path in (
        f"/clinic/patients/{patient_id}/trajectory",
        f"/clinic/patients/{patient_id}/observations",
    ):
        resp = client.get(path, headers=clinician_b)
        # 404 — the record must be indistinguishable from a nonexistent one.
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Patient not found"
    assert client.get("/clinic/patients", headers=clinician_b).json()["patients"] == []


def test_nonconsented_patient_is_404_for_own_clinic(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    _, patient_id = _register_patient(client)
    client.post("/clinic/invitations", headers=clinician, json={"email": "pat@example.com"})
    # Pending, not consented: no read allowed, and the answer is 404, not 403.
    resp = client.get(f"/clinic/patients/{patient_id}/trajectory", headers=clinician)
    assert resp.status_code == 404


def test_revocation_cuts_off_clinician_reads(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, patient_id, connection_id = _connect_consented_patient(client, clinician)
    assert (
        client.get(f"/clinic/patients/{patient_id}/trajectory", headers=clinician).status_code
        == 200
    )
    client.delete(f"/connections/{connection_id}", headers=patient)
    assert (
        client.get(f"/clinic/patients/{patient_id}/trajectory", headers=clinician).status_code
        == 404
    )


def test_clinic_patient_views_require_clinician(client: TestClient) -> None:
    patient, patient_id = _register_patient(client)
    assert client.get("/clinic/patients", headers=patient).status_code == 403
    assert (
        client.get(f"/clinic/patients/{patient_id}/trajectory", headers=patient).status_code == 403
    )
    with TestClient(app) as anon:
        assert anon.get("/clinic/patients").status_code == 401


# ---------------------------------------------------------------- audit trail


async def test_clinician_reads_are_audited_with_clinician_actor(
    client: TestClient, clinic_service: ClinicService
) -> None:
    clinician, _, clinician_user_id = _create_clinician(client)
    _, patient_id, connection_id = _connect_consented_patient(client, clinician)
    client.get("/clinic/patients", headers=clinician)
    client.get(f"/clinic/patients/{patient_id}/trajectory", headers=clinician)
    client.get(f"/clinic/patients/{patient_id}/observations", headers=clinician)

    events = await clinic_service.audit.list_for_patient(patient_id)
    by_action = {e.action: e for e in events}
    for action in ("read_panel", "read_trajectory", "read_observations"):
        event = by_action[action]
        assert event.actor_id == clinician_user_id  # the CLINICIAN is the actor
        assert event.actor_role == "clinician"
        assert event.patient_id == patient_id  # the patient is the subject
        assert event.detail.get("connection_id") == connection_id


async def test_invitation_consent_and_revocation_are_audited(
    client: TestClient, clinic_service: ClinicService
) -> None:
    clinician, clinic_id, clinician_user_id = _create_clinician(client)
    patient, patient_id, connection_id = _connect_consented_patient(client, clinician)
    client.delete(f"/connections/{connection_id}", headers=patient)

    events = await clinic_service.audit.list_for_patient(patient_id)
    actions = [e.action for e in events]
    assert actions == ["invite_patient", "grant_consent", "revoke_connection"]
    invite, consent, revoke = events
    assert invite.actor_id == clinician_user_id
    assert invite.detail == {"clinic_id": str(clinic_id), "matched": True, "created": True}
    assert "example.com" not in str(invite.detail)  # references only, never the email
    assert consent.actor_role == "patient"
    assert revoke.actor_role == "patient"
    assert revoke.detail["connection_id"] == connection_id
