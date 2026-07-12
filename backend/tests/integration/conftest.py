"""Fixtures for the Postgres integration suite.

These tests run only when TEST_DATABASE_URL is set (CI provides a postgres:16
service; each test module skips cleanly otherwise). The session-scoped fixture
resets the schema and applies the committed migrations — exactly what a deploy does —
so the suite exercises the real DDL, not create_all().
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ["TEST_DATABASE_URL"]


async def _reset_schema(url: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> str:
    """Reset the test database and bring it to alembic head via the real migrations."""
    asyncio.run(_reset_schema(database_url))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        check=True,
        capture_output=True,
        text=True,
    )
    return database_url


@pytest.fixture()
async def engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_database)
    yield engine
    await engine.dispose()


@pytest.fixture()
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
