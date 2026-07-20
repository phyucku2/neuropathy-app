"""End-to-end tests for the Visit-Ready Summary endpoints (ADR-0045 Phase 1):

- Patient: GET /me/visit-summary (PatientUserDep + EmrServiceDep)
- Clinician: GET /clinic/patients/{id}/visit-summary (ClinicianUserDep + ClinicServiceDep,
  behind the consented-connection gate, non-enumerating 404)

Both resolve now=datetime.now(UTC) (wall clock), so these assert STRUCTURAL facts,
counts, and flags — never exact dates; exact-date determinism is proven by the pure
`assemble_visit_summary` unit tests. Rows are seeded at offsets from a module-level NOW
(the trajectory-endpoint idiom). All data is synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    CurrentUser,
    get_auth_service,
    get_clinic_service,
    get_current_user,
    get_emr_service,
)
from app.core.config import settings
from app.emr.service import EmrService
from app.main import app
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.models.user import UserRole
from app.services.auth import AuthService
from app.services.clinic import ClinicService

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
        raise AssertionError("visit-summary must not touch the network")

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        raise AssertionError("visit-summary must not touch the network")


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


def _obs(
    code: str,
    value: float,
    days_ago: float,
    *,
    source: SourceType = SourceType.adl,
    origin: DataOrigin = DataOrigin.patient_reported,
    unit: str | None = None,
    patient_id: UUID | None = None,
) -> Observation:
    at = NOW - timedelta(days=days_ago)
    return Observation(
        patient_id=PATIENT.patient_id if patient_id is None else patient_id,
        source=source,
        origin=origin,
        code=code,
        value_num=value,
        unit=unit,
        effective_at=at,
        recorded_at=at,
        status=ObservationStatus.final,
        quality={},
        payload={},
    )


async def _seed(service: EmrService, rows: list[Observation]) -> None:
    for row in rows:
        await service.observations.add(row)


# ------------------------------------------------------------------ patient surface


async def test_patient_visit_summary_defaults_to_window_60(
    client: TestClient, service: EmrService
) -> None:
    await _seed(service, [_obs("symptom_pain", 4.0, 20), _obs("symptom_pain", 3.0, 5)])
    resp = client.get("/me/visit-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_days"] == 60
    assert body["schema_version"] == "1.1"
    assert body["subject_id"] == str(PATIENT.patient_id)
    assert body["lead_section"] == "what_changed"  # 60 is a short window
    assert body["disclaimer"]  # non-diagnostic note co-located
    assert body["sheet_label"] == "current record, not a complete medical record"
    assert body["status"]["narrative_source"] == "deterministic"


async def test_window_selection_changes_the_payload_and_lead_section(
    client: TestClient, service: EmrService
) -> None:
    await _seed(
        service,
        [
            _obs("symptom_pain", 6.0, 200),
            _obs("symptom_pain", 5.0, 100),
            _obs("symptom_pain", 4.0, 50),
            _obs("symptom_pain", 3.0, 20),
            _obs("symptom_pain", 2.0, 5),
        ],
    )
    short = client.get("/me/visit-summary", params={"window": 30}).json()
    long = client.get("/me/visit-summary", params={"window": 365}).json()

    # 30 leads with the diff; 365 leads with the trajectory over time.
    assert short["lead_section"] == "what_changed"
    assert long["lead_section"] == "trajectory"
    # The 30-day window excludes the older rows the 365-day window keeps.
    short_pts = short["symptoms"][0]["points"] if short["symptoms"] else []
    long_pts = long["symptoms"][0]["points"] if long["symptoms"] else []
    assert len(long_pts) > len(short_pts)
    assert short != long


@pytest.mark.parametrize("window", [45, 0, 400, -60, "abc"])
def test_disallowed_window_is_422(client: TestClient, window: object) -> None:
    resp = client.get("/me/visit-summary", params={"window": window})
    assert resp.status_code == 422


def test_anonymous_is_401() -> None:
    with TestClient(app) as anon:
        assert anon.get("/me/visit-summary").status_code == 401


def test_non_patient_is_403(client: TestClient) -> None:
    clinician = CurrentUser(
        user_id=uuid4(),
        role=UserRole.clinician,
        patient_id=None,
        email="dr@example.com",
        display_name="Dr",
        clinic_id=uuid4(),
    )
    app.dependency_overrides[get_current_user] = lambda: clinician
    assert client.get("/me/visit-summary").status_code == 403


async def test_read_is_audited_counts_only(client: TestClient, service: EmrService) -> None:
    await _seed(
        service,
        [
            _obs(
                "4548-4", 7.0, 10, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"
            ),
            _obs(
                "4548-4", 8.0, 30, source=SourceType.lab, origin=DataOrigin.ehr_imported, unit="%"
            ),
        ],
    )
    assert client.get("/me/visit-summary").status_code == 200
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert [e.action for e in events] == ["read_visit_summary"]
    event = events[0]
    assert event.actor_id == PATIENT.user_id
    assert event.actor_role == "patient"
    assert event.patient_id == PATIENT.patient_id
    assert event.detail == {"observations": 2, "window_days": 60}
    # Counts only — no measured value ever enters the audit detail.
    assert "7.0" not in json.dumps(event.detail)
    assert "8.0" not in json.dumps(event.detail)


async def test_response_is_no_store(client: TestClient, service: EmrService) -> None:
    await _seed(service, [_obs("symptom_pain", 3.0, 5)])
    resp = client.get("/me/visit-summary")
    assert resp.headers.get("cache-control") == "no-store"


async def test_payload_carries_no_secret_fixture(client: TestClient, service: EmrService) -> None:
    """Secrets-absent-by-construction (ADR-0031/0045): a synthetic token vaulted in the
    EMR secret store can never appear in the Summary body — there is no field for it."""
    synthetic_token = "synthetic-visit-summary-token"  # noqa: S105 — synthetic fixture
    await service.secret_store.put({"access_token": synthetic_token})
    await _seed(service, [_obs("symptom_pain", 3.0, 5)])
    resp = client.get("/me/visit-summary")
    assert resp.status_code == 200
    assert synthetic_token not in json.dumps(resp.json())


# ------------------------------------------------------------------ clinician surface

# ≥ 32 chars — the settings-load minimum a real deployment must meet (ADR-0017).
BOOTSTRAP_TOKEN = "synthetic-bootstrap-token-0123456789abcdef"
BOOTSTRAP = {"X-Bootstrap-Token": BOOTSTRAP_TOKEN}


@pytest.fixture()
def clinic_emr() -> EmrService:
    return EmrService(transport=_NoNetwork(), client_id="c", redirect_uri="https://a/cb")


@pytest.fixture()
def clinic_auth() -> AuthService:
    return AuthService(secret="endpoint-test-secret")


@pytest.fixture()
def clinic_service(clinic_emr: EmrService, clinic_auth: AuthService) -> ClinicService:
    # Wire the clinic service on the SAME stores the patient's own EmrService uses, so
    # /me/visit-summary and /clinic/.../visit-summary read one shared record (deps parity).
    return ClinicService(
        users=clinic_auth.users, observations=clinic_emr.observations, audit=clinic_emr.audit
    )


@pytest.fixture()
def clinic_client(
    clinic_service: ClinicService,
    clinic_emr: EmrService,
    clinic_auth: AuthService,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "ops_bootstrap_token", BOOTSTRAP_TOKEN)
    app.dependency_overrides[get_auth_service] = lambda: clinic_auth
    app.dependency_overrides[get_clinic_service] = lambda: clinic_service
    app.dependency_overrides[get_emr_service] = lambda: clinic_emr
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_patient(
    client: TestClient, email: str = "pat@example.com"
) -> tuple[dict[str, str], UUID]:
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": "a-strong-password", "display_name": "Pat"},
    )
    assert resp.status_code == 201
    headers = _auth(resp.json()["access_token"])
    me = client.get("/auth/me", headers=headers)
    return headers, uuid.UUID(me.json()["patient_id"])


def _ops_headers(client: TestClient) -> dict[str, str]:
    client.post(
        "/ops/accounts",
        headers=BOOTSTRAP,
        json={"email": "ops@example.com", "password": "a-strong-password", "display_name": "Ops"},
    )
    login = client.post(
        "/auth/login", json={"email": "ops@example.com", "password": "a-strong-password"}
    )
    return _auth(login.json()["access_token"])


def _create_clinician(
    client: TestClient, email: str = "dr@example.com", clinic_name: str = "Synthetic Clinic"
) -> dict[str, str]:
    resp = client.post(
        "/clinic/clinicians",
        headers=_ops_headers(client),
        json={
            "email": email,
            "password": "a-strong-password",
            "display_name": "Dr. Rivera",
            "clinic_name": clinic_name,
        },
    )
    assert resp.status_code == 201, resp.text
    login = client.post("/auth/login", json={"email": email, "password": "a-strong-password"})
    return _auth(login.json()["access_token"])


def _connect_consented(
    client: TestClient, clinician: dict[str, str], email: str = "pat@example.com"
) -> tuple[dict[str, str], UUID]:
    patient, patient_id = _register_patient(client, email=email)
    assert (
        client.post("/clinic/invitations", headers=clinician, json={"email": email}).status_code
        == 202
    )
    connection_id = client.get("/connections", headers=patient).json()[0]["id"]
    assert client.post(f"/connections/{connection_id}/consent", headers=patient).status_code == 200
    return patient, patient_id


async def _seed_symptom_change(service: ClinicService, patient_id: UUID) -> None:
    rows = [
        _obs("symptom_numbness", 2.0, 118, patient_id=patient_id),
        _obs("symptom_numbness", 5.0, 105, patient_id=patient_id),
        _obs("symptom_numbness", 8.0, 95, patient_id=patient_id),
        _obs("symptom_numbness", 8.0, 55, patient_id=patient_id),
        _obs("symptom_numbness", 5.0, 40, patient_id=patient_id),
        _obs("symptom_numbness", 2.0, 20, patient_id=patient_id),
    ]
    for row in rows:
        await service.observations.add(row)


async def test_clinician_visit_summary_matches_patient_shape(
    clinic_client: TestClient, clinic_service: ClinicService
) -> None:
    clinician = _create_clinician(clinic_client)
    patient, patient_id = _connect_consented(clinic_client, clinician)
    await _seed_symptom_change(clinic_service, patient_id)

    clin = clinic_client.get(f"/clinic/patients/{patient_id}/visit-summary", headers=clinician)
    pat = clinic_client.get("/me/visit-summary", headers=patient)
    assert clin.status_code == 200
    assert pat.status_code == 200
    clin_body, pat_body = clin.json(), pat.json()
    # Same VisitSummary shape/data (barring the wall-clock generated_at/boundaries).
    assert clin_body["status"]["narrative_source"] == "deterministic"
    assert clin_body["status"]["direction"] == pat_body["status"]["direction"]
    assert [s["code"] for s in clin_body["symptoms"]] == [s["code"] for s in pat_body["symptoms"]]
    assert clin_body["window_days"] == pat_body["window_days"] == 60


async def test_clinician_visit_summary_shows_meds_and_events(
    clinic_client: TestClient, clinic_service: ClinicService
) -> None:
    """The consented clinician sees the patient's captured medications & events through the
    SAME assembly (one source of truth) — meds fold, events surface, and a med change in the
    window appears in the what-changed delta (ADR-0045 P2)."""
    clinician = _create_clinician(clinic_client)
    _, patient_id = _connect_consented(clinic_client, clinician)
    med = Observation(
        patient_id=patient_id,
        source=SourceType.medication,
        origin=DataOrigin.patient_reported,
        code="med:aaa",
        code_system="neuropathy-app/medication",
        value_num=300.0,
        value_text="Gabapentin",
        unit="mg",
        effective_at=NOW - timedelta(days=10),
        recorded_at=NOW - timedelta(days=10),
        status=ObservationStatus.final,
        quality={"human_confirmed": True, "source_mode": "manual"},
        payload={"change_type": "added", "kind": "prescription", "prescriber": "Dr X"},
    )
    fall = Observation(
        patient_id=patient_id,
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
    await clinic_service.observations.add(med)
    await clinic_service.observations.add(fall)

    body = clinic_client.get(
        f"/clinic/patients/{patient_id}/visit-summary", headers=clinician
    ).json()
    assert [m["medication_id"] for m in body["medications"]] == ["med:aaa"]
    assert body["medications"][0]["provenance"] == "patient-entered"
    assert [n["type"] for n in body["patient_notes"]] == ["fall"]
    assert body["patient_notes"][0]["note"] == "fell in the hall"  # patient's own words
    assert [d["medication_id"] for d in body["what_changed"]["medication_changes"]] == ["med:aaa"]


def test_clinician_non_consented_is_404_not_403(
    clinic_client: TestClient,
) -> None:
    clinician = _create_clinician(clinic_client)
    # A patient with no consented connection to this clinic, and an unknown id: both 404.
    _, patient_id = _register_patient(clinic_client)
    clinic_client.post("/clinic/invitations", headers=clinician, json={"email": "pat@example.com"})
    resp = clinic_client.get(f"/clinic/patients/{patient_id}/visit-summary", headers=clinician)
    assert resp.status_code == 404
    unknown = clinic_client.get(f"/clinic/patients/{uuid4()}/visit-summary", headers=clinician)
    assert unknown.status_code == 404


async def test_clinician_read_is_audited_with_connection_id(
    clinic_client: TestClient, clinic_service: ClinicService
) -> None:
    clinician = _create_clinician(clinic_client)
    _, patient_id = _connect_consented(clinic_client, clinician)
    await _seed_symptom_change(clinic_service, patient_id)
    assert (
        clinic_client.get(
            f"/clinic/patients/{patient_id}/visit-summary", headers=clinician
        ).status_code
        == 200
    )
    events = await clinic_service.audit.list_for_patient(patient_id)
    reads = [e for e in events if e.action == "read_visit_summary"]
    assert len(reads) == 1
    detail = reads[0].detail
    assert reads[0].actor_role == "clinician"
    assert reads[0].patient_id == patient_id
    assert detail["window_days"] == 60
    assert "connection_id" in detail
    assert "observations" in detail
    # Counts/refs only — the seeded symptom values never enter the audit detail.
    assert "8.0" not in json.dumps(detail)


def test_clinician_window_422_mirror(clinic_client: TestClient) -> None:
    clinician = _create_clinician(clinic_client)
    _, patient_id = _connect_consented(clinic_client, clinician)
    resp = clinic_client.get(
        f"/clinic/patients/{patient_id}/visit-summary",
        headers=clinician,
        params={"window": 45},
    )
    assert resp.status_code == 422


def test_clinician_visit_summary_requires_clinician(clinic_client: TestClient) -> None:
    patient, patient_id = _register_patient(clinic_client)
    assert (
        clinic_client.get(
            f"/clinic/patients/{patient_id}/visit-summary", headers=patient
        ).status_code
        == 403
    )


async def test_clinician_visit_summary_carries_no_password_hash(
    clinic_client: TestClient, clinic_service: ClinicService
) -> None:
    """Mirrors the export payload-scan: the registered patient has a real Argon2 hash on
    file, and it must never appear anywhere in the Summary body."""
    clinician = _create_clinician(clinic_client)
    patient, patient_id = _connect_consented(clinic_client, clinician)
    await _seed_symptom_change(clinic_service, patient_id)
    user = await clinic_service.users.get_by_patient_id(patient_id)
    assert user is not None and user.password_hash.startswith("$argon2")
    resp = clinic_client.get(f"/clinic/patients/{patient_id}/visit-summary", headers=clinician)
    assert resp.status_code == 200
    assert user.password_hash not in json.dumps(resp.json())


async def test_change_pointed_questions_gated_on_both_surfaces(
    clinic_client: TestClient, clinic_service: ClinicService, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinician = _create_clinician(clinic_client)
    patient, patient_id = _connect_consented(clinic_client, clinician)
    await _seed_symptom_change(clinic_service, patient_id)

    # Default OFF: change_pointed empty on both surfaces (D2 gate, ADR-0045 open q#2).
    off_clin = clinic_client.get(
        f"/clinic/patients/{patient_id}/visit-summary", headers=clinician
    ).json()
    off_pat = clinic_client.get("/me/visit-summary", headers=patient).json()
    assert off_clin["questions"]["change_pointed"] == []
    assert off_pat["questions"]["change_pointed"] == []

    # Flag ON: change_pointed populated on both surfaces.
    monkeypatch.setattr(settings, "include_change_questions", True)
    on_clin = clinic_client.get(
        f"/clinic/patients/{patient_id}/visit-summary", headers=clinician
    ).json()
    on_pat = clinic_client.get("/me/visit-summary", headers=patient).json()
    assert on_clin["questions"]["change_pointed"]
    assert on_pat["questions"]["change_pointed"]
