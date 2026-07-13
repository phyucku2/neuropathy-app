"""End-to-end tests for POST /biomech/reports and its downstream surfaces (ADR-0014).

Uploaded BioMech reports become research-grade Observations that flow into
GET /observations and the trajectory automatically. All PDFs and data are synthetic
(CLAUDE.md §5); PDFs are built in-test (tests/synthetic_pdf.py), no binary fixtures.
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
from app.main import app
from app.models.observation import DataOrigin, ObservationStatus, SourceType
from app.models.user import UserRole
from app.services.capability import CapabilityService
from tests.synthetic_pdf import build_pdf

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
        raise AssertionError("biomech ingest must not touch the network")

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        raise AssertionError("biomech ingest must not touch the network")


@pytest.fixture()
def service() -> EmrService:
    return EmrService(transport=_NoNetwork(), client_id="c", redirect_uri="https://a/cb")


@pytest.fixture()
def cap_service() -> CapabilityService:
    """A fresh capability service per test so a toggle in one never leaks into another."""
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


def _balance_report(
    *,
    date: str = "2026-06-15T00:00:00",
    score: int = 82,
    sway_velocity: float = 12.4,
    sway_area: int = 340,
) -> str:
    return "\n".join(
        [
            "BioMech Balance Assessment Report",
            f"Assessment Date: {date}",
            "Device: BioMech Balance Platform v3",
            f"Overall Balance Score: {score} / 100",
            f"Sway Velocity: {sway_velocity} mm/s",
            f"Sway Area: {sway_area} mm2",
        ]
    )


def _upload(client: TestClient, text: str, *, filename: str = "report.pdf") -> Any:
    return client.post(
        "/biomech/reports",
        files={"file": (filename, build_pdf(text), "application/pdf")},
    )


# --- happy path ------------------------------------------------------------------------


async def test_upload_persists_research_grade_biomech_rows(
    client: TestClient, service: EmrService
) -> None:
    resp = _upload(client, _balance_report())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["report_kind"] == "balance"
    assert body["assessment_at"] == "2026-06-15T00:00:00Z"
    assert body["imported"] == 3 and body["skipped"] == 0
    assert body["warnings"] == []

    rows = await service.observations.list_for_patient(PATIENT.patient_id)
    assert {row.code for row in rows} == {
        "biomech_balance_score",
        "biomech_sway_velocity",
        "biomech_sway_area",
    }
    for row in rows:
        assert row.source is SourceType.biomech
        assert row.origin is DataOrigin.document_imported
        assert row.status is ObservationStatus.final
        assert row.recorded_by_role == "patient"
        assert row.quality["source_system"] == "BioMech"
        assert row.quality["extraction"] == "pdf_text"
        assert row.quality["report_kind"] == "balance"
        assert row.effective_at == datetime(2026, 6, 15, tzinfo=UTC)
        assert row.import_key is not None and row.import_key.startswith("content:biomech:")


def test_uploaded_rows_are_queryable_via_get_observations(client: TestClient) -> None:
    _upload(client, _balance_report())
    listed = client.get("/observations").json()
    assert listed["total"] == 3
    assert {item["source"] for item in listed["items"]} == {"biomech"}
    by_code = {item["code"]: item for item in listed["items"]}
    assert by_code["biomech_balance_score"]["value"] == 82.0
    assert by_code["biomech_balance_score"]["display"] == "Balance score"
    assert by_code["biomech_sway_velocity"]["unit"] == "mm/s"


def test_reupload_of_same_report_is_idempotent(client: TestClient) -> None:
    assert _upload(client, _balance_report()).json()["imported"] == 3
    second = _upload(client, _balance_report()).json()
    assert second["imported"] == 0 and second["skipped"] == 3


def test_trajectory_shows_a_sourced_biomech_signal(client: TestClient) -> None:
    # Three balance reports over ~2 months: balance rising and sway falling — every
    # judged signal improving, so the overall call is improving too.
    for days_ago, score, sway_v, sway_a in (
        (60, 74, 18.0, 400),
        (30, 79, 15.0, 360),
        (2, 82, 12.0, 320),
    ):
        date = (NOW - timedelta(days=days_ago)).date().isoformat() + "T00:00:00"
        _upload(
            client, _balance_report(date=date, score=score, sway_velocity=sway_v, sway_area=sway_a)
        )

    trajectory = client.get("/trajectory").json()
    balance = [s for s in trajectory["signals"] if s["code"] == "biomech_balance_score"]
    assert balance and balance[0]["source"] == "biomech"
    assert balance[0]["direction"] == "improving"
    assert "balance up" in balance[0]["detail"]  # plain-language, sourced signal
    assert trajectory["direction"] == "improving"


def test_defensive_parse_skips_bad_metrics_but_imports_the_rest(client: TestClient) -> None:
    text = "\n".join(
        [
            "BioMech Balance Assessment Report",
            "Assessment Date: 2026-06-15T00:00:00",
            "Overall Balance Score: 250",  # out of range -> skipped
            "Sway Velocity: not measured",  # non-numeric -> skipped
            "Sway Area: 340 mm2",  # good
        ]
    )
    body = _upload(client, text).json()
    assert body["imported"] == 1
    assert any("250" in w for w in body["warnings"])
    assert any("no numeric value" in w for w in body["warnings"])


async def test_unrecognizable_report_imports_nothing_but_does_not_error(
    client: TestClient, service: EmrService
) -> None:
    # A valid PDF whose text is not a recognizable BioMech report: no kind, no date.
    body = _upload(client, "Just some notes.\nNothing structured here.").json()
    assert body["report_kind"] is None
    assert body["assessment_at"] is None
    assert body["imported"] == 0 and body["skipped"] == 0
    assert any("report kind" in w for w in body["warnings"])
    assert await service.observations.list_for_patient(PATIENT.patient_id) == []


# --- guards ----------------------------------------------------------------------------


def test_non_pdf_upload_is_422(client: TestClient) -> None:
    resp = client.post(
        "/biomech/reports",
        files={"file": ("report.pdf", b"not a pdf at all", "application/pdf")},
    )
    assert resp.status_code == 422


def test_oversized_upload_is_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "biomech_max_pdf_bytes", 64)
    resp = _upload(client, _balance_report())
    assert resp.status_code == 422


async def test_capability_off_refuses_with_409(
    client: TestClient, cap_service: CapabilityService, service: EmrService
) -> None:
    await cap_service.set_for_patient(
        patient_id=PATIENT.patient_id,
        actor_id=PATIENT.user_id,
        key="ingest_biomech",
        active=False,
        now=NOW,
    )
    resp = _upload(client, _balance_report())
    assert resp.status_code == 409
    # Nothing was persisted while the feature was off.
    assert await service.observations.list_for_patient(PATIENT.patient_id) == []


def test_clinician_cannot_upload_biomech(client: TestClient) -> None:
    clinician = CurrentUser(
        user_id=uuid4(),
        role=UserRole.clinician,
        patient_id=None,
        email="dr@example.test",
        display_name="Dr",
    )
    app.dependency_overrides[get_current_user] = lambda: clinician
    assert _upload(client, _balance_report()).status_code == 403


def test_biomech_upload_requires_auth() -> None:
    with TestClient(app) as anon:
        resp = anon.post(
            "/biomech/reports",
            files={"file": ("report.pdf", build_pdf(_balance_report()), "application/pdf")},
        )
        assert resp.status_code == 401


# --- audit -----------------------------------------------------------------------------


async def test_upload_audits_counts_and_kind_only(client: TestClient, service: EmrService) -> None:
    _upload(client, _balance_report(score=82))
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert [e.action for e in events] == ["import_biomech"]
    event = events[0]
    assert event.actor_id == PATIENT.user_id
    assert event.actor_role == "patient"
    assert event.detail == {
        "report_kind": "balance",
        "imported": 3,
        "skipped": 0,
        "warnings": 0,
    }
    # No value ever reaches the audit log (counts + kind only).
    assert "82" not in str(event.detail) and "12.4" not in str(event.detail)
