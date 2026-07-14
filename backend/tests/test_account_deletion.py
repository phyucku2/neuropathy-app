"""End-to-end tests for patient account & data deletion (ADR-0027): DELETE /auth/me.

Drives the in-memory storage mode through the real app with every store SHARED
between the auth/EMR/clinic/capability services and the deletion service — exactly
the deps.py wiring — so a deletion is proven to remove the data those features
actually wrote. All data is synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.api.deps import (
    get_account_deletion_service,
    get_auth_service,
    get_capability_service,
    get_clinic_service,
    get_emr_service,
)
from app.emr.service import EmrService, InMemorySecretStore
from app.main import app
from app.models.capability import Actor
from app.models.clinic import Clinic
from app.models.connection import ClinicConnection, ConnectionStatus, Initiator
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.repositories.patient_capability import InMemoryPatientCapabilityRepository
from app.services.account_deletion import (
    WRONG_PASSWORD_DETAIL,
    AccountDeletionError,
    AccountDeletionService,
)
from app.services.auth import AuthService
from app.services.capability import CapabilityService
from app.services.clinic import ClinicService

SYNTHETIC_PASSWORD = "a-strong-password"
FHIR_BASE = "https://ehr.example/fhir"


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
            "access_token": "synthetic-ehr-access-token",
            "refresh_token": "synthetic-ehr-refresh-token",
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
        self.deletion = AccountDeletionService(
            users=self.auth.users,
            emr_connections=self.emr.connections,
            pending_auth=self.emr._pending,
            secret_store=self.emr.secret_store,
            clinic_connections=self.clinic.connections,
            patient_capabilities=self.patient_capabilities,
            observations=self.emr.observations,
            audit=self.emr.audit,
        )


@pytest.fixture()
def world() -> Iterator[World]:
    built = World()
    app.dependency_overrides[get_auth_service] = lambda: built.auth
    app.dependency_overrides[get_emr_service] = lambda: built.emr
    app.dependency_overrides[get_clinic_service] = lambda: built.clinic
    app.dependency_overrides[get_capability_service] = lambda: built.capability
    app.dependency_overrides[get_account_deletion_service] = lambda: built.deletion
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
        json={"email": email, "password": SYNTHETIC_PASSWORD, "display_name": "Pat"},
    )
    assert resp.status_code == 201
    tokens: dict[str, str] = resp.json()
    me = client.get("/auth/me", headers=_auth(tokens["access_token"]))
    patient_id: str = me.json()["patient_id"]
    return tokens, patient_id


def _delete(client: TestClient, access_token: str, password: str) -> Response:
    return client.request(
        "DELETE", "/auth/me", headers=_auth(access_token), json={"password": password}
    )


def _observation(patient_id: uuid.UUID, revises_id: uuid.UUID | None = None) -> Observation:
    return Observation(
        id=uuid.uuid4(),
        patient_id=patient_id,
        source=SourceType.adl,
        origin=DataOrigin.patient_reported,
        code="adl_daily_score",
        value_num=9.0,
        effective_at=datetime(2026, 7, 1, 12, tzinfo=UTC),
        recorded_at=datetime(2026, 7, 1, 12, tzinfo=UTC),
        status=ObservationStatus.corrected if revises_id else ObservationStatus.final,
        revises_id=revises_id,
        quality={"human_confirmed": True},
        payload={},
    )


async def _populate(world: World, patient_id_str: str) -> None:
    """Give the patient data in EVERY store: an active EMR connection with vaulted
    tokens, a second connection stuck mid-handshake (a live pending_auth entry), a
    consented clinic connection, a toggle row, and a supersede chain of observations."""
    patient_id = uuid.UUID(patient_id_str)

    # Completed SMART flow -> active connection + vaulted tokens.
    _, _, state = await world.emr.start_connect(
        patient_id=patient_id, fhir_base=FHIR_BASE, provider_name="Synthetic Health"
    )
    await world.emr.complete_callback(state=state, code="synthetic-code")
    # Started-but-never-finished flow -> a pending_auth entry that must also die.
    await world.emr.start_connect(patient_id=patient_id, fhir_base=FHIR_BASE, provider_name=None)

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

    await world.patient_capabilities.upsert(
        patient_id=patient_id,
        capability_id=uuid.uuid4(),
        active=False,
        set_by=Actor.patient,
        expires_at=None,
    )

    original = await world.emr.observations.add(_observation(patient_id))
    await world.emr.observations.add(_observation(patient_id, revises_id=original.id))


async def _assert_everything_gone(world: World, patient_id_str: str) -> None:
    patient_id = uuid.UUID(patient_id_str)
    assert await world.emr.connections.list_for_patient(patient_id) == []
    secret_store = world.emr.secret_store
    assert isinstance(secret_store, InMemorySecretStore)
    assert secret_store._secrets == {}  # vaulted EMR tokens purged (ADR-0017 seam)
    pending = world.emr._pending
    assert pending._pending == {}  # type: ignore[attr-defined]  # in-flight handshakes purged
    assert await world.clinic.connections.list_for_patient(patient_id) == []
    assert await world.patient_capabilities.list_for_patient(patient_id) == []
    assert await world.emr.observations.list_for_patient(patient_id) == []
    observations = world.emr.observations
    assert observations._observations == []  # type: ignore[attr-defined]  # superseded rows gone too
    assert await world.auth.users.get_by_patient_id(patient_id) is None
    users = world.auth.users
    assert patient_id not in users.patients  # type: ignore[attr-defined]  # the Patient record itself


def test_happy_path_deletes_every_store_and_retains_anonymous_audit(
    world: World, client: TestClient
) -> None:
    tokens, patient_id = _register(client)
    asyncio.run(_populate(world, patient_id))

    resp = _delete(client, tokens["access_token"], SYNTHETIC_PASSWORD)
    assert resp.status_code == 204

    asyncio.run(_assert_everything_gone(world, patient_id))

    # ONE deletion audit event, retained, PHI-free, detached from the deleted patient
    # (the in-memory mirror of migration 0006's ON DELETE SET NULL).
    events = world.emr.audit._events  # type: ignore[attr-defined]
    deletions = [e for e in events if e.action == "delete_account"]
    assert len(deletions) == 1
    event = deletions[0]
    assert event.patient_id is None
    assert event.actor_role == "patient"
    assert event.detail == {
        "emr_connections": 2,
        "vault_secrets": 1,
        "clinic_connections": 1,
        "patient_capabilities": 1,
    }
    # EVERY retained event for this patient is anonymous now — none still points at
    # the deleted record — and the log itself was never truncated.
    assert all(e.patient_id is None for e in events)
    assert len(events) >= 1


def test_wrong_password_is_403_and_deletes_nothing(world: World, client: TestClient) -> None:
    tokens, patient_id = _register(client)
    asyncio.run(_populate(world, patient_id))

    resp = _delete(client, tokens["access_token"], "not-the-password")
    assert resp.status_code == 403
    assert resp.json()["detail"] == WRONG_PASSWORD_DETAIL

    # Nothing was deleted: the session, the account, and the data all survive.
    assert client.get("/auth/me", headers=_auth(tokens["access_token"])).status_code == 200
    login = client.post(
        "/auth/login", json={"email": "pat@example.com", "password": SYNTHETIC_PASSWORD}
    )
    assert login.status_code == 200
    assert len(asyncio.run(_surviving_row_counts(world, patient_id))) == 4
    # No audit event either — nothing happened to the record (the refusal wrote
    # nothing that could need committing, so raising is safe here).
    events = world.emr.audit._events  # type: ignore[attr-defined]
    assert [e for e in events if e.action == "delete_account"] == []


async def _surviving_row_counts(world: World, patient_id_str: str) -> list[int]:
    patient_id = uuid.UUID(patient_id_str)
    counts = [
        len(await world.emr.connections.list_for_patient(patient_id)),
        len(await world.clinic.connections.list_for_patient(patient_id)),
        len(await world.patient_capabilities.list_for_patient(patient_id)),
        len(await world.emr.observations.list_for_patient(patient_id)),
    ]
    assert all(count >= 1 for count in counts)
    return counts


def test_missing_password_is_422(client: TestClient) -> None:
    tokens, _ = _register(client)
    resp = client.request("DELETE", "/auth/me", headers=_auth(tokens["access_token"]), json={})
    assert resp.status_code == 422


def test_anonymous_delete_is_401(client: TestClient) -> None:
    resp = client.request("DELETE", "/auth/me", json={"password": SYNTHETIC_PASSWORD})
    assert resp.status_code == 401


def test_clinician_cannot_delete_via_this_endpoint(world: World, client: TestClient) -> None:
    asyncio.run(_provision_clinician(world, email="dr@example.com", password=SYNTHETIC_PASSWORD))
    login = client.post(
        "/auth/login", json={"email": "dr@example.com", "password": SYNTHETIC_PASSWORD}
    )
    resp = _delete(client, login.json()["access_token"], SYNTHETIC_PASSWORD)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Patient account required"
    # The clinician account is untouched.
    assert client.get("/auth/me", headers=_auth(login.json()["access_token"])).status_code == 200


async def _provision_clinician(world: World, *, email: str, password: str) -> None:
    await world.auth.create_clinician(
        email=email, password=password, display_name="Dr Synthetic", clinic_id=uuid.uuid4()
    )


def test_ops_cannot_delete_via_this_endpoint(world: World, client: TestClient) -> None:
    asyncio.run(
        world.auth.create_ops(
            email="ops@example.com", password=SYNTHETIC_PASSWORD, display_name="Ops"
        )
    )
    login = client.post(
        "/auth/login", json={"email": "ops@example.com", "password": SYNTHETIC_PASSWORD}
    )
    resp = _delete(client, login.json()["access_token"], SYNTHETIC_PASSWORD)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Patient account required"


def test_after_deletion_every_credential_is_dead(client: TestClient) -> None:
    tokens, _ = _register(client)
    assert _delete(client, tokens["access_token"], SYNTHETIC_PASSWORD).status_code == 204

    # The live access token no longer authenticates.
    assert client.get("/auth/me", headers=_auth(tokens["access_token"])).status_code == 401
    # The refresh token can no longer mint access tokens (refresh re-reads the user).
    refresh = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 401
    # Logging in again fails — same message as an unknown account, no enumeration.
    login = client.post(
        "/auth/login", json={"email": "pat@example.com", "password": SYNTHETIC_PASSWORD}
    )
    assert login.status_code == 401
    assert login.json()["detail"] == "Invalid email or password"
    # A second delete attempt with the dead token is 401, not a second deletion.
    assert _delete(client, tokens["access_token"], SYNTHETIC_PASSWORD).status_code == 401


def test_deletion_is_not_blockable_by_the_ops_kill_switch(world: World, client: TestClient) -> None:
    """Mirror of the ADR-0013 'revocation is never blockable' rule: with EVERY
    registry capability ops-killed (available=False overrides everything), the
    deletion endpoint still works — it carries no capability gate at all."""
    tokens, patient_id = _register(client)

    async def _kill_everything() -> None:
        # Seed the lazy registry rows, then flip the ops kill switch on all of them.
        states = await world.capability.effective_states(
            uuid.UUID(patient_id), now=datetime.now(UTC)
        )
        assert states
        for listed in await world.capability.capabilities.list():
            listed.available = False

    asyncio.run(_kill_everything())
    assert _delete(client, tokens["access_token"], SYNTHETIC_PASSWORD).status_code == 204


def test_deleting_one_patient_leaves_every_other_patient_untouched(
    world: World, client: TestClient
) -> None:
    """Per-user isolation under deletion: patient B's account, data, and NON-anonymous
    audit trail all survive patient A's deletion intact."""
    tokens_a, patient_a = _register(client, email="a@example.com")
    tokens_b, patient_b = _register(client, email="b@example.com")
    asyncio.run(_populate(world, patient_a))
    asyncio.run(world.emr.observations.add(_observation(uuid.UUID(patient_b))))
    # An audit event for B (a real toggle write through the API).
    assert (
        client.put(
            "/capabilities/ingest_adl",
            headers=_auth(tokens_b["access_token"]),
            json={"active": False},
        ).status_code
        == 200
    )

    assert _delete(client, tokens_a["access_token"], SYNTHETIC_PASSWORD).status_code == 204

    # B still works end to end...
    assert client.get("/auth/me", headers=_auth(tokens_b["access_token"])).status_code == 200
    b_id = uuid.UUID(patient_b)
    assert len(asyncio.run(world.emr.observations.list_for_patient(b_id))) == 1
    assert len(asyncio.run(world.patient_capabilities.list_for_patient(b_id))) == 1
    # ...and B's audit events are NOT anonymized — only the deleted patient's were.
    events = world.emr.audit._events  # type: ignore[attr-defined]
    assert any(e.patient_id == b_id for e in events)


async def test_delete_with_patient_is_a_quiet_noop_for_an_unknown_user() -> None:
    """The in-memory repo mirrors DELETE ... WHERE semantics: nothing to remove is
    not an error (Postgres twin: zero-row DELETE)."""
    from app.repositories.user import InMemoryUserRepository

    repo = InMemoryUserRepository()
    await repo.delete_with_patient(user_id=uuid.uuid4(), patient_id=uuid.uuid4())


async def test_service_answers_401_when_the_account_is_already_gone() -> None:
    service = AccountDeletionService()
    with pytest.raises(AccountDeletionError) as excinfo:
        await service.delete_patient_account(user_id=uuid.uuid4(), password="anything-at-all")
    assert excinfo.value.status_code == 401


async def test_service_refuses_non_patient_principals() -> None:
    service = AccountDeletionService()
    auth = AuthService(users=service.users)
    clinician = await auth.create_clinician(
        email="dr@example.com",
        password=SYNTHETIC_PASSWORD,
        display_name="Dr Synthetic",
        clinic_id=uuid.uuid4(),
    )
    with pytest.raises(AccountDeletionError) as excinfo:
        await service.delete_patient_account(user_id=clinician.id, password=SYNTHETIC_PASSWORD)
    assert excinfo.value.status_code == 403
    assert excinfo.value.reason == "Patient account required"


async def test_pending_auth_delete_for_connections_is_scoped_and_noop_on_empty() -> None:
    """The in-memory twin of the Postgres delete: only the named connections' states
    die; an empty id list is a quiet no-op."""
    from app.repositories.pending_auth import InMemoryPendingAuthStore, PendingAuth

    store = InMemoryPendingAuthStore()
    now = datetime.now(UTC)
    keep_id, drop_id = uuid.uuid4(), uuid.uuid4()
    await store.put(
        "keep-state",
        PendingAuth(connection_id=keep_id, code_verifier="v1", token_endpoint="https://t"),
        now=now,
    )
    await store.put(
        "drop-state",
        PendingAuth(connection_id=drop_id, code_verifier="v2", token_endpoint="https://t"),
        now=now,
    )
    await store.delete_for_connections([])
    await store.delete_for_connections([drop_id])
    assert await store.consume("drop-state", now=now) is None
    assert await store.consume("keep-state", now=now) is not None
