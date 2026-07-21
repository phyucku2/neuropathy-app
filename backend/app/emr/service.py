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
from app.emr.notes_client import EmrClinicalNoteClient
from app.emr.providers import client_id_env_for
from app.emr.signals import (
    InMemoryNewChartNoteSink,
    NewChartNoteSignal,
    NewChartNoteSink,
)
from app.emr.smart import (
    NOTE_READ_SCOPE,
    build_authorize_url,
    build_token_request,
    code_challenge_for,
    generate_code_verifier,
)
from app.emr.transport import HttpTransport
from app.ingestion.labs import lab_import_key, lab_result_to_observation
from app.models.audit import AuditEvent
from app.models.emr_clinical_note import EmrClinicalNote
from app.models.emr_connection import EmrConnectionStatus
from app.models.observation import DataOrigin
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.emr_clinical_note import (
    EmrClinicalNoteRepository,
    InMemoryEmrClinicalNoteRepository,
)
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
from app.schemas.emr import ClinicalNoteIn
from app.schemas.lab import LabResultIn

# The clinical-note read scopes that authorize a DocumentReference pull (ADR-0045 P2 #27):
# the opt-in `.rs` scope this build requests, plus the plain `.read` some EHRs grant.
_NOTE_READ_SCOPES = frozenset({NOTE_READ_SCOPE, "patient/DocumentReference.read"})

# Safety overlap subtracted from the note-pull watermark. The watermark is derived from
# the newest FETCHED note's authoring date (never the app clock — app-vs-EHR clock skew
# would otherwise permanently skip notes), and a clinician can sign a note days after
# the encounter with `DocumentReference.date` backdated to it. Re-fetching the overlap
# window is free: the idempotent import absorbs already-imported notes as skips.
NOTES_WATERMARK_OVERLAP = timedelta(days=7)

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
    # Clinical notes are a SEPARATE append-only store (NOT observations) — pulled via
    # DocumentReference, metadata only (ADR-0045 P2 #27).
    clinical_notes: EmrClinicalNoteRepository = field(
        default_factory=InMemoryEmrClinicalNoteRepository
    )
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)
    # New-chart-note signal fan-out (existence only) — the caregiver consumer is out of
    # scope (ADR-0047); the default in-memory sink just records emitted signals.
    note_signals: NewChartNoteSink = field(default_factory=InMemoryNewChartNoteSink)
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
        self,
        *,
        patient_id: uuid.UUID,
        fhir_base: str,
        provider_name: str | None,
        include_notes: bool = False,
    ) -> tuple[ConnectionRecord, str, str]:
        """SMART discovery -> PKCE -> authorize URL. Returns (connection, url, state).

        `include_notes` (ADR-0045 P2 #27) opts this connection into requesting the
        clinical-note (DocumentReference) read scope on the EHR consent screen."""
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
            include_note_scope=include_notes,
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
            # add_if_absent, not add: the on_file probe above narrows the common case, but a
            # concurrent pull of the same connection can commit between that probe and this
            # write — the DB partial-unique index makes the duplicate impossible and this
            # returns False rather than raising, so the race skips instead of 500ing (#3).
            inserted = await self.observations.add_if_absent(
                lab_result_to_observation(
                    result,
                    patient_id=record.patient_id,
                    origin=DataOrigin.ehr_imported,
                    recorded_by_role="system",
                    quality={"source_system": record.provider_name or record.fhir_base},
                    import_key=import_key,
                )
            )
            if inserted:
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

    async def pull_clinical_notes(self, connection_id: uuid.UUID) -> tuple[int, int, int]:
        """Fetch clinical-note metadata from the EMR and persist the notes not already
        imported (ADR-0045 P2 #27).

        Returns ``(fetched, newly persisted, skipped)``. Metadata-eager, body-lazy: only
        the note's existence + metadata is written; the body is never fetched here. Import
        is idempotent per source note, so a re-pull persists 0 and re-alerts nothing. The
        watermark (``last_notes_pulled_at``) is max(fetched ``authored_at``) minus a
        safety overlap — never the app clock — and advances only after a successful
        persist, so a mid-pull failure re-fetches the same window next time.
        """
        record = await self.get_connection(connection_id)
        if record.status is not EmrConnectionStatus.active:
            raise EmrError("Connection is not active", status_code=409)
        if record.token_ref is None or record.patient_fhir_id is None:
            raise EmrError("Connection is missing tokens or patient id", status_code=409)
        # Scope guard BEFORE any EHR call: a connection that never opted into note read must
        # not have a DocumentReference request sent on its behalf — the patient must
        # reconnect and allow notes (mirrors the dangling-ref reconnect posture).
        if not (_granted_scopes(record.granted_scope) & _NOTE_READ_SCOPES):
            raise EmrError(
                "This connection isn't authorized to read clinical notes; "
                "please reconnect your EMR and allow clinical notes",
                status_code=409,
            )
        tokens = await self.secret_store.get(record.token_ref)
        if tokens is None:
            # A dangling reference (tokens vaulted in a process-local store before a restart,
            # or ciphertext a rotated/unconfigured key can no longer open). Ask to re-link.
            raise EmrError(
                "EMR tokens are no longer available on this server; please reconnect your EMR",
                status_code=409,
            )
        client = EmrClinicalNoteClient(record.fhir_base, self.transport)
        notes, skipped = await client.fetch_clinical_notes(
            patient_fhir_id=record.patient_fhir_id,
            access_token=tokens["access_token"],
            watermark=record.last_notes_pulled_at,
        )
        imported = await self._persist_pulled_notes(record, notes)
        # Advance the watermark only AFTER a successful persist, so a mid-pull failure
        # re-fetches the same window next time rather than silently dropping notes. The
        # watermark is derived from the FETCHED notes' authoring dates minus an overlap
        # (never datetime.now: a late-signed/backdated note or app-vs-EHR clock skew
        # would fall permanently below an app-clock watermark). A pull that fetched
        # nothing learned nothing new — the existing bound stays. The write is a
        # TARGETED single-field update: this method's `record` snapshot can be minutes
        # stale after the EHR fetch, and writing the whole record back could resurrect
        # a concurrently revoked connection.
        if notes:
            watermark = max(note.authored_at for note in notes) - NOTES_WATERMARK_OVERLAP
            await self.connections.set_last_notes_pulled_at(record.id, watermark)
        return len(notes), imported, skipped

    async def _persist_pulled_notes(
        self, record: ConnectionRecord, notes: list[ClinicalNoteIn]
    ) -> int:
        """Persist pulled note METADATA as append-only rows + one audit event + one signal
        per newly-persisted note (existence only).

        Idempotent: each note carries a source-scoped import key (its DocumentReference id
        when provided, else type+time+author, always prefixed with the connection's
        ``fhir_base``); already-imported notes are skipped so repeated pulls never
        duplicate the store OR re-alert. The audit detail and the signal carry
        counts/references only — NEVER note text (CLAUDE.md).
        """
        keys = [_note_import_key(note, fhir_base=record.fhir_base) for note in notes]
        on_file = await self.clinical_notes.existing_import_keys(record.patient_id, keys)
        inserted_rows: list[tuple[ClinicalNoteIn, EmrClinicalNote]] = []
        seen: set[str] = set()
        for note, import_key in zip(notes, keys, strict=True):
            if import_key in on_file or import_key in seen:
                continue
            seen.add(import_key)
            row = _clinical_note_to_model(note, record=record, import_key=import_key)
            # add_if_absent, not add: the on_file probe narrows the common case, but a
            # concurrent pull can commit between it and this write — the DB partial-unique
            # index makes the duplicate impossible and this returns False rather than raising.
            if await self.clinical_notes.add_if_absent(row):
                inserted_rows.append((note, row))
        imported = len(inserted_rows)
        await self.audit.add(
            AuditEvent(
                actor_id=None,
                actor_role="system",
                action="import_clinical_notes",
                patient_id=record.patient_id,
                # References/counts only, never note text (audit model contract).
                detail={
                    "connection_id": str(record.id),
                    "fetched": len(notes),
                    "imported": imported,
                },
            )
        )
        # Signal ONLY for real inserts (idempotent, no re-alert), and only AFTER the whole
        # batch + audit event persisted: emitting inside the loop would hand a real fan-out
        # sink (push/queue) phantom alerts for rows a later failure rolls back. Existence +
        # metadata only — no body, no interpretation (ADR-0047 caregiver alert's data
        # source). Residual: emission still precedes the request-level COMMIT (a true
        # post-commit/outbox hook is out of scope this wave), so the signal is keyed on the
        # stable import_key — a consumer dedupes re-emissions after a commit-time rollback.
        for note, row in inserted_rows:
            assert row.import_key is not None  # set by _clinical_note_to_model above
            await self.note_signals.emit(
                NewChartNoteSignal(
                    patient_id=record.patient_id,
                    connection_id=record.id,
                    note_id=row.id,
                    import_key=row.import_key,
                    type_display=note.type_display,
                    author_display=note.author_display,
                    authored_at=note.authored_at,
                    encounter_fhir_id=note.encounter_fhir_id,
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


def _granted_scopes(scope: str | None) -> set[str]:
    """The space-separated granted scopes as a set (empty when None)."""
    return set(scope.split()) if scope else set()


def _note_import_key(note: ClinicalNoteIn, *, fhir_base: str) -> str:
    """Stable idempotency key for one clinical note, SCOPED to its source system.

    Key format: ``{fhir_base}|docref:{id}`` when the EMR provides a DocumentReference id,
    else ``{fhir_base}|note:{type}:{time}:{author}``. FHIR resource ids are unique only
    within one server, so an unscoped key would let two different EHRs' notes that share
    an id (common with sequential-id servers) collide on (patient_id, import_key) — the
    second note silently dropped. Prefixing the connection's ``fhir_base`` (stable across
    re-links, unlike connection_id) makes the key globally unique per source while a
    re-pull of the same note from the same EHR still dedupes (mirrors lab_import_key).
    Pre-existing rows keyed without the prefix are not migrated (synthetic data only).
    """
    if note.document_fhir_id:
        return f"{fhir_base}|docref:{note.document_fhir_id}"
    return f"{fhir_base}|note:{note.type_code}:{note.authored_at.isoformat()}:{note.author_display}"


def _clinical_note_to_model(
    note: ClinicalNoteIn, *, record: ConnectionRecord, import_key: str
) -> EmrClinicalNote:
    """Map parsed note metadata to its append-only row. Metadata + references only; the
    body is never a field here (fetched lazily on demand)."""
    return EmrClinicalNote(
        patient_id=record.patient_id,
        connection_id=record.id,
        origin=DataOrigin.ehr_imported,
        source_system=record.provider_name or record.fhir_base,
        document_fhir_id=note.document_fhir_id,
        type_code=note.type_code,
        type_display=note.type_display,
        category="clinical-note",
        authored_at=note.authored_at,
        author_display=note.author_display,
        encounter_fhir_id=note.encounter_fhir_id,
        content_type=note.content_type,
        attachment_url=note.attachment_url,
        has_inline_data=note.has_inline_data,
        import_key=import_key,
    )
