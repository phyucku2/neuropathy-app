# ADR-0008: Patient EMR Data Pull via SMART on FHIR

**Date:** 2026-07-11
**Status:** Accepted (owner decision)

## Context

Patients want to **log into their EMR / patient portal and pull their data** (labs
first) directly into the app, rather than only uploading PDFs. The recognized standard
for a patient-authorized app reading from an EHR is **SMART on FHIR** (SMART App Launch)
over OAuth2/OIDC, returning **FHIR R4** resources — which our lab mapping already parses.

## Decision

Support **SMART on FHIR standalone patient launch**:

1. **Discovery.** From the EHR's FHIR base URL (`iss`/`aud`), read
   `/.well-known/smart-configuration` to get `authorization_endpoint` and
   `token_endpoint`.
2. **Authorization.** OAuth2 **authorization-code flow with PKCE** (S256). Scopes for a
   patient reading labs: `launch/patient patient/Observation.read openid fhirUser
   offline_access`. `state` for CSRF; `aud` set to the FHIR base.
3. **Token exchange.** Exchange the code (+ PKCE `code_verifier`) for access/refresh
   tokens and the granted `patient` id.
4. **Fetch.** `GET {fhirBase}/Observation?patient={id}&category=laboratory`, page through
   the returned **Bundle**, and parse with the existing `bundle_from_fhir` mapping.
5. **Persist** as research-grade Observations with `origin = ehr_imported` (authoritative
   — no OCR confirmation step needed, unlike an uploaded PDF).

## Security & privacy

- **Patient-authorized.** The patient consents at their own EHR; we act on their behalf.
- **Token handling.** Access/refresh tokens are **secrets**: encrypted at rest in a
  secret manager and referenced from the DB by `token_ref` — never stored in plaintext
  columns and never logged. Tokens refreshed via `offline_access` where granted.
- **PKCE + state** on every launch; exact-match redirect URIs; `aud` validated.
- **Least scope.** Request only what's needed (labs → `patient/Observation.read`);
  broaden per feature, never blanket `patient/*.read`.
- This is a per-patient data-source connection (like `ClinicConnection` for clinics):
  modeled as an `EmrConnection` with lifecycle + revocation, audit-logged.

## Consequences

- New `app/emr/` module: SMART discovery + PKCE authorize-URL + token-request builders
  (pure, tested), and an `EmrClient` (pluggable async transport) that fetches and parses
  lab Observations.
- `EmrConnection` model: provider iss, status, granted scope, `patient_fhir_id`,
  `token_ref`, `token_expires_at` — no raw tokens in the DB.
- `DataOrigin.ehr_imported` added so EMR-sourced labs are distinguishable (and trusted)
  vs. OCR'd uploads.
- Config gains SMART client id / redirect URI / default scopes (env-driven, no secrets
  committed).
- **Not yet:** live end-to-end against a specific EHR sandbox (Epic/Cerner), refresh-token
  rotation job, and dynamic client registration — follow-ups requiring credentials +
  network.

## Options considered

- **Manual upload only:** rejected — the owner wants direct EMR pull; uploads remain as
  a fallback for portals without SMART.
- **Screen-scraping / credential storage:** rejected — insecure and against portal
  terms; SMART/OAuth is the standard and never sees the patient's EHR password.
- **SMART on FHIR standalone patient launch:** chosen.
