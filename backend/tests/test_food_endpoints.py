"""End-to-end tests for the food & nutrition log (ADR-0042 V2, Phase 1).

Patient-role only, capability-gated (`log_food`, OFF by default), confirm-required, ranged,
idempotent per client_entry_id, PHI-safe audit (counts/refs only), and — the structural
guardrail — stored as `source=food` / `origin=patient_estimated` and EXCLUDED from the NSI
(its source is deliberately absent from TRAJECTORY_SOURCES). All data synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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
from app.ingestion.food import food_import_key, food_log_to_observation
from app.main import app
from app.models.observation import DataOrigin, SourceType
from app.models.user import UserRole
from app.repositories.observation import InMemoryObservationRepository
from app.schemas.food import FoodLogIn
from app.services.capability import CapabilityService
from app.services.trajectory import TRAJECTORY_SOURCES, compute_patient_trajectory

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
        raise AssertionError("capture must not touch the network")

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        raise AssertionError("capture must not touch the network")


@pytest.fixture()
def service() -> EmrService:
    return EmrService(transport=_NoNetwork(), client_id="c", redirect_uri="https://a/cb")


@pytest.fixture()
def cap_service() -> CapabilityService:
    return CapabilityService()


@pytest.fixture()
def client(service: EmrService, cap_service: CapabilityService) -> Iterator[TestClient]:
    app.dependency_overrides[get_emr_service] = lambda: service
    app.dependency_overrides[get_capability_service] = lambda: cap_service
    app.dependency_overrides[get_current_user] = lambda: PATIENT
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


async def _enable_food(cap_service: CapabilityService) -> None:
    """Turn the opt-in `log_food` capability on for the fixture patient."""
    await cap_service.set_for_patient(
        patient_id=PATIENT.patient_id,  # type: ignore[arg-type]
        actor_id=PATIENT.user_id,
        key="log_food",
        active=True,
        now=NOW,
    )


def _food_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "description": "Oatmeal with banana",
        "portion": "1 cup",
        "carbs_g": {"low": 30, "high": 45},
        "energy_kcal": {"low": 150, "high": 250},
        "effective_date": "2026-07-10",
        "client_entry_id": str(uuid4()),
        "confirmed": True,
    }
    body.update(overrides)
    return body


# --- capability gate -------------------------------------------------------------------


def test_write_and_estimate_gated_off_by_default(client: TestClient) -> None:
    # log_food defaults OFF (opt-in): both the write and the estimate refuse with 409.
    assert client.post("/food", json=_food_body()).status_code == 409
    assert (
        client.post("/food/estimate", json={"description": "x", "portion": "1 cup"}).status_code
        == 409
    )


def test_requires_auth() -> None:
    with TestClient(app) as anon:
        assert anon.post("/food", json=_food_body()).status_code == 401


def test_clinician_forbidden(service: EmrService, cap_service: CapabilityService) -> None:
    clinician = CurrentUser(
        user_id=uuid4(),
        role=UserRole.clinician,
        patient_id=None,
        email="doc@example.test",
        display_name="Doc",
    )
    app.dependency_overrides[get_emr_service] = lambda: service
    app.dependency_overrides[get_capability_service] = lambda: cap_service
    app.dependency_overrides[get_current_user] = lambda: clinician
    try:
        assert TestClient(app).get("/food").status_code == 403
    finally:
        app.dependency_overrides.clear()


# --- roundtrip + provenance ------------------------------------------------------------


async def test_roundtrip_ranged_and_provenance(
    client: TestClient, service: EmrService, cap_service: CapabilityService
) -> None:
    await _enable_food(cap_service)
    created = client.post("/food", json=_food_body())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["carbs_g"] == {"low": 30.0, "high": 45.0}
    assert body["energy_kcal"] == {"low": 150.0, "high": 250.0}
    assert body["skipped"] is False

    listed = client.get("/food")
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "no-store"
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["description"] == "Oatmeal with banana"
    assert items[0]["carbs_g"] == {"low": 30.0, "high": 45.0}

    # Provenance is the structural guardrail: patient_estimated origin, food source, NO point
    # value (value_num is NULL so it can never read as lab-grade), human_confirmed in quality.
    rows = await service.observations.list_for_patient(PATIENT.patient_id, source=SourceType.food)
    assert len(rows) == 1
    assert rows[0].origin is DataOrigin.patient_estimated
    assert rows[0].source is SourceType.food
    assert rows[0].value_num is None
    assert rows[0].quality["human_confirmed"] is True


async def test_energy_optional(client: TestClient, cap_service: CapabilityService) -> None:
    await _enable_food(cap_service)
    created = client.post("/food", json=_food_body(energy_kcal=None))
    assert created.status_code == 201, created.text
    assert created.json()["energy_kcal"] is None
    assert client.get("/food").json()["items"][0]["energy_kcal"] is None


async def test_idempotent_retry_skips(
    client: TestClient, service: EmrService, cap_service: CapabilityService
) -> None:
    await _enable_food(cap_service)
    body = _food_body()
    first = client.post("/food", json=body)
    second = client.post("/food", json=body)  # same client_entry_id
    assert first.status_code == 201 and first.json()["skipped"] is False
    assert second.status_code == 201 and second.json()["skipped"] is True
    assert first.json()["food_id"] == second.json()["food_id"]
    rows = await service.observations.list_for_patient(PATIENT.patient_id, source=SourceType.food)
    assert len(rows) == 1  # the retry wrote no new row


# --- guardrail validation --------------------------------------------------------------


async def test_unconfirmed_draft_is_rejected(
    client: TestClient, cap_service: CapabilityService
) -> None:
    await _enable_food(cap_service)
    # Human-confirm is structural: an unconfirmed body never stores (422), even with the
    # capability on (so the 422 is the schema guardrail, not the 409 gate).
    assert client.post("/food", json=_food_body(confirmed=False)).status_code == 422


async def test_inverted_range_is_rejected(
    client: TestClient, cap_service: CapabilityService
) -> None:
    await _enable_food(cap_service)
    assert client.post("/food", json=_food_body(carbs_g={"low": 50, "high": 20})).status_code == 422


async def test_absurd_carbs_rejected(client: TestClient, cap_service: CapabilityService) -> None:
    await _enable_food(cap_service)
    assert (
        client.post("/food", json=_food_body(carbs_g={"low": 0, "high": 5000})).status_code == 422
    )


async def test_future_date_rejected(client: TestClient, cap_service: CapabilityService) -> None:
    await _enable_food(cap_service)
    future = (NOW + timedelta(days=3)).date().isoformat()
    assert client.post("/food", json=_food_body(effective_date=future)).status_code == 422


# --- estimate seam (Phase 1: manual fallback) ------------------------------------------


async def test_estimate_returns_manual_fallback(
    client: TestClient, cap_service: CapabilityService
) -> None:
    await _enable_food(cap_service)
    resp = client.post(
        "/food/estimate", json={"description": "a plate of pasta", "portion": "1 cup"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Phase 1 NullNutritionSource: no automated estimate, honest manual-entry framing.
    assert body["estimate"] is None
    assert "estimate" in body["note"].lower()


# --- audit is PHI-free -----------------------------------------------------------------


async def test_audit_is_counts_only(
    client: TestClient, service: EmrService, cap_service: CapabilityService
) -> None:
    await _enable_food(cap_service)
    client.post("/food", json=_food_body(description="Secret Midnight Snack"))
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert [e.action for e in events] == ["record_food"]
    detail = str(events[0].detail)
    assert "Secret Midnight Snack" not in detail  # description never audited
    assert "30" not in detail and "45" not in detail  # estimate values never audited


# --- NSI / trajectory exclusion (the structural guardrail) -----------------------------


def test_food_source_is_excluded_from_trajectory_sources() -> None:
    # The exclusion is by omission: food is NOT in the analyzable set, so a food log can never
    # reach the engine, mint a signal, or enter the NSI (mirrors medication/event).
    assert SourceType.food not in TRAJECTORY_SOURCES


async def test_food_observation_never_counts_toward_trajectory() -> None:
    repo = InMemoryObservationRepository()
    row = food_log_to_observation(
        FoodLogIn.model_validate(_food_body()),
        patient_id=PATIENT.patient_id,  # type: ignore[arg-type]
        import_key=food_import_key(uuid4()),
        recorded_at=NOW,
    )
    await repo.add(row)
    _, analyzable_count = await compute_patient_trajectory(
        repo,
        PATIENT.patient_id,
        now=NOW,  # type: ignore[arg-type]
    )
    assert analyzable_count == 0  # the food row was excluded from the analyzable window
