"""Caregiver push — the FCM HTTP v1 sender + the PHI-free push seam (ADR-0047 Phase B2).

B1 established the seam: a ``PushSender`` Protocol, an ``InMemoryPushSender`` that
captures sends, and a NO-OP ``FcmPushSender`` stub. B2 lands the REAL sender.

``FcmPushSender`` mints an OAuth2 access token from a Firebase service-account
credential (google-auth, signed LOCALLY — no network to sign) and POSTs one message per
device token to the FCM HTTP v1 endpoint over an INJECTED async HTTP transport
(``httpx.AsyncClient`` in prod, a fake in tests). Nothing here ever touches the real
network in a unit test: the transport is the single seam, and the credential in tests is
a SYNTHETIC throwaway keypair — never a real key.

PHI-FREE BY CONTRACT: ``PushMessage`` carries only identifiers + fixed template text —
never a patient name, a value, a code label, or note text. The FCM body is built ONLY
from those fields (``data`` = alert_id/alert_type identifiers; ``notification`` = the
fixed ``ALERT_TEMPLATES`` title/body), so there is structurally no field to leak PHI
into. Error logging is PHI-free too (status + project ref only, never a token or body).

Response handling per device token (ADR-0047 B2):

- ``200`` → delivered.
- ``404`` / ``UNREGISTERED`` / ``INVALID_ARGUMENT`` naming the token field → the device
  token is DEAD; the fan-out prunes it from the store.
- ``401`` / ``403`` → a credential/permission fault: PHI-free error log, the cached
  access token is dropped so the next send re-mints, NO token is deleted, no crash.
- ``429`` / ``5xx`` / any transport error → transient: swallowed, no token side effects,
  never breaks the caregiver feed read.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol

import httpx
from google.auth import jwt as google_jwt
from google.oauth2 import service_account

_log = logging.getLogger(__name__)

# The single OAuth scope FCM v1 sends require.
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
# The FCM HTTP v1 send endpoint (project id is interpolated per credential).
FCM_ENDPOINT = "https://fcm.googleapis.com"
# The Google OAuth2 token endpoint used when a credential omits ``token_uri``.
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
# Access-token lifetime we request, and the safety margin we refresh before (seconds).
_TOKEN_LIFETIME_SECONDS = 3600
_TOKEN_REFRESH_MARGIN_SECONDS = 60
# The JWT-bearer grant used to exchange the signed assertion for an access token.
_JWT_BEARER_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"


@dataclass(frozen=True)
class PushMessage:
    """A caregiver push notification — PHI-FREE by contract (ADR-0047).

    Identifiers + fixed non-diagnostic template text ONLY. There is deliberately no
    field for a patient name, an observation value, a code display, or note text — the
    structural absence is the guarantee (proven by tests scanning the shape)."""

    caregiver_user_id: uuid.UUID
    alert_type: str  # a CaregiverAlertType value — a reference, never a value
    alert_id: uuid.UUID
    title: str  # a fixed non-diagnostic template constant (ALERT_TEMPLATES)
    body: str  # a fixed non-urgent template constant (ALERT_TEMPLATES)


class PushSender(Protocol):
    """Where a caregiver push goes when a new alert is persisted (the B1 seam)."""

    async def send(self, message: PushMessage) -> None: ...


class InMemoryPushSender:
    """List-backed sender for unit tests and DB-less development — captures every send
    so tests can assert the push seam fired with a PHI-free payload."""

    def __init__(self) -> None:
        self.sent: list[PushMessage] = []

    async def send(self, message: PushMessage) -> None:
        self.sent.append(message)


class TokenSendOutcome(Enum):
    """The result of one FCM send to one device token (drives the fan-out's pruning)."""

    delivered = "delivered"  # 200 — accepted by FCM
    unregistered = "unregistered"  # dead token (404 / UNREGISTERED / token INVALID_ARGUMENT)
    auth_error = "auth_error"  # 401/403 — credential/permission fault, NOT a dead token
    transient = "transient"  # 429/5xx/transport error — swallow, no side effects


@dataclass(frozen=True)
class FcmHttpResponse:
    """A minimal HTTP response the push transport returns — status + parsed JSON body."""

    status_code: int
    body: dict[str, Any] = field(default_factory=dict)


class AsyncHttpTransport(Protocol):
    """The one seam real network I/O crosses (mirrors ``emr/transport.py``). Prod wraps an
    ``httpx.AsyncClient``; tests inject a fake capturing calls and returning canned rows."""

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> FcmHttpResponse: ...


class HttpxPushTransport:
    """Production push transport. Never logs URLs, tokens, or response bodies."""

    def __init__(self, client: httpx.AsyncClient | None = None, timeout_s: float = 20.0) -> None:
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> FcmHttpResponse:
        response = await self._client.post(url, headers=headers, data=data, json=json)
        try:
            parsed: dict[str, Any] = response.json()
        except ValueError:
            parsed = {}
        return FcmHttpResponse(status_code=response.status_code, body=parsed)


class TokenPushSender(Protocol):
    """A sender that delivers ONE ``PushMessage`` to ONE device token (the fan-out uses
    the outcome to prune dead tokens). ``FcmPushSender`` is the prod implementation; a
    fake satisfies it in tests."""

    async def send_to_token(self, message: PushMessage, token: str) -> TokenSendOutcome: ...


class FcmCredentialsError(ValueError):
    """A service-account credential could not be parsed/loaded (fail-safe: deps logs
    PHI-free and selects the no-op path; the push sender is never constructed)."""


def _extract_fcm_error(body: dict[str, Any]) -> tuple[str, bool]:
    """Return ``(fcm_error_code, names_token_field)`` from an FCM v1 error body.

    ``fcm_error_code`` is the ``FcmError.errorCode`` (e.g. ``UNREGISTERED``,
    ``INVALID_ARGUMENT``) or the top-level ``status`` when no detail carries it.
    ``names_token_field`` is True when a ``BadRequest.fieldViolations`` entry names the
    ``message.token`` field — the precise "the token is malformed/dead" signal, so a
    generic INVALID_ARGUMENT (our own payload bug) is NOT mistaken for a dead token."""
    error = body.get("error")
    if not isinstance(error, dict):
        return "", False
    code = ""
    status = error.get("status")
    if isinstance(status, str):
        code = status
    names_token = False
    details = error.get("details")
    if isinstance(details, list):
        for detail in details:
            if not isinstance(detail, dict):
                continue
            error_code = detail.get("errorCode")
            if isinstance(error_code, str):
                code = error_code
            violations = detail.get("fieldViolations")
            if isinstance(violations, list):
                for violation in violations:
                    if (
                        isinstance(violation, dict)
                        and "token" in str(violation.get("field", "")).lower()
                    ):
                        names_token = True
    return code, names_token


class FcmPushSender:
    """Real FCM HTTP v1 sender (ADR-0047 B2) — OAuth2 mint + one POST per device token.

    Fully offline-testable: the credential is signed locally (no network) and every HTTP
    call crosses the injected ``AsyncHttpTransport``. Holds a one-per-process cached
    access token, re-minted only when it nears expiry, so a feed fan-out to many tokens
    mints at most once."""

    def __init__(
        self,
        *,
        transport: AsyncHttpTransport,
        service_account_info: dict[str, Any],
        clock: Any = None,
    ) -> None:
        try:
            self._credentials = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=[FCM_SCOPE]
            )
            self._project_id = str(service_account_info["project_id"])
            self._client_email = str(service_account_info["client_email"])
        except (KeyError, ValueError, TypeError) as exc:
            raise FcmCredentialsError("invalid FCM service-account credential") from exc
        self._token_uri = str(service_account_info.get("token_uri") or DEFAULT_TOKEN_URI)
        self._transport = transport
        self._clock = clock or (lambda: datetime.now(UTC))
        self._cached_token: str | None = None
        self._token_expiry: datetime | None = None

    async def _access_token(self) -> str:
        """The cached access token, minting a fresh one when absent or near expiry.

        Signs the JWT grant assertion LOCALLY with the credential's signer (no network),
        then exchanges it over the injected transport. Raises on an unexpected token
        response so ``send_to_token`` classifies it as a transient failure and swallows."""
        now = self._clock()
        if (
            self._cached_token is not None
            and self._token_expiry is not None
            and now < self._token_expiry
        ):
            return self._cached_token
        issued_at = int(now.timestamp())
        assertion = google_jwt.encode(
            self._credentials.signer,
            {
                "iss": self._client_email,
                "scope": FCM_SCOPE,
                "aud": self._token_uri,
                "iat": issued_at,
                "exp": issued_at + _TOKEN_LIFETIME_SECONDS,
            },
        )
        if isinstance(assertion, bytes):
            assertion = assertion.decode("ascii")
        response = await self._transport.post(
            self._token_uri,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": _JWT_BEARER_GRANT, "assertion": assertion},
        )
        token = response.body.get("access_token")
        if response.status_code != 200 or not isinstance(token, str):
            raise FcmCredentialsError("FCM token exchange did not return an access token")
        expires_in = response.body.get("expires_in", _TOKEN_LIFETIME_SECONDS)
        try:
            lifetime = int(expires_in)
        except (TypeError, ValueError):
            lifetime = _TOKEN_LIFETIME_SECONDS
        self._cached_token = token
        self._token_expiry = now + timedelta(
            seconds=max(0, lifetime - _TOKEN_REFRESH_MARGIN_SECONDS)
        )
        return token

    async def send_to_token(self, message: PushMessage, token: str) -> TokenSendOutcome:
        """Deliver one PHI-free message to one device token; classify the result.

        Never raises: a mint/transport failure is swallowed as ``transient`` so a broken
        credential or a network blip can never break the caregiver feed read that
        scheduled this send."""
        try:
            access_token = await self._access_token()
        except Exception:
            # PHI-free: project ref only, never the credential, token, or message body.
            _log.warning("fcm token mint failed (transient); project=%s", self._project_id)
            return TokenSendOutcome.transient

        url = f"{FCM_ENDPOINT}/v1/projects/{self._project_id}/messages:send"
        payload = {
            "message": {
                "token": token,
                # Identifiers ONLY — a reference to the alert, never a value.
                "data": {"alert_id": str(message.alert_id), "alert_type": message.alert_type},
                # Fixed template copy from ALERT_TEMPLATES — never a name/value/note.
                "notification": {"title": message.title, "body": message.body},
            }
        }
        try:
            response = await self._transport.post(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except Exception:
            _log.warning(
                "fcm send failed (transient transport error); project=%s", self._project_id
            )
            return TokenSendOutcome.transient

        return self._classify(response)

    def _classify(self, response: FcmHttpResponse) -> TokenSendOutcome:
        if response.status_code == 200:
            return TokenSendOutcome.delivered
        error_code, names_token = _extract_fcm_error(response.body)
        if (
            response.status_code == 404
            or error_code == "UNREGISTERED"
            or (error_code == "INVALID_ARGUMENT" and names_token)
        ):
            return TokenSendOutcome.unregistered
        if response.status_code in (401, 403):
            # A credential/permission fault — drop the cached token so the next send
            # re-mints, log PHI-free, and delete NO token (this is not the token's fault).
            self._cached_token = None
            self._token_expiry = None
            _log.error(
                "fcm send rejected (auth); status=%s project=%s",
                response.status_code,
                self._project_id,
            )
            return TokenSendOutcome.auth_error
        # 429 / 5xx / anything else — transient; swallow with no token side effects.
        return TokenSendOutcome.transient
