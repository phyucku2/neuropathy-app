"""App-level persistence wiring: with DATABASE_URL configured every request runs on
Postgres-backed repositories in a request-scoped transaction and data survives a
process restart; without it the in-memory fallback serves requests unchanged.

The durability tests need TEST_DATABASE_URL (like the rest of this package) and skip
cleanly otherwise. The provider-contract and fallback tests need no database and always
run. All data is synthetic — no real patient data (CLAUDE.md §5).
"""

from __future__ import annotations

import asyncio
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
from app.ingestion.labs import lab_result_to_observation
from app.main import create_app
from app.models.observation import DataOrigin
from app.repositories.postgres import (
    PostgresAuditEventRepository,
    PostgresObservationRepository,
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
    deps._process_jwt_secret.cache_clear()
    deps._process_secret_store.cache_clear()
    deps._process_pending_auth.cache_clear()
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
    OAuth pending state, the token vault, and the JWT secret stay process-wide."""
    session = cast(AsyncSession, object())
    emr_a = deps.get_emr_service(session)
    emr_b = deps.get_emr_service(session)
    assert emr_a is not emr_b  # request-scoped construction
    assert isinstance(emr_a.observations, PostgresObservationRepository)
    assert emr_a.secret_store is emr_b.secret_store  # tokens survive across requests
    assert emr_a._pending is emr_b._pending  # connect/callback span requests

    auth_a = deps.get_auth_service(session)
    auth_b = deps.get_auth_service(session)
    assert auth_a is not auth_b
    assert isinstance(auth_a.users, PostgresUserRepository)
    assert auth_a.secret == auth_b.secret  # one signing secret per process


def test_db_mode_uses_the_configured_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "configured-secret")
    _reset_process_singletons()
    session = cast(AsyncSession, object())
    assert deps.get_auth_service(session).secret == "configured-secret"


def test_without_a_session_the_cached_singletons_serve() -> None:
    """The in-memory contract is untouched: no session -> the same instances forever."""
    assert deps.get_auth_service() is deps.get_auth_service()
    assert deps.get_emr_service() is deps.get_emr_service()
