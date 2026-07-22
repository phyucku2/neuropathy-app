"""Caregiver REAL push (ADR-0047 Phase B2) — the FCM HTTP v1 sender against a FAKE
transport, the token register/deregister endpoints, the post-commit fan-out, and the
config fail-safe.

ABSOLUTE test rule: the service-account credential here is a SYNTHETIC throwaway RSA
keypair generated in-memory, and every HTTP call crosses a FAKE transport — NEVER a real
key, never the real network (CLAUDE.md §5).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from app.api import deps
from app.api.deps import (
    CaregiverPushDispatcher,
    get_auth_service,
    get_caregiver_push_token_repo,
    get_caregiver_service,
)
from app.core.config import settings
from app.main import app
from app.repositories.caregiver_push_token import InMemoryCaregiverPushTokenRepository
from app.services.caregiver import CaregiverService
from app.services.caregiver_push_dispatch import fan_out_caregiver_push
from app.services.push import (
    FcmCredentialsError,
    FcmHttpResponse,
    FcmPushSender,
    PushMessage,
    TokenSendOutcome,
)

SYNTHETIC_PASSWORD = "a-strong-password"
NOW = datetime.now(UTC)


# ---------------------------------------------------------------- synthetic credential


@pytest.fixture(scope="module")
def service_account_info() -> dict[str, str]:
    """A SYNTHETIC service-account: a throwaway RSA keypair generated in-memory. It signs
    the OAuth assertion offline exactly like a real key would — but it is not, and never
    was, a real credential."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {
        "type": "service_account",
        "project_id": "synthetic-project",
        "private_key_id": "kid-synthetic",
        "private_key": pem,
        "client_email": "svc@synthetic-project.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.test/token",
    }


# ---------------------------------------------------------------- fake transport


class FakeTransport:
    """Captures every call and returns canned rows. Token exchanges (``data=``) always
    mint a token; sends (``json=``) return the next queued response (default 200)."""

    def __init__(self, *, send_responses: list[FcmHttpResponse] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.token_mints = 0
        self._send_responses = list(send_responses or [])

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> FcmHttpResponse:
        self.calls.append({"url": url, "headers": headers, "data": data, "json": json})
        if data is not None:  # the OAuth token exchange
            self.token_mints += 1
            return FcmHttpResponse(200, {"access_token": "fake-access-token", "expires_in": 3600})
        if self._send_responses:  # an FCM send
            return self._send_responses.pop(0)
        return FcmHttpResponse(200, {})

    @property
    def token_calls(self) -> list[dict[str, object]]:
        return [c for c in self.calls if c["data"] is not None]

    @property
    def send_calls(self) -> list[dict[str, object]]:
        return [c for c in self.calls if c["json"] is not None]


def _message() -> PushMessage:
    return PushMessage(
        caregiver_user_id=uuid.uuid4(),
        alert_type="med_change",
        alert_id=uuid.uuid4(),
        title="A medication update",
        body="There's been an update to the medication list. In an emergency call 911.",
    )


# ---------------------------------------------------------------- real sender vs fake transport


async def test_sender_hits_correct_url_and_auth_header(
    service_account_info: dict[str, str],
) -> None:
    transport = FakeTransport()
    sender = FcmPushSender(transport=transport, service_account_info=service_account_info)

    outcome = await sender.send_to_token(_message(), "device-token-1")
    assert outcome is TokenSendOutcome.delivered

    # The OAuth exchange came first, to the credential's token_uri, carrying the JWT-bearer
    # grant and a locally-signed assertion (three dot-separated JWT segments).
    token_call = transport.token_calls[0]
    assert token_call["url"] == "https://oauth2.test/token"
    data = token_call["data"]
    assert isinstance(data, dict)
    assert data["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    assert data["assertion"].count(".") == 2

    # Then the FCM v1 send, to the project-scoped URL with the Bearer access token.
    send_call = transport.send_calls[0]
    assert send_call["url"] == (
        "https://fcm.googleapis.com/v1/projects/synthetic-project/messages:send"
    )
    headers = send_call["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer fake-access-token"
    assert headers["Content-Type"] == "application/json"


async def test_sender_body_is_phi_free(service_account_info: dict[str, str]) -> None:
    transport = FakeTransport()
    sender = FcmPushSender(transport=transport, service_account_info=service_account_info)
    message = _message()

    await sender.send_to_token(message, "device-token-1")

    body = transport.send_calls[0]["json"]
    assert isinstance(body, dict)
    envelope = body["message"]
    assert isinstance(envelope, dict)
    # data = identifiers ONLY; no third key that could smuggle a value.
    assert envelope["data"] == {
        "alert_id": str(message.alert_id),
        "alert_type": message.alert_type,
    }
    # notification = the fixed template copy only.
    assert envelope["notification"] == {"title": message.title, "body": message.body}
    assert set(envelope) == {"token", "data", "notification"}
    # A body scan finds no PHI-shaped field name anywhere in the serialized payload.
    serialized = json.dumps(body).lower()
    for banned in ("patient_name", "display_name", "value_num", '"value"', "note", "code_system"):
        assert banned not in serialized


async def test_oauth_token_is_cached_across_sends(
    service_account_info: dict[str, str],
) -> None:
    transport = FakeTransport()
    sender = FcmPushSender(transport=transport, service_account_info=service_account_info)

    await sender.send_to_token(_message(), "device-token-1")
    await sender.send_to_token(_message(), "device-token-2")

    # One mint reused across both sends; two FCM sends went out.
    assert transport.token_mints == 1
    assert len(transport.send_calls) == 2


@pytest.mark.parametrize(
    "response",
    [
        FcmHttpResponse(404, {"error": {"status": "NOT_FOUND"}}),
        FcmHttpResponse(400, {"error": {"details": [{"errorCode": "UNREGISTERED"}]}}),
        FcmHttpResponse(
            400,
            {
                "error": {
                    "status": "INVALID_ARGUMENT",
                    "details": [
                        {
                            "errorCode": "INVALID_ARGUMENT",
                            "fieldViolations": [{"field": "message.token"}],
                        }
                    ],
                }
            },
        ),
    ],
)
async def test_dead_token_responses_map_to_unregistered(
    service_account_info: dict[str, str], response: FcmHttpResponse
) -> None:
    transport = FakeTransport(send_responses=[response])
    sender = FcmPushSender(transport=transport, service_account_info=service_account_info)
    assert await sender.send_to_token(_message(), "dead") is TokenSendOutcome.unregistered


async def test_invalid_argument_not_naming_token_is_transient(
    service_account_info: dict[str, str],
) -> None:
    # INVALID_ARGUMENT on a NON-token field is our own payload bug, not a dead token —
    # it must never trigger a token deletion.
    response = FcmHttpResponse(
        400,
        {
            "error": {
                "status": "INVALID_ARGUMENT",
                "details": [
                    {
                        "errorCode": "INVALID_ARGUMENT",
                        "fieldViolations": [{"field": "message.data"}],
                    }
                ],
            }
        },
    )
    transport = FakeTransport(send_responses=[response])
    sender = FcmPushSender(transport=transport, service_account_info=service_account_info)
    assert await sender.send_to_token(_message(), "tok") is TokenSendOutcome.transient


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_errors_do_not_crash_or_delete(
    service_account_info: dict[str, str], status: int
) -> None:
    transport = FakeTransport(send_responses=[FcmHttpResponse(status, {"error": {"status": "X"}})])
    sender = FcmPushSender(transport=transport, service_account_info=service_account_info)
    assert await sender.send_to_token(_message(), "tok") is TokenSendOutcome.auth_error


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_transient_statuses_are_swallowed(
    service_account_info: dict[str, str], status: int
) -> None:
    transport = FakeTransport(send_responses=[FcmHttpResponse(status, {})])
    sender = FcmPushSender(transport=transport, service_account_info=service_account_info)
    assert await sender.send_to_token(_message(), "tok") is TokenSendOutcome.transient


async def test_transport_exception_is_transient(service_account_info: dict[str, str]) -> None:
    class BoomTransport(FakeTransport):
        async def post(self, url, *, headers, data=None, json=None):  # type: ignore[no-untyped-def]
            if data is not None:
                return await super().post(url, headers=headers, data=data, json=json)
            raise RuntimeError("network down")

    sender = FcmPushSender(transport=BoomTransport(), service_account_info=service_account_info)
    assert await sender.send_to_token(_message(), "tok") is TokenSendOutcome.transient


async def test_token_mint_failure_is_transient(service_account_info: dict[str, str]) -> None:
    class BadTokenTransport(FakeTransport):
        async def post(self, url, *, headers, data=None, json=None):  # type: ignore[no-untyped-def]
            if data is not None:
                return FcmHttpResponse(400, {"error": "invalid_grant"})
            return FcmHttpResponse(200, {})

    sender = FcmPushSender(transport=BadTokenTransport(), service_account_info=service_account_info)
    assert await sender.send_to_token(_message(), "tok") is TokenSendOutcome.transient


def test_malformed_credential_raises_fcm_credentials_error() -> None:
    with pytest.raises(FcmCredentialsError):
        FcmPushSender(transport=FakeTransport(), service_account_info={"project_id": "x"})


# ---------------------------------------------------------------- fan-out


class _RecordingSender:
    def __init__(self, outcomes: dict[str, TokenSendOutcome] | None = None) -> None:
        self.sent: list[tuple[PushMessage, str]] = []
        self._outcomes = outcomes or {}

    async def send_to_token(self, message: PushMessage, token: str) -> TokenSendOutcome:
        self.sent.append((message, token))
        return self._outcomes.get(token, TokenSendOutcome.delivered)


async def test_fan_out_delivers_to_every_token_and_prunes_dead_ones() -> None:
    tokens = InMemoryCaregiverPushTokenRepository()
    caregiver_id = uuid.uuid4()
    await tokens.upsert(caregiver_user_id=caregiver_id, token="live", platform="android", now=NOW)
    await tokens.upsert(caregiver_user_id=caregiver_id, token="dead", platform="android", now=NOW)
    sender = _RecordingSender({"dead": TokenSendOutcome.unregistered})

    message = PushMessage(
        caregiver_user_id=caregiver_id,
        alert_type="trend_shift",
        alert_id=uuid.uuid4(),
        title="A shift in the wellness trend",
        body="...911...",
    )
    await fan_out_caregiver_push(messages=[message], tokens=tokens, sender=sender)

    assert {t for _, t in sender.sent} == {"live", "dead"}
    remaining = {r.token for r in await tokens.list_for_caregiver(caregiver_id)}
    assert remaining == {"live"}  # the dead token was pruned


async def test_fan_out_swallows_a_sender_that_raises() -> None:
    tokens = InMemoryCaregiverPushTokenRepository()
    caregiver_id = uuid.uuid4()
    await tokens.upsert(caregiver_user_id=caregiver_id, token="t", platform="android", now=NOW)

    class Boom:
        async def send_to_token(self, message: PushMessage, token: str) -> TokenSendOutcome:
            raise RuntimeError("boom")

    message = PushMessage(
        caregiver_user_id=caregiver_id,
        alert_type="trend_shift",
        alert_id=uuid.uuid4(),
        title="t",
        body="b",
    )
    # Must not raise into the background runner.
    await fan_out_caregiver_push(messages=[message], tokens=tokens, sender=Boom())


# ---------------------------------------------------------------- dispatcher gating


def test_dispatcher_schedule_is_noop_without_a_sender() -> None:
    background = BackgroundTasks()
    dispatcher = CaregiverPushDispatcher(sender=None, sessionmaker=None)
    dispatcher.schedule(background, [_message()])
    assert background.tasks == []


def test_dispatcher_schedule_is_noop_without_messages() -> None:
    background = BackgroundTasks()
    dispatcher = CaregiverPushDispatcher(sender=object(), sessionmaker=None)  # type: ignore[arg-type]
    dispatcher.schedule(background, [])
    assert background.tasks == []


def test_dispatcher_schedules_a_task_when_enabled() -> None:
    background = BackgroundTasks()
    dispatcher = CaregiverPushDispatcher(sender=object(), sessionmaker=None)  # type: ignore[arg-type]
    dispatcher.schedule(background, [_message()])
    assert len(background.tasks) == 1


async def test_dispatcher_run_in_memory_path_fans_out(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = InMemoryCaregiverPushTokenRepository()
    caregiver_id = uuid.uuid4()
    await repo.upsert(caregiver_user_id=caregiver_id, token="t", platform="android", now=NOW)
    monkeypatch.setattr(deps, "_process_caregiver_push_token_repo", lambda: repo)
    sender = _RecordingSender()
    dispatcher = CaregiverPushDispatcher(sender=sender, sessionmaker=None)  # type: ignore[arg-type]
    message = PushMessage(
        caregiver_user_id=caregiver_id,
        alert_type="trend_shift",
        alert_id=uuid.uuid4(),
        title="t",
        body="b",
    )
    await dispatcher._run([message])
    assert [t for _, t in sender.sent] == ["t"]


# ---------------------------------------------------------------- config fail-safe


def test_fcm_sender_disabled_by_default() -> None:
    deps._process_fcm_sender.cache_clear()
    assert deps._process_fcm_sender() is None


def test_fcm_sender_fail_safe_when_enabled_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "caregiver_push_enabled", True)
    monkeypatch.setattr(settings, "fcm_credentials_json", None)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    deps._process_fcm_sender.cache_clear()
    try:
        # Flag ON but no credential -> the no-op path (None), never a broken sender.
        assert deps._process_fcm_sender() is None
    finally:
        deps._process_fcm_sender.cache_clear()


def test_fcm_sender_built_when_enabled_with_credentials(
    monkeypatch: pytest.MonkeyPatch, service_account_info: dict[str, str]
) -> None:
    monkeypatch.setattr(settings, "caregiver_push_enabled", True)
    monkeypatch.setattr(settings, "fcm_credentials_json", json.dumps(service_account_info))
    deps._process_fcm_sender.cache_clear()
    try:
        sender = deps._process_fcm_sender()
        assert isinstance(sender, FcmPushSender)
    finally:
        deps._process_fcm_sender.cache_clear()


def test_malformed_credentials_json_fails_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "caregiver_push_enabled", True)
    monkeypatch.setattr(settings, "fcm_credentials_json", "{not valid json")
    deps._process_fcm_sender.cache_clear()
    try:
        assert deps._process_fcm_sender() is None
    finally:
        deps._process_fcm_sender.cache_clear()


# ---------------------------------------------------------------- token endpoints


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def caregiver_service() -> CaregiverService:
    return CaregiverService()


@pytest.fixture()
def token_repo() -> InMemoryCaregiverPushTokenRepository:
    return InMemoryCaregiverPushTokenRepository()


@pytest.fixture()
def client(
    caregiver_service: CaregiverService, token_repo: InMemoryCaregiverPushTokenRepository
) -> Iterator[TestClient]:
    from app.services.auth import AuthService

    auth = AuthService(secret="push-endpoint-secret", users=caregiver_service.users)
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_caregiver_service] = lambda: caregiver_service
    app.dependency_overrides[get_caregiver_push_token_repo] = lambda: token_repo
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _register_patient(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/auth/register",
        json={"email": "pat@example.com", "password": SYNTHETIC_PASSWORD, "display_name": "Pat"},
    )
    assert resp.status_code == 201
    return _auth(resp.json()["access_token"])


def _register_caregiver(client: TestClient, patient: dict[str, str]) -> dict[str, str]:
    code = client.post("/me/caregiver-invites", headers=patient).json()["code"]
    resp = client.post(
        "/caregiver/register",
        json={
            "code": code,
            "email": "care@example.com",
            "password": SYNTHETIC_PASSWORD,
            "display_name": "Cam",
        },
    )
    assert resp.status_code == 201, resp.text
    return _auth(resp.json()["access_token"])


def test_register_and_refresh_and_deregister_token(
    client: TestClient,
    caregiver_service: CaregiverService,
    token_repo: InMemoryCaregiverPushTokenRepository,
) -> None:
    patient = _register_patient(client)
    caregiver = _register_caregiver(client, patient)

    # Register a device token.
    resp = client.post(
        "/caregiver/push-tokens", headers=caregiver, json={"token": "dev-1", "platform": "android"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["platform"] == "android"

    # Re-register the SAME token -> idempotent upsert (one row, refreshed last_seen_at).
    resp2 = client.post(
        "/caregiver/push-tokens", headers=caregiver, json={"token": "dev-1", "platform": "android"}
    )
    assert resp2.status_code == 201
    # Exactly one row, no duplicate (the unique-token upsert updated in place).
    assert [r.token for r in token_repo._rows] == ["dev-1"]

    # Deregister — 204 and the row is gone.
    resp3 = client.request(
        "DELETE", "/caregiver/push-tokens", headers=caregiver, json={"token": "dev-1"}
    )
    assert resp3.status_code == 204
    assert token_repo._rows == []
    # Deregistering again is still 204 (idempotent).
    resp4 = client.request(
        "DELETE", "/caregiver/push-tokens", headers=caregiver, json={"token": "dev-1"}
    )
    assert resp4.status_code == 204

    # PHI-free audit: register + deregister events, platform only, no token in detail.
    events = caregiver_service.audit._events  # type: ignore[attr-defined]
    register_events = [e for e in events if e.action == "caregiver_push_token_register"]
    deregister_events = [e for e in events if e.action == "caregiver_push_token_deregister"]
    assert len(register_events) == 2
    assert register_events[0].detail == {"platform": "android"}
    assert len(deregister_events) == 2
    assert all("dev-1" not in json.dumps(e.detail) for e in events)


def test_push_token_endpoints_require_caregiver(client: TestClient) -> None:
    patient = _register_patient(client)
    # A patient principal is refused (CaregiverUserDep gate).
    assert (
        client.post(
            "/caregiver/push-tokens",
            headers=patient,
            json={"token": "dev-1", "platform": "android"},
        ).status_code
        == 403
    )
    assert (
        client.request(
            "DELETE", "/caregiver/push-tokens", headers=patient, json={"token": "dev-1"}
        ).status_code
        == 403
    )
