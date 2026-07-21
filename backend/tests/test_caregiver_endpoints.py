"""End-to-end tests for the Caregiver Companion Phase A surfaces (ADR-0047):
invite creation, code-gated registration, the double opt-in, scope gating, the
404-over-403 posture on every /caregiver/patients/{id}/* view, instant revocation,
and the caregiver_read audit contract.

All data is synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_service, get_caregiver_service
from app.core.config import settings
from app.main import app
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.services.auth import AuthService
from app.services.caregiver import (
    CLAIM_RATE_LIMITED_DETAIL,
    CODE_INVALID_DETAIL,
    CaregiverService,
)

NOW = datetime.now(UTC)
SYNTHETIC_PASSWORD = "a-strong-password"


@pytest.fixture()
def caregiver_service() -> CaregiverService:
    return CaregiverService()


@pytest.fixture()
def client(caregiver_service: CaregiverService) -> Iterator[TestClient]:
    # Auth and caregiver flows share ONE user store, exactly like the deps wiring does.
    auth = AuthService(secret="endpoint-test-secret", users=caregiver_service.users)
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_caregiver_service] = lambda: caregiver_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_patient(
    client: TestClient, email: str = "pat@example.com", name: str = "Pat"
) -> tuple[dict[str, str], uuid.UUID]:
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": SYNTHETIC_PASSWORD, "display_name": name},
    )
    assert resp.status_code == 201
    headers = _auth(resp.json()["access_token"])
    me = client.get("/auth/me", headers=headers)
    return headers, uuid.UUID(me.json()["patient_id"])


def _create_code(client: TestClient, patient: dict[str, str]) -> str:
    resp = client.post("/me/caregiver-invites", headers=patient)
    assert resp.status_code == 201, resp.text
    code: str = resp.json()["code"]
    return code


def _register_caregiver(
    client: TestClient, code: str, email: str = "care@example.com", name: str = "Cam Caregiver"
) -> dict[str, str]:
    resp = client.post(
        "/caregiver/register",
        json={"code": code, "email": email, "password": SYNTHETIC_PASSWORD, "display_name": name},
    )
    assert resp.status_code == 201, resp.text
    return _auth(resp.json()["access_token"])


def _accept_first_pending(client: TestClient, patient: dict[str, str]) -> str:
    links = client.get("/me/caregivers", headers=patient).json()
    link_id: str = next(row["id"] for row in links if row["status"] == "pending")
    assert client.post(f"/me/caregivers/{link_id}/accept", headers=patient).status_code == 200
    return link_id


def _linked_caregiver(
    client: TestClient, email: str = "care@example.com"
) -> tuple[dict[str, str], uuid.UUID, dict[str, str], str]:
    """Full happy path: invite -> register+claim -> patient accepts.
    Returns (patient headers, patient_id, caregiver headers, link_id)."""
    patient, patient_id = _register_patient(client)
    code = _create_code(client, patient)
    caregiver = _register_caregiver(client, code, email=email)
    link_id = _accept_first_pending(client, patient)
    return patient, patient_id, caregiver, link_id


def _hba1c(value: float, days_ago: float, patient_id: uuid.UUID) -> Observation:
    return Observation(
        patient_id=patient_id,
        source=SourceType.lab,
        origin=DataOrigin.ehr_imported,
        code="4548-4",
        value_num=value,
        effective_at=NOW - timedelta(days=days_ago),
        recorded_at=NOW - timedelta(days=days_ago),
        status=ObservationStatus.final,
        quality={},
        payload={},
    )


async def _seed_improving_labs(service: CaregiverService, patient_id: uuid.UUID) -> None:
    for value, days_ago in ((9.0, 90), (8.3, 60), (7.6, 30), (7.0, 5)):
        await service.observations.add(_hba1c(value, days_ago, patient_id))


# ---------------------------------------------------------------- patient: invites


def test_invite_creation_shows_the_code_exactly_once(client: TestClient) -> None:
    patient, _ = _register_patient(client)
    resp = client.post("/me/caregiver-invites", headers=patient)
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"].count("-") == 2  # XXXX-XXXX-XXXX, read-aloud grouping
    assert len(body["code"].replace("-", "")) == 12
    assert "expires_at" in body
    # The one-time code must never be cacheable.
    assert resp.headers.get("cache-control") == "no-store"
    # The listing carries the invite's metadata but NEVER the code again.
    listed = client.get("/me/caregiver-invites", headers=patient).json()
    assert [row["id"] for row in listed] == [body["id"]]
    assert "code" not in listed[0]


def test_cancelled_invite_is_gone_and_unclaimable(client: TestClient) -> None:
    patient, _ = _register_patient(client)
    code = _create_code(client, patient)
    invite_id = client.get("/me/caregiver-invites", headers=patient).json()[0]["id"]
    assert client.delete(f"/me/caregiver-invites/{invite_id}", headers=patient).status_code == 204
    assert client.get("/me/caregiver-invites", headers=patient).json() == []
    # Idempotent re-cancel; foreign/unknown ids are 404.
    assert client.delete(f"/me/caregiver-invites/{invite_id}", headers=patient).status_code == 204
    unknown = client.delete(f"/me/caregiver-invites/{uuid.uuid4()}", headers=patient)
    assert unknown.status_code == 404
    # The cancelled code can never create an account.
    resp = client.post(
        "/caregiver/register",
        json={
            "code": code,
            "email": "care@example.com",
            "password": SYNTHETIC_PASSWORD,
            "display_name": "Cam",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == CODE_INVALID_DETAIL


def test_other_patients_cannot_cancel_an_invite(client: TestClient) -> None:
    patient_a, _ = _register_patient(client, email="a@example.com")
    _create_code(client, patient_a)
    invite_id = client.get("/me/caregiver-invites", headers=patient_a).json()[0]["id"]
    patient_b, _ = _register_patient(client, email="b@example.com", name="Bea")
    assert client.delete(f"/me/caregiver-invites/{invite_id}", headers=patient_b).status_code == 404
    assert len(client.get("/me/caregiver-invites", headers=patient_a).json()) == 1


# ---------------------------------------------------------------- registration / claim


def test_registration_requires_a_valid_code_and_yields_a_pending_link(
    client: TestClient,
) -> None:
    patient, _ = _register_patient(client)
    code = _create_code(client, patient)
    caregiver = _register_caregiver(client, code)

    me = client.get("/auth/me", headers=caregiver).json()
    assert me["role"] == "caregiver"
    assert me["patient_id"] is None  # a caregiver is never a patient (or clinician)

    # DOUBLE OPT-IN: the claim alone shows the caregiver NOTHING.
    assert client.get("/caregiver/patients", headers=caregiver).json()["patients"] == []
    # ...but the patient sees the pending request with the caregiver's name.
    links = client.get("/me/caregivers", headers=patient).json()
    assert len(links) == 1
    assert links[0]["status"] == "pending"
    assert links[0]["caregiver_display_name"] == "Cam Caregiver"
    assert links[0]["scope"] == "trends"
    assert links[0]["accepted_at"] is None


def test_registration_with_a_dead_code_creates_no_account(client: TestClient) -> None:
    patient, _ = _register_patient(client)
    code = _create_code(client, patient)
    _register_caregiver(client, code)  # consumes the code

    for probe in ("XXXX-YYYY-ZZZZ", code):  # unknown and consumed alike
        resp = client.post(
            "/caregiver/register",
            json={
                "code": probe,
                "email": "second@example.com",
                "password": SYNTHETIC_PASSWORD,
                "display_name": "Nope",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == CODE_INVALID_DETAIL  # byte-identical refusals
    # No account was created for the refused registrations.
    login = client.post(
        "/auth/login", json={"email": "second@example.com", "password": SYNTHETIC_PASSWORD}
    )
    assert login.status_code == 401


def test_duplicate_email_registration_does_not_burn_the_code(client: TestClient) -> None:
    """A 409 on the email happens AFTER the code check but BEFORE the consume — the
    patient's code survives for a corrected retry."""
    patient, _ = _register_patient(client)
    code = _create_code(client, patient)
    resp = client.post(
        "/caregiver/register",
        json={
            "code": code,
            "email": "pat@example.com",  # already the patient's email
            "password": SYNTHETIC_PASSWORD,
            "display_name": "Cam",
        },
    )
    assert resp.status_code == 409
    _register_caregiver(client, code)  # the same code still works with a fresh email


def test_authenticated_claim_is_byte_identical_for_any_code(client: TestClient) -> None:
    patient_b, _ = _register_patient(client, email="b@example.com", name="Bea")
    _, _, caregiver, _ = _linked_caregiver(client)
    real_code = _create_code(client, patient_b)

    matched = client.post("/caregiver/claims", headers=caregiver, json={"code": real_code})
    unmatched = client.post("/caregiver/claims", headers=caregiver, json={"code": "XXXX-YYYY-ZZZZ"})
    assert matched.status_code == unmatched.status_code == 202
    assert matched.content == unmatched.content  # no code enumeration

    # The real claim produced a pending link for patient B; accepting reveals both.
    _accept_first_pending(client, patient_b)
    patients = client.get("/caregiver/patients", headers=caregiver).json()["patients"]
    assert len(patients) == 2  # unlimited patients per caregiver, and vice versa


def test_claims_over_budget_answer_429(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Budget of 2: the registration's own successful claim already counts as one.
    monkeypatch.setattr(settings, "caregiver_claim_rate_limit_max", 2)
    _, _, caregiver, _ = _linked_caregiver(client)
    assert (
        client.post(
            "/caregiver/claims", headers=caregiver, json={"code": "AAAA-BBBB-CCCC"}
        ).status_code
        == 202
    )
    refused = client.post("/caregiver/claims", headers=caregiver, json={"code": "AAAA-BBBB-CCCC"})
    assert refused.status_code == 429
    assert refused.json()["detail"] == CLAIM_RATE_LIMITED_DETAIL


def test_registration_guesses_over_budget_answer_429_per_email(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "caregiver_claim_rate_limit_max", 2)
    body = {
        "code": "XXXX-YYYY-ZZZZ",
        "email": "guesser@example.com",
        "password": SYNTHETIC_PASSWORD,
        "display_name": "Guess",
    }
    for _ in range(2):  # failed guesses spend the email's budget
        assert client.post("/caregiver/register", json=body).status_code == 404
    over = client.post("/caregiver/register", json=body)
    assert over.status_code == 429
    assert over.json()["detail"] == CLAIM_RATE_LIMITED_DETAIL
    # Another email's budget is untouched.
    other = {**body, "email": "other@example.com"}
    assert client.post("/caregiver/register", json=other).status_code == 404


# ---------------------------------------------------------------- double opt-in + reads


async def test_accepted_caregiver_sees_the_trend_deterministically(
    client: TestClient, caregiver_service: CaregiverService
) -> None:
    _, patient_id, caregiver, link_id = _linked_caregiver(client)
    await _seed_improving_labs(caregiver_service, patient_id)

    patients = client.get("/caregiver/patients", headers=caregiver).json()["patients"]
    assert [p["patient_id"] for p in patients] == [str(patient_id)]
    assert patients[0]["display_name"] == "Pat"
    assert patients[0]["link_id"] == link_id

    resp = client.get(f"/caregiver/patients/{patient_id}/trajectory", headers=caregiver)
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"
    body = resp.json()
    assert body["direction"] == "improving"
    # NEVER the AI narrative on the caregiver surface (ADR-0047 / ADR-0011).
    assert body["narrative_source"] == "deterministic"
    assert "4548-4" not in body["summary"]  # plain language, no raw codes


def test_pending_link_shows_nothing_until_the_patient_accepts(client: TestClient) -> None:
    patient, patient_id = _register_patient(client)
    code = _create_code(client, patient)
    caregiver = _register_caregiver(client, code)
    # Before acceptance: no patient list entry, and the per-patient views are 404.
    assert client.get("/caregiver/patients", headers=caregiver).json()["patients"] == []
    assert (
        client.get(f"/caregiver/patients/{patient_id}/trajectory", headers=caregiver).status_code
        == 404
    )
    _accept_first_pending(client, patient)
    assert (
        client.get(f"/caregiver/patients/{patient_id}/trajectory", headers=caregiver).status_code
        == 200
    )


def test_declined_request_never_becomes_readable(client: TestClient) -> None:
    patient, patient_id = _register_patient(client)
    code = _create_code(client, patient)
    caregiver = _register_caregiver(client, code)
    link_id = client.get("/me/caregivers", headers=patient).json()[0]["id"]
    assert client.post(f"/me/caregivers/{link_id}/decline", headers=patient).status_code == 204
    assert client.get("/me/caregivers", headers=patient).json()[0]["status"] == "revoked"
    assert client.get("/caregiver/patients", headers=caregiver).json()["patients"] == []
    assert (
        client.get(f"/caregiver/patients/{patient_id}/trajectory", headers=caregiver).status_code
        == 404
    )
    # A dead request cannot be declined again or accepted later.
    assert client.post(f"/me/caregivers/{link_id}/decline", headers=patient).status_code == 404
    assert client.post(f"/me/caregivers/{link_id}/accept", headers=patient).status_code == 404


def test_trends_scope_gets_404_on_the_visit_summary(client: TestClient) -> None:
    """FULL scope only: a trends-scope caller's visit-summary answer is exactly the
    nonexistent-patient 404 — insufficient scope must not be distinguishable."""
    _, patient_id, caregiver, link_id = _linked_caregiver(client)
    scoped = client.get(f"/caregiver/patients/{patient_id}/visit-summary", headers=caregiver)
    unknown = client.get(f"/caregiver/patients/{uuid.uuid4()}/visit-summary", headers=caregiver)
    assert scoped.status_code == unknown.status_code == 404
    assert scoped.content == unknown.content  # indistinguishable


def test_full_scope_unlocks_the_visit_summary(client: TestClient) -> None:
    patient, patient_id, caregiver, link_id = _linked_caregiver(client)
    resp = client.patch(f"/me/caregivers/{link_id}", headers=patient, json={"scope": "full"})
    assert resp.status_code == 200
    assert resp.json()["scope"] == "full"

    summary = client.get(f"/caregiver/patients/{patient_id}/visit-summary", headers=caregiver)
    assert summary.status_code == 200
    assert summary.headers.get("cache-control") == "no-store"
    # The window whitelist applies here exactly as on the patient/clinic surfaces.
    assert (
        client.get(
            f"/caregiver/patients/{patient_id}/visit-summary?window=123", headers=caregiver
        ).status_code
        == 422
    )
    # Scoping back down re-locks it, instantly.
    client.patch(f"/me/caregivers/{link_id}", headers=patient, json={"scope": "trends"})
    assert (
        client.get(f"/caregiver/patients/{patient_id}/visit-summary", headers=caregiver).status_code
        == 404
    )


def test_revocation_cuts_off_caregiver_reads_instantly(client: TestClient) -> None:
    patient, patient_id, caregiver, link_id = _linked_caregiver(client)
    assert (
        client.get(f"/caregiver/patients/{patient_id}/trajectory", headers=caregiver).status_code
        == 200
    )
    assert client.delete(f"/me/caregivers/{link_id}", headers=patient).status_code == 204
    assert client.get("/caregiver/patients", headers=caregiver).json()["patients"] == []
    assert (
        client.get(f"/caregiver/patients/{patient_id}/trajectory", headers=caregiver).status_code
        == 404
    )
    # Idempotent re-revoke; foreign ids 404; scope changes on the dead link 404.
    assert client.delete(f"/me/caregivers/{link_id}", headers=patient).status_code == 204
    assert client.delete(f"/me/caregivers/{uuid.uuid4()}", headers=patient).status_code == 404
    assert (
        client.patch(
            f"/me/caregivers/{link_id}", headers=patient, json={"scope": "full"}
        ).status_code
        == 404
    )


def test_unlimited_caregivers_per_patient_each_with_own_scope(client: TestClient) -> None:
    patient, patient_id, caregiver_a, _link_a = _linked_caregiver(client, email="a@care.example")
    code = _create_code(client, patient)
    caregiver_b = _register_caregiver(client, code, email="b@care.example", name="Bea Caregiver")
    link_b = _accept_first_pending(client, patient)
    client.patch(f"/me/caregivers/{link_b}", headers=patient, json={"scope": "full"})

    links = client.get("/me/caregivers", headers=patient).json()
    assert len(links) == 2
    assert {row["caregiver_display_name"] for row in links} == {"Cam Caregiver", "Bea Caregiver"}
    # Scope is PER caregiver: B reads the summary, A still cannot.
    assert (
        client.get(
            f"/caregiver/patients/{patient_id}/visit-summary", headers=caregiver_b
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/caregiver/patients/{patient_id}/visit-summary", headers=caregiver_a
        ).status_code
        == 404
    )


def test_unlinked_patient_is_404_not_403(client: TestClient) -> None:
    """The non-enumeration posture: another patient's id answers exactly like a
    nonexistent one on every caregiver view."""
    _register_patient(client, email="stranger@example.com", name="Stranger")
    stranger_id = client.get(
        "/auth/me",
        headers=_auth(
            client.post(
                "/auth/login",
                json={"email": "stranger@example.com", "password": SYNTHETIC_PASSWORD},
            ).json()["access_token"]
        ),
    ).json()["patient_id"]
    _, _, caregiver, _ = _linked_caregiver(client)
    for path in (
        f"/caregiver/patients/{stranger_id}/trajectory",
        f"/caregiver/patients/{stranger_id}/visit-summary",
        f"/caregiver/patients/{uuid.uuid4()}/trajectory",
    ):
        resp = client.get(path, headers=caregiver)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Patient not found"


# ---------------------------------------------------------------- role gates


def test_role_gates_keep_every_principal_in_its_lane(client: TestClient) -> None:
    patient, patient_id, caregiver, _ = _linked_caregiver(client)
    # A patient is not a caregiver...
    assert client.get("/caregiver/patients", headers=patient).status_code == 403
    assert client.post("/caregiver/claims", headers=patient, json={"code": "X"}).status_code == 403
    # ...and a caregiver is not a patient (no /me surfaces, no export)...
    assert client.get("/me/caregivers", headers=caregiver).status_code == 403
    assert client.post("/me/caregiver-invites", headers=caregiver).status_code == 403
    assert client.get("/me/export", headers=caregiver).status_code == 403
    # ...and NEVER a clinician (no clinical authority, ADR-0047).
    assert client.get("/clinic/patients", headers=caregiver).status_code == 403
    with TestClient(app) as anon:
        assert anon.get("/caregiver/patients").status_code == 401
        assert anon.post("/caregiver/claims", json={"code": "X"}).status_code == 401


def test_caregiver_is_refused_by_the_privileged_mfa_gate(client: TestClient) -> None:
    """require_privileged is clinician-or-ops EXPLICITLY: a caregiver must not slip
    through a not-a-patient check into the MFA enrollment surface (ADR-0047 — no
    clinical authority; conflict finding #1)."""
    _, _, caregiver, _ = _linked_caregiver(client)
    resp = client.post("/auth/mfa/enroll", headers=caregiver)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Clinician or ops account required"


def test_caregiver_login_is_untouched_by_the_mfa_required_flag(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caregiver can never enroll a factor, so the privileged-MFA go-live flag
    must never lock one out of login (mfa.login_step_up is clinician-or-ops
    EXPLICITLY, ADR-0047)."""
    _linked_caregiver(client)
    monkeypatch.setattr(settings, "mfa_required_for_privileged", True)
    login = client.post(
        "/auth/login", json={"email": "care@example.com", "password": SYNTHETIC_PASSWORD}
    )
    assert login.status_code == 200
    assert "access_token" in login.json()


def test_deactivated_caregiver_is_denied_at_authentication(
    client: TestClient, caregiver_service: CaregiverService
) -> None:
    """Central revocation (ADR-0019) bites for caregivers too: a deactivated account
    holding a live token is refused before any caregiver gate or read."""
    _, _, caregiver, _ = _linked_caregiver(client)
    assert client.get("/caregiver/patients", headers=caregiver).status_code == 200
    caregiver_service.users._by_email["care@example.com"].active = False  # noqa: SLF001
    assert client.get("/caregiver/patients", headers=caregiver).status_code == 401


# ---------------------------------------------------------------- audit trail


async def test_every_caregiver_read_is_audited_as_caregiver_read(
    client: TestClient, caregiver_service: CaregiverService
) -> None:
    """The Phase A audit contract: action='caregiver_read' on EVERY read, the
    surface disambiguated in detail (a deliberate divergence from the clinic
    routes' per-surface actions), caregiver as actor, patient as subject, counts
    and refs only."""
    patient, patient_id, caregiver, link_id = _linked_caregiver(client)
    await _seed_improving_labs(caregiver_service, patient_id)
    client.patch(f"/me/caregivers/{link_id}", headers=patient, json={"scope": "full"})
    caregiver_user_id = uuid.UUID(client.get("/auth/me", headers=caregiver).json()["user_id"])

    client.get("/caregiver/patients", headers=caregiver)
    client.get(f"/caregiver/patients/{patient_id}/trajectory", headers=caregiver)
    client.get(f"/caregiver/patients/{patient_id}/visit-summary", headers=caregiver)

    events = await caregiver_service.audit.list_for_patient(patient_id)
    reads = [e for e in events if e.action == "caregiver_read"]
    surfaces = {e.detail["surface"] for e in reads}
    assert surfaces == {"patients", "trajectory", "visit_summary"}
    for event in reads:
        assert event.actor_id == caregiver_user_id  # the CAREGIVER is the actor
        assert event.actor_role == "caregiver"
        assert event.patient_id == patient_id  # the patient is the subject
        assert event.detail["link_id"] == link_id
    trajectory = next(e for e in reads if e.detail["surface"] == "trajectory")
    assert trajectory.detail["observations"] == 4  # counts only, never values


async def test_lifecycle_transitions_are_audited_with_refs_only(
    client: TestClient, caregiver_service: CaregiverService
) -> None:
    patient, patient_id, caregiver, link_id = _linked_caregiver(client)
    client.patch(f"/me/caregivers/{link_id}", headers=patient, json={"scope": "full"})
    client.delete(f"/me/caregivers/{link_id}", headers=patient)

    events = await caregiver_service.audit.list_for_patient(patient_id)
    actions = [e.action for e in events]
    assert actions == [
        "create_caregiver_invite",
        "caregiver_claim",
        "accept_caregiver_link",
        "change_caregiver_scope",
        "revoke_caregiver_link",
    ]
    serialized = str([e.detail for e in events])
    assert "example.com" not in serialized  # never an email
    assert link_id in serialized  # refs, not payloads
    claim = events[1]
    assert claim.actor_role == "caregiver"
    assert claim.detail == {"matched": True, "created": True, "registration": True}
