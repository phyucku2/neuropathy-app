"""End-to-end tests for the patient data-entry endpoints: POST /labs, POST /adl, and
GET /observations. All data is synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, get_current_user, get_emr_service
from app.emr.service import EmrService
from app.main import app
from app.models.observation import DataOrigin, ObservationStatus
from app.models.user import UserRole

NOW = datetime.now(UTC)
TODAY = NOW.date().isoformat()

PATIENT = CurrentUser(
    user_id=uuid4(),
    role=UserRole.patient,
    patient_id=uuid4(),
    email="pat@example.test",
    display_name="Pat",
)
OTHER_PATIENT = CurrentUser(
    user_id=uuid4(),
    role=UserRole.patient,
    patient_id=uuid4(),
    email="other@example.test",
    display_name="Other",
)


class _NoNetwork:
    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        raise AssertionError("ingestion endpoints must not touch the network")

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        raise AssertionError("ingestion endpoints must not touch the network")


@pytest.fixture()
def service() -> EmrService:
    return EmrService(transport=_NoNetwork(), client_id="c", redirect_uri="https://a/cb")


@pytest.fixture()
def client(service: EmrService) -> Iterator[TestClient]:
    app.dependency_overrides[get_emr_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: PATIENT
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _sign_in_as(user: CurrentUser) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def _lab(code: str = "4548-4", value: float = 7.2, day: int = 15) -> dict[str, Any]:
    return {
        "loinc_code": code,
        "display": "Hemoglobin A1c",
        "value": value,
        "unit": "%",
        "effective_at": f"2026-06-{day:02d}T08:00:00+00:00",
    }


def _adl(walking: int = 3, stairs: int = 2, balance: int = 4, **extra: Any) -> dict[str, Any]:
    return {"walking": walking, "stairs": stairs, "balance_confidence": balance, **extra}


# --- POST /labs -----------------------------------------------------------------------


async def test_lab_upload_persists_research_grade_rows(
    client: TestClient, service: EmrService
) -> None:
    resp = client.post("/labs", json={"results": [_lab(), _lab(code="2345-7", value=5.4, day=16)]})
    assert resp.status_code == 200
    assert resp.json() == {"imported": 2, "skipped": 0}

    rows = await service.observations.list_for_patient(PATIENT.patient_id)
    assert len(rows) == 2
    for row in rows:
        # Full provenance (data-standards.md): origin, attribution, quality, import key.
        assert row.origin is DataOrigin.document_imported
        assert row.recorded_by_role == "patient"
        assert row.quality == {"human_confirmed": True}
        assert row.import_key is not None and row.import_key.startswith("content:")
        assert row.status is ObservationStatus.final
        assert row.recorded_at is not None


def test_lab_upload_is_idempotent_on_repost(client: TestClient) -> None:
    panel = {"results": [_lab(), _lab(code="2345-7", value=5.4, day=16)]}
    assert client.post("/labs", json=panel).json() == {"imported": 2, "skipped": 0}
    # Re-posting the same confirmed panel (retry, duplicate scan) imports nothing new.
    assert client.post("/labs", json=panel).json() == {"imported": 0, "skipped": 2}
    # A panel mixing known and new rows imports only the new one.
    mixed = {"results": [_lab(), _lab(code="2160-0", value=1.0, day=17)]}
    assert client.post("/labs", json=mixed).json() == {"imported": 1, "skipped": 1}


def test_lab_upload_dedupes_within_one_batch(client: TestClient) -> None:
    resp = client.post("/labs", json={"results": [_lab(), _lab()]})
    assert resp.json() == {"imported": 1, "skipped": 1}


def test_lab_upload_batch_cap_and_empty_batch_are_422(client: TestClient) -> None:
    too_many = {"results": [_lab(value=5.0 + i / 100, day=15) for i in range(101)]}
    assert client.post("/labs", json=too_many).status_code == 422
    assert client.post("/labs", json={"results": []}).status_code == 422


async def test_lab_upload_audits_counts_only(client: TestClient, service: EmrService) -> None:
    client.post("/labs", json={"results": [_lab(value=7.9)]})
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert [e.action for e in events] == ["import_labs"]
    assert events[0].actor_id == PATIENT.user_id
    assert events[0].actor_role == "patient"
    assert events[0].detail == {
        "origin": "document_imported",
        "received": 1,
        "imported": 1,
        "skipped": 0,
    }
    assert "7.9" not in str(events[0].detail)  # counts only, never PHI values


async def test_lab_upload_key_is_content_identity_even_with_source_id(
    client: TestClient, service: EmrService
) -> None:
    """Uploads key on clinical content, not a document's claimed record id — the same
    confirmed value re-posted with a different id must still be skipped."""
    first = _lab()
    first["source_record_id"] = "doc-1"
    second = _lab()
    second["source_record_id"] = "doc-2"
    assert client.post("/labs", json={"results": [first]}).json()["imported"] == 1
    assert client.post("/labs", json={"results": [second]}).json() == {
        "imported": 0,
        "skipped": 1,
    }


# --- POST /adl ------------------------------------------------------------------------


async def test_adl_check_in_stores_answers_and_derived_composite(
    client: TestClient, service: EmrService
) -> None:
    resp = client.post("/adl", json=_adl(walking=3, stairs=2, balance=4))
    assert resp.status_code == 200
    assert resp.json() == {"check_in_date": TODAY, "daily_score": 9, "superseded": False}

    rows = await service.observations.list_for_patient(PATIENT.patient_id)
    by_code = {row.code: row for row in rows}
    assert set(by_code) == {
        "adl_walking",
        "adl_stairs",
        "adl_balance_confidence",
        "adl_daily_score",
    }
    assert by_code["adl_walking"].value_num == 3.0
    assert by_code["adl_stairs"].value_num == 2.0
    assert by_code["adl_balance_confidence"].value_num == 4.0
    assert by_code["adl_daily_score"].value_num == 9.0
    for code, row in by_code.items():
        expected = DataOrigin.derived if code == "adl_daily_score" else DataOrigin.patient_reported
        assert row.origin is expected
        assert row.recorded_by_role == "patient"
        assert row.source.value == "adl"
        assert row.effective_at == datetime.combine(NOW.date(), datetime.min.time(), tzinfo=UTC)
        assert row.quality["instrument"] == "adl-daily-check-in"
        assert row.quality["instrument_version"] == "1"
    assert by_code["adl_daily_score"].quality["derived_from"] == [
        "adl_walking",
        "adl_stairs",
        "adl_balance_confidence",
    ]


async def test_same_day_adl_supersedes_via_revises_chain(
    client: TestClient, service: EmrService
) -> None:
    first = client.post("/adl", json=_adl(walking=1, stairs=1, balance=1)).json()
    assert first["superseded"] is False

    second = client.post("/adl", json=_adl(walking=4, stairs=3, balance=2)).json()
    assert second == {"check_in_date": TODAY, "daily_score": 9, "superseded": True}

    # Corrections-as-new-records (ADR-0006): 8 rows exist, only the 4 current analyze.
    current = await service.observations.list_for_patient(PATIENT.patient_id)
    assert len(current) == 4
    by_code = {row.code: row for row in current}
    assert by_code["adl_walking"].value_num == 4.0
    assert by_code["adl_daily_score"].value_num == 9.0
    for row in current:
        assert row.status is ObservationStatus.amended
        assert row.revises_id is not None

    # A third check-in chains onto the second, not back onto the first.
    client.post("/adl", json=_adl(walking=2, stairs=2, balance=2))
    latest = {r.code: r for r in await service.observations.list_for_patient(PATIENT.patient_id)}
    assert latest["adl_walking"].value_num == 2.0
    assert latest["adl_walking"].revises_id == by_code["adl_walking"].id


def test_superseded_adl_rows_disappear_from_observations_and_trajectory(
    client: TestClient,
) -> None:
    client.post("/adl", json=_adl(walking=0, stairs=0, balance=0))
    client.post("/adl", json=_adl(walking=4, stairs=4, balance=4))

    listed = client.get("/observations").json()
    assert listed["total"] == 4  # the superseded first check-in no longer appears
    values = {item["code"]: item["value"] for item in listed["items"]}
    assert values["adl_daily_score"] == 12.0
    assert all(item["source"] == "adl" for item in listed["items"])

    trajectory = client.get("/trajectory").json()
    # One same-day point per signal -> insufficient for a trend, and the superseded
    # zeros never reach the engine as extra points.
    assert trajectory["direction"] == "insufficient_data"
    walking = [s for s in trajectory["signals"] if s["code"] == "adl_walking"]
    assert walking and "only 1 reading" in walking[0]["detail"]


def test_different_days_do_not_supersede(client: TestClient) -> None:
    yesterday = (NOW - timedelta(days=1)).date().isoformat()
    client.post("/adl", json=_adl(walking=1, stairs=1, balance=1, check_in_date=yesterday))
    resp = client.post("/adl", json=_adl(walking=2, stairs=2, balance=2))
    assert resp.json()["superseded"] is False
    assert client.get("/observations").json()["total"] == 8


def test_adl_check_in_date_cannot_be_in_the_future(client: TestClient) -> None:
    tomorrow = (NOW + timedelta(days=1)).date().isoformat()
    resp = client.post("/adl", json=_adl(check_in_date=tomorrow))
    assert resp.status_code == 422


def test_adl_answers_must_be_in_scale(client: TestClient) -> None:
    assert client.post("/adl", json=_adl(walking=5)).status_code == 422
    assert client.post("/adl", json=_adl(stairs=-1)).status_code == 422
    assert client.post("/adl", json={"walking": 1, "stairs": 1}).status_code == 422


async def test_adl_check_in_audits_counts_only(client: TestClient, service: EmrService) -> None:
    client.post("/adl", json=_adl(walking=3, stairs=2, balance=4))
    client.post("/adl", json=_adl(walking=4, stairs=2, balance=4))
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert [e.action for e in events] == ["record_adl", "record_adl"]
    assert events[0].detail == {"observations": 4, "superseded": 0}
    assert events[1].detail == {"observations": 4, "superseded": 4}
    for event in events:
        assert event.actor_id == PATIENT.user_id
        detail_text = str(event.detail)
        assert "walking" not in detail_text and "3" not in str(event.detail.values())


# --- GET /observations ----------------------------------------------------------------


def test_observations_paginate_newest_first(client: TestClient) -> None:
    days = [10, 12, 14, 16, 18]
    panel = [_lab(value=7.0 + i / 10, day=day) for i, day in enumerate(days)]
    client.post("/labs", json={"results": panel})

    page = client.get("/observations", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 5
    assert page["limit"] == 2 and page["offset"] == 0
    assert [item["effective_at"][:10] for item in page["items"]] == ["2026-06-18", "2026-06-16"]

    rest = client.get("/observations", params={"limit": 2, "offset": 4}).json()
    assert len(rest["items"]) == 1
    assert rest["items"][0]["effective_at"][:10] == "2026-06-10"

    beyond = client.get("/observations", params={"limit": 50, "offset": 50}).json()
    assert beyond["items"] == [] and beyond["total"] == 5


def test_observations_items_expose_display_fields(client: TestClient) -> None:
    client.post("/labs", json={"results": [_lab()]})
    item = client.get("/observations").json()["items"][0]
    assert item == {
        "code": "4548-4",
        "display": "Hemoglobin A1c",
        "value": 7.2,
        "value_text": None,
        "unit": "%",
        "effective_at": "2026-06-15T08:00:00Z",
        "source": "lab",
        "status": "final",
    }


def test_observations_code_filter(client: TestClient) -> None:
    client.post("/labs", json={"results": [_lab(), _lab(code="2345-7", value=5.4, day=16)]})
    filtered = client.get("/observations", params={"code": "4548-4"}).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["code"] == "4548-4"


def test_observations_pagination_bounds_are_enforced(client: TestClient) -> None:
    assert client.get("/observations", params={"limit": 0}).status_code == 422
    assert client.get("/observations", params={"limit": 101}).status_code == 422
    assert client.get("/observations", params={"offset": -1}).status_code == 422
    defaults = client.get("/observations").json()
    assert defaults["limit"] == 50 and defaults["offset"] == 0


async def test_observations_read_is_audit_logged(client: TestClient, service: EmrService) -> None:
    client.post("/labs", json={"results": [_lab()]})
    client.get("/observations")
    events = await service.audit.list_for_patient(PATIENT.patient_id)
    assert [e.action for e in events] == ["import_labs", "read_observations"]
    assert events[1].detail == {"returned": 1, "total": 1}
    assert "7.2" not in str(events[1].detail)


# --- isolation & auth ------------------------------------------------------------------


def test_cross_patient_isolation(client: TestClient) -> None:
    client.post("/labs", json={"results": [_lab()]})
    client.post("/adl", json=_adl())

    _sign_in_as(OTHER_PATIENT)
    other_view = client.get("/observations").json()
    assert other_view["total"] == 0 and other_view["items"] == []
    # The other patient's own check-in never supersedes the first patient's rows.
    assert client.post("/adl", json=_adl()).json()["superseded"] is False

    _sign_in_as(PATIENT)
    assert client.get("/observations").json()["total"] == 5


def test_ingestion_endpoints_require_auth() -> None:
    with TestClient(app) as anon:
        assert anon.post("/labs", json={"results": [_lab()]}).status_code == 401
        assert anon.post("/adl", json=_adl()).status_code == 401
        assert anon.get("/observations").status_code == 401


def test_clinician_cannot_use_patient_ingestion(client: TestClient) -> None:
    clinician = CurrentUser(
        user_id=uuid4(),
        role=UserRole.clinician,
        patient_id=None,
        email="dr@example.test",
        display_name="Dr",
    )
    _sign_in_as(clinician)
    assert client.post("/labs", json={"results": [_lab()]}).status_code == 403
    assert client.post("/adl", json=_adl()).status_code == 403
    assert client.get("/observations").status_code == 403


async def test_non_final_status_upload_is_rejected(client: TestClient) -> None:
    """Uploads are on-device-confirmed values: only status=final is accepted. A
    non-final row would consume the idempotency key and permanently block the real
    value (review finding, verified live)."""
    bad = _lab()
    bad["status"] = "entered_in_error"
    resp = client.post("/labs", json={"results": [bad]})
    assert resp.status_code == 422
    # Nothing was persisted and the key is not consumed: the real value imports fine.
    good = client.post("/labs", json={"results": [_lab()]})
    assert good.json() == {"imported": 1, "skipped": 0}


async def test_emr_pull_and_upload_share_one_idempotency_keyspace(
    client: TestClient, service: EmrService
) -> None:
    """The same real-world lab arriving via EMR pull AND patient upload must not be
    double-counted (review finding: fhir:-vs-content: keys let it through)."""
    from app.ingestion.labs import lab_import_key, lab_result_to_observation
    from app.models.observation import DataOrigin
    from app.schemas.lab import LabResultIn

    pulled = LabResultIn.model_validate(
        {**_lab(), "source_record_id": "obs-123"}  # EMR supplied its own FHIR id
    )
    await service.observations.add(
        lab_result_to_observation(
            pulled,
            patient_id=PATIENT.patient_id,
            origin=DataOrigin.ehr_imported,
            recorded_by_role="system",
            import_key=lab_import_key(pulled),
        )
    )
    # The patient now uploads the identical result from a paper copy: skipped.
    resp = client.post("/labs", json={"results": [_lab()]})
    assert resp.json() == {"imported": 0, "skipped": 1}
    rows = await service.observations.list_for_patient(PATIENT.patient_id)
    assert len(rows) == 1  # one clinical fact, one analyzable row


async def test_adl_accepts_local_today_ahead_of_utc(client: TestClient) -> None:
    """A patient at UTC+14 sends their local date (up to a day ahead of UTC) — must
    not be rejected as 'future' (review finding)."""
    from datetime import UTC, datetime, timedelta

    local_tomorrow = (datetime.now(UTC) + timedelta(hours=14)).date()
    resp = client.post(
        "/adl",
        json={
            "walking": 3,
            "stairs": 2,
            "balance_confidence": 4,
            "check_in_date": local_tomorrow.isoformat(),
        },
    )
    assert resp.status_code == 200
