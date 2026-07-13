"""Same-day ADL supersession against real Postgres: the revises_id anti-join must hide
superseded rows while retaining them (ADR-0006 corrections-as-new-records).

Runs only when TEST_DATABASE_URL is set (skips cleanly otherwise). All data is
synthetic — no real patient data (CLAUDE.md §5).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.adl import ADL_CODES, adl_check_in_to_observations, day_bounds_utc
from app.models.patient import Patient
from app.repositories.postgres import PostgresObservationRepository
from app.schemas.ingestion import AdlCheckInIn

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Postgres integration tests need TEST_DATABASE_URL (the CI service provides it)",
)


async def _new_patient(session: AsyncSession) -> uuid.UUID:
    patient = Patient(display_name="Synthetic ADL Patient")
    session.add(patient)
    await session.flush()
    return patient.id


async def test_second_check_in_supersedes_first_via_revises_chain(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    day = date(2026, 7, 12)
    start, _ = day_bounds_utc(day)
    recorded = datetime(2026, 7, 12, 9, 0, tzinfo=UTC)

    async with session_factory() as session:
        patient_id = await _new_patient(session)
        repo = PostgresObservationRepository(session)
        first = adl_check_in_to_observations(
            AdlCheckInIn(walking=1, stairs=1, balance_confidence=1, check_in_date=day),
            patient_id=patient_id,
            effective_at=start,
            revises={},
            recorded_at=recorded,
        )
        first_ids = {row.code: (await repo.add(row)).id for row in first}
        second = adl_check_in_to_observations(
            AdlCheckInIn(walking=4, stairs=3, balance_confidence=2, check_in_date=day),
            patient_id=patient_id,
            effective_at=start,
            revises={code: rid for code, rid in first_ids.items() if rid is not None},
            recorded_at=recorded,
        )
        for row in second:
            await repo.add(row)
        await session.commit()

    async with session_factory() as session:
        repo = PostgresObservationRepository(session)
        current = await repo.list_for_patient(patient_id)
        # Only the four current rows analyze; the superseded originals are hidden...
        assert len(current) == 4
        assert {row.code for row in current} == set(ADL_CODES)
        by_code = {row.code: row for row in current}
        assert by_code["adl_walking"].value_num == 4.0
        assert by_code["adl_daily_score"].value_num == 9.0
        for code, row in by_code.items():
            assert row.revises_id == first_ids[code]
        # ...but endure in the table (append-only: nothing was deleted or mutated).
        walking_history = await session.get(type(current[0]), first_ids["adl_walking"])
        assert walking_history is not None and walking_history.value_num == 1.0
