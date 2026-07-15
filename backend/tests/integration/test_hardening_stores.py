"""Postgres integration for the hardening stores (ADR-0017): the durable single-use
pending-auth table, the encrypted-at-rest token vault, the audit-log rate-limit
counter, migration 0004 downgrade/upgrade parity, and the OAuth flow surviving a
process restart end to end.

Runs only when TEST_DATABASE_URL is set (skips cleanly otherwise). All data is
synthetic — no real patient data — and every Fernet key is generated at runtime,
never committed (CLAUDE.md §5).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import deps
from app.core.config import settings
from app.emr.service import PendingAuth
from app.main import create_app
from app.models.audit import AuditEvent
from app.models.emr_connection import EmrConnection
from app.models.patient import Patient
from app.models.pending_auth import PendingAuthState
from app.models.secret import StoredSecret
from app.repositories.emr_connection import ConnectionRecord
from app.repositories.postgres import (
    PostgresAuditEventRepository,
    PostgresEmrConnectionRepository,
    PostgresPendingAuthStore,
    PostgresSecretStore,
)
from tests.integration.test_app_db_wiring import (
    SYNTHETIC_PASSWORD,
    _auth_header,
    _register,
    _reset_process_singletons,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Postgres integration tests need TEST_DATABASE_URL (the CI service provides it)",
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture()
def db_url(migrated_database: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point the app at the migrated test database and start from a clean process
    (the test_app_db_wiring twin — fixtures do not cross module boundaries)."""
    monkeypatch.setattr(settings, "database_url", migrated_database)
    _reset_process_singletons()
    return migrated_database


@pytest.fixture(autouse=True)
def _clean_process_state_afterwards() -> Iterator[None]:
    yield
    _reset_process_singletons()


T0 = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
SYNTHETIC_TOKENS = {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh"}


async def _seed_connection(session: AsyncSession) -> uuid.UUID:
    """A patient + EMR connection row for pending_auth's FK to point at."""
    patient = Patient(display_name="Synthetic Integration Patient")
    session.add(patient)
    await session.flush()
    record = ConnectionRecord(
        id=uuid.uuid4(),
        patient_id=patient.id,
        fhir_base="https://ehr.example/fhir",
        provider_name=None,
    )
    await PostgresEmrConnectionRepository(session).add(record)
    return record.id


def _pending(connection_id: uuid.UUID) -> PendingAuth:
    return PendingAuth(
        connection_id=connection_id,
        code_verifier="synthetic-verifier",
        token_endpoint="https://ehr.example/oauth/token",
    )


# ---------------------------------------------------------------- pending auth


async def test_pending_auth_round_trip_is_single_use(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    state = f"state-{uuid.uuid4().hex}"
    async with session_factory() as session:
        connection_id = await _seed_connection(session)
        await PostgresPendingAuthStore(session).put(state, _pending(connection_id), now=T0)
        await session.commit()

    async with session_factory() as session:
        store = PostgresPendingAuthStore(session)
        consumed = await store.consume(state, now=T0 + timedelta(seconds=1))
        assert consumed == _pending(connection_id)
        await session.commit()

    async with session_factory() as session:
        # Replay after a successful (committed) consume: gone for good.
        assert await PostgresPendingAuthStore(session).consume(state, now=T0) is None
        assert await PostgresPendingAuthStore(session).consume("never-issued", now=T0) is None


async def test_pending_auth_expiry_refuses_and_purges(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    expired_state = f"state-{uuid.uuid4().hex}"
    fresh_state = f"state-{uuid.uuid4().hex}"
    ttl = timedelta(seconds=settings.pending_auth_ttl_seconds)
    async with session_factory() as session:
        connection_id = await _seed_connection(session)
        store = PostgresPendingAuthStore(session)
        await store.put(expired_state, _pending(connection_id), now=T0)
        await session.commit()

    async with session_factory() as session:
        # Exactly at the deadline: refused (and the refused row is purged).
        assert await PostgresPendingAuthStore(session).consume(expired_state, now=T0 + ttl) is None
        await session.commit()

    async with session_factory() as session:
        stmt = (
            select(func.count())
            .select_from(PendingAuthState)
            .where(PendingAuthState.state == expired_state)
        )
        assert (await session.scalar(stmt)) == 0  # judged expired AND deleted

    async with session_factory() as session:
        # Opportunistic purge on put: an expired leftover row is swept by the next put.
        connection_id = await _seed_connection(session)
        store = PostgresPendingAuthStore(session)
        await store.put(expired_state, _pending(connection_id), now=T0)
        await store.put(fresh_state, _pending(connection_id), now=T0 + ttl + timedelta(seconds=1))
        remaining = list(await session.scalars(select(PendingAuthState.state)))
        assert expired_state not in remaining
        assert fresh_state in remaining
        await session.rollback()


async def test_two_concurrent_consumes_of_one_state_yield_exactly_one_winner(
    migrated_database: str,
) -> None:
    """THE callback race (ADR-0017): two callbacks presenting the same state on
    separate connections/transactions — DELETE ... RETURNING lets exactly one win."""
    state = f"state-{uuid.uuid4().hex}"
    engine_a = create_async_engine(migrated_database)
    engine_b = create_async_engine(migrated_database)
    try:
        maker_a = async_sessionmaker(engine_a, expire_on_commit=False, class_=AsyncSession)
        maker_b = async_sessionmaker(engine_b, expire_on_commit=False, class_=AsyncSession)
        async with maker_a() as session:
            connection_id = await _seed_connection(session)
            await PostgresPendingAuthStore(session).put(state, _pending(connection_id), now=T0)
            await session.commit()

        async def consume_once(maker: async_sessionmaker[AsyncSession]) -> PendingAuth | None:
            async with maker() as session, session.begin():
                return await PostgresPendingAuthStore(session).consume(
                    state, now=T0 + timedelta(seconds=1)
                )

        results = await asyncio.gather(consume_once(maker_a), consume_once(maker_b))
        winners = [r for r in results if r is not None]
        assert len(winners) == 1  # one callback wins; the racer sees "already used"
        assert winners[0].connection_id == connection_id
    finally:
        await engine_a.dispose()
        await engine_b.dispose()


# ---------------------------------------------------------------- secret vault


async def test_secret_store_round_trips_and_stores_only_ciphertext(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fernet = Fernet(Fernet.generate_key())  # runtime key — never committed
    async with session_factory() as session:
        ref = await PostgresSecretStore(session, fernet).put(SYNTHETIC_TOKENS)
        await session.commit()

    async with session_factory() as session:
        assert await PostgresSecretStore(session, fernet).get(ref) == SYNTHETIC_TOKENS
        assert await PostgresSecretStore(session, fernet).get("secret::never-issued") is None
        row = await session.get(StoredSecret, ref)
        assert row is not None
        for fragment in (b"synthetic-access", b"synthetic-refresh", b"access_token"):
            assert fragment not in row.ciphertext  # encrypted at rest, opaque bytes


async def test_secret_store_with_a_rotated_key_fails_closed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ref = await PostgresSecretStore(session, Fernet(Fernet.generate_key())).put(
            SYNTHETIC_TOKENS
        )
        await session.commit()

    async with session_factory() as session:
        other_key = PostgresSecretStore(session, Fernet(Fernet.generate_key()))
        assert await other_key.get(ref) is None  # undecryptable == missing, never a 500


# ---------------------------------------------------------------- rate-limit counter


async def test_audit_counter_window_edges_in_postgres(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The Postgres twin of the in-memory counter test: trailing edge inclusive,
    other actors/actions excluded — on fixed timestamps."""
    actor = uuid.uuid4()
    window_start = T0 - timedelta(hours=1)
    async with session_factory() as session:
        repo = PostgresAuditEventRepository(session)
        for actor_id, action, at in (
            (actor, "invite_patient", window_start - timedelta(seconds=1)),  # left the window
            (actor, "invite_patient", window_start),  # exactly on the edge — counts
            (actor, "invite_patient", T0),  # in the window
            (uuid.uuid4(), "invite_patient", T0),  # someone else
            (actor, "rate_limited", T0),  # refusals never count
        ):
            await repo.add(
                AuditEvent(
                    actor_id=actor_id,
                    occurred_at=at,
                    actor_role="clinician",
                    action=action,
                    detail={},
                )
            )
        count = await repo.count_actor_events_since(
            actor_id=actor, action="invite_patient", since=window_start
        )
        assert count == 2
        await session.rollback()


# ---------------------------------------------------------------- refusal audits

# ≥ 32 chars — the settings-load minimum a real deployment must meet (ADR-0017).
BOOTSTRAP_TOKEN = "synthetic-bootstrap-token-0123456789abcdef"


async def _count_events(url: str, action: str, clinic_id: str | None = None) -> int:
    engine = create_async_engine(url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with maker() as session:
            stmt = select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
            if clinic_id is not None:
                stmt = stmt.where(AuditEvent.detail["clinic_id"].astext == clinic_id)
            return int(await session.scalar(stmt) or 0)
    finally:
        await engine.dispose()


async def _delete_all_ops(url: str) -> None:
    """Clear ops accounts so the first-ops bootstrap gate is open (ADR-0019): the
    session-scoped DB is shared, so other tests may already have created ops."""
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("DELETE FROM app_user WHERE role = 'ops'"))
    finally:
        await engine.dispose()


def test_denied_attempt_audits_are_durable_in_db_mode(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """rate_limited and bootstrap_denied audits must COMMIT with their request
    (denials are returned responses, never raised HTTPExceptions — an exception
    would roll the request transaction, audit event included, back). The
    bootstrap_denied gate now lives on the first-ops surface (ADR-0019)."""
    monkeypatch.setattr(settings, "ops_bootstrap_token", BOOTSTRAP_TOKEN)
    monkeypatch.setattr(settings, "invite_rate_limit_max", 0)  # every invite refused
    asyncio.run(_delete_all_ops(db_url))  # guarantee the first-ops gate is open
    denied_before = asyncio.run(_count_events(db_url, "bootstrap_denied"))

    email = f"dr-{uuid.uuid4().hex[:12]}@example.com"
    ops_email = f"ops-{uuid.uuid4().hex[:12]}@example.com"
    body = {
        "email": email,
        "password": SYNTHETIC_PASSWORD,
        "display_name": "Dr. Synthetic",
        "clinic_name": f"Synthetic Clinic {uuid.uuid4().hex[:8]}",
    }
    with TestClient(create_app()) as client:
        # First-ops surface, zero ops: a wrong token is a durable bootstrap_denied.
        denied = client.post(
            "/ops/accounts",
            headers={"X-Bootstrap-Token": "wrong-token"},
            json={"email": ops_email, "password": SYNTHETIC_PASSWORD, "display_name": "Ops"},
        )
        assert denied.status_code == 403
        # The real token creates the first operator; provisioning then runs under it.
        provisioned_ops = client.post(
            "/ops/accounts",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json={"email": ops_email, "password": SYNTHETIC_PASSWORD, "display_name": "Ops"},
        )
        assert provisioned_ops.status_code == 201, provisioned_ops.text
        ops_login = client.post(
            "/auth/login", json={"email": ops_email, "password": SYNTHETIC_PASSWORD}
        )
        ops_headers = _auth_header(ops_login.json()["access_token"])
        provisioned = client.post("/clinic/clinicians", headers=ops_headers, json=body)
        assert provisioned.status_code == 201, provisioned.text
        clinic_id = provisioned.json()["clinic_id"]
        login = client.post("/auth/login", json={"email": email, "password": SYNTHETIC_PASSWORD})
        headers = _auth_header(login.json()["access_token"])
        refused = client.post(
            "/clinic/invitations", headers=headers, json={"email": "nobody@example.com"}
        )
        assert refused.status_code == 429

    # Both refusal audits outlived their (refused) requests — committed, not rolled back.
    assert asyncio.run(_count_events(db_url, "rate_limited", clinic_id=clinic_id)) == 1
    assert asyncio.run(_count_events(db_url, "bootstrap_denied")) == denied_before + 1


# ---------------------------------------------------------------- migration 0004


def test_migration_0004_downgrade_and_reupgrade(migrated_database: str) -> None:
    """0004 must walk down (dropping only transient OAuth state) and back up, with
    the model/migration parity check (test_postgres_repositories) still green after —
    the same database continues serving the rest of this suite at head."""

    def _alembic(*args: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=_BACKEND_DIR,
            env={**os.environ, "DATABASE_URL": migrated_database},
            check=True,
            capture_output=True,
            text=True,
        )

    _alembic("downgrade", "0003")
    _alembic("upgrade", "head")


# ---------------------------------------------------------------- end to end


class _FakeEmr:
    """Plays the EMR: SMART discovery, token endpoint, Observation search."""

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        if url.endswith("/.well-known/smart-configuration"):
            return {
                "authorization_endpoint": "https://ehr.example/oauth/authorize",
                "token_endpoint": "https://ehr.example/oauth/token",
            }
        assert access_token == "the-access-token"
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4"}]},
                        "effectiveDateTime": "2026-06-15T08:30:00+00:00",
                        "valueQuantity": {"value": 7.2, "unit": "%"},
                    }
                }
            ],
        }

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        return {
            "access_token": "the-access-token",
            "patient": "fhir-patient-9",
            "scope": "patient/Observation.read",
        }


def test_oauth_flow_survives_process_restarts_between_every_leg(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two retired limitations, proven end to end: connect on one 'process',
    callback on a second (durable pending_auth), pull on a third (encrypted durable
    token vault) — and the used state stays single-use across all of it."""
    monkeypatch.setattr(settings, "secret_store_key", Fernet.generate_key().decode())
    # Connect now fails EARLY (422) on the unconfigured-client placeholder, so the
    # flow under test needs a real (synthetic) generic client id configured.
    monkeypatch.setattr(settings, "smart_client_id", "synthetic-generic-client-id")
    fake = _FakeEmr()
    # lru_cache so _reset_process_singletons can keep calling cache_clear() on it.
    monkeypatch.setattr(deps, "_process_transport", lru_cache(maxsize=1)(lambda: fake))
    _reset_process_singletons()

    email = f"emr-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as first_process:
        tokens = _register(first_process, email, SYNTHETIC_PASSWORD)
        resp = first_process.post(
            "/emr/connect",
            json={"fhir_base": "https://ehr.example/fhir"},
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 200, resp.text
        connection_id, state = resp.json()["connection_id"], resp.json()["state"]

    _reset_process_singletons()  # restart between connect and callback

    with TestClient(create_app()) as second_process:
        login = second_process.post(
            "/auth/login", json={"email": email, "password": SYNTHETIC_PASSWORD}
        )
        headers = _auth_header(login.json()["access_token"])
        callback = second_process.get(
            "/emr/callback", params={"state": state, "code": "auth-code"}, headers=headers
        )
        assert callback.status_code == 200, callback.text
        assert callback.json()["status"] == "active"
        # Single-use survives the success: an immediate replay is refused.
        replay = second_process.get(
            "/emr/callback", params={"state": state, "code": "auth-code"}, headers=headers
        )
        assert replay.status_code == 404

    _reset_process_singletons()  # restart between callback and pull

    with TestClient(create_app()) as third_process:
        login = third_process.post(
            "/auth/login", json={"email": email, "password": SYNTHETIC_PASSWORD}
        )
        headers = _auth_header(login.json()["access_token"])
        pull = third_process.post(f"/emr/connections/{connection_id}/pull", headers=headers)
        assert pull.status_code == 200, pull.text  # tokens outlived the vaulting process
        assert pull.json()["imported"] == 1


# ---------------------------------------------------------------- deletion on revoke


async def _connection_token_ref(url: str, connection_id: str) -> str | None:
    engine = create_async_engine(url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with maker() as session:
            return await session.scalar(
                select(EmrConnection.token_ref).where(EmrConnection.id == uuid.UUID(connection_id))
            )
    finally:
        await engine.dispose()


async def _secret_row_count(url: str, ref: str) -> int:
    engine = create_async_engine(url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with maker() as session:
            stmt = select(func.count()).select_from(StoredSecret).where(StoredSecret.ref == ref)
            return int(await session.scalar(stmt) or 0)
    finally:
        await engine.dispose()


def test_revoke_deletes_the_secret_row_and_pull_still_409s(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deletion-on-revoke in DB mode (ADR-0017): revoking removes the encrypted token
    row itself — a database dump taken afterwards holds no ciphertext to decrypt —
    and a pull after revocation answers the clean 409, never a 500."""
    monkeypatch.setattr(settings, "secret_store_key", Fernet.generate_key().decode())
    # A real (synthetic) generic client id — the placeholder now 422s at connect.
    monkeypatch.setattr(settings, "smart_client_id", "synthetic-generic-client-id")
    fake = _FakeEmr()
    monkeypatch.setattr(deps, "_process_transport", lru_cache(maxsize=1)(lambda: fake))
    _reset_process_singletons()

    email = f"revoke-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as client:
        tokens = _register(client, email, SYNTHETIC_PASSWORD)
        headers = _auth_header(tokens["access_token"])
        started = client.post(
            "/emr/connect", json={"fhir_base": "https://ehr.example/fhir"}, headers=headers
        )
        assert started.status_code == 200, started.text
        connection_id, state = started.json()["connection_id"], started.json()["state"]
        callback = client.get(
            "/emr/callback", params={"state": state, "code": "auth-code"}, headers=headers
        )
        assert callback.status_code == 200, callback.text
        ref = asyncio.run(_connection_token_ref(db_url, connection_id))
        assert ref is not None
        assert asyncio.run(_secret_row_count(db_url, ref)) == 1  # vaulted, encrypted

        revoked = client.delete(f"/emr/connections/{connection_id}", headers=headers)
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        # The ciphertext row AND the dangling reference are both gone for good.
        assert asyncio.run(_secret_row_count(db_url, ref)) == 0
        assert asyncio.run(_connection_token_ref(db_url, connection_id)) is None
        pull = client.post(f"/emr/connections/{connection_id}/pull", headers=headers)
        assert pull.status_code == 409  # revoked answers the clean conflict, never a 500
