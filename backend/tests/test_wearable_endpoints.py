"""End-to-end tests for POST /wearable — phone/watch mobility ingestion (ADR-0035).

Imported samples become research-grade Observations that flow into GET /observations and
the trajectory. The capability is OPT-IN (default off), so the happy paths turn it on
first. All data synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    CurrentUser,
    get_capability_service,
    get_current_user,
    get_emr_service,
)
from app.emr.service import EmrService
from app.main import app
from app.models.observation import DataOrigin, SourceType
from app.models.user import UserRole
from app.services.capability import CapabilityService

NOW = datetime.now(UTC)

PATIENT = CurrentUser(
    user_id=uuid4(),
    role=UserRole.patient,
    patient_id=uuid4(),
    email="pat@example.test",
    display_name="Pat",
)


class _NoNetwork:
    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        raise AssertionError("wearable ingest must not touch the network")

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        raise AssertionError("wearable ingest must not touch the network")


@pytest.fixture()
def service() -> EmrService:
    return EmrService(transport=_NoNetwork(), client_id="c", redirect_uri="https://a/cb")


@pytest.fixture()
def cap_service() -> CapabilityService:
    return CapabilityService()


@pytest.fixture()
async def enabled(cap_service: CapabilityService) -> CapabilityService:
    """ingest_wearable turned ON for the patient (it is opt-in / default off)."""
    await cap_service.set_for_patient(
        patient_id=PATIENT.patient_id,
        actor_id=PATIENT.user_id,
        key="ingest_wearable",
        active=True,
        now=NOW,
    )
    return cap_service


@pytest.fixture()
def client(service: EmrService, cap_service: CapabilityService) -> Iterator[TestClient]:
    app.dependency_overrides[get_emr_service] = lambda: service
    app.dependency_overrides[get_capability_service] = lambda: cap_service
    app.dependency_overrides[get_current_user] = lambda: PATIENT
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _sample(
    *,
    metric: str = "wearable_walking_speed",
    value: float = 1.1,
    platform: str = "apple_health",
    source_device: str = "iphone",
    phone_derived: bool = True,
    external_id: str | None = "HK-1",
) -> dict[str, Any]:
    return {
        "metric": metric,
        "value": value,
        "effective_start": "2026-07-15T08:00:00Z",
        "effective_end": "2026-07-15T08:03:00Z",
        "platform": platform,
        "source_device": source_device,
        "phone_derived": phone_derived,
        "external_id": external_id,
    }


def _post(client: TestClient, *samples: dict[str, Any]) -> Any:
    return client.post("/wearable", json={"samples": list(samples)})


# --- happy path ------------------------------------------------------------------------


async def test_import_persists_research_grade_rows(
    client: TestClient, enabled: CapabilityService, service: EmrService
) -> None:
    resp = _post(
        client,
        _sample(metric="wearable_walking_speed", value=1.1, external_id="HK-1"),
        _sample(metric="wearable_step_length", value=0.62, external_id="HK-2"),
        _sample(metric="wearable_walking_asymmetry", value=3.5, external_id="HK-3"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"imported": 3, "skipped": 0}

    rows = await service.observations.list_for_patient(PATIENT.patient_id)
    assert {r.code for r in rows} == {
        "wearable_walking_speed",
        "wearable_step_length",
        "wearable_walking_asymmetry",
    }
    for row in rows:
        assert row.source is SourceType.wearable
        assert row.origin is DataOrigin.device_measured
        assert row.recorded_by_role == "patient"
        assert row.quality["platform"] == "apple_health"
        assert row.import_key is not None and row.import_key.startswith("wearable:")
    speed = next(r for r in rows if r.code == "wearable_walking_speed")
    assert speed.quality["fidelity"] == "reliable"
    asym = next(r for r in rows if r.code == "wearable_walking_asymmetry")
    assert asym.quality["fidelity"] == "advisory"


def test_rows_are_queryable_via_get_observations(
    client: TestClient, enabled: CapabilityService
) -> None:
    _post(client, _sample(value=1.1))
    listed = client.get("/observations").json()
    assert listed["total"] == 1
    item = listed["items"][0]
    assert item["source"] == "wearable"
    assert item["code"] == "wearable_walking_speed"
    assert item["display"] == "Walking speed"
    assert item["unit"] == "m/s"


def test_reimport_of_same_sample_is_idempotent(
    client: TestClient, enabled: CapabilityService
) -> None:
    assert _post(client, _sample(external_id="HK-1")).json()["imported"] == 1
    second = _post(client, _sample(external_id="HK-1")).json()
    assert second == {"imported": 0, "skipped": 1}


def test_duplicate_within_one_batch_is_deduped(
    client: TestClient, enabled: CapabilityService
) -> None:
    # Two samples with the same platform UUID in one request — imported once.
    resp = _post(client, _sample(external_id="HK-dup"), _sample(external_id="HK-dup")).json()
    assert resp == {"imported": 1, "skipped": 1}


# --- validation ------------------------------------------------------------------------


async def test_out_of_range_value_fails_whole_batch_before_any_write(
    client: TestClient, enabled: CapabilityService, service: EmrService
) -> None:
    resp = _post(
        client,
        _sample(metric="wearable_walking_speed", value=1.1, external_id="ok"),
        _sample(metric="wearable_walking_speed", value=9.0, external_id="bad"),  # > 5 m/s
    )
    assert resp.status_code == 422
    # The good sample was NOT partially written — the batch is all-or-nothing.
    assert await service.observations.list_for_patient(PATIENT.patient_id) == []


def test_unknown_metric_is_422(client: TestClient, enabled: CapabilityService) -> None:
    assert _post(client, _sample(metric="wearable_heart_rate")).status_code == 422


# --- guards ----------------------------------------------------------------------------


async def test_capability_off_by_default_refuses_with_409(
    client: TestClient, service: EmrService
) -> None:
    # No toggle set — ingest_wearable defaults OFF (opt-in), so the write is refused.
    resp = _post(client, _sample())
    assert resp.status_code == 409
    assert await service.observations.list_for_patient(PATIENT.patient_id) == []


def test_clinician_cannot_import(client: TestClient, enabled: CapabilityService) -> None:
    clinician = CurrentUser(
        user_id=uuid4(),
        role=UserRole.clinician,
        patient_id=None,
        email="dr@example.test",
        display_name="Dr",
    )
    app.dependency_overrides[get_current_user] = lambda: clinician
    assert _post(client, _sample()).status_code == 403


def test_import_requires_auth() -> None:
    with TestClient(app) as anon:
        assert anon.post("/wearable", json={"samples": [_sample()]}).status_code == 401


# --- audit -----------------------------------------------------------------------------


async def test_audit_is_counts_and_platforms_only(
    client: TestClient, enabled: CapabilityService, service: EmrService
) -> None:
    _post(
        client,
        _sample(metric="wearable_walking_speed", value=1.1, external_id="HK-1"),
        _sample(metric="wearable_step_length", value=0.62, external_id="HK-2"),
    )
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert [e.action for e in events] == ["import_wearable"]
    event = events[0]
    assert event.detail == {
        "received": 2,
        "imported": 2,
        "skipped": 0,
        "platforms": ["apple_health"],
    }
    # No measured value ever reaches the audit log (counts + platform only).
    assert "1.1" not in str(event.detail) and "0.62" not in str(event.detail)
