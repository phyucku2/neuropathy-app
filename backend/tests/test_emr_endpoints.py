"""End-to-end tests for the EMR endpoints (ADR-0009): providers -> connect -> callback
-> pull -> revoke, against a fake EMR (no network).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, get_current_user
from app.api.routes.emr import get_emr_service
from app.emr.service import UNCONFIGURED_CLIENT_ID, EmrService
from app.main import app
from app.models.user import UserRole

FHIR_BASE = "https://ehr.example/fhir"

USER_A = CurrentUser(
    user_id=uuid4(),
    role=UserRole.patient,
    patient_id=uuid4(),
    email="a@example.test",
    display_name="Patient A",
)
USER_B = CurrentUser(
    user_id=uuid4(),
    role=UserRole.patient,
    patient_id=uuid4(),
    email="b@example.test",
    display_name="Patient B",
)


def _sign_in_as(user: CurrentUser) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


class FakeEmr:
    """Plays the EMR: SMART discovery, token endpoint, and Observation search."""

    def __init__(self) -> None:
        self.token_requests: list[dict[str, str]] = []
        self.discovery_calls = 0

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        if url.endswith("/.well-known/smart-configuration"):
            self.discovery_calls += 1
            return {
                "authorization_endpoint": "https://ehr.example/oauth/authorize",
                "token_endpoint": "https://ehr.example/oauth/token",
            }
        assert url.startswith(f"{FHIR_BASE}/Observation")
        assert access_token == "the-access-token"
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4"}]},
                        "effectiveDateTime": "2026-06-15T08:30:00+00:00",
                        "valueQuantity": {
                            "value": 7.2,
                            "unit": "%",
                            "system": "http://unitsofmeasure.org",
                            "code": "%",
                        },
                    }
                }
            ],
        }

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        assert url == "https://ehr.example/oauth/token"
        self.token_requests.append(data)
        return {
            "access_token": "the-access-token",
            "refresh_token": "the-refresh-token",
            "patient": "fhir-patient-9",
            "scope": "patient/Observation.read",
            "expires_in": 3600,
        }


class NotesEmr(FakeEmr):
    """A FakeEmr that ALSO grants the clinical-note scope and answers DocumentReference +
    Binary (ADR-0045 P2 #27). Records the DocumentReference search URLs so the watermark
    (date=ge on the 2nd pull) can be asserted."""

    def __init__(self) -> None:
        super().__init__()
        self.note_search_urls: list[str] = []
        self.binary_calls: list[str] = []

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        if url.endswith("/.well-known/smart-configuration"):
            return await super().get_json(url, access_token=access_token)
        if url.startswith(f"{FHIR_BASE}/DocumentReference"):
            assert access_token == "the-access-token"
            self.note_search_urls.append(url)
            return {
                "resourceType": "Bundle",
                "type": "searchset",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "DocumentReference",
                            "id": "docref-1",
                            "type": {
                                "coding": [
                                    {
                                        "system": "http://loinc.org",
                                        "code": "11506-3",
                                        "display": "Progress note",
                                    }
                                ]
                            },
                            "date": "2026-06-15T08:30:00+00:00",
                            "author": [{"display": "Dr Synthetic"}],
                            "context": {"encounter": [{"reference": "Encounter/enc-1"}]},
                            "content": [
                                {
                                    "attachment": {
                                        "contentType": "text/plain",
                                        # A body URL AND inline data with SECRET note text
                                        # that must NEVER surface in the summary/audit/signal.
                                        "url": f"{FHIR_BASE}/Binary/bin-1",
                                        "data": "U0VDUkVULU5PVEUtQk9EWQ==",  # "SECRET-NOTE-BODY"
                                    }
                                }
                            ],
                        }
                    }
                ],
            }
        if url.startswith(f"{FHIR_BASE}/Binary"):
            assert access_token == "the-access-token"
            self.binary_calls.append(url)
            return {"resourceType": "Binary", "contentType": "text/plain", "data": "U0VDUkVU"}
        return await super().get_json(url, access_token=access_token)

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        response = await super().post_form(url, data)
        # Grant BOTH labs and clinical-note read for a notes-capable connection.
        response["scope"] = "patient/Observation.read patient/DocumentReference.rs"
        return response


async def _enable_ingest_notes() -> None:
    """Turn ingest_notes ON for BOTH test patients (it is opt-in/off by default) and
    override the capability service so the pull-notes gate passes — enabling USER_B too so
    the cross-user test reaches the ownership 404 rather than the toggle 409."""
    from datetime import UTC, datetime

    from app.api.deps import get_capability_service
    from app.services.capability import CapabilityService

    capability_service = CapabilityService()
    for user in (USER_A, USER_B):
        assert user.patient_id is not None
        await capability_service.set_for_patient(
            patient_id=user.patient_id,
            actor_id=user.user_id,
            key="ingest_notes",
            active=True,
            now=datetime.now(UTC),
        )
    app.dependency_overrides[get_capability_service] = lambda: capability_service


@pytest.fixture()
def client() -> TestClient:
    service = EmrService(
        transport=FakeEmr(), client_id="test-client", redirect_uri="https://app.test/emr/callback"
    )
    app.dependency_overrides[get_emr_service] = lambda: service
    _sign_in_as(USER_A)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _connect(client: TestClient) -> tuple[str, str]:
    resp = client.post("/emr/connect", json={"fhir_base": FHIR_BASE})
    assert resp.status_code == 200
    body = resp.json()
    return body["connection_id"], body["state"]


def test_providers_endpoint_lists_and_searches() -> None:
    with TestClient(app) as anon:
        all_providers = anon.get("/emr/providers").json()
        assert any(p["key"] == "epic" for p in all_providers)
        only_epic = anon.get("/emr/providers", params={"q": "mychart"}).json()
        assert [p["key"] for p in only_epic] == ["epic"]


def test_connect_returns_pkce_authorize_url(client: TestClient) -> None:
    _, state = _connect(client)
    resp = client.post("/emr/connect", json={"fhir_base": FHIR_BASE})
    q = parse_qs(urlparse(resp.json()["authorize_url"]).query)
    assert q["code_challenge_method"] == ["S256"]
    assert q["aud"] == [FHIR_BASE]
    assert q["client_id"] == ["test-client"]
    assert state  # returned so the app can correlate the callback


def test_full_flow_connect_callback_pull(client: TestClient) -> None:
    connection_id, state = _connect(client)

    cb = client.get("/emr/callback", params={"state": state, "code": "auth-code"})
    assert cb.status_code == 200
    body = cb.json()
    assert body["status"] == "active"
    assert body["patient_fhir_id"] == "fhir-patient-9"
    assert "token" not in cb.text.lower().replace("token_expires_at", "")  # no token leaks

    pull = client.post(f"/emr/connections/{connection_id}/pull")
    assert pull.status_code == 200
    assert pull.json()["imported"] == 1
    assert pull.json()["results"][0]["loinc_code"] == "4548-4"


def test_callback_with_unknown_state_is_404(client: TestClient) -> None:
    resp = client.get("/emr/callback", params={"state": "forged", "code": "x"})
    assert resp.status_code == 404


def test_state_is_single_use(client: TestClient) -> None:
    _, state = _connect(client)
    assert client.get("/emr/callback", params={"state": state, "code": "c"}).status_code == 200
    # Replaying the same state must fail (CSRF/replay protection).
    assert client.get("/emr/callback", params={"state": state, "code": "c"}).status_code == 404


def test_revoked_connection_cannot_pull(client: TestClient) -> None:
    connection_id, state = _connect(client)
    client.get("/emr/callback", params={"state": state, "code": "c"})

    revoked = client.delete(f"/emr/connections/{connection_id}")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    assert client.post(f"/emr/connections/{connection_id}/pull").status_code == 409


async def test_revoke_deletes_the_vaulted_tokens_and_clears_the_ref() -> None:
    """Revocation removes the secret material itself, not just the status flag: a
    revoked grant must not stay recoverable from the durable vault (ADR-0017)."""
    from app.models.emr_connection import EmrConnectionStatus

    service = EmrService(transport=FakeEmr(), client_id="c", redirect_uri="https://a/cb")
    record, _, state = await service.start_connect(
        patient_id=uuid4(), fhir_base=FHIR_BASE, provider_name=None
    )
    await service.complete_callback(state=state, code="auth-code")
    ref = (await service.get_connection(record.id)).token_ref
    assert ref is not None
    assert await service.secret_store.get(ref) is not None

    revoked = await service.revoke(record.id)
    assert revoked.status is EmrConnectionStatus.revoked
    assert revoked.token_ref is None  # the dangling reference goes with the secret
    assert await service.secret_store.get(ref) is None
    assert service.secret_store._secrets == {}  # nothing orphaned in the vault
    # Idempotent: a second revoke finds no ref to delete and stays clean.
    assert (await service.revoke(record.id)).token_ref is None


async def test_relink_deletes_the_superseded_token_secret() -> None:
    """A callback completing on a connection that already holds tokens (re-link)
    replaces the vault entry — the old refresh token must not sit orphaned in the
    vault forever (ADR-0017)."""
    from datetime import UTC, datetime

    from app.emr.service import PendingAuth

    service = EmrService(transport=FakeEmr(), client_id="c", redirect_uri="https://a/cb")
    record, _, state = await service.start_connect(
        patient_id=uuid4(), fhir_base=FHIR_BASE, provider_name=None
    )
    await service.complete_callback(state=state, code="auth-code")
    old_ref = (await service.get_connection(record.id)).token_ref
    assert old_ref is not None

    # A fresh handshake landing on the SAME connection — the re-link path.
    await service._pending.put(
        "relink-state",
        PendingAuth(
            connection_id=record.id,
            code_verifier="synthetic-verifier",
            token_endpoint="https://ehr.example/oauth/token",
        ),
        now=datetime.now(UTC),
    )
    await service.complete_callback(state="relink-state", code="auth-code")
    new_ref = (await service.get_connection(record.id)).token_ref
    assert new_ref is not None and new_ref != old_ref
    assert await service.secret_store.get(old_ref) is None  # superseded secret deleted
    assert await service.secret_store.get(new_ref) is not None
    assert len(service.secret_store._secrets) == 1  # exactly the live secret remains


def test_pull_before_callback_is_409(client: TestClient) -> None:
    connection_id, _ = _connect(client)
    assert client.post(f"/emr/connections/{connection_id}/pull").status_code == 409


def test_unknown_connection_is_404(client: TestClient) -> None:
    assert client.post(f"/emr/connections/{uuid4()}/pull").status_code == 404
    assert client.delete(f"/emr/connections/{uuid4()}").status_code == 404


async def test_active_connection_missing_tokens_is_409() -> None:
    # Defensive invariant: active status without vaulted tokens must refuse to pull.
    import uuid as uuid_mod

    from app.emr.service import ConnectionRecord, EmrError
    from app.models.emr_connection import EmrConnectionStatus

    service = EmrService(transport=FakeEmr(), client_id="c", redirect_uri="https://a/cb")
    record = ConnectionRecord(
        id=uuid_mod.uuid4(),
        patient_id=uuid_mod.uuid4(),
        fhir_base=FHIR_BASE,
        provider_name=None,
        status=EmrConnectionStatus.active,
    )
    await service.connections.add(record)  # contrived state for the invariant
    try:
        await service.pull_labs(record.id)
        raise AssertionError("expected EmrError")
    except EmrError as exc:
        assert exc.status_code == 409


def test_unknown_provider_key_is_404(client: TestClient) -> None:
    resp = client.post("/emr/connect", json={"provider_key": "not-an-emr"})
    assert resp.status_code == 404


def test_provider_without_sandbox_requires_fhir_base(client: TestClient) -> None:
    resp = client.post("/emr/connect", json={"provider_key": "meditech"})
    assert resp.status_code == 422


def test_connect_requires_provider_or_fhir_base(client: TestClient) -> None:
    resp = client.post("/emr/connect", json={})
    assert resp.status_code == 422


class BrokenEmr(FakeEmr):
    """An EMR with no SMART config and a token endpoint that returns no token."""

    def __init__(self, *, empty_config: bool) -> None:
        super().__init__()
        self._empty_config = empty_config

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        if self._empty_config and url.endswith("/.well-known/smart-configuration"):
            return {}
        return await super().get_json(url, access_token=access_token)

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        return {"error": "server_error"}


def _client_with(service: EmrService) -> TestClient:
    app.dependency_overrides[get_emr_service] = lambda: service
    _sign_in_as(USER_A)
    return TestClient(app)


def test_emr_without_smart_config_is_502() -> None:
    service = EmrService(
        transport=BrokenEmr(empty_config=True), client_id="c", redirect_uri="https://a/cb"
    )
    try:
        resp = _client_with(service).post("/emr/connect", json={"fhir_base": FHIR_BASE})
        assert resp.status_code == 502
    finally:
        app.dependency_overrides.clear()


def test_token_exchange_without_access_token_is_502() -> None:
    service = EmrService(
        transport=BrokenEmr(empty_config=False), client_id="c", redirect_uri="https://a/cb"
    )
    try:
        c = _client_with(service)
        state = c.post("/emr/connect", json={"fhir_base": FHIR_BASE}).json()["state"]
        assert c.get("/emr/callback", params={"state": state, "code": "x"}).status_code == 502
    finally:
        app.dependency_overrides.clear()


class MinimalTokenEmr(FakeEmr):
    """Token response with only an access token — optional fields must default safely."""

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        return {"access_token": "the-access-token"}


def test_minimal_token_response_still_activates() -> None:
    service = EmrService(transport=MinimalTokenEmr(), client_id="c", redirect_uri="https://a/cb")
    try:
        c = _client_with(service)
        state = c.post("/emr/connect", json={"fhir_base": FHIR_BASE}).json()["state"]
        body = c.get("/emr/callback", params={"state": state, "code": "x"}).json()
        assert body["status"] == "active"
        assert body["patient_fhir_id"] is None
        assert body["granted_scope"] is None
        assert body["token_expires_at"] is None
    finally:
        app.dependency_overrides.clear()


def test_default_service_builds_from_settings() -> None:
    from app.api.routes.emr import get_emr_service as real_dep

    service = real_dep()
    assert isinstance(service, EmrService)
    assert service is real_dep()  # cached singleton


def test_registry_provider_connects_via_sandbox(client: TestClient) -> None:
    # Epic entry resolves to its sandbox base until per-org production endpoints land.
    resp = client.post("/emr/connect", json={"provider_key": "epic"})
    assert resp.status_code == 200
    q = parse_qs(urlparse(resp.json()["authorize_url"]).query)
    assert q["aud"] == ["https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4"]


# --- auth on EMR endpoints (ADR-0010) -------------------------------------------------


def test_emr_endpoints_require_auth() -> None:
    # No get_current_user override -> real dependency -> 401 without a bearer token.
    with TestClient(app) as anon:
        assert anon.post("/emr/connect", json={"fhir_base": FHIR_BASE}).status_code == 401
        assert anon.post(f"/emr/connections/{uuid4()}/pull").status_code == 401
        assert anon.delete(f"/emr/connections/{uuid4()}").status_code == 401
        assert anon.get("/emr/callback", params={"state": "s", "code": "c"}).status_code == 401


def test_cross_user_access_is_404_indistinguishable_from_unknown(client: TestClient) -> None:
    """Someone else's connection answers 404 — byte-identical to a nonexistent id — so a
    leaked connection UUID can never be confirmed live from another account (the house
    404-over-403 posture; an existence oracle would survive even revocation)."""
    # User A creates and activates a connection...
    connection_id, state = _connect(client)
    assert client.get("/emr/callback", params={"state": state, "code": "c"}).status_code == 200

    # ...user B must not be able to pull or revoke it — and must not learn it exists.
    _sign_in_as(USER_B)
    cross_pull = client.post(f"/emr/connections/{connection_id}/pull")
    unknown_pull = client.post(f"/emr/connections/{uuid4()}/pull")
    assert cross_pull.status_code == unknown_pull.status_code == 404
    assert cross_pull.json() == unknown_pull.json()  # indistinguishable bodies too
    cross_revoke = client.delete(f"/emr/connections/{connection_id}")
    unknown_revoke = client.delete(f"/emr/connections/{uuid4()}")
    assert cross_revoke.status_code == unknown_revoke.status_code == 404
    assert cross_revoke.json() == unknown_revoke.json()

    # And back as user A, it still works.
    _sign_in_as(USER_A)
    assert client.post(f"/emr/connections/{connection_id}/pull").status_code == 200


def test_callback_for_another_users_state_is_404_like_unknown_state(client: TestClient) -> None:
    _, state = _connect(client)  # started by user A
    _sign_in_as(USER_B)
    cross = client.get("/emr/callback", params={"state": state, "code": "c"})
    unknown = client.get("/emr/callback", params={"state": "forged", "code": "c"})
    assert cross.status_code == unknown.status_code == 404
    assert cross.json() == unknown.json()  # no existence leak on the callback either


def test_clinician_cannot_use_patient_endpoints(client: TestClient) -> None:
    clinician = CurrentUser(
        user_id=uuid4(),
        role=UserRole.clinician,
        patient_id=None,
        email="dr@example.test",
        display_name="Dr. Example",
    )
    _sign_in_as(clinician)
    assert client.post("/emr/connect", json={"fhir_base": FHIR_BASE}).status_code == 403


async def test_connect_flow_is_gated_by_the_emr_connect_toggle(client: TestClient) -> None:
    """emr_connect gates ESTABLISHING/REFRESHING a connection (ADR-0020): with it off,
    POST /emr/connect and GET /emr/callback answer 409 — the patient turning it off
    prevents NEW connections. Revoke stays ungated (revocation must never be toggle-
    blockable), and the pull is governed by ingest_labs, not emr_connect (the connect-
    vs-pull split): so with emr_connect off but a connection already active, the pull
    still works."""
    from datetime import UTC, datetime

    from app.api.deps import get_capability_service
    from app.services.capability import CapabilityService

    # Establish an active connection FIRST, while emr_connect is on (default).
    connection_id, state = _connect(client)
    assert client.get("/emr/callback", params={"state": state, "code": "c"}).status_code == 200

    capability_service = CapabilityService()
    assert USER_A.patient_id is not None
    await capability_service.set_for_patient(
        patient_id=USER_A.patient_id,
        actor_id=USER_A.user_id,
        key="emr_connect",
        active=False,
        now=datetime.now(UTC),
    )
    app.dependency_overrides[get_capability_service] = lambda: capability_service

    # New connections are blocked at connect and at callback.
    assert client.post("/emr/connect", json={"fhir_base": FHIR_BASE}).status_code == 409
    assert client.get("/emr/callback", params={"state": "x", "code": "c"}).status_code == 409
    # The connect-vs-pull split: ingest_labs governs the data write, so the existing
    # connection can still be pulled while emr_connect is off.
    assert client.post(f"/emr/connections/{connection_id}/pull").status_code == 200
    # Revoke is NEVER toggle-blockable — the existing connection can still be dropped.
    assert client.delete(f"/emr/connections/{connection_id}").status_code == 200

    # Re-enabled: a new connection can be established again.
    del app.dependency_overrides[get_capability_service]
    assert client.post("/emr/connect", json={"fhir_base": FHIR_BASE}).status_code == 200


async def test_pull_is_gated_by_the_ingest_labs_toggle(client: TestClient) -> None:
    """EMR pull writes lab Observations — the same data class as POST /labs — so
    ingest_labs=off refuses it too; an ungated pull would defeat a clinician's
    ingest_labs=off order and the ops kill switch (ADR-0013 review finding).
    Revocation stays ungated: turning off a toggle must never trap a connection."""
    from datetime import UTC, datetime

    from app.api.deps import get_capability_service
    from app.services.capability import CapabilityService

    capability_service = CapabilityService()
    assert USER_A.patient_id is not None
    await capability_service.set_for_patient(
        patient_id=USER_A.patient_id,
        actor_id=USER_A.user_id,
        key="ingest_labs",
        active=False,
        now=datetime.now(UTC),
    )
    app.dependency_overrides[get_capability_service] = lambda: capability_service

    # The gate fires before the handler: even an unknown connection id answers 409.
    refused = client.post(f"/emr/connections/{uuid4()}/pull")
    assert refused.status_code == 409
    assert "turned off" in refused.json()["detail"]
    # Revoke is NOT toggle-gated — unknown id keeps answering 404, never 409.
    assert client.delete(f"/emr/connections/{uuid4()}").status_code == 404

    await capability_service.set_for_patient(
        patient_id=USER_A.patient_id,
        actor_id=USER_A.user_id,
        key="ingest_labs",
        active=True,
        now=datetime.now(UTC),
    )
    connection_id, state = _connect(client)
    assert client.get("/emr/callback", params={"state": state, "code": "c"}).status_code == 200
    resp = client.post(f"/emr/connections/{connection_id}/pull")
    assert resp.status_code == 200  # re-enabled: the pull works again


def test_provider_connect_uses_the_vendor_client_id_on_both_hops() -> None:
    """ADR-0028 per-provider client ids: each EMR issues its OWN client_id, so a
    registry-provider connect must carry the vendor id on the authorize URL AND the
    token exchange — mixing the vendor id on one hop with the fallback on the other
    would fail every exchange."""
    fake = FakeEmr()
    service = EmrService(
        transport=fake,
        client_id="generic-client",
        redirect_uri="https://app.test/emr/callback",
        provider_client_ids={"Epic (MyChart)": "synthetic-epic-client-id"},
    )
    try:
        c = _client_with(service)
        resp = c.post("/emr/connect", json={"provider_key": "epic"})
        assert resp.status_code == 200
        q = parse_qs(urlparse(resp.json()["authorize_url"]).query)
        assert q["client_id"] == ["synthetic-epic-client-id"]

        cb = c.get("/emr/callback", params={"state": resp.json()["state"], "code": "auth-code"})
        assert cb.status_code == 200
        assert fake.token_requests[-1]["client_id"] == "synthetic-epic-client-id"
    finally:
        app.dependency_overrides.clear()


def test_custom_fhir_base_connect_keeps_the_generic_client_id() -> None:
    """A custom fhir_base connect has no registry provider, so the generic
    SMART_CLIENT_ID fallback applies on both hops — existing behavior, unchanged."""
    fake = FakeEmr()
    service = EmrService(
        transport=fake,
        client_id="generic-client",
        redirect_uri="https://app.test/emr/callback",
        provider_client_ids={"Epic (MyChart)": "synthetic-epic-client-id"},
    )
    try:
        c = _client_with(service)
        resp = c.post("/emr/connect", json={"fhir_base": FHIR_BASE})
        q = parse_qs(urlparse(resp.json()["authorize_url"]).query)
        assert q["client_id"] == ["generic-client"]
        cb = c.get("/emr/callback", params={"state": resp.json()["state"], "code": "c"})
        assert cb.status_code == 200
        assert fake.token_requests[-1]["client_id"] == "generic-client"
    finally:
        app.dependency_overrides.clear()


def test_provider_without_a_configured_client_id_falls_back_to_the_generic() -> None:
    """When the generic SMART_CLIENT_ID IS configured, an unconfigured vendor id falls
    back to it — a single-vendor pilot may legitimately run everything on the generic
    id, and the fallback keeps sandbox development working until the user registers
    with that vendor. (With NOTHING real configured, connect now fails early with a
    422 instead — the tests below.)"""
    fake = FakeEmr()
    service = EmrService(
        transport=fake, client_id="generic-client", redirect_uri="https://app.test/emr/callback"
    )
    try:
        c = _client_with(service)
        resp = c.post("/emr/connect", json={"provider_key": "epic"})
        q = parse_qs(urlparse(resp.json()["authorize_url"]).query)
        assert q["client_id"] == ["generic-client"]
    finally:
        app.dependency_overrides.clear()


def test_provider_connect_fails_early_when_no_real_client_id_is_configured() -> None:
    """With neither the vendor id nor the generic SMART_CLIENT_ID configured, deps
    wires the 'unconfigured-client' placeholder — and the OLD behavior redirected the
    patient to the REAL EMR carrying it, dead-ending in an opaque vendor-side
    invalid_client error. Connect itself now answers 422 naming the exact env var to
    set, before any discovery call and before any connection record is born."""
    fake = FakeEmr()
    service = EmrService(
        transport=fake,
        client_id=UNCONFIGURED_CLIENT_ID,
        redirect_uri="https://app.test/emr/callback",
    )
    try:
        c = _client_with(service)
        resp = c.post("/emr/connect", json={"provider_key": "epic"})
        assert resp.status_code == 422
        assert "SMART_CLIENT_ID_EPIC" in resp.json()["detail"]  # actionable: the env var
        assert fake.discovery_calls == 0  # failed EARLY — the EMR was never contacted
    finally:
        app.dependency_overrides.clear()


def test_custom_fhir_base_connect_fails_early_without_a_client_id() -> None:
    """A custom fhir_base connect has no vendor env var, so the 422 points the
    operator at the generic SMART_CLIENT_ID. An empty client id is exactly as
    unusable as the placeholder — both fail early."""
    fake = FakeEmr()
    service = EmrService(transport=fake, client_id="", redirect_uri="https://app.test/emr/callback")
    try:
        c = _client_with(service)
        resp = c.post("/emr/connect", json={"fhir_base": FHIR_BASE})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "must set SMART_CLIENT_ID" in detail
        assert "SMART_CLIENT_ID_" not in detail  # generic, not a vendor env var
        assert fake.discovery_calls == 0
    finally:
        app.dependency_overrides.clear()


def test_deps_build_the_provider_client_id_map_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wiring seam (deps._smart_provider_client_ids): configured vendors appear,
    keyed by DISPLAY NAME (what a ConnectionRecord persists), and unconfigured ones are
    simply absent so the service falls back to the generic id."""
    from app.api.deps import _smart_provider_client_ids
    from app.core.config import settings

    monkeypatch.setattr(settings, "smart_client_id_epic", "synthetic-epic-client-id")
    monkeypatch.setattr(settings, "smart_client_id_oracle_health", "synthetic-oracle-client-id")
    ids = _smart_provider_client_ids()
    assert ids["Epic (MyChart)"] == "synthetic-epic-client-id"
    assert ids["Oracle Health (Cerner)"] == "synthetic-oracle-client-id"
    assert "athenahealth" not in ids and "MEDITECH" not in ids  # unconfigured -> absent


# --- Clinical-note pull (ADR-0045 P2 #27) ---------------------------------------------


async def _connect_notes_and_activate(service: EmrService) -> UUID:
    """A full connect->callback on a notes-capable EMR; returns the active connection id.

    Uses the service API directly (the callback grants the DocumentReference scope) so the
    connection is ready for a note pull. USER_A owns it (matching the signed-in override)."""
    assert USER_A.patient_id is not None
    record, _, state = await service.start_connect(
        patient_id=USER_A.patient_id, fhir_base=FHIR_BASE, provider_name=None, include_notes=True
    )
    await service.complete_callback(state=state, code="auth-code")
    return record.id


async def test_pull_notes_full_flow_imports_and_is_idempotent_with_one_signal() -> None:
    """Two pulls of the same note import 1 then 0 (idempotent), and exactly ONE
    new-chart-note signal is emitted (only on the first, real insert — no re-alert)."""
    service = EmrService(transport=NotesEmr(), client_id="c", redirect_uri="https://a/cb")
    try:
        c = _client_with(service)
        await _enable_ingest_notes()
        connection_id = await _connect_notes_and_activate(service)

        first = c.post(f"/emr/connections/{connection_id}/pull-notes")
        assert first.status_code == 200
        assert first.json() == {"imported": 1, "skipped": 0, "fetched": 1}

        second = c.post(f"/emr/connections/{connection_id}/pull-notes")
        assert second.status_code == 200
        assert second.json()["imported"] == 0  # already on file — re-pull persists nothing

        # Exactly ONE signal across the two pulls, carrying metadata only (no body).
        signals = service.note_signals.signals  # type: ignore[attr-defined]
        assert len(signals) == 1
        signal = signals[0]
        assert signal.type_display == "Progress note"
        assert signal.author_display == "Dr Synthetic"
        assert signal.encounter_fhir_id == "enc-1"
        # The signal is keyed on the STABLE source-scoped import key (consumers dedupe on
        # it — note_id is a fresh row UUID that changes across a rolled-back retry).
        assert signal.import_key == f"{FHIR_BASE}|docref:docref-1"
        assert "SECRET" not in repr(signal)  # existence + metadata only, never the body
    finally:
        app.dependency_overrides.clear()


async def test_pull_notes_watermark_bounds_the_second_search() -> None:
    """The first pull searches unbounded; the second carries date=ge(last_notes_pulled_at)
    so it only asks for notes authored since the last sync."""
    emr = NotesEmr()
    service = EmrService(transport=emr, client_id="c", redirect_uri="https://a/cb")
    try:
        c = _client_with(service)
        await _enable_ingest_notes()
        connection_id = await _connect_notes_and_activate(service)

        c.post(f"/emr/connections/{connection_id}/pull-notes")
        c.post(f"/emr/connections/{connection_id}/pull-notes")

        assert len(emr.note_search_urls) == 2
        assert "date=ge" not in emr.note_search_urls[0]  # first pull unbounded
        assert "date=ge" in emr.note_search_urls[1]  # second pull carries the watermark
    finally:
        app.dependency_overrides.clear()


def _docref_resource(doc_id: str, date: str) -> dict[str, Any]:
    return {
        "resourceType": "DocumentReference",
        "id": doc_id,
        "type": {
            "coding": [
                {"system": "http://loinc.org", "code": "11506-3", "display": "Progress note"}
            ]
        },
        "date": date,
        "author": [{"display": "Dr Synthetic"}],
        "content": [
            {"attachment": {"contentType": "text/plain", "url": f"{FHIR_BASE}/Binary/{doc_id}"}}
        ],
    }


class BackdatingNotesEmr(NotesEmr):
    """A NotesEmr whose DocumentReference search honors the ``date=ge`` bound against a
    MUTABLE doc list — models an EHR gaining a late-signed note whose authoring date is
    backdated to the encounter (before the previous pull ran)."""

    def __init__(self) -> None:
        super().__init__()
        self.docs: list[tuple[str, str]] = [("docref-1", "2026-06-15T08:30:00+00:00")]

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        if not url.startswith(f"{FHIR_BASE}/DocumentReference"):
            return await super().get_json(url, access_token=access_token)
        self.note_search_urls.append(url)
        bound: datetime | None = None
        for value in parse_qs(urlparse(url).query).get("date", []):
            if value.startswith("ge"):
                bound = datetime.fromisoformat(value[2:])
        entries = [
            {"resource": _docref_resource(doc_id, date)}
            for doc_id, date in self.docs
            if bound is None or datetime.fromisoformat(date) >= bound
        ]
        return {"resourceType": "Bundle", "type": "searchset", "entry": entries}


async def test_pull_notes_watermark_is_authoring_based_and_catches_backdated_notes() -> None:
    """The watermark is max(fetched authored_at) MINUS the safety overlap — never the app
    clock. A note signed after the first pull but authoring-DATED before it (late-signed/
    backdated, or app-vs-EHR clock skew) still falls inside the next pull's ``date=ge``
    bound and is imported, instead of being permanently missed by every future pull."""
    emr = BackdatingNotesEmr()
    service = EmrService(transport=emr, client_id="c", redirect_uri="https://a/cb")
    try:
        c = _client_with(service)
        await _enable_ingest_notes()
        connection_id = await _connect_notes_and_activate(service)

        first = c.post(f"/emr/connections/{connection_id}/pull-notes")
        assert first.json()["imported"] == 1

        # A clinician signs a note AFTER the first pull, backdated 3 days before the
        # newest already-pulled note — well inside the 7-day overlap window.
        emr.docs.append(("docref-backdated", "2026-06-12T09:00:00+00:00"))

        second = c.post(f"/emr/connections/{connection_id}/pull-notes")
        assert second.json()["imported"] == 1  # fetched AND imported, not lost forever

        # The second search's bound derives from the pulled notes' authoring time
        # (Jun 15 minus the 7-day overlap) — NOT from the pull's wall-clock time.
        bound = parse_qs(urlparse(emr.note_search_urls[1]).query)["date"][0]
        assert bound == "ge2026-06-08T08:30:00+00:00"

        # Idempotent overlap re-fetch: a third pull re-sees both notes, imports none.
        third = c.post(f"/emr/connections/{connection_id}/pull-notes")
        assert third.json()["imported"] == 0
    finally:
        app.dependency_overrides.clear()


class _FailingNoteRepo:
    """A clinical-note store whose insert always fails (synthetic transient DB error)."""

    async def existing_import_keys(self, patient_id: UUID, import_keys: list[str]) -> set[str]:
        return set()

    async def add_if_absent(self, note: Any) -> bool:
        raise RuntimeError("synthetic storage failure")

    async def list_for_patient(self, patient_id: UUID, **kwargs: Any) -> list[Any]:
        return []

    async def delete_for_patient(self, patient_id: UUID) -> None:
        return None


async def test_pull_notes_watermark_does_not_advance_when_persist_fails() -> None:
    """The docstring invariant, pinned: a mid-pull persistence failure leaves the
    watermark untouched, so the NEXT pull re-fetches the same window instead of
    permanently losing the notes behind an advanced bound. No phantom signal either."""
    from app.repositories.emr_clinical_note import InMemoryEmrClinicalNoteRepository

    emr = NotesEmr()
    service = EmrService(transport=emr, client_id="c", redirect_uri="https://a/cb")
    connection_id = await _connect_notes_and_activate(service)

    service.clinical_notes = _FailingNoteRepo()
    with pytest.raises(RuntimeError):
        await service.pull_clinical_notes(connection_id)
    assert (await service.get_connection(connection_id)).last_notes_pulled_at is None
    assert service.note_signals.signals == []  # type: ignore[attr-defined]

    # Recovery: storage heals, and the SAME (unbounded) window is re-fetched + imported.
    service.clinical_notes = InMemoryEmrClinicalNoteRepository()
    _fetched, imported, _skipped = await service.pull_clinical_notes(connection_id)
    assert imported == 1
    assert "date=ge" not in emr.note_search_urls[0]
    assert "date=ge" not in emr.note_search_urls[1]  # the failed pull advanced nothing


class _FailingAudit:
    """An audit store whose write always fails (models a failure late in the batch)."""

    async def add(self, event: Any) -> Any:
        raise RuntimeError("synthetic audit failure")

    async def list_for_patient(self, patient_id: UUID) -> list[Any]:
        return []


async def test_pull_notes_emits_no_signal_when_a_later_batch_write_fails() -> None:
    """Signals fire only AFTER the whole batch (note rows + audit event) persisted: a
    failure between the inserts and the batch's end must not hand the fan-out sink an
    alert for a transaction that rolls back (no phantom caregiver alerts, ADR-0047)."""
    service = EmrService(transport=NotesEmr(), client_id="c", redirect_uri="https://a/cb")
    connection_id = await _connect_notes_and_activate(service)
    service.audit = _FailingAudit()
    with pytest.raises(RuntimeError):
        await service.pull_clinical_notes(connection_id)
    assert service.note_signals.signals == []  # type: ignore[attr-defined]


FHIR_BASE_2 = "https://other-ehr.example/fhir"


class TwoEhrNotes(NotesEmr):
    """Answers discovery/token/DocumentReference under BOTH synthetic EHR bases; each
    base returns a note with the SAME DocumentReference id (ids are per-server)."""

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        return await super().get_json(
            url.replace(FHIR_BASE_2, FHIR_BASE, 1), access_token=access_token
        )


async def test_note_import_keys_are_scoped_per_source_ehr_no_collision() -> None:
    """FHIR resource ids are unique only within one server: with TWO connected EHRs both
    using DocumentReference id 'docref-1', the source-scoped import key keeps the second
    EHR's note from being silently dropped as a duplicate of the first."""
    service = EmrService(transport=TwoEhrNotes(), client_id="c", redirect_uri="https://a/cb")
    assert USER_A.patient_id is not None
    connection_ids = []
    for base in (FHIR_BASE, FHIR_BASE_2):
        record, _, state = await service.start_connect(
            patient_id=USER_A.patient_id, fhir_base=base, provider_name=None, include_notes=True
        )
        await service.complete_callback(state=state, code="auth-code")
        connection_ids.append(record.id)

    assert (await service.pull_clinical_notes(connection_ids[0]))[1] == 1
    assert (await service.pull_clinical_notes(connection_ids[1]))[1] == 1  # NOT a "dupe"
    notes = await service.clinical_notes.list_for_patient(USER_A.patient_id)
    assert sorted(n.import_key for n in notes if n.import_key is not None) == [
        f"{FHIR_BASE}|docref:docref-1",
        f"{FHIR_BASE_2}|docref:docref-1",
    ]


async def test_revoke_during_note_pull_is_not_resurrected() -> None:
    """A patient revoking from another tab/device while a (slow) note pull is in flight
    must STAY revoked: the pull's end-of-flow write is a targeted watermark update, never
    a write-back of its stale pre-fetch snapshot (which would flip the status back to
    active, erase revoked_at, and restore a dangling token_ref)."""
    from app.models.emr_connection import EmrConnectionStatus

    service = EmrService(transport=NotesEmr(), client_id="c", redirect_uri="https://a/cb")
    connection_id = await _connect_notes_and_activate(service)

    class RevokingEmr(NotesEmr):
        async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
            if url.startswith(f"{FHIR_BASE}/DocumentReference"):
                await service.revoke(connection_id)  # the concurrent revoke, mid-fetch
            return await super().get_json(url, access_token=access_token)

    service.transport = RevokingEmr()
    _fetched, imported, _skipped = await service.pull_clinical_notes(connection_id)
    assert imported == 1  # the in-flight pull itself completes

    record = await service.get_connection(connection_id)
    assert record.status is EmrConnectionStatus.revoked  # NOT resurrected to active
    assert record.revoked_at is not None  # the revocation timestamp survives
    assert record.token_ref is None  # the dangling ref was not restored


async def test_pull_notes_no_body_in_summary_or_audit() -> None:
    """The pull writes note METADATA only: the note body (inline data / Binary) never
    appears in the endpoint response OR in the import_clinical_notes audit event."""
    service = EmrService(transport=NotesEmr(), client_id="c", redirect_uri="https://a/cb")
    try:
        c = _client_with(service)
        await _enable_ingest_notes()
        connection_id = await _connect_notes_and_activate(service)

        resp = c.post(f"/emr/connections/{connection_id}/pull-notes")
        assert "SECRET" not in resp.text  # no body in the response payload

        events = service.audit._events  # type: ignore[attr-defined]
        note_events = [e for e in events if e.action == "import_clinical_notes"]
        assert len(note_events) == 1
        assert note_events[0].detail == {
            "connection_id": str(connection_id),
            "fetched": 1,
            "imported": 1,
        }
        # No note text anywhere in the audit detail (counts/refs only).
        import json as _json

        assert "SECRET" not in _json.dumps(note_events[0].detail)
    finally:
        app.dependency_overrides.clear()


async def test_pull_notes_scope_guard_refuses_without_the_note_scope() -> None:
    """A connection whose granted scope lacks DocumentReference read must NOT have a
    DocumentReference request sent on its behalf — the pull answers 409 (reconnect) and
    makes no EHR search call (the base FakeEmr grants only Observation.read)."""
    service = EmrService(transport=FakeEmr(), client_id="c", redirect_uri="https://a/cb")
    try:
        c = _client_with(service)
        await _enable_ingest_notes()
        assert USER_A.patient_id is not None
        record, _, state = await service.start_connect(
            patient_id=USER_A.patient_id, fhir_base=FHIR_BASE, provider_name=None
        )
        await service.complete_callback(state=state, code="auth-code")

        resp = c.post(f"/emr/connections/{record.id}/pull-notes")
        assert resp.status_code == 409
        assert "clinical notes" in resp.json()["detail"]
        # No note was persisted and no signal emitted (no EHR call was made).
        assert service.note_signals.signals == []  # type: ignore[attr-defined]
    finally:
        app.dependency_overrides.clear()


async def test_pull_notes_is_gated_by_the_ingest_notes_toggle(client: TestClient) -> None:
    """ingest_notes is OPT-IN (default off): the pull-notes gate answers 409 before the
    handler even for an unknown connection id, until the patient turns it on."""
    refused = client.post(f"/emr/connections/{uuid4()}/pull-notes")
    assert refused.status_code == 409
    assert "turned off" in refused.json()["detail"]


async def test_pull_notes_cross_user_is_404_like_unknown() -> None:
    """A note pull on someone else's connection is 404 (ownership, no existence leak) —
    byte-identical to a nonexistent connection id, like the lab pull."""
    service = EmrService(transport=NotesEmr(), client_id="c", redirect_uri="https://a/cb")
    try:
        c = _client_with(service)
        await _enable_ingest_notes()
        connection_id = await _connect_notes_and_activate(service)
        _sign_in_as(USER_B)
        cross = c.post(f"/emr/connections/{connection_id}/pull-notes")
        unknown = c.post(f"/emr/connections/{uuid4()}/pull-notes")
        assert cross.status_code == unknown.status_code == 404
        assert cross.json() == unknown.json()
    finally:
        app.dependency_overrides.clear()


def test_pull_notes_requires_auth() -> None:
    with TestClient(app) as anon:
        assert anon.post(f"/emr/connections/{uuid4()}/pull-notes").status_code == 401


def test_connect_notes_opt_in_requests_the_document_reference_scope(client: TestClient) -> None:
    """connect_notes=True adds patient/DocumentReference.rs to the authorize URL scopes;
    a labs-only connect (default) never requests it."""
    with_notes = client.post("/emr/connect", json={"fhir_base": FHIR_BASE, "connect_notes": True})
    scope = parse_qs(urlparse(with_notes.json()["authorize_url"]).query)["scope"][0]
    assert "patient/DocumentReference.rs" in scope

    labs_only = client.post("/emr/connect", json={"fhir_base": FHIR_BASE})
    scope_labs = parse_qs(urlparse(labs_only.json()["authorize_url"]).query)["scope"][0]
    assert "patient/DocumentReference.rs" not in scope_labs
