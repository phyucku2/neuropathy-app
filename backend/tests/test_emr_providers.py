"""Tests for the top-EMR provider registry (ADR-0009)."""

from __future__ import annotations

import pytest

from app.emr.providers import TOP_PROVIDERS, get_provider, search_providers


def test_top_vendors_are_present() -> None:
    keys = {p.key for p in TOP_PROVIDERS}
    assert {"epic", "oracle-health", "athenahealth", "meditech", "nextgen", "veradigm"} <= keys


def test_every_provider_has_an_endpoint_directory() -> None:
    # Production FHIR bases are per-organization; the directory is how we resolve them.
    assert all(p.endpoint_directory for p in TOP_PROVIDERS)


def test_search_matches_name_vendor_and_key() -> None:
    assert [p.key for p in search_providers("mychart")] == ["epic"]
    assert [p.key for p in search_providers("cerner")] == ["oracle-health"]
    assert search_providers("") == list(TOP_PROVIDERS)
    assert search_providers("no-such-emr") == []


def test_get_provider_by_key() -> None:
    epic = get_provider("epic")
    assert epic is not None and epic.vendor == "Epic Systems"
    assert get_provider("nope") is None


def test_every_provider_names_a_real_per_vendor_client_id_setting() -> None:
    """ADR-0028: each registry entry resolves its OWN client id from env. A typo'd
    `client_id_env` would silently fall back to the generic client id, so every entry's
    env name must follow the SMART_CLIENT_ID_<KEY> convention AND map to an actual
    Settings field (the env name lowercased, pydantic-settings' mapping)."""
    from app.core.config import settings

    for provider in TOP_PROVIDERS:
        expected = "SMART_CLIENT_ID_" + provider.key.upper().replace("-", "_")
        assert provider.client_id_env == expected
        assert hasattr(settings, provider.client_id_env.lower())


def test_client_id_for_reads_the_configured_setting_or_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.emr.providers import client_id_for

    epic = get_provider("epic")
    assert epic is not None
    monkeypatch.setattr(settings, "smart_client_id_epic", "synthetic-epic-client-id")
    assert client_id_for(epic) == "synthetic-epic-client-id"
    # Unset and blank both mean "unconfigured" — callers fall back to the generic id.
    monkeypatch.setattr(settings, "smart_client_id_epic", None)
    assert client_id_for(epic) is None
    monkeypatch.setattr(settings, "smart_client_id_epic", "")
    assert client_id_for(epic) is None


def test_client_id_env_for_resolves_display_names_only() -> None:
    """The service's fail-early 422 names the exact env var to set — resolution is by
    provider DISPLAY NAME (what a ConnectionRecord persists); anything else (custom
    fhir_base connections) yields None and the generic SMART_CLIENT_ID message."""
    from app.emr.providers import client_id_env_for

    assert client_id_env_for("Epic (MyChart)") == "SMART_CLIENT_ID_EPIC"
    assert client_id_env_for("Oracle Health (Cerner)") == "SMART_CLIENT_ID_ORACLE_HEALTH"
    assert client_id_env_for("https://ehr.example/fhir") is None
    assert client_id_env_for("epic") is None  # keys are not display names
