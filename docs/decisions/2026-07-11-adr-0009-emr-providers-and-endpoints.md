# ADR-0009: Top-EMR Provider Registry, Clinic Backend Auth, and API Wiring

**Date:** 2026-07-11
**Status:** Accepted (owner decision)
**Builds on:** ADR-0008 (SMART on FHIR patient pull).

## Context

Three directives:
1. Patient side supports login to the **top EMRs** out of the box.
2. The **clinic backend follows the EMR's standard login procedure** for system access.
3. The HTTP **endpoints get wired** so the flows are callable.

## Decision

### 1. Provider registry (patient side)
Ship a registry of the major US EMR vendors with patient-access FHIR support —
**Epic (MyChart), Oracle Health (Cerner), athenahealth, MEDITECH, NextGen, Veradigm** —
plus a custom-URL escape hatch for any other SMART-capable portal.

- Each entry: key, display name, vendor, **sandbox FHIR base** (where public),
  and the vendor's **production endpoint directory** (production FHIR bases are
  per-organization and resolved from those directories at registration time).
- Registry is data, not code logic — extending it is adding an entry.
- ⚠️ Sandbox URLs are point-in-time and must be re-verified when we register the app
  with each vendor (they change; registration is the per-vendor paperwork step).

### 2. Clinic backend auth = SMART Backend Services
For clinic/system-level access (scheduled pulls, no human in the loop), we implement
**SMART Backend Services** — the EMR-standard machine login:
- **OAuth2 `client_credentials`** with a **signed JWT client assertion** (RS384,
  `iss = sub = client_id`, `aud = token_endpoint`, short `exp`, unique `jti`).
- **`system/…` scopes**, least privilege (`system/Observation.read` for labs).
- The signing private key lives in the secret manager; never in the repo or DB.
For clinicians launching from inside an EHR session, the authorize-URL builder also
accepts SMART **EHR-launch context** (`launch` param + scope) — same code path as the
patient flow.

### 3. Endpoint wiring
New `emr` API router (mounted under `/emr`):
- `GET /emr/providers` — list/search the registry.
- `POST /emr/connect` — start a patient connection: SMART discovery → PKCE →
  returns the authorize URL to open.
- `GET /emr/callback` — OAuth redirect target: validates `state`, exchanges the code,
  stores tokens in the secret store, activates the connection.
- `POST /emr/connections/{id}/pull` — fetch + parse the patient's lab Observations.
- `DELETE /emr/connections/{id}` — patient revokes the connection.

**Persistence posture (deliberate):** the service layer uses **in-memory
repositories + an in-memory secret store behind the same interfaces** the Postgres/
secret-manager implementations will use. The HTTP contract, OAuth flow, and parsing are
real and fully tested; swapping storage is an implementation change, not an API change.
**Auth on our own endpoints is a placeholder** (patient_id passed explicitly) until the
app-auth ADR lands — flagged, not hidden.

## Consequences
- New deps: `httpx` (async HTTP; BSD) and `pyjwt[crypto]` (JWT signing; MIT +
  Apache/BSD `cryptography`) — permissive per CLAUDE.md §4.
- Real network transport (`HttpxTransport`) implemented and unit-tested via httpx's
  MockTransport; endpoint tests inject fakes (no network in CI).
- Follow-ups: vendor app registrations (per-EMR paperwork), token-refresh job,
  DB-backed repositories, app auth, per-org endpoint resolution from vendor directories.

## Options considered
- **Aggregator services (1upHealth/Particle/Flexpa-style) for EMR connectivity:**
  faster org coverage, but adds a PHI-handling vendor, per-record costs, and BAA
  complexity — revisit if direct registrations prove too slow. Direct SMART chosen.
- **Custom clinic credentials (username/API key):** rejected — Backend Services is the
  standard EMRs actually offer and audit.
