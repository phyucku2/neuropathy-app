"""Tests for the top-EMR provider registry (ADR-0009)."""

from __future__ import annotations

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
