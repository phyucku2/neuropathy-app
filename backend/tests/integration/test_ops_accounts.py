"""Postgres integration for the ops-auth surface (ADR-0019): the first-ops bootstrap
against a real database, the PostgresUserRepository primitives the surface relies on
(count_with_role, set_active), per-operator deactivation persisting and blocking login,
the real ops actor landing in the clinician-provisioning audit, and migration 0005
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
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.main import create_app
from app.models.audit import AuditEvent
from app.models.user import UserRole
from app.repositories.postgres import PostgresUserRepository
from app.repositories.user import UserRecord
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
# ≥ 32 chars — the settings-load minimum a real deployment must meet (ADR-0017).
BOOTSTRAP_TOKEN = "synthetic-bootstrap-token-0123456789abcdef"


@pytest.fixture()
def db_url(migrated_database: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "database_url", migrated_database)
    monkeypatch.setattr(settings, "ops_bootstrap_token", BOOTSTRAP_TOKEN)
    _reset_process_singletons()
    return migrated_database


@pytest.fixture(autouse=True)
def _clean_process_state_afterwards() -> Iterator[None]:
    yield
    _reset_process_singletons()


async def _delete_all_ops(url: str) -> None:
    """Clear ops accounts so the first-ops bootstrap gate is open (the session-scoped
    DB is shared across tests, so ops may already exist)."""
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("DELETE FROM app_user WHERE role = 'ops'"))
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- repository primitives


async def test_postgres_user_repo_count_and_set_active(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The Postgres twins of the ADR-0019 primitives: count_with_role(active_only) and
    set_active flipping the flag, on a real database."""
    async with session_factory() as session:
        repo = PostgresUserRepository(session)
        first = UserRecord(
            id=uuid.uuid4(),
            email=f"ops-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="synthetic-hash",
            display_name="Ops A",
            role=UserRole.ops,
            patient_id=None,
        )
        second = UserRecord(
            id=uuid.uuid4(),
            email=f"ops-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="synthetic-hash",
            display_name="Ops B",
            role=UserRole.ops,
            patient_id=None,
        )
        await repo.add(first)
        await repo.add(second)
        await session.flush()

        assert await repo.count_with_role(UserRole.ops, active_only=True) >= 2
        active_before = await repo.count_with_role(UserRole.ops, active_only=True)

        when = datetime.now(UTC)
        updated = await repo.set_active(second.id, active=False, disabled_at=when)
        assert updated is not None
        assert updated.active is False
        assert updated.disabled_at is not None
        assert await repo.count_with_role(UserRole.ops, active_only=True) == active_before - 1
        # The whole account still exists — a deactivated ops still closes the gate.
        assert await repo.count_with_role(UserRole.ops) >= 2
        assert await repo.set_active(uuid.uuid4(), active=False, disabled_at=None) is None
        await session.rollback()


# ---------------------------------------------------------------- end to end


def test_first_ops_bootstrap_and_attributed_provisioning_in_db_mode(db_url: str) -> None:
    """First-ops bootstrap through a real database, then a clinician provisioned under
    the ops bearer — with the REAL ops actor id landing in the create_clinician audit."""
    asyncio.run(_delete_all_ops(db_url))
    ops_email = f"ops-{uuid.uuid4().hex[:12]}@example.com"
    dr_email = f"dr-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as client:
        created = client.post(
            "/ops/accounts",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json={"email": ops_email, "password": SYNTHETIC_PASSWORD, "display_name": "Ops"},
        )
        assert created.status_code == 201, created.text
        ops_user_id = created.json()["user_id"]

        login = client.post(
            "/auth/login", json={"email": ops_email, "password": SYNTHETIC_PASSWORD}
        )
        ops_headers = _auth_header(login.json()["access_token"])

        provisioned = client.post(
            "/clinic/clinicians",
            headers=ops_headers,
            json={
                "email": dr_email,
                "password": SYNTHETIC_PASSWORD,
                "display_name": "Dr. Synthetic",
                "clinic_name": f"Synthetic Clinic {uuid.uuid4().hex[:8]}",
            },
        )
        assert provisioned.status_code == 201, provisioned.text

    actor = asyncio.run(_create_clinician_actor(db_url, provisioned.json()["user_id"]))
    assert actor == uuid.UUID(ops_user_id)  # attributed to the real operator, durably


def test_ops_deactivation_persists_and_blocks_login_in_db_mode(db_url: str) -> None:
    asyncio.run(_delete_all_ops(db_url))
    ops1_email = f"ops-{uuid.uuid4().hex[:12]}@example.com"
    ops2_email = f"ops-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(create_app()) as client:
        client.post(
            "/ops/accounts",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json={"email": ops1_email, "password": SYNTHETIC_PASSWORD, "display_name": "Ops 1"},
        )
        ops1 = _auth_header(
            client.post(
                "/auth/login", json={"email": ops1_email, "password": SYNTHETIC_PASSWORD}
            ).json()["access_token"]
        )
        second = client.post(
            "/ops/accounts",
            headers=ops1,
            json={"email": ops2_email, "password": SYNTHETIC_PASSWORD, "display_name": "Ops 2"},
        )
        target_id = second.json()["user_id"]
        assert client.post(f"/ops/accounts/{target_id}/deactivate", headers=ops1).status_code == 200

    # A fresh process (dropped caches) must still refuse the deactivated operator —
    # the flag is durable, not process state.
    _reset_process_singletons()
    with TestClient(create_app()) as fresh:
        relogin = fresh.post(
            "/auth/login", json={"email": ops2_email, "password": SYNTHETIC_PASSWORD}
        )
        assert relogin.status_code == 401


async def _create_clinician_actor(url: str, provisioned_user_id: str) -> uuid.UUID | None:
    engine = create_async_engine(url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with maker() as session:
            stmt = (
                select(AuditEvent.actor_id)
                .where(AuditEvent.action == "create_clinician")
                .where(AuditEvent.detail["user_id"].astext == provisioned_user_id)
            )
            return await session.scalar(stmt)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- migration 0005


def test_migration_0005_downgrade_and_reupgrade(migrated_database: str) -> None:
    """0005 must walk down (dropping only the activation columns) and back up, with the
    model/migration parity check (test_postgres_repositories) still green after — the
    same database keeps serving the rest of this suite at head."""

    def _alembic(*args: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=_BACKEND_DIR,
            env={**os.environ, "DATABASE_URL": migrated_database},
            check=True,
            capture_output=True,
            text=True,
        )

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")


async def test_active_column_defaults_true_for_preexisting_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The server_default keeps every account active: a row inserted without touching
    `active` (as a pre-0005 row effectively is) comes back active."""
    async with session_factory() as session:
        email = f"pat-{uuid.uuid4().hex[:10]}@example.com"
        await session.execute(
            text(
                "INSERT INTO app_user (id, email, password_hash, display_name, role) "
                "VALUES (:id, :email, 'h', 'Pat', 'patient')"
            ),
            {"id": uuid.uuid4(), "email": email},
        )
        row = await session.execute(
            text("SELECT active, disabled_at FROM app_user WHERE email = :e"), {"e": email}
        )
        active, disabled_at = row.one()
        assert active is True  # server_default true
        assert disabled_at is None
        await session.rollback()
