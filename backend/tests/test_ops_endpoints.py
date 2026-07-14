"""End-to-end tests for the ops-auth surface (ADR-0019): the first-ops bootstrap
lifecycle (token-gated only while zero ops exist, then self-closed), steady-state
attributed ops creation under require_ops, per-operator deactivation blocking login and
require_ops, and the denial-audit + rate-limit protections on the one remaining
unauthenticated surface (the first-ops bootstrap).

The bootstrap-denial machinery moved here from the clinician gate (ADR-0017 -> 0019):
these tests are that gate's new home.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_service, get_clinic_service
from app.api.routes.ops import _first_ops_bootstrap_denial
from app.core.config import settings
from app.main import app
from app.models.audit import AuditEvent
from app.services.auth import AuthService
from app.services.clinic import OPS_BOOTSTRAP_ACTOR_ID, ClinicService

# ≥ 32 chars — the settings-load minimum a real deployment must meet (ADR-0017).
BOOTSTRAP_TOKEN = "synthetic-bootstrap-token-0123456789abcdef"
BOOTSTRAP = {"X-Bootstrap-Token": BOOTSTRAP_TOKEN}
SYNTHETIC_PASSWORD = "a-strong-password"


@pytest.fixture()
def clinic_service() -> ClinicService:
    return ClinicService()


@pytest.fixture()
def client(clinic_service: ClinicService, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Ops creation (AuthService) and the bootstrap-denial audit (ClinicService) share
    # ONE user/audit store, exactly like the deps wiring does.
    auth = AuthService(secret="endpoint-test-secret", users=clinic_service.users)
    monkeypatch.setattr(settings, "ops_bootstrap_token", BOOTSTRAP_TOKEN)
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_clinic_service] = lambda: clinic_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_first_ops(
    client: TestClient, email: str = "ops@example.com"
) -> tuple[dict[str, str], uuid.UUID]:
    """First-ops bootstrap + login; returns (ops headers, ops user_id)."""
    resp = client.post(
        "/ops/accounts",
        headers=BOOTSTRAP,
        json={"email": email, "password": SYNTHETIC_PASSWORD, "display_name": "Ops One"},
    )
    assert resp.status_code == 201, resp.text
    login = client.post("/auth/login", json={"email": email, "password": SYNTHETIC_PASSWORD})
    return _auth(login.json()["access_token"]), uuid.UUID(resp.json()["user_id"])


# ---------------------------------------------------------------- first-ops bootstrap


def test_first_ops_bootstrap_creates_an_ops_with_the_token(
    client: TestClient, clinic_service: ClinicService
) -> None:
    resp = client.post(
        "/ops/accounts",
        headers=BOOTSTRAP,
        json={"email": "ops@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Ops"},
    )
    assert resp.status_code == 201
    assert resp.json()["active"] is True
    # The first-ops creation is audited as a bootstrap (no authenticated actor).
    created = next(e for e in clinic_service.audit._events if e.action == "create_ops")
    assert created.actor_id is None
    assert created.detail == {"user_id": resp.json()["user_id"], "bootstrap": True}
    # And the operator can log in with role=ops.
    me = client.get(
        "/auth/me",
        headers=_auth(
            client.post(
                "/auth/login", json={"email": "ops@example.com", "password": SYNTHETIC_PASSWORD}
            ).json()["access_token"]
        ),
    )
    assert me.json()["role"] == "ops"
    assert me.json()["patient_id"] is None


def test_bootstrap_fails_closed_when_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ops_bootstrap_token", None)
    resp = client.post(
        "/ops/accounts",
        headers=BOOTSTRAP,
        json={"email": "ops@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Ops"},
    )
    assert resp.status_code == 403


def test_bootstrap_rejects_wrong_or_missing_token(client: TestClient) -> None:
    body = {"email": "ops@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Ops"}
    wrong = client.post("/ops/accounts", headers={"X-Bootstrap-Token": "nope"}, json=body)
    missing = client.post("/ops/accounts", json=body)
    assert wrong.status_code == 403
    assert missing.status_code == 403


def test_bootstrap_self_disables_once_an_ops_exists(client: TestClient) -> None:
    """THE lifecycle invariant (ADR-0019): the token creates the FIRST ops, then opens
    nothing. A second /ops/accounts with the same valid token but no ops bearer is a
    401 — the shared secret is off the steady-state path for good."""
    _bootstrap_first_ops(client)
    second = client.post(
        "/ops/accounts",
        headers=BOOTSTRAP,  # valid token, but an ops now exists -> bearer required
        json={"email": "ops2@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Ops 2"},
    )
    assert second.status_code == 401  # require_ops via get_current_user: no bearer


def test_duplicate_ops_email_is_409(client: TestClient) -> None:
    ops, _ = _bootstrap_first_ops(client)
    resp = client.post(
        "/ops/accounts",
        headers=ops,
        json={"email": "ops@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Dup"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------- steady state (require_ops)


def test_authenticated_ops_creates_another_ops_attributed(
    client: TestClient, clinic_service: ClinicService
) -> None:
    ops, ops_id = _bootstrap_first_ops(client)
    resp = client.post(
        "/ops/accounts",
        headers=ops,
        json={"email": "ops2@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Ops 2"},
    )
    assert resp.status_code == 201
    created = [e for e in clinic_service.audit._events if e.action == "create_ops"]
    # First (bootstrap, no actor) then the second attributed to the authenticated ops.
    assert created[-1].actor_id == ops_id
    assert created[-1].detail["bootstrap"] is False


def test_create_ops_rejects_patient_and_clinician_bearers(client: TestClient) -> None:
    _bootstrap_first_ops(client)  # ensure steady-state (bearer path) is active
    reg = client.post(
        "/auth/register",
        json={"email": "pat@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Pat"},
    )
    patient = _auth(reg.json()["access_token"])
    resp = client.post(
        "/ops/accounts",
        headers=patient,
        json={"email": "x@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "X"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Ops account required"


# ---------------------------------------------------------------- deactivation


def test_deactivation_blocks_login_and_require_ops(client: TestClient) -> None:
    ops1, _ = _bootstrap_first_ops(client)
    # A second operator to deactivate (the first is protected as the last active ops).
    created = client.post(
        "/ops/accounts",
        headers=ops1,
        json={"email": "ops2@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Ops 2"},
    )
    target_id = created.json()["user_id"]
    login2 = client.post(
        "/auth/login", json={"email": "ops2@example.com", "password": SYNTHETIC_PASSWORD}
    )
    ops2 = _auth(login2.json()["access_token"])

    resp = client.post(f"/ops/accounts/{target_id}/deactivate", headers=ops1)
    assert resp.status_code == 200
    assert resp.json()["active"] is False

    # Login is now refused (same 401 as a bad password — no enumeration)...
    relogin = client.post(
        "/auth/login", json={"email": "ops2@example.com", "password": SYNTHETIC_PASSWORD}
    )
    assert relogin.status_code == 401
    # ...and the still-valid pre-deactivation token fails require_ops immediately.
    stale = client.post(
        "/ops/accounts",
        headers=ops2,
        json={"email": "z@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Z"},
    )
    assert stale.status_code == 403


def test_deactivation_refuses_the_last_active_ops(client: TestClient) -> None:
    """With the bootstrap gate closed once any ops exists, removing the last active
    operator would lock provisioning out entirely — refused with 409 (ADR-0019)."""
    ops1, ops1_id = _bootstrap_first_ops(client)
    resp = client.post(f"/ops/accounts/{ops1_id}/deactivate", headers=ops1)
    assert resp.status_code == 409
    assert "last active" in resp.json()["detail"]


def test_deactivation_of_unknown_or_non_ops_is_404(client: TestClient) -> None:
    ops1, _ = _bootstrap_first_ops(client)
    reg = client.post(
        "/auth/register",
        json={"email": "pat@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Pat"},
    )
    patient_id = client.get("/auth/me", headers=_auth(reg.json()["access_token"])).json()["user_id"]
    assert client.post(f"/ops/accounts/{uuid.uuid4()}/deactivate", headers=ops1).status_code == 404
    # A patient user id is not an ops account — 404, never a leak that it exists.
    assert client.post(f"/ops/accounts/{patient_id}/deactivate", headers=ops1).status_code == 404


def test_deactivation_is_idempotent(client: TestClient, clinic_service: ClinicService) -> None:
    ops1, _ = _bootstrap_first_ops(client)
    created = client.post(
        "/ops/accounts",
        headers=ops1,
        json={"email": "ops2@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Ops 2"},
    )
    target_id = created.json()["user_id"]
    assert client.post(f"/ops/accounts/{target_id}/deactivate", headers=ops1).status_code == 200
    again = client.post(f"/ops/accounts/{target_id}/deactivate", headers=ops1)
    assert again.status_code == 200  # quiet idempotent success
    assert again.json()["active"] is False
    # Only ONE deactivate audit event despite two calls.
    events = [e for e in clinic_service.audit._events if e.action == "deactivate_ops"]
    assert len(events) == 1
    assert events[0].detail == {"user_id": target_id, "self": False}


def test_deactivation_requires_an_ops_bearer(client: TestClient) -> None:
    ops1, ops1_id = _bootstrap_first_ops(client)
    reg = client.post(
        "/auth/register",
        json={"email": "pat@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Pat"},
    )
    patient = _auth(reg.json()["access_token"])
    assert client.post(f"/ops/accounts/{ops1_id}/deactivate", headers=patient).status_code == 403
    with TestClient(app) as anon:
        assert anon.post(f"/ops/accounts/{ops1_id}/deactivate").status_code == 401


# ---------------------------------------------------------------- denial audits (ADR-0017 posture)


def test_failed_bootstrap_attempts_are_audited_without_token_material(
    client: TestClient, clinic_service: ClinicService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every FAILED first-ops attempt writes a bootstrap_denied audit event recording
    only the failure shape — never the presented or configured token (ADR-0017)."""
    body = {"email": "ops@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Ops"}
    assert (
        client.post(
            "/ops/accounts", headers={"X-Bootstrap-Token": "wrong-token"}, json=body
        ).status_code
        == 403
    )
    assert client.post("/ops/accounts", json=body).status_code == 403
    monkeypatch.setattr(settings, "ops_bootstrap_token", None)
    assert client.post("/ops/accounts", headers=BOOTSTRAP, json=body).status_code == 403

    denied = [e for e in clinic_service.audit._events if e.action == "bootstrap_denied"]
    assert [e.detail for e in denied] == [
        {"configured": True, "token_presented": True},  # wrong token
        {"configured": True, "token_presented": False},  # missing token
        {"configured": False, "token_presented": True},  # gate unconfigured (fail closed)
    ]
    for event in denied:
        assert event.actor_id == OPS_BOOTSTRAP_ACTOR_ID  # the fixed sentinel, no real user
        assert event.actor_role == "ops"
        assert event.patient_id is None
        assert "wrong-token" not in str(event.detail)
        assert BOOTSTRAP_TOKEN not in str(event.detail)


def test_successful_bootstrap_writes_no_denied_event(
    client: TestClient, clinic_service: ClinicService
) -> None:
    _bootstrap_first_ops(client)
    actions = [e.action for e in clinic_service.audit._events]
    assert "create_ops" in actions
    assert "bootstrap_denied" not in actions


def test_bootstrap_denial_audits_are_capped_but_the_403_is_unchanged(
    client: TestClient, clinic_service: ClinicService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first-ops gate is UNAUTHENTICATED: without a cap, every anonymous failed
    attempt commits a durable audit row — a log-flood primitive against the PHI
    database (ADR-0017). Beyond the budget the answer stays a byte-identical 403."""
    monkeypatch.setattr(settings, "bootstrap_denied_audit_max", 2)
    body = {"email": "ops@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Ops"}
    responses = [
        client.post("/ops/accounts", headers={"X-Bootstrap-Token": "wrong-token"}, json=body)
        for _ in range(5)
    ]
    assert [r.status_code for r in responses] == [403] * 5
    assert len({r.content for r in responses}) == 1  # capped/uncapped indistinguishable
    denied = [e for e in clinic_service.audit._events if e.action == "bootstrap_denied"]
    assert len(denied) == 2  # the durable trail is bounded to the window budget


async def test_bootstrap_denial_audits_resume_after_the_window_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Window math on FIXED injected timestamps (the ADR-0013 CI-flake rule): inside a
    full window the denial audit is skipped; once the old denials slide out, auditing
    resumes — and every answer is the same 403 throughout."""
    monkeypatch.setattr(settings, "ops_bootstrap_token", BOOTSTRAP_TOKEN)
    monkeypatch.setattr(settings, "bootstrap_denied_audit_max", 1)
    service = ClinicService()
    window = timedelta(seconds=settings.bootstrap_denied_audit_window_seconds)
    t0 = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    await service.audit.add(
        AuditEvent(
            actor_id=OPS_BOOTSTRAP_ACTOR_ID,
            occurred_at=t0,
            actor_role="ops",
            action="bootstrap_denied",
            patient_id=None,
            detail={},
        )
    )

    capped = await _first_ops_bootstrap_denial(
        "wrong-token", service, now=t0 + timedelta(minutes=30)
    )
    assert capped is not None and capped.status_code == 403  # still denied...
    denied = [e for e in service.audit._events if e.action == "bootstrap_denied"]
    assert len(denied) == 1  # ...but nothing new written inside the full window

    resumed = await _first_ops_bootstrap_denial(
        "wrong-token", service, now=t0 + window + timedelta(seconds=1)
    )
    assert resumed is not None and resumed.status_code == 403
    denied = [e for e in service.audit._events if e.action == "bootstrap_denied"]
    assert len(denied) == 2  # the t0 denial left the window — auditing resumed
