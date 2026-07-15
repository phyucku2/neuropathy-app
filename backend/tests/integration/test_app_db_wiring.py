"""App-level persistence wiring: with DATABASE_URL configured every request runs on
Postgres-backed repositories in a request-scoped transaction and data survives a
process restart; without it the in-memory fallback serves requests unchanged.

The durability tests need TEST_DATABASE_URL (like the rest of this package) and skip
cleanly otherwise. The provider-contract and fallback tests need no database and always
run. All data is synthetic — no real patient data (CLAUDE.md §5).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import deps
from app.core.config import settings
from app.emr.service import InMemorySecretStore
from app.ingestion.labs import lab_result_to_observation
from app.main import create_app
from app.models.observation import DataOrigin
from app.repositories.postgres import (
    PostgresAuditEventRepository,
    PostgresCapabilityRepository,
    PostgresClinicConnectionRepository,
    PostgresClinicRepository,
    PostgresEmrConnectionRepository,
    PostgresObservationRepository,
    PostgresPatientCapabilityRepository,
    PostgresPendingAuthStore,
    PostgresSecretStore,
    PostgresUserRepository,
)
from app.schemas.lab import LabResultIn, LabStatus

requires_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Postgres integration tests need TEST_DATABASE_URL (the CI service provides it)",
)


def _reset_process_singletons() -> None:
    """Drop every process-level cache in deps.py — what a real restart would do."""
    deps._default_auth_service.cache_clear()
    deps._default_emr_service.cache_clear()
    deps._default_clinic_service.cache_clear()
    deps._default_capability_service.cache_clear()
    deps._default_account_deletion_service.cache_clear()
    deps._default_patient_data_export_service.cache_clear()
    deps._process_jwt_secret.cache_clear()
    deps._process_secret_store.cache_clear()
    deps._process_pending_auth.cache_clear()
    deps._process_fernet.cache_clear()
    deps._process_transport.cache_clear()


@pytest.fixture()
def db_url(migrated_database: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point the app at the migrated test database and start from a clean process."""
    monkeypatch.setattr(settings, "database_url", migrated_database)
    _reset_process_singletons()
    return migrated_database


@pytest.fixture(autouse=True)
def _clean_process_state_afterwards() -> Iterator[None]:
    yield
    _reset_process_singletons()


# Synthetic credential for durability tests (never a real secret; CLAUDE.md §5).
SYNTHETIC_PASSWORD = "a-strong-password"


def _register(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": "Synthetic Pat"},
    )
    assert resp.status_code == 201, resp.text
    return cast("dict[str, str]", resp.json())


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def _seed_observations(url: str, patient_id: uuid.UUID) -> None:
    """Ingest a falling (improving) HbA1c series through the Postgres repository."""
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = datetime.now(UTC)
    try:
        async with maker() as session, session.begin():
            repo = PostgresObservationRepository(session)
            for days_ago, value in ((90, 9.0), (60, 8.3), (30, 7.6), (5, 7.0)):
                await repo.add(
                    lab_result_to_observation(
                        LabResultIn(
                            loinc_code="4548-4",
                            display="Hemoglobin A1c",
                            value=value,
                            unit="%",
                            effective_at=now - timedelta(days=days_ago),
                            status=LabStatus.final,
                        ),
                        patient_id=patient_id,
                        origin=DataOrigin.ehr_imported,
                        recorded_by_role="system",
                        quality={"source_system": "Synthetic Health"},
                    )
                )
    finally:
        await engine.dispose()


async def _audit_events(url: str, patient_id: uuid.UUID) -> list[tuple[str, uuid.UUID | None]]:
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with maker() as session:
            events = await PostgresAuditEventRepository(session).list_for_patient(patient_id)
            return [(e.action, e.actor_id) for e in events]
    finally:
        await engine.dispose()


@requires_postgres
def test_registration_survives_a_process_restart(db_url: str) -> None:
    """Register in one 'process', restart (fresh app + dropped caches), log in again."""
    email = f"durable-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as first_process:
        _register(first_process, email, SYNTHETIC_PASSWORD)

    # Simulated restart: new app instance, all process-level singletons dropped.
    # Only the database carries state across the boundary.
    _reset_process_singletons()

    with TestClient(create_app()) as second_process:
        resp = second_process.post(
            "/auth/login", json={"email": email, "password": SYNTHETIC_PASSWORD}
        )
        assert resp.status_code == 200, resp.text
        me = second_process.get("/auth/me", headers=_auth_header(resp.json()["access_token"]))
        assert me.status_code == 200
        assert me.json()["email"] == email
        assert me.json()["patient_id"] is not None


@requires_postgres
def test_capability_toggle_survives_a_process_restart(db_url: str) -> None:
    """Toggle off in one 'process'; after a restart the durable row still refuses the
    feature (ADR-0013) and the change audit is on file (CLAUDE.md §5)."""
    email = f"toggle-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as first_process:
        tokens = _register(first_process, email, SYNTHETIC_PASSWORD)
        headers = _auth_header(tokens["access_token"])
        me = first_process.get("/auth/me", headers=headers).json()
        patient_id = uuid.UUID(me["patient_id"])
        user_id = uuid.UUID(me["user_id"])
        resp = first_process.put(
            "/capabilities/ingest_adl", headers=headers, json={"active": False}
        )
        assert resp.status_code == 200, resp.text

    _reset_process_singletons()

    with TestClient(create_app()) as second_process:
        login = second_process.post(
            "/auth/login", json={"email": email, "password": SYNTHETIC_PASSWORD}
        )
        headers = _auth_header(login.json()["access_token"])
        states = second_process.get("/capabilities", headers=headers).json()["capabilities"]
        by_key = {c["key"]: c for c in states}
        assert by_key["ingest_adl"]["active"] is False  # the toggle outlived the restart
        assert by_key["ingest_labs"]["active"] is True  # absence of a row = default
        adl = second_process.post(
            "/adl", headers=headers, json={"walking": 3, "stairs": 2, "balance_confidence": 4}
        )
        assert adl.status_code == 409  # the enforcement seam reads the durable row

    # The config-change audit was committed by the request transaction and is durable.
    events = asyncio.run(_audit_events(db_url, patient_id))
    assert ("set_capability", user_id) in events


@requires_postgres
def test_observations_persist_and_flow_through_the_trajectory_api(db_url: str) -> None:
    """Repository-ingested observations are visible via GET /trajectory, and the PHI
    read lands in the persisted audit log (CLAUDE.md §5)."""
    email = f"trend-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as client:
        tokens = _register(client, email, "a-strong-password")
        me = client.get("/auth/me", headers=_auth_header(tokens["access_token"]))
        patient_id = uuid.UUID(me.json()["patient_id"])
        user_id = uuid.UUID(me.json()["user_id"])

        asyncio.run(_seed_observations(db_url, patient_id))

        resp = client.get("/trajectory", headers=_auth_header(tokens["access_token"]))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["direction"] == "improving"  # the seeded HbA1c series, read back
        assert body["signals"][0]["source"] == "lab"

    # The audit event was committed by the request-scoped transaction and is
    # durable — read back over a completely fresh engine.
    events = asyncio.run(_audit_events(db_url, patient_id))
    assert ("read_trajectory", user_id) in events


@requires_postgres
def test_duplicate_email_rolls_back_and_stays_registrable_once(db_url: str) -> None:
    """The request-scoped transaction maps a unique violation to 409 (no half-writes)."""
    email = f"dup-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as client:
        _register(client, email, "a-strong-password")
        resp = client.post(
            "/auth/register",
            json={"email": email, "password": "another-pass-1", "display_name": "X"},
        )
        assert resp.status_code == 409
        # The failed request's transaction rolled back; the original login still works.
        ok = client.post("/auth/login", json={"email": email, "password": "a-strong-password"})
        assert ok.status_code == 200


def test_in_memory_fallback_serves_requests_without_a_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No DATABASE_URL: the app boots, serves auth + trajectory from the in-memory
    singletons, and (by design) loses state on a process restart."""
    monkeypatch.setattr(settings, "database_url", None)
    _reset_process_singletons()
    email = f"fallback-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as client:
        tokens = _register(client, email, "a-strong-password")
        resp = client.get("/trajectory", headers=_auth_header(tokens["access_token"]))
        assert resp.status_code == 200
        assert resp.json()["direction"] == "insufficient_data"

    # Same process, new app instance: in-memory state is process-scoped, so the
    # account is still there...
    with TestClient(create_app()) as same_process:
        resp = same_process.post(
            "/auth/login", json={"email": email, "password": "a-strong-password"}
        )
        assert resp.status_code == 200

    # ...but a restart loses it — the documented non-durable posture of this mode.
    _reset_process_singletons()
    with TestClient(create_app()) as restarted:
        resp = restarted.post("/auth/login", json={"email": email, "password": "a-strong-password"})
        assert resp.status_code == 401


def test_db_mode_services_are_request_scoped_but_share_process_state() -> None:
    """With a session, providers build fresh services on Postgres repositories while
    the JWT secret stays process-wide. OAuth pending state is DB-backed per request
    (ADR-0017); the token vault WITHOUT a key falls back to the shared process store
    (fail closed — never plaintext in the DB)."""
    session = cast(AsyncSession, object())
    emr_a = deps.get_emr_service(session)
    emr_b = deps.get_emr_service(session)
    assert emr_a is not emr_b  # request-scoped construction
    assert isinstance(emr_a.observations, PostgresObservationRepository)
    # Pending auth is durable: DB-backed store per request, not a process dict.
    assert isinstance(emr_a._pending, PostgresPendingAuthStore)
    assert emr_a._pending is not emr_b._pending
    # No SECRET_STORE_KEY here: both requests share the fail-closed process vault.
    assert isinstance(emr_a.secret_store, InMemorySecretStore)
    assert emr_a.secret_store is emr_b.secret_store  # tokens survive across requests

    auth_a = deps.get_auth_service(session)
    auth_b = deps.get_auth_service(session)
    assert auth_a is not auth_b
    assert isinstance(auth_a.users, PostgresUserRepository)
    assert auth_a.secret == auth_b.secret  # one signing secret per process

    clinic_a = deps.get_clinic_service(session)
    clinic_b = deps.get_clinic_service(session)
    assert clinic_a is not clinic_b  # request-scoped construction
    assert isinstance(clinic_a.clinics, PostgresClinicRepository)
    assert isinstance(clinic_a.connections, PostgresClinicConnectionRepository)
    assert isinstance(clinic_a.users, PostgresUserRepository)
    assert isinstance(clinic_a.observations, PostgresObservationRepository)
    assert isinstance(clinic_a.audit, PostgresAuditEventRepository)

    capability_a = deps.get_capability_service(session)
    capability_b = deps.get_capability_service(session)
    assert capability_a is not capability_b  # request-scoped construction
    assert isinstance(capability_a.capabilities, PostgresCapabilityRepository)
    assert isinstance(capability_a.patient_capabilities, PostgresPatientCapabilityRepository)
    assert isinstance(capability_a.connections, PostgresClinicConnectionRepository)
    assert isinstance(capability_a.audit, PostgresAuditEventRepository)

    deletion_a = deps.get_account_deletion_service(session)
    deletion_b = deps.get_account_deletion_service(session)
    assert deletion_a is not deletion_b  # request-scoped construction
    assert isinstance(deletion_a.users, PostgresUserRepository)
    assert isinstance(deletion_a.observations, PostgresObservationRepository)
    assert isinstance(deletion_a.audit, PostgresAuditEventRepository)
    assert isinstance(deletion_a.pending_auth, PostgresPendingAuthStore)
    # No SECRET_STORE_KEY here: deletion purges tokens from the SAME fail-closed
    # process vault EMR requests use — wherever the tokens live is where they die.
    assert deletion_a.secret_store is deps.get_emr_service(session).secret_store

    # Data export (ADR-0031): request-scoped over the same Postgres repositories, with
    # the clinic/capability services composed on the SAME session so their reads join
    # the request transaction.
    export_a = deps.get_patient_data_export_service(session)
    export_b = deps.get_patient_data_export_service(session)
    assert export_a is not export_b  # request-scoped construction
    assert isinstance(export_a.users, PostgresUserRepository)
    assert isinstance(export_a.observations, PostgresObservationRepository)
    assert isinstance(export_a.emr_connections, PostgresEmrConnectionRepository)
    assert isinstance(export_a.audit, PostgresAuditEventRepository)
    assert isinstance(export_a.clinic.connections, PostgresClinicConnectionRepository)
    assert isinstance(export_a.capabilities.capabilities, PostgresCapabilityRepository)
    # In-memory mode (no session) hands back the shared process-wide singleton.
    assert deps.get_patient_data_export_service() is deps.get_patient_data_export_service()


def test_db_mode_uses_the_configured_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "configured-secret")
    _reset_process_singletons()
    session = cast(AsyncSession, object())
    assert deps.get_auth_service(session).secret == "configured-secret"


def test_db_mode_with_a_key_uses_the_encrypted_postgres_vault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With SECRET_STORE_KEY configured, DB mode vaults tokens encrypted at rest —
    a request-scoped PostgresSecretStore over the one process-parsed key (ADR-0017)."""
    from cryptography.fernet import Fernet

    monkeypatch.setattr(settings, "secret_store_key", Fernet.generate_key().decode())
    _reset_process_singletons()
    session = cast(AsyncSession, object())
    emr_a = deps.get_emr_service(session)
    emr_b = deps.get_emr_service(session)
    assert isinstance(emr_a.secret_store, PostgresSecretStore)
    assert isinstance(emr_b.secret_store, PostgresSecretStore)
    assert emr_a.secret_store is not emr_b.secret_store  # bound to each request's session


def test_db_mode_without_a_key_logs_and_keeps_the_process_vault(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Fail closed (ADR-0017): no key means the in-memory vault — with a clear
    warning — and NEVER plaintext token rows in the database."""
    monkeypatch.setattr(settings, "secret_store_key", None)
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://synthetic-only/db")
    _reset_process_singletons()
    with caplog.at_level(logging.WARNING):
        assert deps._process_fernet() is None
    assert any("SECRET_STORE_KEY" in record.message for record in caplog.records)
    session = cast(AsyncSession, object())
    assert deps.get_emr_service(session).secret_store is deps._process_secret_store()


def test_without_a_session_the_cached_singletons_serve() -> None:
    """The in-memory contract is untouched: no session -> the same instances forever."""
    assert deps.get_auth_service() is deps.get_auth_service()
    assert deps.get_emr_service() is deps.get_emr_service()
    assert deps.get_clinic_service() is deps.get_clinic_service()
    assert deps.get_capability_service() is deps.get_capability_service()
    # In-memory mode keeps the process-level pending store: connect and callback
    # still meet in one process (the ADR-0017 DB store is a DB-mode concern).
    assert deps.get_emr_service()._pending is deps._process_pending_auth()
    # The clinic singleton reads/writes the SAME stores auth and EMR use, so a
    # clinician sees exactly the data the patient's own endpoints wrote.
    clinic = deps.get_clinic_service()
    assert clinic.users is deps.get_auth_service().users
    assert clinic.observations is deps.get_emr_service().observations
    assert clinic.audit is deps.get_emr_service().audit
    # The capability singleton judges toggle authority on the SAME connection store
    # the clinic service maintains, and audits into the same log.
    capability = deps.get_capability_service()
    assert capability.connections is clinic.connections
    assert capability.audit is clinic.audit
    # Account deletion (ADR-0027) destroys data from the SAME stores every feature
    # wrote into — users, EMR connections/tokens, clinic connections, toggles,
    # observations — and audits into the same log.
    deletion = deps.get_account_deletion_service()
    assert deletion is deps.get_account_deletion_service()
    assert deletion.users is deps.get_auth_service().users
    assert deletion.emr_connections is deps.get_emr_service().connections
    assert deletion.pending_auth is deps._process_pending_auth()
    assert deletion.secret_store is deps.get_emr_service().secret_store
    assert deletion.clinic_connections is clinic.connections
    assert deletion.patient_capabilities is capability.patient_capabilities
    assert deletion.observations is clinic.observations
    assert deletion.audit is clinic.audit
