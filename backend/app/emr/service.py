"""EMR connection service — orchestrates the SMART flow end to end (ADR-0009).

Storage posture: connections and pending auth states live behind in-memory stores with
the same shapes as the DB models; OAuth tokens live in a SecretStore (in-memory now,
secret manager later). Swapping storage changes implementations, not this flow or the
API contract. Our own endpoint auth is a placeholder until the app-auth ADR lands.
"""

from __future__ import annotations

import secrets as pysecrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.emr.client import EmrClient
from app.emr.smart import (
    build_authorize_url,
    build_token_request,
    code_challenge_for,
    generate_code_verifier,
)
from app.emr.transport import HttpTransport
from app.models.emr_connection import EmrConnectionStatus
from app.schemas.lab import LabResultIn


class EmrError(Exception):
    """Flow error with an HTTP-ish reason the route layer maps to a response."""

    def __init__(self, reason: str, status_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


@dataclass
class ConnectionRecord:
    """In-memory twin of models.EmrConnection (same fields the DB row will hold)."""

    id: uuid.UUID
    patient_id: uuid.UUID
    fhir_base: str
    provider_name: str | None
    status: EmrConnectionStatus = EmrConnectionStatus.authorizing
    granted_scope: str | None = None
    patient_fhir_id: str | None = None
    token_ref: str | None = None
    token_expires_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass
class _PendingAuth:
    connection_id: uuid.UUID
    code_verifier: str
    token_endpoint: str


class InMemorySecretStore:
    """Token vault stand-in: same put/get contract the secret manager adapter will have."""

    def __init__(self) -> None:
        self._secrets: dict[str, dict[str, str]] = {}

    def put(self, tokens: dict[str, str]) -> str:
        ref = f"secret::{uuid.uuid4()}"
        self._secrets[ref] = tokens
        return ref

    def get(self, ref: str) -> dict[str, str]:
        return self._secrets[ref]


@dataclass
class EmrService:
    transport: HttpTransport
    client_id: str
    redirect_uri: str
    secret_store: InMemorySecretStore = field(default_factory=InMemorySecretStore)
    _connections: dict[uuid.UUID, ConnectionRecord] = field(default_factory=dict)
    _pending: dict[str, _PendingAuth] = field(default_factory=dict)

    async def start_connect(
        self, *, patient_id: uuid.UUID, fhir_base: str, provider_name: str | None
    ) -> tuple[ConnectionRecord, str, str]:
        """SMART discovery -> PKCE -> authorize URL. Returns (connection, url, state)."""
        base = fhir_base.rstrip("/")
        config = await self.transport.get_json(f"{base}/.well-known/smart-configuration")
        authorization_endpoint = config.get("authorization_endpoint")
        token_endpoint = config.get("token_endpoint")
        if not authorization_endpoint or not token_endpoint:
            raise EmrError("EMR did not advertise SMART OAuth endpoints", status_code=502)

        record = ConnectionRecord(
            id=uuid.uuid4(), patient_id=patient_id, fhir_base=base, provider_name=provider_name
        )
        self._connections[record.id] = record

        verifier = generate_code_verifier()
        state = pysecrets.token_urlsafe(32)
        self._pending[state] = _PendingAuth(
            connection_id=record.id, code_verifier=verifier, token_endpoint=token_endpoint
        )
        url = build_authorize_url(
            authorization_endpoint=authorization_endpoint,
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            fhir_base=base,
            state=state,
            code_challenge=code_challenge_for(verifier),
        )
        return record, url, state

    async def complete_callback(self, *, state: str, code: str) -> ConnectionRecord:
        """Validate state, exchange the code (PKCE), vault the tokens, activate."""
        pending = self._pending.pop(state, None)
        if pending is None:
            raise EmrError("Unknown or already-used state", status_code=404)

        token_response: dict[str, Any] = await self.transport.post_form(
            pending.token_endpoint,
            build_token_request(
                client_id=self.client_id,
                redirect_uri=self.redirect_uri,
                code=code,
                code_verifier=pending.code_verifier,
            ),
        )
        access_token = token_response.get("access_token")
        if not access_token:
            raise EmrError("EMR token exchange returned no access token", status_code=502)

        record = self._connections[pending.connection_id]
        tokens = {"access_token": str(access_token)}
        if token_response.get("refresh_token"):
            tokens["refresh_token"] = str(token_response["refresh_token"])
        record.token_ref = self.secret_store.put(tokens)
        record.patient_fhir_id = (
            str(token_response["patient"]) if token_response.get("patient") else None
        )
        record.granted_scope = str(token_response["scope"]) if token_response.get("scope") else None
        if token_response.get("expires_in"):
            record.token_expires_at = datetime.now(UTC) + timedelta(
                seconds=int(token_response["expires_in"])
            )
        record.status = EmrConnectionStatus.active
        return record

    async def pull_labs(self, connection_id: uuid.UUID) -> list[LabResultIn]:
        record = self.get_connection(connection_id)
        if record.status is not EmrConnectionStatus.active:
            raise EmrError("Connection is not active", status_code=409)
        if record.token_ref is None or record.patient_fhir_id is None:
            raise EmrError("Connection is missing tokens or patient id", status_code=409)

        tokens = self.secret_store.get(record.token_ref)
        client = EmrClient(record.fhir_base, self.transport)
        return await client.fetch_lab_observations(
            patient_fhir_id=record.patient_fhir_id, access_token=tokens["access_token"]
        )

    def revoke(self, connection_id: uuid.UUID) -> ConnectionRecord:
        record = self.get_connection(connection_id)
        record.status = EmrConnectionStatus.revoked
        record.revoked_at = datetime.now(UTC)
        return record

    def get_connection(self, connection_id: uuid.UUID) -> ConnectionRecord:
        record = self._connections.get(connection_id)
        if record is None:
            raise EmrError("Connection not found", status_code=404)
        return record
