"""End-to-end tests for POST /biomech/reports and its downstream surfaces (ADR-0014;
real report format per ADR-0036).

Uploaded BioMech reports become research-grade Observations that flow into
GET /observations and the trajectory automatically. All PDFs and data are synthetic
(CLAUDE.md §5); PDFs are built in-test (tests/synthetic_pdf.py) with the REAL pypdf line
structure (label → unit → value), no binary fixtures.
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
    date: str = "3/6/25",
    eyes_open: bool = True,
    score: str = "93",
    speed: str = "97",
    movement: str = "97",
    position: str = "80",
) -> str:
    stance = (
        ["PARALLEL APART,", "EYES OPEN,"] if eyes_open else ["PARALLEL TOGETHER,", "EYES CLOSED,"]
    )
    return "\n".join(
        [
            "BALANCE INDIVIDUAL TEST REPORT",
            *stance,
            "(Static, Stable Surface)",
            "Date of Service:",
            date,
            "Balance Score",
            "Percent",
            score,
            "0 - 100",
            "Average Speed % Normal",
            "Percent",
            speed,
            "0 - 100",
            "Average Movement % Normal",
            "Percent",
            movement,
            "0 - 100",
            "Average Position % Normal",
            "Percent",
            position,
            "0 - 100",
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
    assert body["assessment_at"] == "2025-03-06T00:00:00Z"
    assert body["imported"] == 4 and body["skipped"] == 0
    assert body["warnings"] == []

    rows = await service.observations.list_for_patient(PATIENT.patient_id)
    assert {row.code for row in rows} == {
        "biomech_balance_score",
        "biomech_balance_speed_normal",
        "biomech_balance_movement_normal",
        "biomech_balance_position_normal",
    }
    for row in rows:
        assert row.source is SourceType.biomech
        assert row.origin is DataOrigin.document_imported
        assert row.status is ObservationStatus.final
        assert row.recorded_by_role == "patient"
        assert row.quality["source_system"] == "BioMech"
        assert row.quality["extraction"] == "pdf_text"
        assert row.quality["report_kind"] == "balance"
        # The balance condition (eyes-open/closed) is preserved as provenance.
        assert row.quality["condition"] == "PARALLEL APART, EYES OPEN"
        assert row.effective_at == datetime(2025, 3, 6, tzinfo=UTC)
        assert row.import_key is not None and row.import_key.startswith("content:biomech:")


def test_uploaded_rows_are_queryable_via_get_observations(client: TestClient) -> None:
    _upload(client, _balance_report())
    listed = client.get("/observations").json()
    assert listed["total"] == 4
    assert {item["source"] for item in listed["items"]} == {"biomech"}
    by_code = {item["code"]: item for item in listed["items"]}
    assert by_code["biomech_balance_score"]["value"] == 93.0
    assert by_code["biomech_balance_score"]["display"] == "Balance score"
    assert by_code["biomech_balance_score"]["unit"] == "%"


def test_reupload_of_same_report_is_idempotent(client: TestClient) -> None:
    assert _upload(client, _balance_report()).json()["imported"] == 4
    second = _upload(client, _balance_report()).json()
    assert second["imported"] == 0 and second["skipped"] == 4


async def test_same_day_eyes_open_and_closed_do_not_collide(
    client: TestClient, service: EmrService
) -> None:
    # Two balance tests on the same day under different protocols must both persist —
    # the condition is in the idempotency key even when a value coincides.
    _upload(client, _balance_report(eyes_open=True, score="93"))
    _upload(client, _balance_report(eyes_open=False, score="93"))
    scores = [
        r
        for r in await service.observations.list_for_patient(PATIENT.patient_id)
        if r.code == "biomech_balance_score"
    ]
    assert len(scores) == 2
    assert {r.quality["condition"] for r in scores} == {
        "PARALLEL APART, EYES OPEN",
        "PARALLEL TOGETHER, EYES CLOSED",
    }


def test_trajectory_shows_a_sourced_biomech_signal(client: TestClient) -> None:
    # Three balance reports over ~2 months, every metric rising — balance improving.
    for days_ago, score, sp, mv, ps in (
        (60, 74, 90, 90, 70),
        (30, 84, 94, 94, 76),
        (2, 93, 97, 97, 80),
    ):
        date = (NOW - timedelta(days=days_ago)).strftime("%m/%d/%Y")
        _upload(
            client,
            _balance_report(
                date=date, score=str(score), speed=str(sp), movement=str(mv), position=str(ps)
            ),
        )

    trajectory = client.get("/trajectory").json()
    balance = [s for s in trajectory["signals"] if s["code"] == "biomech_balance_score"]
    assert balance and balance[0]["source"] == "biomech"
    assert balance[0]["direction"] == "improving"
    assert "balance up" in balance[0]["detail"]
    assert trajectory["direction"] == "improving"


def test_defensive_parse_skips_bad_metrics_but_imports_the_rest(client: TestClient) -> None:
    text = "\n".join(
        [
            "BALANCE INDIVIDUAL TEST REPORT",
            "Date of Service:",
            "3/6/25",
            "Balance Score",
            "Percent",
            "250",  # out of range -> skipped
            "0 - 100",
            "Average Speed % Normal",
            "Percent",
            "N/A",  # non-numeric -> skipped
            "Average Movement % Normal",
            "Percent",
            "96",  # good
            "0 - 100",
        ]
    )
    body = _upload(client, text).json()
    assert body["imported"] == 1
    assert any("250" in w for w in body["warnings"])
    assert any("no clean numeric value" in w for w in body["warnings"])


async def test_unrecognizable_report_imports_nothing_but_does_not_error(
    client: TestClient, service: EmrService
) -> None:
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
    assert "size cap" in resp.json()["detail"]


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
    _upload(client, _balance_report(score="93"))
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert [e.action for e in events] == ["import_biomech"]
    event = events[0]
    assert event.actor_id == PATIENT.user_id
    assert event.actor_role == "patient"
    assert event.detail == {
        "report_kind": "balance",
        "imported": 4,
        "skipped": 0,
        "warnings": 0,
    }
    # No measured value ever reaches the audit log (counts + kind only).
    assert "93" not in str(event.detail)
