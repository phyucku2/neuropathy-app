"""End-to-end tests for the EMR endpoints (ADR-0009): providers -> connect -> callback
-> pull -> revoke, against a fake EMR (no network).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, get_current_user
from app.api.routes.emr import get_emr_service
from app.emr.service import EmrService
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

    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        if url.endswith("/.well-known/smart-configuration"):
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


def test_cross_user_access_is_403(client: TestClient) -> None:
    # User A creates and activates a connection...
    connection_id, state = _connect(client)
    assert client.get("/emr/callback", params={"state": state, "code": "c"}).status_code == 200

    # ...user B must not be able to pull or revoke it.
    _sign_in_as(USER_B)
    assert client.post(f"/emr/connections/{connection_id}/pull").status_code == 403
    assert client.delete(f"/emr/connections/{connection_id}").status_code == 403

    # And back as user A, it still works.
    _sign_in_as(USER_A)
    assert client.post(f"/emr/connections/{connection_id}/pull").status_code == 200


def test_callback_for_another_users_state_is_403(client: TestClient) -> None:
    _, state = _connect(client)  # started by user A
    _sign_in_as(USER_B)
    resp = client.get("/emr/callback", params={"state": state, "code": "c"})
    assert resp.status_code == 403


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
    """An unconfigured vendor id must not break the flow — the fallback keeps sandbox
    development working until the user registers with that vendor."""
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
