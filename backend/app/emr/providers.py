"""Registry of top EMR vendors with patient-access FHIR support (ADR-0009).

Data, not logic: each entry carries the vendor's public sandbox FHIR base (where one
exists) and the directory where per-organization PRODUCTION endpoints are published.
Production bases are resolved per health system at app-registration time.

⚠️ Sandbox URLs are point-in-time references — re-verify each when registering the app
with that vendor.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmrProvider:
    key: str
    name: str  # patient-facing name (portal brand where recognizable)
    vendor: str
    sandbox_fhir_base: str | None
    endpoint_directory: str  # where per-org production FHIR bases are published
    note: str


TOP_PROVIDERS: tuple[EmrProvider, ...] = (
    EmrProvider(
        key="epic",
        name="Epic (MyChart)",
        vendor="Epic Systems",
        sandbox_fhir_base="https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
        endpoint_directory="https://open.epic.com/MyApps/Endpoints",
        note="Largest US hospital EMR; patient portal is MyChart.",
    ),
    EmrProvider(
        key="oracle-health",
        name="Oracle Health (Cerner)",
        vendor="Oracle Health",
        sandbox_fhir_base=(
            "https://fhir-ehr-code.cerner.com/r4/ec2458f2-1e24-41c8-b71b-0e701af7583d"
        ),
        endpoint_directory="https://github.com/cerner/ignite-endpoints",
        note="Second-largest US hospital EMR; secure sandbox tenant shown.",
    ),
    EmrProvider(
        key="athenahealth",
        name="athenahealth",
        vendor="athenahealth",
        sandbox_fhir_base="https://api.preview.platform.athenahealth.com/fhir/r4",
        endpoint_directory="https://docs.athenahealth.com/api/base-fhir-urls",
        note="Strong in ambulatory/clinic practices.",
    ),
    EmrProvider(
        key="meditech",
        name="MEDITECH",
        vendor="MEDITECH",
        sandbox_fhir_base=None,
        endpoint_directory="https://fhir.meditech.com/explorer/endpoints",
        note="Community-hospital EMR; sandbox access granted on registration.",
    ),
    EmrProvider(
        key="nextgen",
        name="NextGen",
        vendor="NextGen Healthcare",
        sandbox_fhir_base=None,
        endpoint_directory="https://www.nextgen.com/patient-access-api",
        note="Ambulatory EMR; sandbox access granted on registration.",
    ),
    EmrProvider(
        key="veradigm",
        name="Veradigm (Allscripts)",
        vendor="Veradigm",
        sandbox_fhir_base=None,
        endpoint_directory="https://developer.veradigm.com/",
        note="Formerly Allscripts; sandbox access granted on registration.",
    ),
)

_BY_KEY = {p.key: p for p in TOP_PROVIDERS}


def get_provider(key: str) -> EmrProvider | None:
    return _BY_KEY.get(key)


def search_providers(query: str = "") -> list[EmrProvider]:
    """Case-insensitive match on key, name, or vendor; empty query returns all."""
    q = query.strip().lower()
    if not q:
        return list(TOP_PROVIDERS)
    return [
        p
        for p in TOP_PROVIDERS
        if q in p.key.lower() or q in p.name.lower() or q in p.vendor.lower()
    ]
