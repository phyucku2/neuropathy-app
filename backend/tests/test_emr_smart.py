"""Tests for SMART on FHIR OAuth/PKCE helpers (ADR-0008) — the security-critical bits."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.emr.smart import (
    build_authorize_url,
    build_token_request,
    code_challenge_for,
    generate_code_verifier,
)


def test_pkce_challenge_is_deterministic_s256() -> None:
    # Known RFC 7636 test vector.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert code_challenge_for(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_code_verifier_is_high_entropy_and_urlsafe() -> None:
    v = generate_code_verifier()
    assert len(v) >= 43  # RFC 7636 minimum
    assert "=" not in v and "+" not in v and "/" not in v


def test_authorize_url_has_required_smart_params() -> None:
    url = build_authorize_url(
        authorization_endpoint="https://ehr.example/oauth/authorize",
        client_id="my-client",
        redirect_uri="https://app.example/callback",
        fhir_base="https://ehr.example/fhir",
        state="xyz",
        code_challenge="challenge123",
    )
    q = parse_qs(urlparse(url).query)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["my-client"]
    assert q["redirect_uri"] == ["https://app.example/callback"]
    assert q["aud"] == ["https://ehr.example/fhir"]
    assert q["code_challenge"] == ["challenge123"]
    assert q["code_challenge_method"] == ["S256"]
    assert "patient/Observation.read" in q["scope"][0]
    assert q["state"] == ["xyz"]


def test_ehr_launch_adds_launch_scope_and_param() -> None:
    # Clinician launching from inside the EHR (SMART EHR launch — ADR-0009).
    url = build_authorize_url(
        authorization_endpoint="https://ehr.example/oauth/authorize",
        client_id="my-client",
        redirect_uri="https://app.example/callback",
        fhir_base="https://ehr.example/fhir",
        state="xyz",
        code_challenge="challenge123",
        launch="launch-context-token",
    )
    q = parse_qs(urlparse(url).query)
    assert q["launch"] == ["launch-context-token"]
    assert q["scope"][0].startswith("launch ")


def test_token_request_uses_pkce_verifier() -> None:
    body = build_token_request(
        client_id="my-client",
        redirect_uri="https://app.example/callback",
        code="the-code",
        code_verifier="the-verifier",
    )
    assert body["grant_type"] == "authorization_code"
    assert body["code"] == "the-code"
    assert body["code_verifier"] == "the-verifier"
