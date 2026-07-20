"""Postgres integration for patient account & data deletion (ADR-0027): the full
DELETE /auth/me transaction against a real database — every table's rows destroyed in
FK-safe order, the encrypted vault row purged, the audit history retained with
patient_id detached by the ON DELETE SET NULL FK (migration 0006), refresh/login dead
afterwards — plus the wrong-password refusal deleting nothing, and migration 0006
upgrade/downgrade/re-upgrade with model parity intact.

Runs only when TEST_DATABASE_URL is set (skips cleanly otherwise). All data is
synthetic — no real patient data (CLAUDE.md §5).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.main import create_app
from app.models.emr_clinical_note import EmrClinicalNote
from app.models.emr_connection import EmrConnectionStatus
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.repositories.emr_connection import ConnectionRecord
from app.repositories.pending_auth import PendingAuth
from app.repositories.postgres import (
    PostgresEmrClinicalNoteRepository,
    PostgresEmrConnectionRepository,
    PostgresPendingAuthStore,
    PostgresSecretStore,
)
from tests.integration.test_app_db_wiring import (
    SYNTHETIC_PASSWORD,
    _auth_header,
    _reset_process_singletons,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Postgres integration tests need TEST_DATABASE_URL (the CI service provides it)",
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]

# Every table that holds (or references) one patient's data, checked to be empty after
# the deletion — plus audit_event, checked separately because it is RETAINED.
_PATIENT_SCOPED_COUNTS = {
    "app_user": "SELECT count(*) FROM app_user WHERE id = :user_id",
    "patient": "SELECT count(*) FROM patient WHERE id = :patient_id",
    "emr_connection": "SELECT count(*) FROM emr_connection WHERE patient_id = :patient_id",
    "pending_auth": (
        "SELECT count(*) FROM pending_auth WHERE connection_id IN "
        "(SELECT id FROM emr_connection WHERE patient_id = :patient_id)"
    ),
    "clinic_connection": "SELECT count(*) FROM clinic_connection WHERE patient_id = :patient_id",
    "patient_capability": (
        "SELECT count(*) FROM patient_capability WHERE patient_id = :patient_id"
    ),
    "observation": "SELECT count(*) FROM observation WHERE patient_id = :patient_id",
    "emr_clinical_note": ("SELECT count(*) FROM emr_clinical_note WHERE patient_id = :patient_id"),
}


@pytest.fixture()
def vault_db(migrated_database: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """The app on the migrated database WITH an encrypted vault key configured, so
    EMR tokens live as real ciphertext rows in the `secret` table (ADR-0017)."""
    monkeypatch.setattr(settings, "database_url", migrated_database)
    monkeypatch.setattr(settings, "secret_store_key", Fernet.generate_key().decode())
    _reset_process_singletons()
    yield migrated_database
    _reset_process_singletons()


def _delete(client: TestClient, access_token: str, password: str) -> Response:
    return client.request(
        "DELETE", "/auth/me", headers=_auth_header(access_token), json={"password": password}
    )


def _register(client: TestClient, email: str) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": SYNTHETIC_PASSWORD, "display_name": "Synthetic Pat"},
    )
    assert resp.status_code == 201, resp.text
    tokens: dict[str, str] = resp.json()
    me = client.get("/auth/me", headers=_auth_header(tokens["access_token"])).json()
    return tokens, uuid.UUID(me["user_id"]), uuid.UUID(me["patient_id"])


async def _seed_all_tables(url: str, patient_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    """Give the patient rows in every deletable table, straight through the Postgres
    repositories: an active EMR connection whose tokens are REAL ciphertext in the
    `secret` table, a pending handshake, a clinic connection, and a supersede chain
    of observations. Returns (clinic_id, secret_ref)."""
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = datetime.now(UTC)
    assert settings.secret_store_key is not None
    fernet = Fernet(settings.secret_store_key.encode())
    try:
        async with maker() as session, session.begin():
            secret_ref = await PostgresSecretStore(session, fernet).put(
                {"access_token": "synthetic-ehr-access", "refresh_token": "synthetic-ehr-refresh"}
            )
            connections = PostgresEmrConnectionRepository(session)
            active_id, authorizing_id = uuid.uuid4(), uuid.uuid4()
            await connections.add(
                ConnectionRecord(
                    id=active_id,
                    patient_id=patient_id,
                    fhir_base="https://ehr.example/fhir",
                    provider_name="Synthetic Health",
                    status=EmrConnectionStatus.active,
                    token_ref=secret_ref,
                    patient_fhir_id="fhir-patient-9",
                )
            )
            await connections.add(
                ConnectionRecord(
                    id=authorizing_id,
                    patient_id=patient_id,
                    fhir_base="https://ehr.example/fhir",
                    provider_name=None,
                )
            )
            await PostgresPendingAuthStore(session).put(
                f"synthetic-state-{uuid.uuid4().hex}",
                PendingAuth(
                    connection_id=authorizing_id,
                    code_verifier="synthetic-verifier",
                    token_endpoint="https://ehr.example/oauth/token",
                ),
                now=now,
            )

            # A pulled EMR clinical note (FKs the active connection) — must die BEFORE the
            # connection in the deletion's FK-safe order (ADR-0045 P2 #27).
            await PostgresEmrClinicalNoteRepository(session).add_if_absent(
                EmrClinicalNote(
                    patient_id=patient_id,
                    connection_id=active_id,
                    origin=DataOrigin.ehr_imported,
                    source_system="Synthetic Health",
                    document_fhir_id="DocRef/synthetic-1",
                    type_code="11506-3",
                    type_display="Progress note",
                    category="clinical-note",
                    authored_at=now,
                    author_display="Dr Synthetic",
                    has_inline_data=False,
                    import_key="docref:DocRef/synthetic-1",
                )
            )

            clinic_id = uuid.uuid4()
            await session.execute(
                text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
                {"id": clinic_id},
            )
            await session.execute(
                text(
                    "INSERT INTO clinic_connection "
                    "(id, patient_id, clinic_id, status, initiated_by, consent_granted_at, "
                    "created_at, updated_at) "
                    "VALUES (:id, :patient_id, :clinic_id, 'active', 'clinic', now(), "
                    "now(), now())"
                ),
                {"id": uuid.uuid4(), "patient_id": patient_id, "clinic_id": clinic_id},
            )

            original = Observation(
                patient_id=patient_id,
                source=SourceType.adl,
                origin=DataOrigin.patient_reported,
                code="adl_daily_score",
                value_num=9.0,
                effective_at=now - timedelta(days=1),
                recorded_at=now - timedelta(days=1),
                status=ObservationStatus.final,
                quality={"human_confirmed": True},
                payload={},
            )
            session.add(original)
            await session.flush()
            # The self-referencing supersede FK the deletion must clear (ADR-0027).
            session.add(
                Observation(
                    patient_id=patient_id,
                    source=SourceType.adl,
                    origin=DataOrigin.patient_reported,
                    code="adl_daily_score",
                    value_num=8.0,
                    effective_at=now,
                    recorded_at=now,
                    status=ObservationStatus.corrected,
                    revises_id=original.id,
                    quality={"human_confirmed": True},
                    payload={},
                )
            )
        return clinic_id, secret_ref
    finally:
        await engine.dispose()


async def _scalar(url: str, sql: str, params: dict[str, Any]) -> Any:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return await conn.scalar(text(sql), params)
    finally:
        await engine.dispose()


async def _row_counts(url: str, user_id: uuid.UUID, patient_id: uuid.UUID) -> dict[str, int]:
    engine = create_async_engine(url)
    params = {"user_id": user_id, "patient_id": patient_id}
    try:
        async with engine.connect() as conn:
            return {
                table: int(await conn.scalar(text(sql), params) or 0)
                for table, sql in _PATIENT_SCOPED_COUNTS.items()
            }
    finally:
        await engine.dispose()


def test_deletion_destroys_every_table_and_retains_anonymous_audit(vault_db: str) -> None:
    email = f"delete-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as client:
        tokens, user_id, patient_id = _register(client, email)
        headers = _auth_header(tokens["access_token"])
        # A real toggle write -> a patient_capability row AND a retained audit event.
        assert (
            client.put("/capabilities/ingest_adl", headers=headers, json={"active": False})
        ).status_code == 200
        _, secret_ref = asyncio.run(_seed_all_tables(vault_db, patient_id))

        before = asyncio.run(_row_counts(vault_db, user_id, patient_id))
        assert all(count >= 1 for count in before.values()), before

        resp = _delete(client, tokens["access_token"], SYNTHETIC_PASSWORD)
        assert resp.status_code == 204, resp.text

        # Every patient-scoped table is empty — verified over a fresh engine, so this
        # is committed state, not the request session's view.
        after = asyncio.run(_row_counts(vault_db, user_id, patient_id))
        assert after == dict.fromkeys(_PATIENT_SCOPED_COUNTS, 0), after
        # The vault ciphertext row is gone (the ADR-0017 deletion seam).
        assert (
            asyncio.run(
                _scalar(
                    vault_db, "SELECT count(*) FROM secret WHERE ref = :ref", {"ref": secret_ref}
                )
            )
            == 0
        )

        # Audit rows are RETAINED — anonymous. The FK (migration 0006) detached them:
        # the deletion event itself and the earlier set_capability event both survive
        # with patient_id NULL, still attributable via actor_id.
        actions = asyncio.run(
            _scalar(
                vault_db,
                "SELECT count(*) FROM audit_event "
                "WHERE actor_id = :actor AND patient_id IS NULL "
                "AND action IN ('delete_account', 'set_capability')",
                {"actor": user_id},
            )
        )
        assert actions == 2
        assert (
            asyncio.run(
                _scalar(
                    vault_db,
                    "SELECT count(*) FROM audit_event WHERE patient_id = :patient_id",
                    {"patient_id": patient_id},
                )
            )
            == 0
        )
        detail = asyncio.run(
            _scalar(
                vault_db,
                "SELECT detail::text FROM audit_event "
                "WHERE actor_id = :actor AND action = 'delete_account'",
                {"actor": user_id},
            )
        )
        # PHI-free: counts only, no email/name/values.
        assert '"vault_secrets": 1' in detail
        assert email not in detail

        # Every credential is dead: access token, refresh token, password login.
        assert client.get("/auth/me", headers=headers).status_code == 401
        refresh = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert refresh.status_code == 401
        login = client.post("/auth/login", json={"email": email, "password": SYNTHETIC_PASSWORD})
        assert login.status_code == 401
        # A second delete attempt is 401 (the token no longer authenticates anyone).
        assert _delete(client, tokens["access_token"], SYNTHETIC_PASSWORD).status_code == 401


def test_wrong_password_is_403_and_the_transaction_deletes_nothing(vault_db: str) -> None:
    email = f"keep-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as client:
        tokens, user_id, patient_id = _register(client, email)
        asyncio.run(_seed_all_tables(vault_db, patient_id))
        before = asyncio.run(_row_counts(vault_db, user_id, patient_id))

        resp = _delete(client, tokens["access_token"], "not-the-password")
        assert resp.status_code == 403
        assert "didn't match" in resp.json()["detail"]

        # Nothing changed — same counts, account still logs in, no deletion audit.
        assert asyncio.run(_row_counts(vault_db, user_id, patient_id)) == before
        login = client.post("/auth/login", json={"email": email, "password": SYNTHETIC_PASSWORD})
        assert login.status_code == 200
        assert (
            asyncio.run(
                _scalar(
                    vault_db,
                    "SELECT count(*) FROM audit_event "
                    "WHERE actor_id = :actor AND action = 'delete_account'",
                    {"actor": user_id},
                )
            )
            == 0
        )
        # The refusal itself IS audited — one bounded 'account_delete_denied' row,
        # COMMITTED despite the 403 (the denial is returned, not raised, so the
        # request transaction commits the event the throttle counts).
        assert (
            asyncio.run(
                _scalar(
                    vault_db,
                    "SELECT count(*) FROM audit_event "
                    "WHERE actor_id = :actor AND action = 'account_delete_denied'",
                    {"actor": user_id},
                )
            )
            == 1
        )


def test_failed_password_throttle_answers_429_over_the_committed_budget(
    vault_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dual-store parity for the DELETE /auth/me throttle: the denial rows commit,
    the sliding-window count reads them back across requests, and over the budget
    even the CORRECT password answers 429 — while the row volume stays capped."""
    monkeypatch.setattr(settings, "delete_account_rate_limit_max", 2)
    email = f"throttle-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as client:
        tokens, user_id, _ = _register(client, email)

        for _ in range(2):
            assert _delete(client, tokens["access_token"], "not-the-password").status_code == 403
        over = _delete(client, tokens["access_token"], "not-the-password")
        assert over.status_code == 429
        assert "Nothing was deleted" in over.json()["detail"]
        # Correct password inside the exhausted window: still 429 (the limiter fires
        # before the Argon2id verify), and the account survives untouched.
        assert _delete(client, tokens["access_token"], SYNTHETIC_PASSWORD).status_code == 429
        me = client.get("/auth/me", headers=_auth_header(tokens["access_token"]))
        assert me.status_code == 200

        # The audit volume is bounded by the budget: exactly 2 denial rows, no more.
        denials = asyncio.run(
            _scalar(
                vault_db,
                "SELECT count(*) FROM audit_event "
                "WHERE actor_id = :actor AND action = 'account_delete_denied'",
                {"actor": user_id},
            )
        )
        assert denials == 2


def test_clinician_and_ops_roles_cannot_reach_the_deletion_flow(
    vault_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """require_patient answers 403 before the service runs — proven here against the
    real DB wiring with a provisioned ops principal (clinician covered in unit)."""
    from tests.integration.test_ops_accounts import BOOTSTRAP_TOKEN, _delete_all_ops

    email = f"ops-{uuid.uuid4().hex[:12]}@example.com"
    monkeypatch.setattr(settings, "ops_bootstrap_token", BOOTSTRAP_TOKEN)
    with TestClient(create_app()) as client:
        # Clear ops accounts so the first-ops bootstrap gate is open for this test.
        asyncio.run(_delete_all_ops(vault_db))
        created = client.post(
            "/ops/accounts",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json={"email": email, "password": SYNTHETIC_PASSWORD, "display_name": "Ops"},
        )
        assert created.status_code == 201, created.text
        login = client.post("/auth/login", json={"email": email, "password": SYNTHETIC_PASSWORD})
        resp = _delete(client, login.json()["access_token"], SYNTHETIC_PASSWORD)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Patient account required"


async def test_fk_detaches_audit_rows_when_the_patient_row_dies(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The migration-0006 behavior in isolation: deleting a patient row flips its
    audit events to patient_id NULL instead of erroring or cascading them away."""
    patient_id = uuid.uuid4()
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO patient (id, display_name, connection_mode, created_at, "
                "updated_at) VALUES (:id, 'Synthetic', 'self_connected', now(), now())"
            ),
            {"id": patient_id},
        )
        await session.execute(
            text(
                "INSERT INTO audit_event (id, actor_id, actor_role, action, patient_id, "
                "detail) VALUES (:id, :actor, 'patient', 'synthetic_action', :patient_id, "
                "'{}'::jsonb)"
            ),
            {"id": uuid.uuid4(), "actor": uuid.uuid4(), "patient_id": patient_id},
        )
        await session.execute(text("DELETE FROM patient WHERE id = :id"), {"id": patient_id})
        retained = await session.scalar(
            text(
                "SELECT count(*) FROM audit_event "
                "WHERE action = 'synthetic_action' AND patient_id IS NULL"
            )
        )
        assert retained == 1
        await session.rollback()


def test_migration_0006_downgrade_and_reupgrade(migrated_database: str) -> None:
    """0006 must walk down (restoring the plain FK — always safe: patient_id is
    nullable and remaining values reference live patients) and back up, with the
    model/migration parity check (test_postgres_repositories) still green after."""

    def _alembic(*args: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=_BACKEND_DIR,
            env={**os.environ, "DATABASE_URL": migrated_database},
            check=True,
            capture_output=True,
            text=True,
        )

    _alembic("downgrade", "0005")
    _alembic("upgrade", "head")
