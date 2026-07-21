"""MFA (TOTP) tests for privileged accounts (readiness plan §1B C6): enrollment,
activation, the login step-up, kind confusion at the endpoints, the enforcement flag,
and the patients-unaffected guarantee.

Drives the in-memory storage mode through the real app with auth + MFA sharing the
SAME users/audit/vault stores — exactly the deps.py wiring. All data is synthetic
(CLAUDE.md §5).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.api.deps import get_auth_service, get_mfa_service
from app.core.config import settings
from app.core.totp import totp_at
from app.main import app
from app.models.audit import AuditEvent
from app.services.auth import AuthService
from app.services.mfa import (
    MFA_ENROLLMENT_REQUIRED_DETAIL,
    WRONG_CODE_DETAIL,
    MfaService,
)

# Uppercase constants keep the CI secret scanner from matching synthetic credentials.
SYNTHETIC_PASSWORD = "a-strong-password"
CLINICIAN_EMAIL = "dr@example.com"
OPS_EMAIL = "ops@example.com"
PATIENT_EMAIL = "pat@example.com"


class World:
    """One shared in-memory world: auth + MFA on the SAME users/audit/vault stores,
    the way deps.py wires the singletons."""

    def __init__(self) -> None:
        self.auth = AuthService(secret="endpoint-test-secret")
        self.mfa = MfaService(secret=self.auth.secret, users=self.auth.users, audit=self.auth.audit)

    def events(self, action: str) -> list[AuditEvent]:
        return [e for e in self.auth.audit._events if e.action == action]  # type: ignore[attr-defined]


@pytest.fixture()
def world() -> Iterator[World]:
    built = World()
    asyncio.run(
        built.auth.create_clinician(
            email=CLINICIAN_EMAIL,
            password=SYNTHETIC_PASSWORD,
            display_name="Dr. Rivera",
            clinic_id=uuid.uuid4(),
        )
    )
    asyncio.run(
        built.auth.create_ops(email=OPS_EMAIL, password=SYNTHETIC_PASSWORD, display_name="Ops")
    )
    app.dependency_overrides[get_auth_service] = lambda: built.auth
    app.dependency_overrides[get_mfa_service] = lambda: built.mfa
    try:
        yield built
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def client(world: World) -> TestClient:
    return TestClient(app)


def _login(client: TestClient, email: str, password: str = SYNTHETIC_PASSWORD) -> Response:
    return client.post("/auth/login", json={"email": email, "password": password})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _access_token(client: TestClient, email: str) -> str:
    resp = _login(client, email)
    assert resp.status_code == 200
    token: str = resp.json()["access_token"]
    return token


def _enroll_and_confirm(client: TestClient, access: str) -> str:
    """Run the full enrollment: returns the TOTP secret the authenticator would hold."""
    enroll = client.post("/auth/mfa/enroll", headers=_auth(access))
    assert enroll.status_code == 201
    secret: str = enroll.json()["secret"]
    confirm = client.post(
        "/auth/mfa/enroll/confirm",
        headers=_auth(access),
        json={"code": totp_at(secret, datetime.now(UTC))},
    )
    assert confirm.status_code == 200
    assert confirm.json() == {"enrolled": True}
    return secret


# ---------------------------------------------------------------- happy path


def test_enroll_activate_step_up_happy_path(world: World, client: TestClient) -> None:
    """The whole §1B C6 loop: enroll (one-time secret + otpauth URI), confirm with a
    matching code, then the next login answers ONLY the mfa_pending step-up, and
    /auth/mfa/verify exchanges it + a code for real, working tokens."""
    access = _access_token(client, CLINICIAN_EMAIL)
    assert client.get("/auth/mfa", headers=_auth(access)).json() == {"enrolled": False}

    enroll = client.post("/auth/mfa/enroll", headers=_auth(access))
    assert enroll.status_code == 201
    body = enroll.json()
    secret = body["secret"]
    assert body["otpauth_uri"].startswith("otpauth://totp/Neuropathy:dr%40example.com?")
    assert f"secret={secret}" in body["otpauth_uri"]
    # A pending factor gates nothing yet: status stays false, login stays plain.
    assert client.get("/auth/mfa", headers=_auth(access)).json() == {"enrolled": False}
    assert "access_token" in _login(client, CLINICIAN_EMAIL).json()

    confirm = client.post(
        "/auth/mfa/enroll/confirm",
        headers=_auth(access),
        json={"code": totp_at(secret, datetime.now(UTC))},
    )
    assert confirm.status_code == 200
    assert client.get("/auth/mfa", headers=_auth(access)).json() == {"enrolled": True}

    step_up = _login(client, CLINICIAN_EMAIL)
    assert step_up.status_code == 200
    pending = step_up.json()
    assert pending["token_type"] == "mfa_pending"
    assert set(pending) == {"mfa_pending_token", "token_type"}  # NO access/refresh token

    verified = client.post(
        "/auth/mfa/verify",
        json={
            "mfa_pending_token": pending["mfa_pending_token"],
            "code": totp_at(secret, datetime.now(UTC)),
        },
    )
    assert verified.status_code == 200
    tokens = verified.json()
    assert tokens["token_type"] == "bearer"
    me = client.get("/auth/me", headers=_auth(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json()["role"] == "clinician"
    # Refresh works too — the step-up minted a full session.
    assert (
        client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code
        == 200
    )
    # Audited with references only (never the secret or a code).
    assert len(world.events("mfa_enroll")) == 1
    assert len(world.events("mfa_activate")) == 1
    assert len(world.events("mfa_verify")) == 1
    every = world.events("mfa_enroll") + world.events("mfa_activate") + world.events("mfa_verify")
    assert all(secret not in str(e.detail) for e in every)


def test_ops_accounts_get_the_same_step_up(world: World, client: TestClient) -> None:
    access = _access_token(client, OPS_EMAIL)
    secret = _enroll_and_confirm(client, access)
    step_up = _login(client, OPS_EMAIL)
    assert step_up.json()["token_type"] == "mfa_pending"
    verified = client.post(
        "/auth/mfa/verify",
        json={
            "mfa_pending_token": step_up.json()["mfa_pending_token"],
            "code": totp_at(secret, datetime.now(UTC)),
        },
    )
    assert verified.status_code == 200


# ---------------------------------------------------------------- the secret's custody


def test_totp_secret_is_never_stored_outside_the_vault(world: World, client: TestClient) -> None:
    """The factor row carries only an opaque vault ref; the secret itself lives
    behind the SecretStore seam (encrypted at rest in DB mode, ADR-0017)."""
    access = _access_token(client, CLINICIAN_EMAIL)
    secret = _enroll_and_confirm(client, access)
    user = asyncio.run(world.auth.users.get_by_email(CLINICIAN_EMAIL))
    assert user is not None
    factor = asyncio.run(world.mfa.factors.get_for_user(user.id))
    assert factor is not None
    assert secret not in factor.secret_ref  # an opaque reference, not the secret
    vaulted = asyncio.run(world.mfa.secret_store.get(factor.secret_ref))
    assert vaulted == {"totp_secret": secret}


def test_re_enrollment_replaces_the_factor_and_purges_the_old_vault_entry(
    world: World, client: TestClient
) -> None:
    """Re-enrolling starts over: fresh UNCONFIRMED factor (the old one stops gating
    login until confirmed again) and the superseded vault entry is deleted through
    the same seam revocation uses."""
    access = _access_token(client, CLINICIAN_EMAIL)
    _enroll_and_confirm(client, access)
    user = asyncio.run(world.auth.users.get_by_email(CLINICIAN_EMAIL))
    assert user is not None
    old_factor = asyncio.run(world.mfa.factors.get_for_user(user.id))
    assert old_factor is not None

    again = client.post("/auth/mfa/enroll", headers=_auth(access))
    assert again.status_code == 201
    assert asyncio.run(world.mfa.secret_store.get(old_factor.secret_ref)) is None  # purged
    new_factor = asyncio.run(world.mfa.factors.get_for_user(user.id))
    assert new_factor is not None
    assert new_factor.secret_ref != old_factor.secret_ref
    assert new_factor.confirmed_at is None  # back to pending
    assert client.get("/auth/mfa", headers=_auth(access)).json() == {"enrolled": False}
    assert "access_token" in _login(client, CLINICIAN_EMAIL).json()  # no step-up while pending
    assert world.events("mfa_enroll")[-1].detail == {"replaced_existing_factor": True}


# ---------------------------------------------------------------- wrong codes


def test_wrong_confirmation_code_is_401_and_does_not_activate(
    world: World, client: TestClient
) -> None:
    access = _access_token(client, CLINICIAN_EMAIL)
    enroll = client.post("/auth/mfa/enroll", headers=_auth(access))
    resp = client.post("/auth/mfa/enroll/confirm", headers=_auth(access), json={"code": "000000"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == WRONG_CODE_DETAIL
    assert enroll.status_code == 201
    assert client.get("/auth/mfa", headers=_auth(access)).json() == {"enrolled": False}
    assert world.events("mfa_activate") == []


def test_confirm_without_an_enrollment_is_409(world: World, client: TestClient) -> None:
    access = _access_token(client, CLINICIAN_EMAIL)
    resp = client.post("/auth/mfa/enroll/confirm", headers=_auth(access), json={"code": "123456"})
    assert resp.status_code == 409


def test_wrong_step_up_code_is_401_audited_and_throttled(
    world: World, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wrong codes at /auth/mfa/verify: the generic 401 + one 'mfa_verify_failed'
    event each; over the (login-budget) window the answer is 429 BEFORE the code is
    even compared — C5's limiter guarding C6's oracle."""
    monkeypatch.setattr(settings, "login_rate_limit_max", 3)
    access = _access_token(client, CLINICIAN_EMAIL)
    secret = _enroll_and_confirm(client, access)
    pending = _login(client, CLINICIAN_EMAIL).json()["mfa_pending_token"]

    for _ in range(3):
        resp = client.post(
            "/auth/mfa/verify", json={"mfa_pending_token": pending, "code": "000000"}
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == WRONG_CODE_DETAIL
    assert len(world.events("mfa_verify_failed")) == 3

    def _must_not_run(secret_value: str, code: str, *, at: datetime) -> bool:
        raise AssertionError("verify_totp must not run over the budget")

    monkeypatch.setattr("app.services.mfa.verify_totp", _must_not_run)
    over = client.post(
        "/auth/mfa/verify",
        json={"mfa_pending_token": pending, "code": totp_at(secret, datetime.now(UTC))},
    )
    assert over.status_code == 429
    assert len(world.events("mfa_verify_failed")) == 3  # the 429 wrote no failure row


# ---------------------------------------------------------------- kind confusion


def test_mfa_pending_token_is_useless_as_access_or_refresh(
    world: World, client: TestClient
) -> None:
    """Endpoint-level kind enforcement (§1B C6): the half-authenticated token opens
    NO authenticated surface and mints nothing."""
    access = _access_token(client, CLINICIAN_EMAIL)
    _enroll_and_confirm(client, access)
    pending = _login(client, CLINICIAN_EMAIL).json()["mfa_pending_token"]

    assert client.get("/auth/me", headers=_auth(pending)).status_code == 401
    assert client.get("/auth/mfa", headers=_auth(pending)).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": pending}).status_code == 401


def test_access_and_refresh_tokens_are_useless_at_the_verify_endpoint(
    world: World, client: TestClient
) -> None:
    """The other direction: a stolen full-session token cannot impersonate the
    step-up handshake (and writes no failure rows — refused at decode)."""
    access = _access_token(client, CLINICIAN_EMAIL)
    secret = _enroll_and_confirm(client, access)
    tokens = client.post(
        "/auth/mfa/verify",
        json={
            "mfa_pending_token": _login(client, CLINICIAN_EMAIL).json()["mfa_pending_token"],
            "code": totp_at(secret, datetime.now(UTC)),
        },
    ).json()
    for wrong_kind in (tokens["access_token"], tokens["refresh_token"]):
        resp = client.post(
            "/auth/mfa/verify",
            json={"mfa_pending_token": wrong_kind, "code": totp_at(secret, datetime.now(UTC))},
        )
        assert resp.status_code == 401
    assert world.events("mfa_verify_failed") == []


# ---------------------------------------------------------------- patients unaffected


def test_patients_are_completely_unaffected(
    world: World, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Patients: full tokens at login (flag on OR off), no enrollment surface, and an
    always-false status — the whole feature is invisible to them."""
    resp = client.post(
        "/auth/register",
        json={"email": PATIENT_EMAIL, "password": SYNTHETIC_PASSWORD, "display_name": "Pat"},
    )
    assert resp.status_code == 201
    assert _login(client, PATIENT_EMAIL).json()["token_type"] == "bearer"

    access = _login(client, PATIENT_EMAIL).json()["access_token"]
    assert client.get("/auth/mfa", headers=_auth(access)).json() == {"enrolled": False}
    enroll = client.post("/auth/mfa/enroll", headers=_auth(access))
    assert enroll.status_code == 403  # patients can never hold a factor

    monkeypatch.setattr(settings, "mfa_required_for_privileged", True)
    flagged = _login(client, PATIENT_EMAIL)
    assert flagged.status_code == 200
    assert flagged.json()["token_type"] == "bearer"  # never enrollment-blocked


# ---------------------------------------------------------------- the enforcement flag


def test_flag_off_keeps_unenrolled_privileged_login_unchanged(
    world: World, client: TestClient
) -> None:
    """mfa_required_for_privileged=False (the default): an unenrolled clinician logs
    in exactly as before — full tokens, no step-up, no refusal."""
    assert settings.mfa_required_for_privileged is False
    resp = _login(client, CLINICIAN_EMAIL)
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"


def test_flag_on_blocks_unenrolled_privileged_login(
    world: World, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag on (the go-live act): password success for an UNENROLLED clinician/ops
    account answers the enrollment-required 403 — no tokens of any kind."""
    monkeypatch.setattr(settings, "mfa_required_for_privileged", True)
    for email in (CLINICIAN_EMAIL, OPS_EMAIL):
        resp = _login(client, email)
        assert resp.status_code == 403
        assert resp.json() == {"detail": MFA_ENROLLMENT_REQUIRED_DETAIL}

    # A wrong password still answers the generic 401 FIRST — the flag discloses
    # nothing to callers who don't hold the credential.
    assert _login(client, CLINICIAN_EMAIL, "wrong-password").status_code == 401


def test_flag_on_still_steps_up_enrolled_accounts(
    world: World, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    access = _access_token(client, CLINICIAN_EMAIL)
    secret = _enroll_and_confirm(client, access)
    monkeypatch.setattr(settings, "mfa_required_for_privileged", True)
    step_up = _login(client, CLINICIAN_EMAIL)
    assert step_up.status_code == 200
    assert step_up.json()["token_type"] == "mfa_pending"
    verified = client.post(
        "/auth/mfa/verify",
        json={
            "mfa_pending_token": step_up.json()["mfa_pending_token"],
            "code": totp_at(secret, datetime.now(UTC)),
        },
    )
    assert verified.status_code == 200
