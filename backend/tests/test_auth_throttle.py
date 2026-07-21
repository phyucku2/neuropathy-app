"""Login/refresh throttle tests (readiness plan §1B C5) — the ADR-0017 sliding-window
pattern on /auth/login and /auth/refresh.

Endpoint tests drive the real app over the in-memory stores (the deps wiring shape);
window-math tests inject fixed timestamps (the ADR-0013 CI-flake rule). All data is
synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.api.deps import get_auth_service, get_mfa_service
from app.core.config import settings
from app.main import app
from app.models.audit import AuditEvent
from app.repositories.audit import InMemoryAuditEventRepository
from app.services.auth import (
    INVALID_CREDENTIALS_DETAIL,
    LOGIN_RATE_LIMITED_DETAIL,
    AuthService,
    login_rate_limiter,
    login_throttle_actor_id,
    refresh_rate_limiter,
    refresh_throttle_actor_id,
)
from app.services.mfa import MfaService

# Uppercase constants keep the CI secret scanner from matching synthetic credentials.
SYNTHETIC_PASSWORD = "a-strong-password"

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


class World:
    """One shared in-memory world: auth + MFA on the SAME users/audit/secret, the way
    deps.py wires the singletons (the login route needs both services)."""

    def __init__(self) -> None:
        self.auth = AuthService(secret="endpoint-test-secret")
        self.mfa = MfaService(secret=self.auth.secret, users=self.auth.users, audit=self.auth.audit)

    def events(self, action: str) -> list[AuditEvent]:
        return [e for e in self.auth.audit._events if e.action == action]  # type: ignore[attr-defined]


@pytest.fixture()
def world() -> Iterator[World]:
    built = World()
    app.dependency_overrides[get_auth_service] = lambda: built.auth
    app.dependency_overrides[get_mfa_service] = lambda: built.mfa
    try:
        yield built
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def client(world: World) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def small_budget(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(settings, "login_rate_limit_max", 3)
    return 3


def _register(client: TestClient, email: str = "pat@example.com") -> dict[str, str]:
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": SYNTHETIC_PASSWORD, "display_name": "Pat"},
    )
    assert resp.status_code == 201
    body: dict[str, str] = resp.json()
    return body


def _login(client: TestClient, email: str, password: str) -> Response:
    return client.post("/auth/login", json={"email": email, "password": password})


# ---------------------------------------------------------------- login throttle


def test_login_burst_is_429_before_the_password_verify(
    world: World, client: TestClient, small_budget: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under the budget every wrong password is the generic 401 with one PHI-free
    'login_failed' event; over it the answer flips to 429 BEFORE the Argon2id verify
    — even the CORRECT password answers 429 without spending hashing CPU."""
    _register(client)
    for _ in range(small_budget):
        resp = _login(client, "pat@example.com", "not-the-password")
        assert resp.status_code == 401
        assert resp.json()["detail"] == INVALID_CREDENTIALS_DETAIL
    assert len(world.events("login_failed")) == small_budget

    def _must_not_run(password_hash: str, password: str) -> bool:
        raise AssertionError("verify_password must not run over the budget")

    monkeypatch.setattr("app.services.auth.verify_password", _must_not_run)
    over = _login(client, "pat@example.com", SYNTHETIC_PASSWORD)
    assert over.status_code == 429
    assert over.json()["detail"] == LOGIN_RATE_LIMITED_DETAIL
    # The refusal wrote its own bounded PHI-free event, never more 'login_failed' rows.
    assert len(world.events("login_failed")) == small_budget
    assert len(world.events("login_rate_limited")) == 1


def test_unknown_email_and_wrong_password_are_indistinguishable_under_the_limit(
    world: World, client: TestClient, small_budget: int
) -> None:
    """Non-enumeration holds THROUGH the throttle: probing an unknown email and
    fumbling a real account produce byte-identical 401s, identical audit shapes, and
    the identical 429 at the budget — a refusal never reveals whether the email
    matches an account."""
    _register(client, email="real@example.com")
    real = [_login(client, "real@example.com", "wrong-password") for _ in range(small_budget + 1)]
    ghost = [_login(client, "ghost@example.com", "wrong-password") for _ in range(small_budget + 1)]
    assert [(r.status_code, r.text) for r in real] == [(r.status_code, r.text) for r in ghost]
    assert [r.status_code for r in real] == [401] * small_budget + [429]
    # The audit trail is just as symmetric: same actions, same PHI-free detail shape,
    # and never the probed email anywhere in any event.
    failed = world.events("login_failed")
    assert len(failed) == 2 * small_budget
    assert {tuple(sorted(e.detail)) for e in failed} == {("limit", "window_seconds")}
    every_event = world.events("login_failed") + world.events("login_rate_limited")
    assert all("example.com" not in str(e.detail) for e in every_event)


def test_login_throttle_is_per_email_sentinel_not_global(
    world: World, client: TestClient, small_budget: int
) -> None:
    """Exhausting one email's budget never locks out another account (the sentinel
    keys the window), and a successful login inside an open window still works —
    only failures count."""
    _register(client, email="a@example.com")
    _register(client, email="b@example.com")
    for _ in range(small_budget):
        assert _login(client, "a@example.com", "wrong-password").status_code == 401
    assert _login(client, "a@example.com", SYNTHETIC_PASSWORD).status_code == 429
    # b's window is untouched: a fumble then a success, exactly as today.
    assert _login(client, "b@example.com", "wrong-password").status_code == 401
    assert _login(client, "b@example.com", SYNTHETIC_PASSWORD).status_code == 200


def test_login_window_slides_free_on_fixed_timestamps() -> None:
    """Window math on injected instants: failures exactly one window old still count;
    one second past the trailing edge the budget frees up (the ADR-0017 contract)."""
    repo = InMemoryAuditEventRepository()
    actor = login_throttle_actor_id("pat@example.com")
    window = timedelta(seconds=settings.login_rate_limit_window_seconds)

    async def _failure(at: datetime) -> None:
        await repo.add(
            AuditEvent(
                actor_id=actor,
                occurred_at=at,
                actor_role="system",
                action="login_failed",
                detail={},
            )
        )

    async def _scenario() -> None:
        for i in range(settings.login_rate_limit_max - 1):
            await _failure(NOW - timedelta(seconds=i))
        await _failure(NOW - window)  # exactly on the trailing edge — still counts
        limiter = login_rate_limiter(repo)
        assert await limiter.allow(actor, now=NOW) is False  # budget spent
        assert await limiter.allow(actor, now=NOW + timedelta(seconds=1)) is True  # slid free

    asyncio.run(_scenario())


def test_login_sentinel_is_normalized_and_non_enumerating() -> None:
    """The throttle actor is a uuid5 of the normalized-email hash: case/whitespace
    variants share one budget, distinct emails never collide, and the raw email is
    not recoverable from (or embedded in) the sentinel."""
    sentinel = login_throttle_actor_id("pat@example.com")
    assert login_throttle_actor_id("  PAT@Example.COM ") == sentinel
    assert login_throttle_actor_id("other@example.com") != sentinel
    assert "pat" not in str(sentinel)
    # Deterministic across processes (a stable namespace, not a per-boot salt): the
    # durable audit counter must aggregate one email's failures across workers.
    assert sentinel == login_throttle_actor_id("pat@example.com")


def test_rate_limited_audit_writes_are_capped(
    world: World, client: TestClient, small_budget: int
) -> None:
    """The 429 path's own 'login_rate_limited' rows are budget-capped per sentinel
    (the bootstrap_denied pattern): hammering past the cap answers identical 429s
    while only the audit write is skipped — no anonymous log-flood primitive."""
    for _ in range(small_budget):
        assert _login(client, "ghost@example.com", "wrong-password").status_code == 401
    responses = [
        _login(client, "ghost@example.com", "wrong-password") for _ in range(small_budget * 3)
    ]
    assert all(r.status_code == 429 for r in responses)
    assert len(world.events("login_rate_limited")) == small_budget


def test_settings_driven_login_limiter() -> None:
    repo = InMemoryAuditEventRepository()
    limiter = login_rate_limiter(repo)
    assert limiter.counter is repo
    assert limiter.action == "login_failed"
    assert limiter.max_events == settings.login_rate_limit_max
    assert limiter.window == timedelta(seconds=settings.login_rate_limit_window_seconds)


# ---------------------------------------------------------------- refresh throttle


def test_refresh_failures_are_audited_then_throttled(
    world: World, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Signature-valid refreshes whose account is gone: 401 + one 'refresh_failed'
    event each, then 429 once the per-subject budget is spent — BEFORE the
    repository lookup runs."""
    monkeypatch.setattr(settings, "refresh_rate_limit_max", 2)
    tokens = _register(client, email="gone@example.com")
    user = world.auth.users._by_email.pop("gone@example.com")  # noqa: SLF001
    world.auth.users._by_id.pop(user.id)  # noqa: SLF001

    for _ in range(2):
        resp = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 401
    assert len(world.events("refresh_failed")) == 2

    async def _must_not_run(user_id: uuid.UUID) -> None:
        raise AssertionError("the account lookup must not run over the budget")

    monkeypatch.setattr(world.auth.users, "get_by_id", _must_not_run)
    over = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert over.status_code == 429
    assert over.json()["detail"] == LOGIN_RATE_LIMITED_DETAIL
    assert len(world.events("refresh_failed")) == 2  # the 429 wrote no failure row


def test_healthy_refreshes_never_count_against_the_budget(
    world: World, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only FAILED refreshes spend budget: a live client can refresh far past the
    max without ever seeing a 429."""
    monkeypatch.setattr(settings, "refresh_rate_limit_max", 2)
    tokens = _register(client)
    for _ in range(5):
        resp = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 200
    assert world.events("refresh_failed") == []


def test_garbage_refresh_tokens_are_401_and_never_audited(world: World, client: TestClient) -> None:
    """A token that fails the signature/kind decode is refused outright and writes
    nothing — the sentinel space stays non-attacker-minted (no audit flood from
    random bytes)."""
    resp = client.post("/auth/refresh", json={"refresh_token": "not.a.token"})
    assert resp.status_code == 401
    assert world.events("refresh_failed") == []
    assert world.events("login_rate_limited") == []


def test_refresh_sentinel_hashes_the_subject() -> None:
    subject = uuid.uuid4()
    sentinel = refresh_throttle_actor_id(subject)
    assert sentinel == refresh_throttle_actor_id(subject)  # deterministic
    assert sentinel != subject  # never the raw subject id
    assert refresh_throttle_actor_id(uuid.uuid4()) != sentinel


def test_settings_driven_refresh_limiter() -> None:
    repo = InMemoryAuditEventRepository()
    limiter = refresh_rate_limiter(repo)
    assert limiter.counter is repo
    assert limiter.action == "refresh_failed"
    assert limiter.max_events == settings.refresh_rate_limit_max
    assert limiter.window == timedelta(seconds=settings.refresh_rate_limit_window_seconds)
