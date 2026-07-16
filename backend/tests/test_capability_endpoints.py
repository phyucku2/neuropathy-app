"""End-to-end tests for the feature-toggles surface (ADR-0013): the patient's own
toggles (B2C authority), the clinician-managed variant with expiry, the authority
flip on consent/revocation, the ops kill switch, the enforcement seam on the first
two consumer endpoints, and the change audit trail.

Expiry values are fixed offsets from a module-level NOW — never derived from the
wall clock at assert time (time-of-day-dependent assertions are forbidden).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_auth_service,
    get_capability_service,
    get_clinic_service,
    get_emr_service,
)
from app.core.config import settings
from app.emr.service import EmrService
from app.main import app
from app.services.auth import AuthService
from app.services.capability import CAPABILITIES, CapabilityService, EffectiveCapability
from app.services.clinic import ClinicService

NOW = datetime.now(UTC)
BOOTSTRAP = {"X-Bootstrap-Token": "test-bootstrap-value"}
ALL_KEYS = [spec.key for spec in CAPABILITIES]


class _NoNetwork:
    async def get_json(self, url: str, *, access_token: str | None = None) -> dict[str, Any]:
        raise AssertionError("capability endpoints must not touch the network")

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        raise AssertionError("capability endpoints must not touch the network")


@pytest.fixture()
def clinic_service() -> ClinicService:
    return ClinicService()


@pytest.fixture()
def capability_service(clinic_service: ClinicService) -> CapabilityService:
    # Shares the connection, audit, AND capability stores with the clinic service,
    # exactly like the deps wiring does — toggle authority tracks the real consent
    # state, and the clinic service's share_with_clinic read gate (ADR-0020) sees every
    # toggle write the patient makes here.
    return CapabilityService(
        connections=clinic_service.connections,
        audit=clinic_service.audit,
        capabilities=clinic_service.capabilities,
        patient_capabilities=clinic_service.patient_capabilities,
    )


@pytest.fixture()
def client(
    clinic_service: ClinicService,
    capability_service: CapabilityService,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    auth = AuthService(secret="endpoint-test-secret", users=clinic_service.users)
    emr = EmrService(transport=_NoNetwork(), client_id="c", redirect_uri="https://a/cb")
    monkeypatch.setattr(settings, "ops_bootstrap_token", "test-bootstrap-value")
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_clinic_service] = lambda: clinic_service
    app.dependency_overrides[get_capability_service] = lambda: capability_service
    app.dependency_overrides[get_emr_service] = lambda: emr
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_patient(
    client: TestClient, email: str = "pat@example.com", name: str = "Pat"
) -> tuple[dict[str, str], uuid.UUID]:
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": "a-strong-password", "display_name": name},
    )
    assert resp.status_code == 201
    headers = _auth(resp.json()["access_token"])
    me = client.get("/auth/me", headers=headers)
    return headers, uuid.UUID(me.json()["patient_id"])


def _ops_headers(client: TestClient) -> dict[str, str]:
    """Provision + log in the first ops operator (ADR-0019), idempotently. The first
    call bootstraps it with the token; later calls find it already present and just log
    in — clinician provisioning now runs under this ops bearer, not the shared token."""
    client.post(
        "/ops/accounts",
        headers=BOOTSTRAP,
        json={"email": "ops@example.com", "password": "a-strong-password", "display_name": "Ops"},
    )
    login = client.post(
        "/auth/login", json={"email": "ops@example.com", "password": "a-strong-password"}
    )
    return _auth(login.json()["access_token"])


def _create_clinician(
    client: TestClient,
    email: str = "dr@example.com",
    clinic_name: str = "Advanced Health & Wellness Group",
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    resp = client.post(
        "/clinic/clinicians",
        headers=_ops_headers(client),
        json={
            "email": email,
            "password": "a-strong-password",
            "display_name": "Dr. Rivera",
            "clinic_name": clinic_name,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    login = client.post("/auth/login", json={"email": email, "password": "a-strong-password"})
    return (
        _auth(login.json()["access_token"]),
        uuid.UUID(body["clinic_id"]),
        uuid.UUID(body["user_id"]),
    )


def _connect_consented_patient(
    client: TestClient, clinician: dict[str, str], email: str = "pat@example.com"
) -> tuple[dict[str, str], uuid.UUID, str]:
    patient, patient_id = _register_patient(client, email=email)
    assert (
        client.post("/clinic/invitations", headers=clinician, json={"email": email}).status_code
        == 202
    )
    connection_id = client.get("/connections", headers=patient).json()[0]["id"]
    assert client.post(f"/connections/{connection_id}/consent", headers=patient).status_code == 200
    return patient, patient_id, connection_id


def _states(client: TestClient, headers: dict[str, str], url: str = "/capabilities") -> dict:
    resp = client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    return {c["key"]: c for c in resp.json()["capabilities"]}


def _adl(walking: int = 3, stairs: int = 2, balance: int = 4) -> dict[str, int]:
    return {"walking": walking, "stairs": stairs, "balance_confidence": balance}


def _lab() -> dict[str, Any]:
    return {
        "results": [
            {
                "loinc_code": "4548-4",
                "display": "Hemoglobin A1c",
                "value": 7.2,
                "unit": "%",
                "effective_at": "2026-06-15T08:00:00+00:00",
            }
        ]
    }


# ---------------------------------------------------------------- B2C patient authority


def test_b2c_patient_sees_registry_defaults(client: TestClient) -> None:
    patient, _ = _register_patient(client)
    states = _states(client, patient)
    assert sorted(states) == sorted(ALL_KEYS)
    for state in states.values():
        assert state["managed_by"] == "patient"
        assert state["expires_at"] is None
    # Back-compat keys default ON (absence of a row = default). `ingest_symptoms` is the
    # one opt-in key (ADR-0034 Phase 1): default OFF until the owner turns it on.
    for key, state in states.items():
        expected = key != "ingest_symptoms"
        assert state["active"] is expected, key


def test_b2c_patient_toggles_own_capability(client: TestClient) -> None:
    patient, _ = _register_patient(client)
    off = client.put("/capabilities/ingest_adl", headers=patient, json={"active": False})
    assert off.status_code == 200
    assert off.json() == {
        "key": "ingest_adl",
        "name": "Daily function check-in",
        "active": False,
        "managed_by": "patient",
        "expires_at": None,
        "enforced": True,
    }
    states = _states(client, patient)
    assert states["ingest_adl"]["active"] is False
    assert states["ingest_labs"]["active"] is True  # others untouched

    on = client.put("/capabilities/ingest_adl", headers=patient, json={"active": True})
    assert on.status_code == 200 and on.json()["active"] is True
    assert _states(client, patient)["ingest_adl"]["active"] is True


def test_all_shipped_keys_are_enforced_and_settable(client: TestClient) -> None:
    """Every shipped key is now wired to a consumer (ADR-0020), so all are
    enforced=true and a B2C patient can set them — the "not changeable yet" refusal
    only ever applies to a FUTURE key introduced un-wired."""
    patient, _ = _register_patient(client)
    states = _states(client, patient)
    assert all(state["enforced"] is True for state in states.values())

    for key in ("ai_narrative", "emr_connect", "share_with_clinic"):
        resp = client.put(f"/capabilities/{key}", headers=patient, json={"active": False})
        assert resp.status_code == 200, resp.text
        assert resp.json()["active"] is False
        assert _states(client, patient)[key]["active"] is False


def test_clinician_cannot_set_patient_held_share_with_clinic(client: TestClient) -> None:
    """share_with_clinic is a PATIENT-HELD consent control (ADR-0020): even a consented
    clinician write to it is refused (409) — a clinic must never control the patient's
    ability to stop sharing. (Other keys stay clinician-settable while managed.)"""
    clinician, _, _ = _create_clinician(client)
    _, patient_id, _ = _connect_consented_patient(client, clinician, email="managed@example.com")
    refused = client.put(
        f"/clinic/patients/{patient_id}/capabilities/share_with_clinic",
        headers=clinician,
        json={"active": False},
    )
    assert refused.status_code == 409
    assert "controlled by the patient" in refused.json()["detail"]
    # A normal managed key is still clinician-settable, proving this is a carve-out.
    assert (
        client.put(
            f"/clinic/patients/{patient_id}/capabilities/ingest_adl",
            headers=clinician,
            json={"active": False},
        ).status_code
        == 200
    )


def test_clinician_cannot_pair_expiry_with_disable(client: TestClient) -> None:
    """Expiry deactivates, it never re-enables: active=false + expires_at would read
    as "suspended until <date>" but silently be permanent-off — refused (422)."""
    clinician, _, _ = _create_clinician(client)
    _, patient_id, _ = _connect_consented_patient(client, clinician)
    resp = client.put(
        f"/clinic/patients/{patient_id}/capabilities/ingest_adl",
        headers=clinician,
        json={"active": False, "expires_at": (NOW + timedelta(days=30)).isoformat()},
    )
    assert resp.status_code == 422


def test_patient_cannot_smuggle_an_expiry(client: TestClient) -> None:
    """expires_at is clinician authority: the patient contract has no such field, so
    a smuggled value is ignored and the stored row carries none."""
    patient, _ = _register_patient(client)
    resp = client.put(
        "/capabilities/ingest_adl",
        headers=patient,
        json={"active": True, "expires_at": (NOW + timedelta(days=1)).isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()["expires_at"] is None
    assert _states(client, patient)["ingest_adl"]["expires_at"] is None


def test_unknown_capability_key_is_404_for_both_actors(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, patient_id, _ = _connect_consented_patient(client, clinician)
    own = client.put("/capabilities/not_a_feature", headers=patient, json={"active": False})
    managed = client.put(
        f"/clinic/patients/{patient_id}/capabilities/not_a_feature",
        headers=clinician,
        json={"active": False},
    )
    assert own.status_code == 404
    assert managed.status_code == 404


def test_capability_routes_require_the_right_role(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, patient_id = _register_patient(client)
    assert client.get("/capabilities", headers=clinician).status_code == 403
    assert (
        client.put("/capabilities/ingest_adl", headers=clinician, json={"active": True}).status_code
        == 403
    )
    assert (
        client.get(f"/clinic/patients/{patient_id}/capabilities", headers=patient).status_code
        == 403
    )
    with TestClient(app) as anon:
        assert anon.get("/capabilities").status_code == 401


# ---------------------------------------------------------------- clinical authority


def test_clinically_managed_patient_cannot_self_toggle(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, _, _ = _connect_consented_patient(client, clinician)
    states = _states(client, patient)
    # Every key reads clinic-managed EXCEPT the patient-held share_with_clinic (ADR-0020).
    assert all(s["managed_by"] == "clinic" for k, s in states.items() if k != "share_with_clinic")
    assert states["share_with_clinic"]["managed_by"] == "patient"
    resp = client.put("/capabilities/ingest_adl", headers=patient, json={"active": False})
    assert resp.status_code == 409
    assert "managed by your connected clinic" in resp.json()["detail"]
    assert _states(client, patient)["ingest_adl"]["active"] is True  # nothing changed


def test_managed_patient_always_controls_share_with_clinic(client: TestClient) -> None:
    """The patient-held-consent carve-out (ADR-0020): a clinically-managed patient can
    turn share_with_clinic OFF themselves — unlike every OTHER key, which 409s for the
    managed patient. A clinic controlling the patient's ability to stop sharing would
    be perverse, so the managed-authority refusal never applies to this one key."""
    clinician, _, _ = _create_clinician(client)
    patient, patient_id, _ = _connect_consented_patient(client, clinician)
    # Other keys 409 for the managed patient...
    assert (
        client.put("/capabilities/ingest_adl", headers=patient, json={"active": False}).status_code
        == 409
    )
    # ...but share_with_clinic is the patient's own consent and always succeeds.
    off = client.put("/capabilities/share_with_clinic", headers=patient, json={"active": False})
    assert off.status_code == 200
    assert off.json() == {
        "key": "share_with_clinic",
        "name": "Share data with my clinic",
        "active": False,
        "managed_by": "patient",
        "expires_at": None,
        "enforced": True,
    }
    # And turning it off cuts the clinic off entirely (neutral 404, no existence leak).
    assert (
        client.get(f"/clinic/patients/{patient_id}/trajectory", headers=clinician).status_code
        == 404
    )
    # The patient can turn it back on again — still their control.
    assert (
        client.put(
            "/capabilities/share_with_clinic", headers=patient, json={"active": True}
        ).status_code
        == 200
    )


def test_pending_invitation_does_not_transfer_authority(client: TestClient) -> None:
    """Authority follows CONSENT, not invitations: a pending connection leaves the
    patient in control (may_transmit_to_clinic is the judge)."""
    clinician, _, _ = _create_clinician(client)
    patient, _ = _register_patient(client)
    client.post("/clinic/invitations", headers=clinician, json={"email": "pat@example.com"})
    assert _states(client, patient)["ingest_adl"]["managed_by"] == "patient"
    assert (
        client.put("/capabilities/ingest_adl", headers=patient, json={"active": False}).status_code
        == 200
    )


def test_clinician_sets_toggle_with_expiry_and_renews_it(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, patient_id, _ = _connect_consented_patient(client, clinician)
    url = f"/clinic/patients/{patient_id}/capabilities/ingest_adl"

    expired = (NOW - timedelta(hours=1)).isoformat()
    resp = client.put(url, headers=clinician, json={"active": True, "expires_at": expired})
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"] is False  # granted but already lapsed -> effectively off
    assert body["managed_by"] == "clinic"
    assert body["expires_at"] is not None
    assert _states(client, patient)["ingest_adl"]["active"] is False

    # Renewal, like an order: the same toggle re-issued with a future expiry.
    renewed = (NOW + timedelta(days=30)).isoformat()
    resp = client.put(url, headers=clinician, json={"active": True, "expires_at": renewed})
    assert resp.status_code == 200 and resp.json()["active"] is True
    clinician_view = _states(client, clinician, url=f"/clinic/patients/{patient_id}/capabilities")
    assert clinician_view["ingest_adl"]["active"] is True
    assert clinician_view["ingest_adl"]["expires_at"] is not None

    # No expiry = stands until changed.
    resp = client.put(url, headers=clinician, json={"active": True})
    assert resp.status_code == 200 and resp.json()["expires_at"] is None


def test_clinician_expiry_must_be_timezone_aware(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    _, patient_id, _ = _connect_consented_patient(client, clinician)
    resp = client.put(
        f"/clinic/patients/{patient_id}/capabilities/ingest_adl",
        headers=clinician,
        json={"active": True, "expires_at": "2026-08-01T00:00:00"},  # naive -> rejected
    )
    assert resp.status_code == 422


def test_revocation_flips_authority_back_to_the_patient(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, patient_id, connection_id = _connect_consented_patient(client, clinician)
    off = client.put(
        f"/clinic/patients/{patient_id}/capabilities/ingest_adl",
        headers=clinician,
        json={"active": False},
    )
    assert off.status_code == 200
    assert (
        client.put("/capabilities/ingest_adl", headers=patient, json={"active": True}).status_code
        == 409
    )  # still clinic-managed

    assert client.delete(f"/connections/{connection_id}", headers=patient).status_code == 204

    states = _states(client, patient)
    assert states["ingest_adl"]["managed_by"] == "patient"
    assert states["ingest_adl"]["active"] is False  # the clinician's last word stands...
    resp = client.put("/capabilities/ingest_adl", headers=patient, json={"active": True})
    assert resp.status_code == 200  # ...until the patient, back in authority, changes it
    assert _states(client, patient)["ingest_adl"]["active"] is True
    # Clinician reads and writes are cut off by the same revocation (404, not 403).
    assert (
        client.get(f"/clinic/patients/{patient_id}/capabilities", headers=clinician).status_code
        == 404
    )


def test_share_off_drops_patient_from_every_clinician_surface(client: TestClient) -> None:
    """share_with_clinic OFF is an ADDITIONAL gate on top of connection consent
    (ADR-0020): the patient drops off the panel, every /clinic/patients/{id}/* read
    answers the SAME neutral 404 as a cross-clinic patient, and clinician capability
    writes are refused the same way — one predicate, so they can never drift. Default
    is on, so the consented flow works until the patient turns it off."""
    clinician, _, _ = _create_clinician(client)
    patient, patient_id, _ = _connect_consented_patient(client, clinician)

    # Default-on: the consented patient is fully visible.
    panel = client.get("/clinic/patients", headers=clinician).json()["patients"]
    assert any(p["patient_id"] == str(patient_id) for p in panel)
    reads = [
        f"/clinic/patients/{patient_id}/trajectory",
        f"/clinic/patients/{patient_id}/observations",
        f"/clinic/patients/{patient_id}/capabilities",
    ]
    for url in reads:
        assert client.get(url, headers=clinician).status_code == 200, url

    # The patient turns sharing off (their own consent control).
    assert (
        client.put(
            "/capabilities/share_with_clinic", headers=patient, json={"active": False}
        ).status_code
        == 200
    )

    # (a) off the panel; (b) every read is a neutral 404; (c) writes refused the same way.
    panel = client.get("/clinic/patients", headers=clinician).json()["patients"]
    assert all(p["patient_id"] != str(patient_id) for p in panel)
    for url in reads:
        resp = client.get(url, headers=clinician)
        assert resp.status_code == 404, url
        assert resp.json()["detail"] == "Patient not found"  # neutral — no existence leak
    write = client.put(
        f"/clinic/patients/{patient_id}/capabilities/ingest_adl",
        headers=clinician,
        json={"active": False},
    )
    assert write.status_code == 404
    assert write.json()["detail"] == "Patient not found"

    # Back on — the patient reappears everywhere (back-compat, symmetric).
    assert (
        client.put(
            "/capabilities/share_with_clinic", headers=patient, json={"active": True}
        ).status_code
        == 200
    )
    assert client.get(reads[0], headers=clinician).status_code == 200


async def test_share_off_revocation_is_audited_and_leaks_nothing(
    client: TestClient, capability_service: CapabilityService
) -> None:
    """Revoking share (patient) is an auditable consent change (set_capability), and the
    clinician's resulting 404 carries nothing about why (ADR-0020)."""
    clinician, _, _ = _create_clinician(client)
    patient, patient_id, _ = _connect_consented_patient(client, clinician)
    client.put("/capabilities/share_with_clinic", headers=patient, json={"active": False})

    events = [
        e
        for e in await capability_service.audit.list_for_patient(patient_id)
        if e.action == "set_capability"
    ]
    assert len(events) == 1
    assert events[0].detail["key"] == "share_with_clinic"
    assert events[0].detail["active"] is False
    assert events[0].detail["set_by"] == "patient"
    # The denial the clinician sees says only "Patient not found".
    denied = client.get(f"/clinic/patients/{patient_id}/observations", headers=clinician)
    assert denied.json() == {"detail": "Patient not found"}


def test_cross_clinic_clinician_gets_404(client: TestClient) -> None:
    clinician_a, _, _ = _create_clinician(client)
    _, patient_id, _ = _connect_consented_patient(client, clinician_a)
    clinician_b, _, _ = _create_clinician(
        client, email="dr-b@example.com", clinic_name="Other Clinic"
    )
    read = client.get(f"/clinic/patients/{patient_id}/capabilities", headers=clinician_b)
    write = client.put(
        f"/clinic/patients/{patient_id}/capabilities/ingest_adl",
        headers=clinician_b,
        json={"active": False},
    )
    # 404 — a cross-clinic patient must be indistinguishable from a nonexistent one.
    assert read.status_code == 404
    assert write.status_code == 404
    assert read.json()["detail"] == "Patient not found"


def test_nonconsented_patient_is_404_for_own_clinic(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    _, patient_id = _register_patient(client)
    client.post("/clinic/invitations", headers=clinician, json={"email": "pat@example.com"})
    assert (
        client.get(f"/clinic/patients/{patient_id}/capabilities", headers=clinician).status_code
        == 404
    )


def test_service_defense_in_depth_surfaces_as_404(client: TestClient) -> None:
    """If the service's re-judging of the connection ever answers None despite the
    route gate passing, the clinician still sees a plain 404 — no existence leak."""
    clinician, _, _ = _create_clinician(client)
    _, patient_id, _ = _connect_consented_patient(client, clinician)

    class _RefusingService(CapabilityService):
        async def set_for_clinician(self, **kwargs: Any) -> EffectiveCapability | None:
            return None

    app.dependency_overrides[get_capability_service] = lambda: _RefusingService()
    resp = client.put(
        f"/clinic/patients/{patient_id}/capabilities/ingest_adl",
        headers=clinician,
        json={"active": False},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Patient not found"


# ---------------------------------------------------------------- ops kill switch


async def test_kill_switch_overrides_toggles_and_blocks_writes(
    client: TestClient, capability_service: CapabilityService
) -> None:
    patient, _ = _register_patient(client)
    assert (
        client.put("/capabilities/ingest_adl", headers=patient, json={"active": True}).status_code
        == 200
    )
    registry_row = await capability_service.capabilities.get_by_key("ingest_adl")
    assert registry_row is not None
    registry_row.available = False  # the ops kill switch

    assert _states(client, patient)["ingest_adl"]["active"] is False  # overrides the row
    resp = client.put("/capabilities/ingest_adl", headers=patient, json={"active": True})
    assert resp.status_code == 409
    assert "not currently available" in resp.json()["detail"]
    # The seam refuses the feature itself too.
    assert client.post("/adl", headers=patient, json=_adl()).status_code == 409


# ---------------------------------------------------------------- enforcement seam


def test_seam_allows_by_default_blocks_when_off_and_recovers(client: TestClient) -> None:
    patient, _ = _register_patient(client)
    # No toggle row at all: the default keeps today's behavior working.
    assert client.post("/adl", headers=patient, json=_adl()).status_code == 200
    assert client.post("/labs", headers=patient, json=_lab()).status_code == 200

    client.put("/capabilities/ingest_adl", headers=patient, json={"active": False})
    resp = client.post("/adl", headers=patient, json=_adl(walking=2))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "This feature is turned off"
    # The gates are per-capability: labs still flow while ADL is off.
    assert client.post("/labs", headers=patient, json=_lab()).status_code == 200

    client.put("/capabilities/ingest_labs", headers=patient, json={"active": False})
    assert client.post("/labs", headers=patient, json=_lab()).status_code == 409

    client.put("/capabilities/ingest_adl", headers=patient, json={"active": True})
    assert client.post("/adl", headers=patient, json=_adl(walking=2)).status_code == 200


def test_seam_honors_clinician_expiry(client: TestClient) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, patient_id, _ = _connect_consented_patient(client, clinician)
    url = f"/clinic/patients/{patient_id}/capabilities/ingest_adl"
    expired = (NOW - timedelta(hours=1)).isoformat()
    assert (
        client.put(url, headers=clinician, json={"active": True, "expires_at": expired}).status_code
        == 200
    )
    assert client.post("/adl", headers=patient, json=_adl()).status_code == 409  # lapsed
    renewed = (NOW + timedelta(days=30)).isoformat()
    assert (
        client.put(url, headers=clinician, json={"active": True, "expires_at": renewed}).status_code
        == 200
    )
    assert client.post("/adl", headers=patient, json=_adl()).status_code == 200


# ---------------------------------------------------------------- audit trail


async def test_every_toggle_change_is_audited(
    client: TestClient, capability_service: CapabilityService
) -> None:
    clinician, _, clinician_user_id = _create_clinician(client)
    patient, patient_id, connection_id = _connect_consented_patient(client, clinician)
    expiry = (NOW + timedelta(days=30)).isoformat()
    client.put(
        f"/clinic/patients/{patient_id}/capabilities/ingest_adl",
        headers=clinician,
        json={"active": True, "expires_at": expiry},
    )
    client.delete(f"/connections/{connection_id}", headers=patient)
    me = client.get("/auth/me", headers=patient).json()
    client.put("/capabilities/ingest_adl", headers=patient, json={"active": True})

    events = [
        e
        for e in await capability_service.audit.list_for_patient(patient_id)
        if e.action == "set_capability"
    ]
    assert len(events) == 2  # one per change — refused and read requests write nothing
    by_clinician, by_patient = events
    assert by_clinician.actor_id == clinician_user_id
    assert by_clinician.actor_role == "clinician"
    assert by_clinician.patient_id == patient_id
    assert by_clinician.detail["key"] == "ingest_adl"
    assert by_clinician.detail["active"] is True
    assert by_clinician.detail["set_by"] == "clinician"
    assert by_clinician.detail["expires_at"] is not None
    assert by_clinician.detail["connection_id"] == connection_id
    assert by_patient.actor_id == uuid.UUID(me["user_id"])
    assert by_patient.actor_role == "patient"
    assert by_patient.detail == {
        "key": "ingest_adl",
        "active": True,
        "expires_at": None,
        "set_by": "patient",
    }


async def test_refused_patient_writes_leave_no_toggle_audit(
    client: TestClient, capability_service: CapabilityService
) -> None:
    clinician, _, _ = _create_clinician(client)
    patient, patient_id, _ = _connect_consented_patient(client, clinician)
    assert (
        client.put("/capabilities/ingest_adl", headers=patient, json={"active": False}).status_code
        == 409
    )
    events = await capability_service.audit.list_for_patient(patient_id)
    assert all(e.action != "set_capability" for e in events)
