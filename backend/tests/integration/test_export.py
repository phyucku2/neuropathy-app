"""Postgres integration for the patient data export (ADR-0031): GET /me/export against
a real database — every data class assembled through the Postgres repositories, the
NO-secrets guarantee proven against REAL vault ciphertext (the plaintext tokens, the
opaque token_ref, and the Argon2id password hash are all real rows here and NONE may
appear in the payload), and the one PHI-free export_account audit event committed.

Runs only when TEST_DATABASE_URL is set (skips cleanly otherwise). All data is
synthetic — no real patient data (CLAUDE.md §5).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.main import create_app
from app.models.emr_connection import EmrConnectionStatus
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.repositories.emr_connection import ConnectionRecord
from app.repositories.postgres import PostgresEmrConnectionRepository, PostgresSecretStore
from tests.integration.test_app_db_wiring import (
    SYNTHETIC_PASSWORD,
    _auth_header,
    _reset_process_singletons,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Postgres integration tests need TEST_DATABASE_URL (the CI service provides it)",
)

# The synthetic OAuth tokens vaulted below — the exact strings the no-secrets scan
# proves are absent from the export payload.
SYNTHETIC_ACCESS_TOKEN = "synthetic-ehr-access-token"  # noqa: S105 — synthetic fixture
SYNTHETIC_REFRESH_TOKEN = "synthetic-ehr-refresh-token"  # noqa: S105 — synthetic fixture


@pytest.fixture()
def vault_db(migrated_database: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """The app on the migrated database WITH an encrypted vault key configured, so EMR
    tokens live as real ciphertext rows in the `secret` table (ADR-0017)."""
    monkeypatch.setattr(settings, "database_url", migrated_database)
    monkeypatch.setattr(settings, "secret_store_key", Fernet.generate_key().decode())
    _reset_process_singletons()
    yield migrated_database
    _reset_process_singletons()


def _register(client: TestClient, email: str) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": SYNTHETIC_PASSWORD, "display_name": "Synthetic Pat"},
    )
    assert resp.status_code == 201, resp.text
    tokens: dict[str, str] = resp.json()
    me = client.get("/auth/me", headers=_auth_header(tokens["access_token"])).json()
    return tokens, uuid.UUID(me["user_id"]), uuid.UUID(me["patient_id"])


async def _seed_all_classes(url: str, patient_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    """Give the patient rows in every exported class straight through the Postgres
    repositories: an active EMR connection whose tokens are REAL ciphertext in the
    `secret` table, a consented clinic connection, and observations from all three
    sources. Returns (clinic_id, secret_ref)."""
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = datetime.now(UTC)
    assert settings.secret_store_key is not None
    fernet = Fernet(settings.secret_store_key.encode())
    try:
        async with maker() as session, session.begin():
            secret_ref = await PostgresSecretStore(session, fernet).put(
                {"access_token": SYNTHETIC_ACCESS_TOKEN, "refresh_token": SYNTHETIC_REFRESH_TOKEN}
            )
            await PostgresEmrConnectionRepository(session).add(
                ConnectionRecord(
                    id=uuid.uuid4(),
                    patient_id=patient_id,
                    fhir_base="https://ehr.example/fhir",
                    provider_name="Synthetic Health",
                    status=EmrConnectionStatus.active,
                    granted_scope="patient/Observation.read",
                    token_ref=secret_ref,
                    patient_fhir_id="fhir-patient-9",
                    token_expires_at=now + timedelta(hours=1),
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
                    "VALUES (:id, :patient_id, :clinic_id, 'active', 'clinic', now(), now(), now())"
                ),
                {"id": uuid.uuid4(), "patient_id": patient_id, "clinic_id": clinic_id},
            )

            for source, origin, code, value in (
                (SourceType.lab, DataOrigin.ehr_imported, "4548-4", 7.2),
                (SourceType.biomech, DataOrigin.device_measured, "biomech_balance_score", 64.0),
                (SourceType.adl, DataOrigin.patient_reported, "adl_daily_score", 9.0),
            ):
                session.add(
                    Observation(
                        patient_id=patient_id,
                        source=source,
                        origin=origin,
                        code=code,
                        value_num=value,
                        effective_at=now - timedelta(days=1),
                        recorded_at=now - timedelta(days=1),
                        status=ObservationStatus.final,
                        quality={"human_confirmed": True},
                        payload={"raw": "synthetic"},
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


def test_export_assembles_every_class_and_leaks_no_secret(vault_db: str) -> None:
    email = f"export-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as client:
        tokens, user_id, patient_id = _register(client, email)
        headers = _auth_header(tokens["access_token"])
        # A real toggle write -> a patient_capability row AND a retained audit event.
        assert (
            client.put("/capabilities/ingest_adl", headers=headers, json={"active": False})
        ).status_code == 200
        _, secret_ref = asyncio.run(_seed_all_classes(vault_db, patient_id))

        resp = client.get("/me/export", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Every class assembled from the real DB.
        assert body["schema_version"] == "1.0"
        assert body["subject_id"] == str(patient_id)
        assert body["account"]["email"] == email
        assert body["account"]["created_at"] is not None
        assert body["patient"]["connection_mode"] == "self_connected"
        assert {o["source"] for o in body["observations"]} == {"lab", "biomech", "adl"}
        assert body["emr_connections"][0]["provider_name"] == "Synthetic Health"
        assert body["emr_connections"][0]["patient_fhir_id"] == "fhir-patient-9"
        assert body["clinic_connections"][0]["clinic_name"] == "Synthetic Clinic"
        adl = next(c for c in body["capabilities"] if c["key"] == "ingest_adl")
        assert adl["active"] is False

        # NO SECRETS: the real password hash, the vaulted tokens, and the token_ref
        # that points at them are all live rows here — none may appear in the payload.
        password_hash = asyncio.run(
            _scalar(vault_db, "SELECT password_hash FROM app_user WHERE id = :id", {"id": user_id})
        )
        assert isinstance(password_hash, str) and password_hash.startswith("$argon2")
        serialized = json.dumps(body)
        for forbidden in (
            SYNTHETIC_ACCESS_TOKEN,
            SYNTHETIC_REFRESH_TOKEN,
            password_hash,
            secret_ref,
        ):
            assert forbidden not in serialized

        # ONE PHI-free export_account audit event, committed (verified over a fresh
        # engine, so it is committed state, not the request session's view).
        detail = asyncio.run(
            _scalar(
                vault_db,
                "SELECT detail::text FROM audit_event "
                "WHERE actor_id = :actor AND action = 'export_account'",
                {"actor": user_id},
            )
        )
        assert detail is not None
        assert '"observations": 3' in detail
        assert email not in detail  # counts only, never values


def test_anonymous_export_is_401_against_the_real_app(vault_db: str) -> None:
    with TestClient(create_app()) as client:
        assert client.get("/me/export").status_code == 401
