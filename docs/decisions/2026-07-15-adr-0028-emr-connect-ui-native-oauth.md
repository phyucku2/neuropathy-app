# ADR-0028 — Patient EMR-connect UI, per-provider client ids, and the native OAuth return path

- **Status:** Accepted (Wave 3, code portion)
- **Date:** 2026-07-15
- **Builds on:** ADR-0008/0009 (SMART flow + endpoints), ADR-0013/0020 (`emr_connect`
  capability gating), ADR-0022 (browser E2E DoD), ADR-0023/0025 (native shell; the
  OAuth handler deferral this ADR closes), ADR-0017 (token vault, single-use pending
  state), and `docs/emr/sandbox-registration-runbook.md` (the five code findings).

## Context

The backend EMR flow (connect → callback → pull → revoke) has existed since ADR-0009,
but no patient-facing UI ever called it, and the registration runbook surfaced code
mismatches that block two-vendor sandbox testing: one global `SMART_CLIENT_ID` for all
vendors (mismatch b), `openid fhirUser` requested but never read (mismatch a), a
bearer-authenticated callback no bare browser redirect can reach (mismatch d), and the
Wave-2 deferral of the native OAuth return handler (ADR-0025). This portion ships the
UI plus those code changes, so vendor registration is the ONLY remaining step before a
sandbox smoke test.

## Decisions

### 1. The callback relays through the authenticated SPA — the backend auth model is unchanged

`GET /emr/callback` stays bearer-authenticated + `emr_connect`-gated (ADR-0020). The
EMR's redirect lands on a NEW authenticated SPA route **`/emr/callback`** (inside
RequireAuth + PatientArea), which:

1. validates the echoed `state` against the pending handshake the connect flow
   persisted (`sessionStorage`, `neuropathy.emr_pending_connect`, keyed like the token
   store) — a mismatch is refused **without calling the backend**, so a forged link
   can never make the app relay an attacker-chosen code+state;
2. relays `code`+`state` to the backend callback with the patient's bearer attached
   (exactly once — the backend state is single-use, so the relay guards against
   StrictMode double-effects);
3. shows the activated connection (provider, status) with **Pull labs now** and a
   two-tap **Disconnect** (mirroring ConnectionRow), and a route back to Sources.

API failures surface the backend `detail` **verbatim** in a `role=alert` (the ADR-0013
convention — including the `emr_connect`-off 409 "This feature is turned off"), with a
retry-from-Sources hint. Alternative considered: make the backend callback anonymous
and bind it to the patient via the state — rejected; it would weaken the endpoint (an
unauthenticated PHI-adjacent action) for zero UX gain, since the patient returns to the
app either way.

**Deployment consequence (adversarial-review finding, fixed):** in the ADR-0018
one-origin topology `/emr/callback` is BOTH the SPA relay route and the backend API
route, and the nginx template's blanket `location /emr/` proxy would have handed the
EMR's bare redirect the backend's 401 JSON — the handshake could never complete in
production. `nginx.conf.template` now splits the exact path on the Authorization
header (no header → the SPA shell via `rewrite … last`, the documented-safe `if`
usage; bearer → proxied to the backend), locked by a template test in the backend
suite (`test_nginx_logging.py`). The registered `SMART_REDIRECT_URI` remains
`https://<origin>/emr/callback` — one URL serves both hops.

### 2. Connect UI in Sources, gated by the `emr_connect` capability as a UI hint

A "Health record connections" card on the Settings/Sources page, beside the clinic
connections (deliberately NOT in the danger zone): provider picker over
`GET /emr/providers` (the server-side search), Connect per provider →
`POST /emr/connect` → persist `{state, connectionId, providerName}` → open
`authorize_url`. Providers with no public sandbox render "Not available yet" instead of
a Connect that can only 422. When the patient's `emr_connect` toggle is off, the card
says so and hides the picker — a **UI hint only**; the server remains the authority
(ADR-0013) and its 409 renders verbatim if raced.

**Gap (recorded, deliberate):** the API has **no EMR-connections list endpoint** —
`/emr` exposes connect/callback/pull/revoke, and `GET /connections` is the *clinic*
connection list. The Sources card therefore starts connections and the post-connect
confirmation (with pull/revoke) lives on `/emr/callback`; previously-connected records
are not enumerable in the UI. Inventing a client-side ledger (e.g. caching connections
in storage) was rejected — it would drift from server truth (revocations, expiry). The
follow-up is a small backend `GET /emr/connections` + a card list, its own portion.

### 3. System-browser OAuth on native; full-page redirect on web

`openAuthorizeUrl` (src/native/externalBrowser.ts): on web, `window.location.assign`
(the standard SMART redirect; sessionStorage survives the same-tab round trip); on
native, the official **`@capacitor/browser@^6.0.6`** (MIT, Cap-6 line verified the
ADR-0024 way: its devDeps pin `@capacitor/cli` ^6 and `cap sync` is warning-free;
prod audit + license allowlist stay green). **Never the in-app WebView** — EMRs and
identity providers block WebView OAuth (RFC 8252), and the system browser keeps the
patient's portal session + password manager. The web navigation is injected so jsdom
tests stub it (ADR-0024 seam lesson).

### 4. Native return path: App Links preferred, custom scheme fallback

The ADR-0025 deferral closes: `initNativeShell` now registers an `@capacitor/app`
**`appUrlOpen`** listener (no new plugin — already installed) that parses the incoming
URL with the pure, unit-locked `appUrlPath` and routes the SPA router to its
path+query, so `https://<app-origin>/emr/callback?code=..&state=..` — or the
`com.ahwg.neuropathy://emr/callback?..` fallback — enters the SAME relay route as web.
Routing is internal-only (React Router); an unexpected path just hits the router's
catch-all. The custom-scheme VIEW intent-filter was added to `AndroidManifest.xml`
(the string resource already existed). The **App Links (https) intent-filter and
`/.well-known/assetlinks.json` are owner-side** — they need the deployed app origin and
the RELEASE cert SHA-256 (after the keystore exists): exact templates in
[`docs/mobile/emr-app-links.md`](../mobile/emr-app-links.md).

### 5. Per-provider client ids (runbook mismatch b)

Each registry entry (`app/emr/providers.py`) names its env-driven Settings field via
`client_id_env` (`SMART_CLIENT_ID_EPIC`, `SMART_CLIENT_ID_ORACLE_HEALTH`, …), and
`EmrService` gains `provider_client_ids`, keyed by provider **display name** — exactly
what a `ConnectionRecord` persists — so the SAME resolution runs on both handshake hops
(authorize URL and token exchange) **without a schema change or migration**; the
callback now loads the connection record *before* the token exchange for that reason.
The generic `SMART_CLIENT_ID` stays the fallback for custom `fhir_base` connects and
unconfigured vendors, so existing behavior and tests hold. Values are env-only, never
committed. A registry test locks every `client_id_env` to the
`SMART_CLIENT_ID_<KEY>` convention AND to a real Settings field, so a typo cannot
silently fall back.

### 6. Scope trim (runbook mismatch a)

`DEFAULT_SCOPES` is now exactly **`launch/patient patient/Observation.read
offline_access`**. `openid fhirUser` were dropped: `complete_callback` never reads the
id_token, so requesting identity scopes was a false disclosure on the EHR consent
screen; `patient/Patient.read` stays absent (the pull never fetches Patient). Re-adding
a scope happens only in the PR that adds its consumer. The unused `smart_scopes`
setting was **removed** — nothing read it, so an operator changing `SMART_SCOPES`
changed nothing (the enforced-flag-honesty rule applied to config). The scope set is
code, locked by test.

## Verification boundary (honest)

- **Verified here:** backend 100% coverage (ruff/mypy-strict/pytest incl. live
  Postgres); frontend tsc/eslint/prettier/vitest (coverage ≥90 all four) and the
  **31-spec browser E2E suite** (all green, zero console errors) driving the built
  bundle through the full round trip — Sources → connect → simulated EMR redirect →
  authenticated relay → pull → revoke; `cap sync` warning-free; prod audit + license
  allowlist clean; secret scan clean.
- **NOT verifiable here (user's registrations needed):** a REAL sandbox smoke test.
  Epic/Oracle sandbox client ids exist only after the user registers the app
  (runbook §1/§2) and sets `SMART_CLIENT_ID_*`; the E2E EMR is a same-origin mock
  mirroring the backend schemas, not fhir.epic.com. Likewise on-device App Links need
  the deployed origin + release-cert `assetlinks.json` (owner-side; see
  docs/mobile/emr-app-links.md) — the shipped custom-scheme filter and appUrlOpen
  routing are unit/compile-verified only.

## Consequences

- New frontend surface: `EmrConnectCard` (Sources), `EmrCallbackPage` (+ route),
  `pendingConnect` store, `externalBrowser` seam, `appUrlPath`/appUrlOpen in the native
  shell; `/emr` added to the dev-proxy prefixes (shared prefix handled like `/clinic`,
  ADR-0022 pattern).
- New dependency: `@capacitor/browser@^6.0.6` (official, MIT).
- Backend: per-provider client-id resolution (registry + Settings + service mapping),
  trimmed `DEFAULT_SCOPES`, callback loads the record before the exchange. No schema
  change, no migration.
- Wave 3 remainder is user-side: vendor registrations, sandbox smoke (runbook §5,
  now executable end-to-end in the app), then production enrollment.
