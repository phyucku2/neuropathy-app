"""End-to-end tests for the patient data export (ADR-0031): GET /me/export.

Drives the in-memory storage mode through the real app with every store SHARED
between the auth/EMR/clinic/capability services and the export service — exactly the
deps.py wiring — so the export is proven to return the data those features actually
wrote. All data is synthetic (CLAUDE.md §5).

The no-secrets guarantee (ADR-0031) is proven by ABSENCE: the payload is serialized
and scanned for the known token/secret/hash fixtures, and none may appear.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_auth_service,
    get_capability_service,
    get_clinic_service,
    get_emr_service,
    get_patient_data_export_service,
)
from app.core.config import settings
from app.emr.service import EmrService
from app.main import app
from app.models.audit import AuditEvent
from app.models.clinic import Clinic
from app.models.connection import ClinicConnection, ConnectionStatus, Initiator
from app.models.emr_clinical_note import EmrClinicalNote
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.repositories.audit import InMemoryAuditEventRepository
from app.repositories.patient_capability import InMemoryPatientCapabilityRepository
from app.services.auth import AuthService
from app.services.capability import CapabilityService
from app.services.clinic import ClinicService
from app.services.export import (
    RATE_LIMITED_DETAIL,
    ExportError,
    PatientDataExportService,
    export_rate_limiter,
)

SYNTHETIC_PASSWORD = "a-strong-password"
FHIR_BASE = "https://ehr.example/fhir"
# The synthetic OAuth tokens FakeEmr hands back — vaulted on connect, and the exact
# strings the no-secrets scan proves are absent from the export payload.
SYNTHETIC_ACCESS_TOKEN = "synthetic-ehr-access-token"  # noqa: S105 — synthetic fixture
SYNTHETIC_REFRESH_TOKEN = "synthetic-ehr-refresh-token"  # noqa: S105 — synthetic fixture


class FakeEmr:
    """Plays the EMR for the SMART flow: discovery + token exchange (no network)."""

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        assert url.endswith("/.well-known/smart-configuration")
        return {
            "authorization_endpoint": "https://ehr.example/oauth/authorize",
            "token_endpoint": "https://ehr.example/oauth/token",
        }

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        return {
            "access_token": SYNTHETIC_ACCESS_TOKEN,
            "refresh_token": SYNTHETIC_REFRESH_TOKEN,
            "patient": "fhir-patient-9",
            "scope": "patient/Observation.read",
            "expires_in": 3600,
        }


class World:
    """One shared in-memory world, wired the way deps.py wires the singletons."""

    def __init__(self) -> None:
        self.auth = AuthService(secret="endpoint-test-secret")
        self.emr = EmrService(
            transport=FakeEmr(),
            client_id="test-client",
            redirect_uri="https://app.test/emr/callback",
        )
        self.clinic = ClinicService(
            users=self.auth.users, observations=self.emr.observations, audit=self.emr.audit
        )
        self.patient_capabilities = InMemoryPatientCapabilityRepository()
        self.capability = CapabilityService(
            patient_capabilities=self.patient_capabilities,
            connections=self.clinic.connections,
            audit=self.emr.audit,
        )
        self.export = PatientDataExportService(
            users=self.auth.users,
            observations=self.emr.observations,
            emr_connections=self.emr.connections,
            clinical_notes=self.emr.clinical_notes,
            clinic=self.clinic,
            capabilities=self.capability,
            audit=self.emr.audit,
        )


@pytest.fixture()
def world() -> Iterator[World]:
    built = World()
    app.dependency_overrides[get_auth_service] = lambda: built.auth
    app.dependency_overrides[get_emr_service] = lambda: built.emr
    app.dependency_overrides[get_clinic_service] = lambda: built.clinic
    app.dependency_overrides[get_capability_service] = lambda: built.capability
    app.dependency_overrides[get_patient_data_export_service] = lambda: built.export
    try:
        yield built
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def client(world: World) -> TestClient:
    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, email: str = "pat@example.com") -> tuple[dict[str, str], str]:
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": SYNTHETIC_PASSWORD, "display_name": "Pat Synthetic"},
    )
    assert resp.status_code == 201
    tokens: dict[str, str] = resp.json()
    me = client.get("/auth/me", headers=_auth(tokens["access_token"]))
    patient_id: str = me.json()["patient_id"]
    return tokens, patient_id


def _observation(
    patient_id: uuid.UUID,
    *,
    source: SourceType,
    origin: DataOrigin,
    code: str,
    value_num: float,
) -> Observation:
    return Observation(
        id=uuid.uuid4(),
        patient_id=patient_id,
        source=source,
        origin=origin,
        code=code,
        value_num=value_num,
        unit="{score}",
        effective_at=datetime(2026, 7, 1, 12, tzinfo=UTC),
        recorded_at=datetime(2026, 7, 1, 12, tzinfo=UTC),
        status=ObservationStatus.final,
        quality={"human_confirmed": True},
        payload={"raw": "synthetic"},
    )


async def _populate(world: World, patient_id_str: str) -> None:
    """Give the patient data in EVERY exported class: an active EMR connection whose
    tokens are vaulted, a consented clinic connection, and observations from all three
    sources (lab + BioMech + ADL)."""
    patient_id = uuid.UUID(patient_id_str)

    # Completed SMART flow -> active connection + vaulted tokens (token_ref set).
    _, _, state = await world.emr.start_connect(
        patient_id=patient_id, fhir_base=FHIR_BASE, provider_name="Synthetic Health"
    )
    await world.emr.complete_callback(state=state, code="synthetic-code")

    clinic_row = await world.clinic.clinics.add(Clinic(id=uuid.uuid4(), name="Synthetic Clinic"))
    await world.clinic.connections.add(
        ClinicConnection(
            patient_id=patient_id,
            clinic_id=clinic_row.id,
            status=ConnectionStatus.active,
            initiated_by=Initiator.clinic,
            consent_granted_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
    )

    await world.emr.observations.add(
        _observation(
            patient_id,
            source=SourceType.lab,
            origin=DataOrigin.ehr_imported,
            code="4548-4",
            value_num=7.2,
        )
    )
    await world.emr.observations.add(
        _observation(
            patient_id,
            source=SourceType.biomech,
            origin=DataOrigin.device_measured,
            code="biomech_balance_score",
            value_num=64.0,
        )
    )
    await world.emr.observations.add(
        _observation(
            patient_id,
            source=SourceType.adl,
            origin=DataOrigin.patient_reported,
            code="adl_daily_score",
            value_num=9.0,
        )
    )

    # A pulled EMR clinical note (separate store) — exported as METADATA ONLY, no body.
    emr_connections = await world.emr.connections.list_for_patient(patient_id)
    await world.emr.clinical_notes.add_if_absent(
        EmrClinicalNote(
            patient_id=patient_id,
            connection_id=emr_connections[0].id,
            origin=DataOrigin.ehr_imported,
            source_system="Synthetic Health",
            document_fhir_id="DocRef/synthetic-1",
            type_code="11506-3",
            type_display="Progress note",
            authored_at=datetime(2026, 7, 1, 12, tzinfo=UTC),
            author_display="Dr Synthetic",
            content_type="text/plain",
            attachment_url="https://ehr.example/fhir/Binary/synthetic-1",
            import_key="docref:DocRef/synthetic-1",
        )
    )


def test_export_returns_every_data_class_with_correct_values(
    world: World, client: TestClient
) -> None:
    tokens, patient_id = _register(client)
    # A real toggle write (before the clinic connection makes the patient
    # clinically-managed) so a non-default capability state is present in the export.
    assert (
        client.put(
            "/capabilities/ingest_adl",
            headers=_auth(tokens["access_token"]),
            json={"active": False},
        ).status_code
        == 200
    )
    asyncio.run(_populate(world, patient_id))

    resp = client.get("/me/export", headers=_auth(tokens["access_token"]))
    assert resp.status_code == 200
    body = resp.json()

    # Envelope.
    assert body["schema_version"] == "1.0"
    assert body["subject_id"] == patient_id
    assert "exported_at" in body

    # Account profile — display name/email/role, and NO password hash field anywhere.
    assert body["account"] == {
        "display_name": "Pat Synthetic",
        "email": "pat@example.com",
        "role": "patient",
        "created_at": body["account"]["created_at"],
    }
    assert body["account"]["created_at"] is not None
    assert "password" not in json.dumps(body["account"]).lower()

    # Patient row (non-secret fields).
    assert body["patient"]["patient_id"] == patient_id
    assert body["patient"]["display_name"] == "Pat Synthetic"
    assert body["patient"]["connection_mode"] == "self_connected"

    # Observations — all three sources present with their provenance + dates.
    sources = {o["source"] for o in body["observations"]}
    assert sources == {"lab", "biomech", "adl"}
    lab = next(o for o in body["observations"] if o["source"] == "lab")
    assert lab["code"] == "4548-4"
    assert lab["origin"] == "ehr_imported"
    assert lab["value_num"] == 7.2
    assert lab["effective_at"].startswith("2026-07-01")
    assert lab["quality"] == {"human_confirmed": True}

    # Trajectory snapshot.
    assert body["trajectory"]["direction"] in {
        "improving",
        "stable",
        "declining",
        "insufficient_data",
    }

    # Capability states — the toggled-off ADL source is reflected.
    adl_state = next(c for c in body["capabilities"] if c["key"] == "ingest_adl")
    assert adl_state["active"] is False

    # Clinic connection metadata WITH the clinic name (never tokens).
    assert len(body["clinic_connections"]) == 1
    assert body["clinic_connections"][0]["clinic_name"] == "Synthetic Clinic"
    assert body["clinic_connections"][0]["status"] == "active"

    # EMR connection metadata WITH provider + status (never the vault token/ref).
    assert len(body["emr_connections"]) == 1
    emr = body["emr_connections"][0]
    assert emr["provider_name"] == "Synthetic Health"
    assert emr["status"] == "active"
    assert emr["patient_fhir_id"] == "fhir-patient-9"

    # EMR clinical note — METADATA ONLY (ADR-0045 P2 #27), no body field at all.
    assert len(body["emr_clinical_notes"]) == 1
    note = body["emr_clinical_notes"][0]
    assert note["type_display"] == "Progress note"
    assert note["author_display"] == "Dr Synthetic"
    assert note["document_fhir_id"] == "DocRef/synthetic-1"
    assert "body" not in note and "text" not in note  # the note text is structurally absent


def test_export_never_contains_a_token_secret_or_password_hash(
    world: World, client: TestClient
) -> None:
    """The NO-secrets rule (ADR-0031), proven by ABSENCE: the vaulted OAuth tokens, the
    opaque token_ref that points at them, and the account's Argon2id password hash are
    all real fixtures in this world — and NONE may appear anywhere in the payload."""
    tokens, patient_id = _register(client)
    asyncio.run(_populate(world, patient_id))

    # The concrete secrets that exist for this patient right now.
    user = asyncio.run(world.auth.users.get_by_id(uuid.UUID(tokens_user_id(client, tokens))))
    assert user is not None
    password_hash = user.password_hash
    assert password_hash.startswith("$argon2")  # a real hash, not a placeholder
    connections = asyncio.run(world.emr.connections.list_for_patient(uuid.UUID(patient_id)))
    token_refs = [c.token_ref for c in connections if c.token_ref is not None]
    assert token_refs  # the flow really vaulted a secret and set a ref

    resp = client.get("/me/export", headers=_auth(tokens["access_token"]))
    assert resp.status_code == 200
    serialized = json.dumps(resp.json())

    for forbidden in (
        SYNTHETIC_ACCESS_TOKEN,
        SYNTHETIC_REFRESH_TOKEN,
        password_hash,
        *token_refs,
    ):
        assert forbidden not in serialized


def tokens_user_id(client: TestClient, tokens: dict[str, str]) -> str:
    return client.get("/auth/me", headers=_auth(tokens["access_token"])).json()["user_id"]


def test_export_writes_one_phi_free_audit_event(world: World, client: TestClient) -> None:
    tokens, patient_id = _register(client)
    asyncio.run(_populate(world, patient_id))

    assert client.get("/me/export", headers=_auth(tokens["access_token"])).status_code == 200

    events = world.emr.audit._events  # type: ignore[attr-defined]
    exports = [e for e in events if e.action == "export_account"]
    assert len(exports) == 1
    event = exports[0]
    assert event.actor_role == "patient"
    assert event.patient_id == uuid.UUID(patient_id)
    # Counts and references only — never values (audit contract).
    assert event.detail == {
        "observations": 3,
        "emr_connections": 1,
        "emr_clinical_notes": 1,  # the pulled note (metadata-only export, ADR-0045 P2 #27)
        "clinic_connections": 1,
        "capabilities": 11,  # + ADR-0045 P2 ingest_medications, ingest_events, ingest_notes
    }
    assert "Synthetic" not in json.dumps(event.detail)


def test_export_on_an_empty_account_is_honest_and_still_audited(
    world: World, client: TestClient
) -> None:
    """A brand-new patient with no data exports empty collections (not an error), and
    the disclosure is still audited."""
    tokens, patient_id = _register(client)
    resp = client.get("/me/export", headers=_auth(tokens["access_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["observations"] == []
    assert body["clinic_connections"] == []
    assert body["emr_connections"] == []
    assert body["capabilities"]  # the registry defaults are always present
    exports = [e for e in world.emr.audit._events if e.action == "export_account"]  # type: ignore[attr-defined]
    assert len(exports) == 1


def test_clinician_cannot_export_via_this_endpoint(world: World, client: TestClient) -> None:
    asyncio.run(
        world.auth.create_clinician(
            email="dr@example.com",
            password=SYNTHETIC_PASSWORD,
            display_name="Dr Synthetic",
            clinic_id=uuid.uuid4(),
        )
    )
    login = client.post(
        "/auth/login", json={"email": "dr@example.com", "password": SYNTHETIC_PASSWORD}
    )
    resp = client.get("/me/export", headers=_auth(login.json()["access_token"]))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Patient account required"


def test_ops_cannot_export_via_this_endpoint(world: World, client: TestClient) -> None:
    asyncio.run(
        world.auth.create_ops(
            email="ops@example.com", password=SYNTHETIC_PASSWORD, display_name="Ops"
        )
    )
    login = client.post(
        "/auth/login", json={"email": "ops@example.com", "password": SYNTHETIC_PASSWORD}
    )
    resp = client.get("/me/export", headers=_auth(login.json()["access_token"]))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Patient account required"


def test_anonymous_export_is_401(client: TestClient) -> None:
    assert client.get("/me/export").status_code == 401


def test_route_maps_a_service_export_error_to_its_status(world: World, client: TestClient) -> None:
    """The route's ExportError handler: a defense-in-depth refusal raised by the
    service (e.g. the account vanished mid-request) is rendered as its HTTP status.
    Overriding the service lets us drive that path, which require_patient normally
    preempts."""
    tokens, _ = _register(client)

    class _Raising(PatientDataExportService):
        async def export_patient_data(self, *, user_id: uuid.UUID) -> Any:
            raise ExportError("Account no longer exists", status_code=401)

    app.dependency_overrides[get_patient_data_export_service] = lambda: _Raising()
    resp = client.get("/me/export", headers=_auth(tokens["access_token"]))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Account no longer exists"


async def test_service_answers_401_when_the_account_is_already_gone() -> None:
    service = PatientDataExportService()
    with pytest.raises(ExportError) as excinfo:
        await service.export_patient_data(user_id=uuid.uuid4())
    assert excinfo.value.status_code == 401


async def test_service_refuses_non_patient_principals() -> None:
    service = PatientDataExportService()
    auth = AuthService(users=service.users)
    clinician = await auth.create_clinician(
        email="dr@example.com",
        password=SYNTHETIC_PASSWORD,
        display_name="Dr Synthetic",
        clinic_id=uuid.uuid4(),
    )
    with pytest.raises(ExportError) as excinfo:
        await service.export_patient_data(user_id=clinician.id)
    assert excinfo.value.status_code == 403
    assert excinfo.value.reason == "Patient account required"


async def test_service_tolerates_a_missing_patient_row() -> None:
    """Defense in depth: if the linked Patient row is somehow absent, the export falls
    back to the account's own display name rather than crashing."""
    service = PatientDataExportService()
    auth = AuthService(users=service.users)
    user = await auth.register_patient(
        email="pat@example.com", password=SYNTHETIC_PASSWORD, display_name="Pat Synthetic"
    )
    assert user.patient_id is not None
    # Drop the linked Patient record out from under the export.
    service.users.patients.pop(user.patient_id, None)  # type: ignore[attr-defined]

    export = await service.export_patient_data(user_id=user.id)
    assert export.patient.display_name == "Pat Synthetic"
    assert export.patient.connection_mode == "self_connected"
    assert export.patient.created_at is None


# --- Cache-Control (FIX 5): the PHI payload is never cacheable ---


def test_export_response_sets_cache_control_no_store(world: World, client: TestClient) -> None:
    """The 200 export body is the patient's whole record — it must carry
    `Cache-Control: no-store` so no proxy or browser caches the PHI (ADR-0031)."""
    tokens, patient_id = _register(client)
    asyncio.run(_populate(world, patient_id))

    resp = client.get("/me/export", headers=_auth(tokens["access_token"]))
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"


# --- Rate limit (FIX 1): the unbounded full-account assembly is throttled per actor ---


@pytest.fixture()
def small_export_budget(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(settings, "export_rate_limit_max", 2)
    return 2


def test_export_is_throttled_over_the_budget(
    world: World, client: TestClient, small_export_budget: int
) -> None:
    """Under the budget every export is a 200 that writes exactly one 'export_account'
    event; over it the answer flips to 429 and writes NOTHING more — the cap bounds both
    the O(n) work and the audited disclosure volume (at most the budget per actor)."""
    tokens, patient_id = _register(client)
    asyncio.run(_populate(world, patient_id))

    for _ in range(small_export_budget):
        assert client.get("/me/export", headers=_auth(tokens["access_token"])).status_code == 200

    events = world.emr.audit._events  # type: ignore[attr-defined]
    assert len([e for e in events if e.action == "export_account"]) == small_export_budget

    over = client.get("/me/export", headers=_auth(tokens["access_token"]))
    assert over.status_code == 429
    assert over.json()["detail"] == RATE_LIMITED_DETAIL
    # The 429 assembled and disclosed nothing: the export-event volume stays at the cap.
    assert len([e for e in events if e.action == "export_account"]) == small_export_budget


async def test_export_rate_limiter_trips_at_the_budget_on_a_fixed_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The limiter's window math, proven on an INJECTED fixed `now` (no wall clock —
    docs/lessons.md 'No wall-clock in tests'): seeding exactly the budget of
    'export_account' events inside the window flips `allow` from True to False, and an
    event just outside the window does not count against the budget."""
    monkeypatch.setattr(settings, "export_rate_limit_max", 3)
    monkeypatch.setattr(settings, "export_rate_limit_window_seconds", 3600)

    audit = InMemoryAuditEventRepository()
    actor = uuid.uuid4()
    now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    window_start = now - timedelta(seconds=3600)

    limiter = export_rate_limiter(audit)

    async def _seed(occurred_at: datetime) -> None:
        await audit.add(
            AuditEvent(
                actor_id=actor,
                actor_role="patient",
                action="export_account",
                patient_id=None,
                detail={},
                occurred_at=occurred_at,
            )
        )

    # An event OLDER than the window must not count.
    await _seed(window_start - timedelta(seconds=1))
    assert await limiter.allow(actor, now=now) is True

    # Fill the budget with events inside the window; the last one exhausts it.
    for _ in range(2):
        await _seed(now)
    assert await limiter.allow(actor, now=now) is True  # 2 in-window < 3
    await _seed(now)
    assert await limiter.allow(actor, now=now) is False  # 3 in-window == budget
