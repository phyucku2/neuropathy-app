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

from app.ai.narrative import NARRATIVE_CACHE
from app.api.deps import (
    get_account_deletion_service,
    get_auth_service,
    get_capability_service,
    get_caregiver_service,
    get_clinic_service,
    get_emr_service,
)
from app.core.config import settings
from app.emr.service import EmrService, InMemorySecretStore
from app.main import app
from app.models.audit import AuditEvent
from app.models.capability import Actor
from app.models.caregiver import CaregiverLink, CaregiverLinkStatus
from app.models.clinic import Clinic
from app.models.connection import ClinicConnection, ConnectionStatus, Initiator
from app.models.emr_clinical_note import EmrClinicalNote
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.repositories.audit import InMemoryAuditEventRepository
from app.repositories.emr_connection import ConnectionRecord
from app.repositories.patient_capability import InMemoryPatientCapabilityRepository
from app.repositories.user import InMemoryUserRepository
from app.services.account_deletion import (
    RATE_LIMITED_DETAIL,
    WRONG_PASSWORD_DETAIL,
    AccountDeletionError,
    AccountDeletionService,
)
from app.services.auth import AuthService
from app.services.capability import CapabilityService
from app.services.caregiver import CaregiverService
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
        self.caregiver = CaregiverService(
            users=self.auth.users,
            observations=self.emr.observations,
            clinical_notes=self.emr.clinical_notes,
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
            clinical_notes=self.emr.clinical_notes,
            caregiver_invites=self.caregiver.invites,
            caregiver_links=self.caregiver.links,
            audit=self.emr.audit,
        )


@pytest.fixture()
def world() -> Iterator[World]:
    built = World()
    app.dependency_overrides[get_auth_service] = lambda: built.auth
    app.dependency_overrides[get_emr_service] = lambda: built.emr
    app.dependency_overrides[get_clinic_service] = lambda: built.clinic
    app.dependency_overrides[get_capability_service] = lambda: built.capability
    app.dependency_overrides[get_caregiver_service] = lambda: built.caregiver
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

    # A pulled EMR clinical note (separate store, FKs the connection) — must be erased too.
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
            import_key="docref:DocRef/synthetic-1",
        )
    )

    # A caregiver share (ADR-0047): one open invite + one accepted link — both must die.
    await world.caregiver.create_invite(patient_id=patient_id, actor_id=uuid.uuid4())
    await world.caregiver.links.add(
        CaregiverLink(
            patient_id=patient_id,
            caregiver_user_id=uuid.uuid4(),
            status=CaregiverLinkStatus.active,
            accepted_at=datetime(2026, 7, 1, tzinfo=UTC),
            initiated_by=Initiator.patient,
        )
    )


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
    assert await world.emr.clinical_notes.list_for_patient(patient_id) == []  # notes erased
    # Caregiver invites + links purged (ADR-0047): no dangling consent rows survive,
    # and with no link left _may_caregiver_read can never pass for this patient again.
    assert await world.caregiver.invites.list_for_patient(patient_id) == []
    assert await world.caregiver.links.list_for_patient(patient_id) == []
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
        "emr_clinical_notes": 1,
        "vault_secrets": 1,
        "clinic_connections": 1,
        "patient_capabilities": 1,
        "caregiver_invites": 1,
        "caregiver_links": 1,
        "caregiver_alerts": 0,
        "caregiver_alert_preferences": 0,
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
    # No deletion event — nothing happened to the record. The refusal itself IS
    # audited (one bounded, PHI-free 'account_delete_denied' row: config only, no
    # password material), because the throttle counts exactly those events.
    events = world.emr.audit._events  # type: ignore[attr-defined]
    assert [e for e in events if e.action == "delete_account"] == []
    denials = [e for e in events if e.action == "account_delete_denied"]
    assert len(denials) == 1
    assert denials[0].detail == {
        "limit": settings.delete_account_rate_limit_max,
        "window_seconds": settings.delete_account_rate_limit_window_seconds,
    }


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
    assert resp.json()["detail"] == "Patient or caregiver account required"
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
    assert resp.json()["detail"] == "Patient or caregiver account required"


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
    repo = InMemoryUserRepository()
    await repo.delete_with_patient(user_id=uuid.uuid4(), patient_id=uuid.uuid4())


async def test_service_answers_401_when_the_account_is_already_gone() -> None:
    service = AccountDeletionService()
    with pytest.raises(AccountDeletionError) as excinfo:
        # SYNTHETIC_ constant, not a quoted literal — keeps the secret scan
        # meaningful (docs/lessons.md).
        await service.delete_patient_account(user_id=uuid.uuid4(), password=SYNTHETIC_PASSWORD)
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


# --- Vault purge ordering (review finding): secrets die AFTER every DB row delete ---


class _OrderRecordingSecretStore(InMemorySecretStore):
    """InMemorySecretStore that records when its delete seam fires."""

    def __init__(self, calls: list[str]) -> None:
        super().__init__()
        self._calls = calls

    async def delete(self, ref: str) -> None:
        self._calls.append("secret_store.delete")
        await super().delete(ref)


class _OrderRecordingUsers(InMemoryUserRepository):
    """User repo that records the LAST row delete of the flow (user + patient)."""

    def __init__(self, calls: list[str]) -> None:
        super().__init__()
        self._calls = calls

    async def delete_with_patient(self, *, user_id: uuid.UUID, patient_id: uuid.UUID) -> None:
        self._calls.append("users.delete_with_patient")
        await super().delete_with_patient(user_id=user_id, patient_id=patient_id)


class _DetachFailsAudit(InMemoryAuditEventRepository):
    """Audit repo whose detach step blows up — a synthetic DB failure that fires only
    after every row delete has already run."""

    async def detach_patient(self, patient_id: uuid.UUID) -> None:
        raise RuntimeError("synthetic DB failure after the row deletes")


async def _service_with_vaulted_connection(
    service: AccountDeletionService,
) -> tuple[uuid.UUID, str]:
    """Register a patient on the service's stores and give them an EMR connection
    whose tokens are vaulted; returns (user_id, secret_ref)."""
    auth = AuthService(users=service.users)
    user = await auth.register_patient(
        email="order@example.com", password=SYNTHETIC_PASSWORD, display_name="Pat"
    )
    assert user.patient_id is not None
    ref = await service.secret_store.put({"access_token": "synthetic-ehr-access"})
    await service.emr_connections.add(
        ConnectionRecord(
            id=uuid.uuid4(),
            patient_id=user.patient_id,
            fhir_base=FHIR_BASE,
            provider_name="Synthetic Health",
            token_ref=ref,
        )
    )
    return user.id, ref


async def test_vault_purge_runs_after_every_db_row_delete() -> None:
    """The purge-ordering contract (review finding): the SecretStore delete fires
    strictly AFTER the last DB row delete (user + patient), so a keyless in-memory
    vault can never lose an entry that a rolled-back transaction still references."""
    calls: list[str] = []
    service = AccountDeletionService(
        users=_OrderRecordingUsers(calls), secret_store=_OrderRecordingSecretStore(calls)
    )
    user_id, ref = await _service_with_vaulted_connection(service)

    assert (
        await service.delete_patient_account(user_id=user_id, password=SYNTHETIC_PASSWORD) is None
    )

    assert calls == ["users.delete_with_patient", "secret_store.delete"]
    assert await service.secret_store.get(ref) is None  # ...and the purge did happen


async def test_db_failure_after_the_row_deletes_leaves_the_keyless_vault_intact() -> None:
    """The rationale behind the ordering: with the NON-transactional keyless vault, a
    DB failure after the row deletes (which all roll back) must leave the secret in
    place — a fully intact account, never an orphaned token_ref at a purged entry."""
    service = AccountDeletionService(audit=_DetachFailsAudit())
    user_id, ref = await _service_with_vaulted_connection(service)

    with pytest.raises(RuntimeError, match="synthetic DB failure"):
        await service.delete_patient_account(user_id=user_id, password=SYNTHETIC_PASSWORD)

    assert await service.secret_store.get(ref) is not None  # vault untouched


# --- Failed-password throttle (review finding): the destruction oracle is bounded ---


@pytest.fixture()
def small_budget(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(settings, "delete_account_rate_limit_max", 3)
    return 3


def test_wrong_password_attempts_are_audited_then_throttled(
    world: World, client: TestClient, small_budget: int
) -> None:
    """Under the budget every wrong password is a 403 with one bounded PHI-free
    denial event; over it the answer flips to 429 and writes NOTHING more — the cap
    is also the audit-flood bound (at most the window budget of rows per actor)."""
    tokens, patient_id = _register(client)

    for _ in range(small_budget):
        resp = _delete(client, tokens["access_token"], "not-the-password")
        assert resp.status_code == 403
        assert resp.json()["detail"] == WRONG_PASSWORD_DETAIL

    events = world.emr.audit._events  # type: ignore[attr-defined]
    assert len([e for e in events if e.action == "account_delete_denied"]) == small_budget

    over = _delete(client, tokens["access_token"], "not-the-password")
    assert over.status_code == 429
    assert over.json()["detail"] == RATE_LIMITED_DETAIL
    # The 429 wrote no further audit rows: the denial volume is capped at the budget.
    assert len([e for e in events if e.action == "account_delete_denied"]) == small_budget
    # Nothing was deleted along the way.
    assert client.get("/auth/me", headers=_auth(tokens["access_token"])).status_code == 200
    assert [e for e in events if e.action == "delete_account"] == []


def test_over_the_budget_the_argon2_verify_never_runs(
    world: World, client: TestClient, small_budget: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The limiter fires BEFORE the password verify, so over the budget even the
    CORRECT password answers 429 without spending Argon2id CPU on the attacker."""
    tokens, _ = _register(client)
    me = client.get("/auth/me", headers=_auth(tokens["access_token"]))
    user_id = uuid.UUID(me.json()["user_id"])

    async def _seed_denials() -> None:
        for _ in range(small_budget):
            await world.emr.audit.add(
                AuditEvent(
                    actor_id=user_id,
                    actor_role="patient",
                    action="account_delete_denied",
                    patient_id=None,
                    detail={},
                )
            )

    asyncio.run(_seed_denials())

    def _must_not_run(password_hash: str, password: str) -> bool:
        raise AssertionError("verify_password must not run over the budget")

    monkeypatch.setattr("app.services.account_deletion.verify_password", _must_not_run)
    resp = _delete(client, tokens["access_token"], SYNTHETIC_PASSWORD)
    assert resp.status_code == 429
    assert resp.json()["detail"] == RATE_LIMITED_DETAIL


def test_correct_password_still_deletes_inside_an_open_window(
    world: World, client: TestClient, small_budget: int
) -> None:
    """A real owner who fumbled the password a couple of times is NOT locked out:
    under the budget the correct password deletes normally — only failures count."""
    tokens, patient_id = _register(client)
    for _ in range(small_budget - 1):
        assert _delete(client, tokens["access_token"], "not-the-password").status_code == 403

    assert _delete(client, tokens["access_token"], SYNTHETIC_PASSWORD).status_code == 204
    asyncio.run(_assert_everything_gone(world, patient_id))
    # The earlier denial rows are retained — anonymized by the patient-row detach.
    events = world.emr.audit._events  # type: ignore[attr-defined]
    denials = [e for e in events if e.action == "account_delete_denied"]
    assert len(denials) == small_budget - 1
    assert all(e.patient_id is None for e in denials)


# --- Caregiver-account deletion (ADR-0047): same re-auth, far smaller footprint ---


def _register_caregiver(
    client: TestClient, code: str, email: str = "care@example.com"
) -> dict[str, str]:
    resp = client.post(
        "/caregiver/register",
        json={
            "code": code,
            "email": email,
            "password": SYNTHETIC_PASSWORD,
            "display_name": "Cam Caregiver",
        },
    )
    assert resp.status_code == 201, resp.text
    tokens: dict[str, str] = resp.json()
    return tokens


def test_caregiver_deletes_own_account_and_links_only(world: World, client: TestClient) -> None:
    """A caregiver deletion removes the caregiver identity and its links — and NOTHING
    of the patient's record; the patient's account and surfaces survive untouched."""
    tokens, _patient_id = _register(client)
    code = client.post("/me/caregiver-invites", headers=_auth(tokens["access_token"])).json()[
        "code"
    ]
    care_tokens = _register_caregiver(client, code)
    link_id = client.get("/me/caregivers", headers=_auth(tokens["access_token"])).json()[0]["id"]
    assert (
        client.post(
            f"/me/caregivers/{link_id}/accept", headers=_auth(tokens["access_token"])
        ).status_code
        == 200
    )

    assert _delete(client, care_tokens["access_token"], SYNTHETIC_PASSWORD).status_code == 204

    # Every caregiver credential is dead; the link is gone from the patient's list.
    assert client.get("/auth/me", headers=_auth(care_tokens["access_token"])).status_code == 401
    login = client.post(
        "/auth/login", json={"email": "care@example.com", "password": SYNTHETIC_PASSWORD}
    )
    assert login.status_code == 401
    assert client.get("/me/caregivers", headers=_auth(tokens["access_token"])).json() == []
    # The patient is untouched.
    assert client.get("/auth/me", headers=_auth(tokens["access_token"])).status_code == 200
    # ONE PHI-free deletion event, caregiver as actor, counts only, no patient subject.
    events = world.emr.audit._events  # type: ignore[attr-defined]
    deletions = [e for e in events if e.action == "delete_account"]
    assert len(deletions) == 1
    assert deletions[0].actor_role == "caregiver"
    assert deletions[0].patient_id is None
    assert deletions[0].detail == {"caregiver_links": 1, "caregiver_alerts": 0}


def test_caregiver_wrong_password_is_403_and_deletes_nothing(
    world: World, client: TestClient
) -> None:
    tokens, _ = _register(client)
    code = client.post("/me/caregiver-invites", headers=_auth(tokens["access_token"])).json()[
        "code"
    ]
    care_tokens = _register_caregiver(client, code)

    resp = _delete(client, care_tokens["access_token"], "not-the-password")
    assert resp.status_code == 403
    assert resp.json()["detail"] == WRONG_PASSWORD_DETAIL
    # Nothing was deleted: the caregiver session and the pending link both survive.
    assert client.get("/auth/me", headers=_auth(care_tokens["access_token"])).status_code == 200
    assert len(client.get("/me/caregivers", headers=_auth(tokens["access_token"])).json()) == 1
    denials = [
        e
        for e in world.emr.audit._events  # type: ignore[attr-defined]
        if e.action == "account_delete_denied"
    ]
    assert len(denials) == 1
    assert denials[0].actor_role == "caregiver"


async def test_caregiver_delete_service_refuses_non_caregiver_principals() -> None:
    """Defense in depth behind the route dispatch: the caregiver deleter refuses a
    patient principal outright (the patient path owns patient deletions)."""
    service = AccountDeletionService()
    auth = AuthService(users=service.users)
    patient = await auth.register_patient(
        email="pat@example.com", password=SYNTHETIC_PASSWORD, display_name="Pat"
    )
    with pytest.raises(AccountDeletionError) as excinfo:
        await service.delete_caregiver_account(user_id=patient.id, password=SYNTHETIC_PASSWORD)
    assert excinfo.value.status_code == 403
    assert excinfo.value.reason == "Caregiver account required"


# --- Narrative cache invalidation (review finding): no cached narrative outlives ---


def test_deletion_clears_the_ai_narrative_cache(world: World, client: TestClient) -> None:
    """The process-level narrative cache is keyed by trajectory content, not patient
    id, so deletion clears it wholesale via the clear_narrative_cache seam."""
    tokens, _ = _register(client)
    NARRATIVE_CACHE.finish("synthetic-key", "A cached narrative derived from PHI.")
    assert NARRATIVE_CACHE.lookup("synthetic-key") == (True, "A cached narrative derived from PHI.")
    try:
        assert _delete(client, tokens["access_token"], SYNTHETIC_PASSWORD).status_code == 204
        assert NARRATIVE_CACHE.lookup("synthetic-key") == (False, None)
        assert NARRATIVE_CACHE._entries == {}  # noqa: SLF001 — the whole cache is gone
        assert NARRATIVE_CACHE._pending == set()  # noqa: SLF001
    finally:
        NARRATIVE_CACHE.clear()  # test isolation, same as test_ai_narrative's fixture
