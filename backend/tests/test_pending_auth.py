"""Unit tests for the pending-auth store contract (ADR-0017): TTL expiry and
single-use consumption, on fixed injected timestamps (never wall-clock assertions).

The Postgres implementation is exercised by tests/integration/test_hardening_stores.py
against a real database (including the concurrent-consume race).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core.config import settings
from app.emr.service import (
    EmrError,
    EmrService,
    InMemoryPendingAuthStore,
    PendingAuth,
    pending_auth_ttl,
)

T0 = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _pending() -> PendingAuth:
    return PendingAuth(
        connection_id=uuid.uuid4(), code_verifier="synthetic-verifier", token_endpoint="https://t"
    )


def test_ttl_is_settings_driven(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pending_auth_ttl_seconds", 42)
    assert pending_auth_ttl() == timedelta(seconds=42)


async def test_consume_is_single_use() -> None:
    store = InMemoryPendingAuthStore()
    pending = _pending()
    await store.put("state-1", pending, now=T0)
    assert await store.consume("state-1", now=T0 + timedelta(seconds=1)) == pending
    # Replay: the state is gone — same answer as a state that never existed.
    assert await store.consume("state-1", now=T0 + timedelta(seconds=2)) is None
    assert await store.consume("never-issued", now=T0) is None


async def test_expired_states_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pending_auth_ttl_seconds", 600)
    store = InMemoryPendingAuthStore()
    await store.put("state-1", _pending(), now=T0)
    # One second before the deadline: honored; exactly at it: refused (and gone).
    store_late = InMemoryPendingAuthStore()
    await store_late.put("state-2", _pending(), now=T0)
    assert await store_late.consume("state-2", now=T0 + timedelta(seconds=599)) is not None
    assert await store.consume("state-1", now=T0 + timedelta(seconds=600)) is None
    assert await store.consume("state-1", now=T0) is None  # refusal purged it


async def test_put_purges_expired_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pending_auth_ttl_seconds", 600)
    store = InMemoryPendingAuthStore()
    await store.put("old", _pending(), now=T0)
    await store.put("fresh", _pending(), now=T0 + timedelta(seconds=601))  # 'old' is expired
    assert list(store._pending) == ["fresh"]  # noqa: SLF001 — asserting the purge itself


async def test_callback_with_expired_state_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end at the service: a handshake older than the TTL answers the same
    404 as an unknown state (ttl=0 makes every state expired at consume time —
    deterministic, no sleeping)."""

    class Discovery:
        async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
            return {
                "authorization_endpoint": "https://ehr.example/authorize",
                "token_endpoint": "https://ehr.example/token",
            }

        async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
            raise AssertionError("an expired state must never reach the token endpoint")

    monkeypatch.setattr(settings, "pending_auth_ttl_seconds", 0)
    service = EmrService(transport=Discovery(), client_id="c", redirect_uri="https://a/cb")
    _, _, state = await service.start_connect(
        patient_id=uuid.uuid4(), fhir_base="https://ehr.example/fhir", provider_name=None
    )
    with pytest.raises(EmrError) as exc_info:
        await service.complete_callback(state=state, code="auth-code")
    assert exc_info.value.status_code == 404
    assert "expired" in exc_info.value.reason
