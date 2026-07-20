# EMR sandbox registration runbook — Epic & Oracle Health (Cerner)

> ⚠️ **Operational guide — vendor terms, portals, and URLs change.** Everything here was
> researched 2026-07-14 against the sources cited inline. **Re-verify each step at
> execution time**, especially costs, program names, and redirect-URI policies. Items
> that could not be confirmed from a primary source are marked **UNVERIFIED**.

This is the operator runbook for Wave 3 ([roadmap](../roadmap-status.md)): registering
the app with Epic's and Oracle Health's developer programs so the SMART on FHIR patient
pull (ADR-0008/0009) runs against real sandboxes. It is docs-only; required code changes
it surfaces are listed in the [checklist](#7-checklist) as `code change`.

---

## 0. What our code actually does (ground truth for every form below)

Read before filling in any vendor form — register what the code *is*, not what the ADR
aspires to.

- **Flow:** SMART **standalone launch, patient context**, OAuth2 **authorization-code +
  PKCE (S256)**. Confirmed in `backend/app/emr/service.py::start_connect` — it never
  passes `launch`, so `build_authorize_url` (`backend/app/emr/smart.py`) builds a
  standalone-launch URL with `aud` = FHIR base, `state`, and an S256 challenge. This is
  **not** an EHR launch.
- **Scopes the code requests** (`DEFAULT_SCOPES` in `backend/app/emr/smart.py`):
  `launch/patient patient/Observation.read offline_access` (SMART **v1** scope syntax).
  `openid fhirUser` were dropped 2026-07-15 (ADR-0028 — mismatch (a) resolved:
  least-privilege; the id_token was never read).
- **Resources the pull actually reads** (`backend/app/emr/client.py`): only
  `GET {fhirBase}/Observation?patient={id}&category=laboratory` + Bundle `next` paging.
  **No other resource is fetched — not even Patient.** The patient's FHIR id comes from
  the `patient` field of the token response (that's what `launch/patient` is for), and
  `service.py::pull_labs` hard-requires it (409 without it).
- **FHIR version:** R4 (registry bases in `backend/app/emr/providers.py` are R4; lab
  mapping per ADR-0007).
- **Client type:** **PUBLIC client — no client secret anywhere.**
  `build_token_request` sends only `client_id` + `code_verifier`; there is no
  `client_secret` parameter or config field. Register as a public/PKCE app.
- **Redirect URI:** the **backend** route `GET /emr/callback`
  (`backend/app/api/routes/emr.py`), configured via `SMART_REDIRECT_URI`
  (`backend/.env.example`, fallback `http://localhost:8000/emr/callback` in
  `backend/app/api/deps.py::_smart_client_config`).

### Minimal scope set (derived from the code) and mismatches

| Scope | Needed by code? | Why |
|---|---|---|
| `patient/Observation.read` | **Yes** | The only resource the pull reads. |
| `launch/patient` | **Yes** | Standalone launch patient-context; `pull_labs` requires the token response's `patient` id. |
| `offline_access` | **Yes (intent)** | `complete_callback` vaults `refresh_token` when returned — but see mismatch (c). |
| `openid` + `fhirUser` | **No — and no longer requested** | ADR-0028 dropped them (mismatch (a) resolved): `complete_callback` never reads an `id_token`. Re-add only with a consumer. |
| `patient/Patient.read` | **No** | Code never fetches Patient; demographics aren't used. Do **not** add it just because tutorials do. |

**Mismatches to resolve (flagged, not fixed here):**

1. **(a) `openid fhirUser` requested but unused.** ✅ **RESOLVED (ADR-0028,
   2026-07-15):** dropped from `DEFAULT_SCOPES` — the code and the registration now
   agree on `launch/patient patient/Observation.read offline_access`. If a future
   identity check needs the id_token, the scope returns in the PR that reads it.
2. **(b) One `SMART_CLIENT_ID` for all providers.** ✅ **RESOLVED (ADR-0028,
   2026-07-15):** every registry entry now carries `client_id_env`
   (`SMART_CLIENT_ID_EPIC`, `SMART_CLIENT_ID_ORACLE_HEALTH`, …, mapped to Settings
   fields; see `backend/.env.example`), and both handshake hops resolve the
   connection's provider id with the generic `SMART_CLIENT_ID` as the
   custom-fhir_base/unconfigured fallback. Values stay env-only, never committed.
3. **(c) `offline_access` without a refresh implementation.** The refresh-token rotation
   job is a recorded follow-up (ADR-0008); until it exists, pulls fail after access-token
   expiry and the patient must re-link. Also see Epic's refresh-token caveat in §1.4.
4. **(d) The callback requires OUR bearer auth.** ✅ **RESOLVED (ADR-0028,
   2026-07-15):** the backend callback stays bearer-authenticated (unchanged, by
   design), and the shipped connect UI provides the relay — the SPA's authenticated
   `/emr/callback` route validates the echoed `state` against the pending handshake it
   persisted and forwards `code`+`state` with the patient's token. On Android the
   redirect re-enters the app via App Links / the custom-scheme fallback
   (`docs/mobile/emr-app-links.md`). The §5 manual relay still works for curl-level
   smoke tests.

---

## 1. Epic

> **✅ Status (2026-07-19): the app IS registered in the Epic sandbox** (app name "Advanced
> Health and Wellness Group", **Draft** state — which is the normal, correct state for a
> non-production/sandbox app). The **Non-Production Client ID** was issued and wired into the
> live backend (`SMART_CLIENT_ID_EPIC`, via env on the staging deployment — value is env-only,
> never committed). The settings that worked on the "Create an App" form:
> - **Application Audience:** Patients · **Automatic Client Distribution:** None (USCDI v1 is
>   the production auto-distribution lever, revisit at go-live)
> - **Incoming APIs:** `Observation.Read (Labs) (R4)` only (matches `patient/Observation.read`
>   + the `category=laboratory` query — least privilege)
> - **SMART on FHIR Version:** R4 · **SMART Scope Version:** SMART v1 · **FHIR ID Scheme:**
>   Unconstrained · **Confidential Client:** **unchecked** (we are a PUBLIC/PKCE client) ·
>   **Dynamic Clients:** unchecked
> - **Endpoint URI (redirect):** the **public frontend** origin + `/emr/callback` (byte-exact),
>   NOT the internal backend — the browser lands on the frontend, whose nginx proxies
>   `/emr/callback` to the backend (ADR-0028 / deploy-azure §8a).
> - Saved with **"Save & Ready for Sandbox"** (NOT production — production is irreversible and
>   makes the app un-editable + customer-visible).
>
> **⚠️ The ~1-hour sync gotcha (verified live):** immediately after registering/wiring the
> client, an Epic authorize attempt returns **"OAuth2 Error — Something went wrong trying to
> authorize the client."** This is Epic's sandbox client-sync lag (records sync on a schedule,
> ~1h), **not** a bug — our authorize request was verified to carry the correct
> `client_id`/`redirect_uri`/`scope`/`aud`/PKCE. Wait ~1h and retry the same Connect flow.
> **Production checklist still open:** Terms & Conditions secure URL, Privacy/disclosure URL,
> the 2 Data Use Questionnaires, screenshots + thumbnail, accepting open.epic terms of use.

### 1.1 Program signup

- **Portal:** [fhir.epic.com](https://fhir.epic.com/) ("Epic on FHIR"). Create a
  developer account, then apps under
  [fhir.epic.com/Developer/Apps](https://fhir.epic.com/Developer/Apps).
- **Cost:** the Epic on FHIR program is a **free resource** for building patient- and
  provider-facing apps; the R4 sandbox and the USCDI-read APIs (which cover our
  `Patient`/`Observation` labs surface) are free. Paid tiers exist beyond the
  standardized floor (write-back, bulk at scale, "Showroom"/Vendor Services
  sponsorship) — not needed for this app today. Sources:
  [fhir.epic.com](https://fhir.epic.com/),
  [open.epic Developer Resources](https://open.epic.com/DeveloperResources).
  **Re-verify tier boundaries at signup — Epic reorganized its programs (open.epic /
  Vendor Services) and terms move; exact current gating: UNVERIFIED.**
- **Identity/org info:** account signup asks for developer identity and organization
  details (company name, contact). Exact current field list: **UNVERIFIED** (behind
  login). No DUNS or fee required for sandbox per the sources above.
- **Lead time:** account is immediate; after an app is created and marked ready for
  sandbox, secondary sources report the non-production client_id goes live against the
  sandbox in **about an hour** (Epic syncs client records on a schedule) —
  **approximate, UNVERIFIED against primary docs**. Plan for "same day".

### 1.2 App registration (the form)

- **Application audience:** **Patients** (patient-facing). This selects
  patient-standalone launch usable from MyChart-linked logins.
- **APIs/resources to select:** Epic's form works by selecting FHIR APIs, not by typing
  scope strings. Select **Observation.Read (Labs) (R4)** — Epic splits Observation by
  category; pick the Labs flavor(s). Select nothing else (see §0: no Patient read).
  If the form versions differ, match each selected API to R4.
- **SMART version / scopes:** our code sends SMART v1 syntax
  (`patient/Observation.read`); Epic supports v1 and v2 styles. Keep v1 unless the form
  forces v2 (`patient/Observation.rs`).
- **OAuth details:** authorization-code with **PKCE (Epic supports PKCE since its
  August 2019 version; required for public clients)**; standalone launch;
  `aud` required on the authorize request (our `smart.py` sends it).
- **Client type:** public / native — **do NOT generate a client secret** (§0). See §1.4
  for the refresh-token consequence.
- **What you get:** **two client ids on the app record — a Non-Production Client ID
  (use against the sandbox) and a Production Client ID** (only works in production
  environments after go-live steps). Source: Epic client-ID background
  ([open.epic Client ID tutorial PDF](https://open.epic.com/Tech/GetTechSpec?spec=Client+ID+tutorial.pdf))
  and [fhir.epic.com/Documentation](https://fhir.epic.com/Documentation).
- **Sandbox FHIR base** (already in `providers.py`):
  `https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4` — re-verify on the
  sandbox docs page at registration time.

### 1.3 Redirect URIs to register

- **Web/backend (the one our code needs):**
  `https://<deployed-backend-origin>/emr/callback` — exact, fully qualified; Epic does
  exact-match. For local sandbox testing you may also register a localhost URI if the
  form allows (`http://localhost:8000/emr/callback`) — **whether Epic's form accepts
  plain-http localhost: UNVERIFIED**; if not, tunnel (e.g. an https dev tunnel) and
  register that.
- **Native Android:** see §3 — with our backend-callback architecture the *OAuth*
  redirect_uri stays the backend https URL even on Android; register only that unless
  §3's option B is chosen.

### 1.4 Credentials that come back, and where they go

- **Client secret: none** for a public/PKCE app — matches our token request exactly.
- **Epic refresh-token caveat:** Epic's docs/tooling tie refresh tokens to client
  authentication — the fhir.epic.com site can *generate a client secret* "to obtain
  refresh tokens". Whether Epic issues refresh tokens to a **secretless PKCE public
  client** requesting `offline_access` is **UNVERIFIED** (secondary sources conflict;
  see [Epic OAuth2 docs](https://fhir.epic.com/Documentation?docId=oauth2) §offline
  access, and community threads). **Test this explicitly in the sandbox**; if Epic
  requires a secret for refresh, our options are (i) accept short sessions + re-link,
  or (ii) become a confidential client for Epic only (code change: secret in the
  secret store, `client_secret_basic` on token requests). Do not silently add a secret.
- **Where config goes:**
  - `SMART_CLIENT_ID` (or per-provider variant per mismatch (b)) ← Epic
    **Non-Production Client ID** for sandbox; Production Client ID later.
  - `SMART_REDIRECT_URI` ← the registered callback URL.
  - `providers.py` `epic` entry: `sandbox_fhir_base` already set; re-verify. Production
    per-org bases come from `endpoint_directory`
    ([open.epic Endpoints](https://open.epic.com/MyApps/Endpoints)) later.
  - **No real credential values are ever committed** — `.env` only
    (`backend/.env.example` pattern; client_ids are low-sensitivity but stay env-driven).

### 1.5 Sandbox test patients

Epic publishes sandbox test data at
[fhir.epic.com/Documentation?docId=testpatients](https://fhir.epic.com/Documentation?docId=testpatients).
For **patient-standalone (MyChart) logins** the commonly documented accounts are:

| Patient | MyChart username | Password |
|---|---|---|
| Camila Lopez | `fhircamila` | `epicepic1` |
| Derrick Lin | `fhirderrick` | `epicepic1` |
| Desiree Powell | `fhirdesiree` | `epicepic1` |

Camila Lopez is widely reported to have populated lab Observations. **Exact current
credentials, FHIR ids, and which patients carry `category=laboratory` Observations:
verify on the testpatients page at execution time (page requires login; the above are
from secondary sources — UNVERIFIED).**

### 1.6 Production enrollment (brief)

- Developer marks the app **ready for production**; the Production Client ID then
  becomes usable. For eligible patient-facing apps Epic supports **automatic client-ID
  distribution** to community members that enable auto-download; otherwise orgs
  sync/approve the client id per organization (developer can approve org requests
  directly). Source: [Client ID tutorial](https://open.epic.com/Tech/GetTechSpec?spec=Client+ID+tutorial.pdf).
- **Listing:** [Connection Hub](https://fhir.epic.com/ConnectionHub) is Epic's
  self-reported directory of live-connected apps (free, vendor-reported, not reviewed
  by Epic). Deeper partnership/marketing tiers (Showroom/Vendor Services) cost money —
  not required for patient access.
- **Per-org endpoints:** resolve each org's production R4 base from
  [open.epic Endpoints](https://open.epic.com/MyApps/Endpoints) (our
  `endpoint_directory`).
- **Prerequisites we don't meet yet:** a deployed backend with a **stable HTTPS
  origin** (the registered redirect URI), privacy policy URL, and the per-provider
  client-id config (mismatch (b)). Realistic lead time once marked live: days (auto
  distribution) to weeks (org-by-org), **UNVERIFIED**.

---

## 2. Oracle Health (Cerner)

### 2.1 Program signup

- **Portal:** [code-console.cerner.com/console](https://code-console.cerner.com/console)
  (Oracle Health **code Console**), under the
  [Oracle Health Developer Program](https://www.oracle.com/health/developer/).
- **Account:** a free **Cerner Care account** (created on first use of code Console).
  Source: [Oracle SMART developer overview](https://docs.oracle.com/en/industries/health/millennium-platform-apis/smart-developer-overview/).
- **Cost:** the sandbox is **freely accessible**; no fee to register an app for
  sandbox. Production/partnership fee structure under the Oracle Health Developer
  Program: **UNVERIFIED — confirm current terms**; the Cures-Act patient-access surface
  should not require paid partnership, but Oracle's program packaging changes.
- **Lead time:** account + sandbox app registration are self-service, same day.

### 2.2 App registration

- **In code Console → register a new application:**
  - **Application type / persona:** **Patient** (consumer-facing), **standalone
    launch** (Oracle supports `launch/patient` on standalone so the user selects/is
    bound to a patient at authorization — exactly our flow).
  - **Application privacy:** **Public** (browser/native app, no secret). Confidential
    clients get a secret; public clients authenticate with **PKCE** instead. Oracle
    **requires PKCE (S256) for SMART v2 scopes** and advertises it in
    `/.well-known/smart-configuration`; our code always sends PKCE, which is fine for
    v1 too. Source: [Millennium authorization framework](https://docs.oracle.com/en/industries/health/millennium-platform-apis/millennium-authorization-framework/).
  - **FHIR spec:** R4. **Scopes:** tick exactly `launch/patient`,
    `patient/Observation.read`, `offline_access` (the ADR-0028 trimmed set — no
    `openid`/`fhirUser`; v1 syntax, v2 equivalent is `patient/Observation.rs`). **No
    wildcard scopes exist at Oracle — each scope is explicit.** Note `offline_access` refresh tokens are auto-revoked
    after **3 months of disuse**. Same source.
  - **Redirect URI:** see §2.3. If multiple URIs are registered, `redirect_uri` must be
    sent on both authorize and token requests — our code always sends it on both
    (`smart.py`), so registering several is safe.
- **What you get:** a **client_id per environment/tenant**; **public apps get NO
  client secret** (verified stance: public clients rely on PKCE; secrets are for
  confidential clients only). The sandbox tenant already in `providers.py` is
  `ec2458f2-1e24-41c8-b71b-0e701af7583d`
  (`https://fhir-ehr-code.cerner.com/r4/ec2458f2-...`) — re-verify in the console.
- **`aud` is mandatory** — Oracle's authorization server rejects requests without it
  (our code sends it).

### 2.3 Redirect URIs

- **Web/backend:** `https://<deployed-backend-origin>/emr/callback`. HTTPS is the norm
  for browser apps; localhost/http for sandbox testing: **UNVERIFIED — check the
  console's validation**.
- **Native:** Oracle **explicitly supports custom URI schemes for native apps** (e.g.
  `sample.application://callback` — something must follow `://`), per the
  [authorization framework](https://docs.oracle.com/en/industries/health/millennium-platform-apis/millennium-authorization-framework/)
  and the [cerner-fhir-developers thread](https://groups.google.com/g/cerner-fhir-developers/c/SwC0JZ2ucRs)
  ("only explicit internet hosts or explicit URI activation schemes"). Community
  reports of token-exchange `redirect_uri is invalid` hiccups with custom schemes
  exist — test early. Android App Links (https) fall under "explicit internet hosts"
  and are accepted as ordinary https URIs.

### 2.4 Credentials → our config

- `SMART_CLIENT_ID_ORACLE_HEALTH` (per mismatch (b)) ← console client_id (sandbox).
- `SMART_REDIRECT_URI` ← registered callback.
- `providers.py` `oracle-health` entry: `sandbox_fhir_base` re-verified; production
  per-org bases from `endpoint_directory`
  ([github.com/cerner/ignite-endpoints](https://github.com/cerner/ignite-endpoints)).
- **No secret exists; nothing secret-shaped to store.** No credentials committed.

### 2.5 Sandbox test patients

- Patients live in the shared sandbox tenant; for our flow you need **patient-persona
  portal credentials**, which code Console surfaces when you use **"Begin Testing"** on
  your app (it shows the username/password to use, and lets you pick a patient in
  context). Provider-standalone testing uses `portal`/`portal`. Sources:
  [Cerner SMART on FHIR tutorial](https://engineering.cerner.com/smart-on-fhir-tutorial/),
  cerner-fhir-developers group threads.
- Specific well-known patient logins (e.g. the "SMART/Nancy Smart" family) are listed
  in the developer-group's pinned posts and inside the console — **exact current
  usernames/passwords: UNVERIFIED here; read them off "Begin Testing" at execution
  time.** Confirm the chosen patient has `category=laboratory` Observations before
  smoke-testing (query the open sandbox endpoint or the console's patient list).

### 2.6 Production enrollment (brief)

- Create the app **against the production cloud environment** in code Console (separate
  from sandbox registration) → production client_id/app_id.
- **Per-customer provisioning:** each Oracle Health customer enables your app for their
  Millennium domain/tenant (customer logs a service request; RHO/CHO flows differ) —
  see [SMART application provisioning](https://docs.oracle.com/en/industries/health/millennium-platform-apis/smart-app-provisioning/).
  Patient-access apps benefit from Cures-Act information-blocking rules, but the
  per-tenant provisioning mechanics still apply. **Whether patient-facing apps get
  blanket enablement without per-org action: UNVERIFIED.**
- Secondary-source timelines: sandbox build-out 4–8 weeks, customer security review
  2–4 weeks per org (**estimates, UNVERIFIED**).
- **Prerequisites we don't meet yet:** deployed stable-HTTPS backend, per-provider
  client-id config, privacy policy, and a customer org to provision against.

---

## 3. Native Android redirect story (feeds the Wave 3 native OAuth handler)

Repo facts: Android app id **`com.ahwg.neuropathy`**
(`frontend/capacitor.config.ts`, permanent per ADR-0023) and
`frontend/android/app/src/main/res/values/strings.xml` carries
`custom_url_scheme=com.ahwg.neuropathy`. (An older working note calling the app id
`com.ahwg.neuropathy` is wrong — the shipped, permanent id is `com.ahwg.neuropathy`.)

**Key architectural point:** in our flow the *vendor-registered* `redirect_uri` is the
**backend's** `https://…/emr/callback` — the backend holds the PKCE verifier and does
the token exchange (`service.py`). The app-scheme/App-Link question is therefore about
the **second hop**: how the browser gets the patient *back into the Android app* after
the callback completes. Two designs:

- **Option A (recommended, current architecture):** register **only the backend https
  callback** with Epic/Oracle. Native flow: connect UI opens the authorize URL in the
  system browser (Custom Tab) → EHR redirects to our backend `/emr/callback` → backend
  page/redirect deep-links back into the app. For that final hop prefer **Android App
  Links** (`https://<our-domain>/…` + `/.well-known/assetlinks.json` binding the domain
  to `com.ahwg.neuropathy`'s signing cert): not user-hijackable, no interstitial
  chooser, and vendor policy is irrelevant because vendors never see it. The custom
  scheme (`com.ahwg.neuropathy://…`) stays as a fallback for devices where App Links
  verification fails. Note mismatch (d): the callback must become reachable from a bare
  browser redirect for this to work — part of the Wave 3 build.
- **Option B (in-app token exchange — NOT our design):** the app itself would be the
  OAuth client and the vendor-registered redirect must reach the app directly. Vendor
  acceptance: **Oracle Health explicitly accepts custom schemes** (verified, §2.3) and
  https hosts (App Links). **Epic:** secondary sources say custom schemes are accepted
  and claimed-https links are preferred; **primary confirmation UNVERIFIED** — check
  the redirect-URI validation in the fhir.epic.com app form. If Option B is ever
  chosen, use **App Links where accepted, custom scheme only as fallback** (RFC 8252
  guidance both vendors' docs echo).

**Recommendation:** Option A. Register only the backend https redirect with both
vendors; build the Wave 3 native handler on App Links with the existing custom scheme
as fallback.

---

## 4. Where every value lands in our config

| Value from vendor | Our home | Notes |
|---|---|---|
| Epic Non-Production Client ID | env `SMART_CLIENT_ID` (today) → per-provider env after mismatch (b) fix | never committed |
| Epic Production Client ID | same slot, production env only | |
| Oracle sandbox client_id | per-provider env (needs mismatch (b) fix) | never committed |
| Redirect URI (as registered) | env `SMART_REDIRECT_URI` | must byte-match registration |
| Sandbox FHIR bases | `backend/app/emr/providers.py` `sandbox_fhir_base` | already present; re-verify both |
| Production per-org FHIR bases | resolved later from `endpoint_directory` entries | per-org, at production enrollment |
| Client secrets | **none — public PKCE client for both vendors** | if Epic forces a secret for refresh tokens, that's a deliberate ADR-level change, not a config tweak |

> **On Azure**, these env vars are wired as optional Bicep params (`smartClientIdEpic`,
> `smartClientIdOracleHealth`, …, `smartRedirectUri`) → Container Apps secrets — see
> `docs/ops/deploy-azure.md` §8a. The redirect URI to register is the **public frontend
> origin + `/emr/callback`** (the frontend reverse-proxies it to the internal backend); the
> deployment output `suggestedSmartRedirectUri` prints the exact value.

---

## 5. Smoke test (sandbox, per vendor)

Prereqs: backend running with `SMART_CLIENT_ID*` + `SMART_REDIRECT_URI` set; a patient
account + bearer token on OUR app (`/auth` flow); `emr_connect` capability on (default).

1. `GET /emr/providers?q=epic` (or `oracle`) — confirm the registry entry and
   `sandbox_fhir_base`.
2. `POST /emr/connect` with bearer auth, body `{"provider_key": "epic"}` (or
   `"oracle-health"`) → returns `connection_id`, `authorize_url`, `state`.
3. Open `authorize_url` in a browser. Log in as the vendor sandbox test patient
   (§1.5 / §2.5), approve the requested scopes. **Check the consent screen lists
   exactly our scope set** — a scope silently dropped here is how mismatch (a)/(c)
   shows up in the granted scope.
4. The browser lands on `SMART_REDIRECT_URI` with `?code=…&state=…`. Because the
   callback requires our auth (mismatch (d)), copy those params and relay:
   `curl -H "Authorization: Bearer $TOKEN" "$API/emr/callback?state=…&code=…"` →
   expect 200, `status: active`, a `patient_fhir_id`, and `granted_scope` — diff
   `granted_scope` against what we requested and record any vendor-side narrowing.
5. `POST /emr/connections/{connection_id}/pull` with bearer auth → expect 200 with
   fetched/imported counts > 0 for a lab-bearing test patient; re-run to confirm
   idempotency (imported=0 on the second pull).
6. `DELETE /emr/connections/{connection_id}` → revoked; confirm a subsequent pull 409s.

Failure worth expecting: Epic sandbox returning **no refresh_token** to our secretless
client despite `offline_access` (§1.4) — record the token response shape (minus values).

## 6. Production enrollment delta (both vendors, summary)

Sandbox → production changes: production client_id (Epic: second id on the same app,
marked live; Oracle: separate production-cloud registration), per-organization FHIR
bases from each vendor's endpoint directory, per-org enablement (Epic auto-distribution
where enabled / org sync approvals; Oracle per-tenant provisioning service requests),
and a **stable HTTPS deployed backend** whose origin is the registered redirect URI.
Listing (Epic Connection Hub; Oracle marketplace equivalent — **UNVERIFIED**) is
optional for patient access. Do not start production paperwork until the §7 `user`
items above the line are done.

## 7. Checklist

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | Create Epic on FHIR developer account (fhir.epic.com) | user | ☐ |
| 2 | Create Cerner Care account + code Console access | user | ☐ |
| 3 | Register Epic app (Patients audience, R4 Observation-Labs read, PKCE public, backend https redirect) | user | ☐ |
| 4 | Register Oracle Health app (Patient persona, Public, standalone, scope set §0, backend https redirect) | user | ☐ |
| 5 | Record sandbox client_ids into env (never committed) | user | ☐ |
| 6 | Re-verify both `sandbox_fhir_base` values in `providers.py` against the portals | user + code change (if drifted) | ☐ |
| 7 | Per-provider client_id support (mismatch (b)) | code change | ✅ ADR-0028 (`SMART_CLIENT_ID_<VENDOR>` env per registry entry) |
| 8 | Decide & align `openid fhirUser` (mismatch (a)) | code change + ADR note | ✅ ADR-0028 (dropped; scope set = §0 minimal set) |
| 9 | Callback reachable from a bare browser redirect / connect-UI relay (mismatch (d)) — part of Wave 3 connect UI | code change | ✅ ADR-0028 (SPA `/emr/callback` relay; backend auth unchanged) |
| 10 | Native handler: App Links (`assetlinks.json` for `com.ahwg.neuropathy`) + custom-scheme fallback (§3 Option A) | code change | ✅ code (ADR-0028: appUrlOpen + scheme filter) / ☐ owner: serve `assetlinks.json` + https intent-filter once origin+keystore exist (`docs/mobile/emr-app-links.md`) |
| 11 | Run §5 smoke test vs Epic sandbox; record `granted_scope` + refresh-token outcome | user | ☐ |
| 12 | Run §5 smoke test vs Oracle sandbox; same records | user | ☐ |
| 13 | Refresh-token rotation job (mismatch (c)) — informed by #11/#12 outcomes | code change | ☐ |
| 14 | Deployed backend with stable HTTPS origin (prereq for production redirect URIs) | user + ops | ☐ |
| 15 | Production enrollment (Epic mark-live/distribution; Oracle production registration + per-tenant provisioning) | user | ☐ |

## Sources

Primary: [fhir.epic.com](https://fhir.epic.com/) · [fhir.epic.com/Developer/Apps](https://fhir.epic.com/Developer/Apps) ·
[Epic OAuth2 docs](https://fhir.epic.com/Documentation?docId=oauth2) ·
[Epic test patients](https://fhir.epic.com/Documentation?docId=testpatients) ·
[Epic Connection Hub](https://fhir.epic.com/ConnectionHub) ·
[open.epic Client ID tutorial (PDF)](https://open.epic.com/Tech/GetTechSpec?spec=Client+ID+tutorial.pdf) ·
[open.epic Developer Resources](https://open.epic.com/DeveloperResources) ·
[open.epic Endpoints](https://open.epic.com/MyApps/Endpoints) ·
[Oracle Millennium authorization framework](https://docs.oracle.com/en/industries/health/millennium-platform-apis/millennium-authorization-framework/) ·
[Oracle SMART developer overview](https://docs.oracle.com/en/industries/health/millennium-platform-apis/smart-developer-overview/) ·
[Oracle SMART app provisioning](https://docs.oracle.com/en/industries/health/millennium-platform-apis/smart-app-provisioning/) ·
[Oracle Health code Console](https://code-console.cerner.com/console) ·
[Oracle Health Developer Program](https://www.oracle.com/health/developer/) ·
[Cerner SMART on FHIR tutorial](https://engineering.cerner.com/smart-on-fhir-tutorial/) ·
[cerner-fhir-developers: custom-scheme redirects](https://groups.google.com/g/cerner-fhir-developers/c/SwC0JZ2ucRs) ·
[cerner/ignite-endpoints](https://github.com/cerner/ignite-endpoints).
Secondary (used only where marked): community threads and integration guides for Epic
sandbox credentials, sandbox sync timing, and production timelines.
