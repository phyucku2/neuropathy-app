"""EMR connection service — orchestrates the SMART flow end to end (ADR-0009).

Storage posture: connections live behind the injected `EmrConnectionRepository` and
pulled labs are persisted as research-grade Observations through the injected
`ObservationRepository` (in-memory defaults for unit tests and DB-less development;
Postgres in deployment). OAuth tokens live behind the `SecretStore` protocol and
pending auth states — which span the connect and callback requests — behind
`PendingAuthStore`; DB mode wires their Postgres implementations (encrypted-at-rest
vault + durable single-use state rows, ADR-0017) while in-memory mode keeps
process-level singletons. Swapping storage changes implementations, not this flow or
the API contract.
"""

from __future__ import annotations

import secrets as pysecrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.emr.client import EmrClient
from app.emr.providers import client_id_env_for
from app.emr.smart import (
    build_authorize_url,
    build_token_request,
    code_challenge_for,
    generate_code_verifier,
)
from app.emr.transport import HttpTransport
from app.ingestion.labs import lab_import_key, lab_result_to_observation
from app.models.audit import AuditEvent
from app.models.emr_connection import EmrConnectionStatus
from app.models.observation import DataOrigin
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.emr_connection import (
    ConnectionRecord,
    EmrConnectionRepository,
    InMemoryEmrConnectionRepository,
)
from app.repositories.observation import InMemoryObservationRepository, ObservationRepository
from app.repositories.pending_auth import (
    InMemoryPendingAuthStore,
    PendingAuth,
    PendingAuthStore,
    pending_auth_ttl,
)
from app.schemas.lab import LabResultIn

__all__ = [
    "UNCONFIGURED_CLIENT_ID",
    "ConnectionRecord",
    "EmrError",
    "EmrService",
    "InMemoryPendingAuthStore",
    "InMemorySecretStore",
    "PendingAuth",
    "PendingAuthStore",
    "SecretStore",
    "pending_auth_ttl",
]

# The DB-less-development placeholder deps.py wires when no SMART_CLIENT_ID is
# configured. `start_connect` refuses to build an authorize URL around it (fail
# early, review finding): redirecting the patient to the REAL EMR with this value
# only produces an opaque vendor-side invalid_client error the app never sees.
UNCONFIGURED_CLIENT_ID = "unconfigured-client"


class EmrError(Exception):
    """Flow error with an HTTP-ish reason the route layer maps to a response."""

    def __init__(self, reason: str, status_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


class SecretStore(Protocol):
    """Token vault contract: put secret material, get it back by opaque reference."""

    async def put(self, tokens: dict[str, str]) -> str:
        """Vault the tokens; returns the reference to store on the connection."""
        ...

    async def get(self, ref: str) -> dict[str, str] | None:
        """The vaulted tokens, or None when the ref is unknown (or undecryptable)."""
        ...

    async def delete(self, ref: str) -> None:
        """Remove the vaulted tokens for good; an unknown ref is a quiet no-op.

        Revocation and re-linking call this so secret material never outlives the
        grant it belongs to (ADR-0017): a revoked or superseded refresh token must
        not remain recoverable from a database dump plus the vault key.
        """
        ...


class InMemorySecretStore:
    """Dict-backed vault for unit tests, DB-less development, and DB mode without a
    configured SECRET_STORE_KEY (fail closed: never plaintext secrets in the DB)."""

    def __init__(self) -> None:
        self._secrets: dict[str, dict[str, str]] = {}

    async def put(self, tokens: dict[str, str]) -> str:
        ref = f"secret::{uuid.uuid4()}"
        self._secrets[ref] = tokens
        return ref

    async def get(self, ref: str) -> dict[str, str] | None:
        return self._secrets.get(ref)

    async def delete(self, ref: str) -> None:
        self._secrets.pop(ref, None)


@dataclass
class EmrService:
    transport: HttpTransport
    # Fallback SMART client id — used for custom fhir_base connections and any provider
    # without a configured per-vendor id.
    client_id: str
    redirect_uri: str
    # Vendor-issued client ids keyed by provider DISPLAY NAME (ADR-0028): each EMR issues
    # its own client_id, and the display name is exactly what a ConnectionRecord persists
    # (`provider_name`), so the SAME resolution works on both handshake hops — the
    # authorize URL at connect and the token exchange at callback — without a schema
    # change. Custom fhir_base connections have provider_name=None -> the fallback.
    # deps.py builds this from the registry + settings; tests inject dicts directly.
    provider_client_ids: Mapping[str, str] = field(default_factory=dict)
    secret_store: SecretStore = field(default_factory=InMemorySecretStore)
    connections: EmrConnectionRepository = field(default_factory=InMemoryEmrConnectionRepository)
    observations: ObservationRepository = field(default_factory=InMemoryObservationRepository)
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)
    _pending: PendingAuthStore = field(default_factory=InMemoryPendingAuthStore)

    def _client_id_for(self, provider_name: str | None) -> str:
        """The client id this connection's authorize URL AND token exchange must use.

        The two hops MUST resolve identically — an authorize URL built with the vendor
        id but a token request sent with the fallback would fail every exchange."""
        if provider_name is None:
            return self.client_id
        return self.provider_client_ids.get(provider_name, self.client_id)

    def _require_configured_client_id(self, provider_name: str | None) -> str:
        """The resolved client id — or a 422 EmrError when nothing real is configured.

        The vendor-env -> generic fallback order is preserved (a single-vendor pilot
        may legitimately run on the generic SMART_CLIENT_ID alone); ONLY landing on the
        DB-less-dev placeholder / an empty value fails, and it fails EARLY — at connect,
        with the exact env var to set — instead of redirecting the patient to the real
        EMR to hit an opaque vendor-side invalid_client error (review finding)."""
        client_id = self._client_id_for(provider_name)
        if client_id and client_id != UNCONFIGURED_CLIENT_ID:
            return client_id
        env = client_id_env_for(provider_name) if provider_name is not None else None
        if env is not None:
            detail = (
                "This provider isn't configured yet — the app operator must set "
                f"{env} (or the generic SMART_CLIENT_ID)"
            )
        else:
            detail = (
                "EMR connections aren't configured yet — the app operator must set SMART_CLIENT_ID"
            )
        raise EmrError(detail, status_code=422)

    async def start_connect(
        self, *, patient_id: uuid.UUID, fhir_base: str, provider_name: str | None
    ) -> tuple[ConnectionRecord, str, str]:
        """SMART discovery -> PKCE -> authorize URL. Returns (connection, url, state)."""
        # Fail BEFORE discovery and before persisting anything: an unconfigured client
        # id can never complete a handshake, so no record or pending state may be born.
        client_id = self._require_configured_client_id(provider_name)
        base = fhir_base.rstrip("/")
        config = await self.transport.get_json(f"{base}/.well-known/smart-configuration")
        authorization_endpoint = config.get("authorization_endpoint")
        token_endpoint = config.get("token_endpoint")
        if not authorization_endpoint or not token_endpoint:
            raise EmrError("EMR did not advertise SMART OAuth endpoints", status_code=502)

        record = ConnectionRecord(
            id=uuid.uuid4(), patient_id=patient_id, fhir_base=base, provider_name=provider_name
        )
        await self.connections.add(record)

        verifier = generate_code_verifier()
        state = pysecrets.token_urlsafe(32)
        await self._pending.put(
            state,
            PendingAuth(
                connection_id=record.id, code_verifier=verifier, token_endpoint=token_endpoint
            ),
            now=datetime.now(UTC),
        )
        url = build_authorize_url(
            authorization_endpoint=authorization_endpoint,
            client_id=client_id,
            redirect_uri=self.redirect_uri,
            fhir_base=base,
            state=state,
            code_challenge=code_challenge_for(verifier),
        )
        return record, url, state

    async def complete_callback(self, *, state: str, code: str) -> ConnectionRecord:
        """Validate state, exchange the code (PKCE), vault the tokens, activate.

        `consume` is atomic and single-use: expired states and replays — including
        two concurrent callbacks racing on the same state — answer the same 404.
        """
        pending = await self._pending.consume(state, now=datetime.now(UTC))
        if pending is None:
            raise EmrError("Unknown, expired, or already-used state", status_code=404)

        # The record comes FIRST: the token exchange must present the SAME client id the
        # authorize URL carried, and that id is resolved from the connection's provider
        # name (ADR-0028 per-provider client ids). Also avoids exchanging a code for a
        # connection that no longer exists.
        record = await self.connections.get(pending.connection_id)
        if record is None:
            raise EmrError("Connection not found", status_code=404)

        token_response: dict[str, Any] = await self.transport.post_form(
            pending.token_endpoint,
            build_token_request(
                client_id=self._client_id_for(record.provider_name),
                redirect_uri=self.redirect_uri,
                code=code,
                code_verifier=pending.code_verifier,
            ),
        )
        access_token = token_response.get("access_token")
        if not access_token:
            raise EmrError("EMR token exchange returned no access token", status_code=502)
        tokens = {"access_token": str(access_token)}
        if token_response.get("refresh_token"):
            tokens["refresh_token"] = str(token_response["refresh_token"])
        if record.token_ref is not None:
            # Re-linking replaces the vaulted tokens: delete the superseded secret
            # before storing the new one, or the old (still-working) refresh token
            # would sit orphaned in the vault forever (ADR-0017).
            await self.secret_store.delete(record.token_ref)
        record.token_ref = await self.secret_store.put(tokens)
        record.patient_fhir_id = (
            str(token_response["patient"]) if token_response.get("patient") else None
        )
        record.granted_scope = str(token_response["scope"]) if token_response.get("scope") else None
        if token_response.get("expires_in"):
            record.token_expires_at = datetime.now(UTC) + timedelta(
                seconds=int(token_response["expires_in"])
            )
        record.status = EmrConnectionStatus.active
        await self.connections.update(record)
        return record

    async def pull_labs(self, connection_id: uuid.UUID) -> tuple[list[LabResultIn], int, int]:
        """Fetch labs from the EMR and persist the ones not already imported.

        Returns (fetched results, newly persisted count, skipped count) — re-pulling never
        duplicates the analyzable dataset (import is idempotent per source record), and
        un-mappable EHR search-set entries are skipped rather than aborting the pull.
        """
        record = await self.get_connection(connection_id)
        if record.status is not EmrConnectionStatus.active:
            raise EmrError("Connection is not active", status_code=409)
        if record.token_ref is None or record.patient_fhir_id is None:
            raise EmrError("Connection is missing tokens or patient id", status_code=409)

        tokens = await self.secret_store.get(record.token_ref)
        if tokens is None:
            # A dangling reference: tokens vaulted in a process-local store before a
            # restart, or ciphertext an unconfigured/rotated SECRET_STORE_KEY can no
            # longer open. Tell the patient to re-link instead of a bare 500 (review
            # finding).
            raise EmrError(
                "EMR tokens are no longer available on this server; please reconnect your EMR",
                status_code=409,
            )
        client = EmrClient(record.fhir_base, self.transport)
        results, skipped = await client.fetch_lab_observations(
            patient_fhir_id=record.patient_fhir_id, access_token=tokens["access_token"]
        )
        imported = await self._persist_pulled_labs(record, results)
        return results, imported, skipped

    async def _persist_pulled_labs(
        self, record: ConnectionRecord, results: list[LabResultIn]
    ) -> int:
        """Persist pulled labs as research-grade Observations + one audit event.

        Idempotent: each result carries an import key (the source FHIR record id when
        the EMR provides one, else code+time+value); already-imported records are
        skipped so repeated pulls never duplicate the analyzable dataset.
        Provenance (data-standards.md): origin=ehr_imported, recorded by the system,
        source system named in quality. The PHI write is audit-logged (CLAUDE.md §5).
        """
        keys = [lab_import_key(result) for result in results]
        on_file = await self.observations.existing_import_keys(record.patient_id, keys)
        imported = 0
        seen: set[str] = set()
        for result, import_key in zip(results, keys, strict=True):
            if import_key in on_file or import_key in seen:
                continue
            seen.add(import_key)
            await self.observations.add(
                lab_result_to_observation(
                    result,
                    patient_id=record.patient_id,
                    origin=DataOrigin.ehr_imported,
                    recorded_by_role="system",
                    quality={"source_system": record.provider_name or record.fhir_base},
                    import_key=import_key,
                )
            )
            imported += 1
        await self.audit.add(
            AuditEvent(
                actor_id=None,
                actor_role="system",
                action="import_labs",
                patient_id=record.patient_id,
                # References only, never PHI values (audit model contract).
                detail={
                    "connection_id": str(record.id),
                    "fetched": len(results),
                    "imported": imported,
                },
            )
        )
        return imported

    async def revoke(self, connection_id: uuid.UUID) -> ConnectionRecord:
        """Revoke the connection AND delete its vaulted tokens (ADR-0017).

        Flipping the status alone would leave the encrypted access+refresh tokens in
        the durable vault forever — a patient who revokes must not stay one DB dump +
        key away from a working refresh token. Idempotent: re-revoking finds no ref.
        """
        record = await self.get_connection(connection_id)
        record.status = EmrConnectionStatus.revoked
        record.revoked_at = datetime.now(UTC)
        if record.token_ref is not None:
            await self.secret_store.delete(record.token_ref)
            record.token_ref = None
        await self.connections.update(record)
        return record

    async def get_connection(self, connection_id: uuid.UUID) -> ConnectionRecord:
        record = await self.connections.get(connection_id)
        if record is None:
            raise EmrError("Connection not found", status_code=404)
        return record
