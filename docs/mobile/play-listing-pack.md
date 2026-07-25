# Play Store listing pack (health app)

Drafted from the app's ACTUAL data flows (verified against the codebase at ADR-0026 time).
Anything marked **[verify]** must be re-checked at submission time — a listing answer that
drifts from the shipped app is a Play policy violation. This is preparation material, not
legal or regulatory advice; the privacy policy and health claims need counsel review.

## 1. App content declarations

- **Category:** Medical
- **Health apps declaration:** declare as a health & wellness / medical app. The app is a
  **non-diagnostic tracking and decision-support tool** — it must NOT be described anywhere
  in the listing as diagnosing, treating, or preventing disease (this also matches the
  in-app non-diagnostic disclaimers, ADR-0016).
- **Target audience:** 18+ (not directed at children — avoids Families policy scope).
- **Login credentials for review:** provide a synthetic demo account (never a real
  patient account).

## 2. Data Safety form — draft answers

Grounded in the shipped flows; the form asks per data type: collected? shared? processed
ephemerally? required? purpose.

| Data type | Collected? | Shared with third parties? | Notes (source of truth) |
|---|---|---|---|
| Personal info → Name | Yes | No | display_name at registration |
| Personal info → Email | Yes | No | account identity (ADR-0010) |
| Health info | Yes | No | ADL check-ins, lab results (FHIR/LOINC), balance/gait report data, trajectory outputs |
| Financial info | No | — | nothing collected |
| Location | No | — | nothing collected |
| Contacts / photos / files | No | — | PDF report upload is user-initiated file selection, contents become Health info [verify wording in form's file-access follow-up] |
| App activity / diagnostics | No | — | **[verify]** PHI-free server metrics are operational, not user analytics; no client-side analytics SDK exists — keep it that way or update this row |
| Device IDs / advertising ID | No | — | no ads, no ad SDKs — the manifest must never gain AD_ID [verify at each release] |

Cross-cutting answers:

- **Encryption in transit:** Yes — TLS only (`allowMixedContent:false`, no cleartext).
- **Encryption at rest (device):** refresh token in Android Keystore-backed secure storage
  (ADR-0024); `allowBackup=false` so app data is excluded from OS backups (ADR-0023).
- **Deletion mechanism:** **SHIPPED** (ADR-0027). In-app: Settings → Danger zone →
  "Delete my account" (password re-entry + acknowledgment + two-tap confirm). API:
  `DELETE /auth/me`. Deletes the account and ALL health data transactionally (EMR
  connections + vaulted tokens, clinic connections, toggles, observations, the patient
  record); PHI-free audit events are retained anonymized (regulatory retention —
  disclose this retention in the form's deletion follow-up and the privacy policy).
  **[verify at submission]** the form's "deletion request" URL/steps point at this flow
  in the shipped build; if Play requires a web deletion-request URL for
  logged-out users, that page is a submission-time work item (the API is ready for it).
- **Data sharing:** none to third parties. The optional AI narrative runs behind a
  BAA-gated seam (ADR-0011) and is OFF by default — if enabled in production with a vendor,
  the form's "service providers" answer and the privacy policy MUST be updated first.

## 3. Listing checklist

- [ ] App name, short (80) + full (4000) descriptions — non-diagnostic wording only
- [ ] Privacy policy URL live (counsel-approved; draft: `docs/legal/privacy-policy-draft.md`)
- [x] In-app **About + Privacy** screens exist (ADR-0032) — auth-less `/about` + `/privacy`,
      reachable by a store reviewer and a logged-out user; the in-app Privacy screen is an
      honest SUMMARY that points to the counsel-reviewed full policy URL above (it does not
      replace the hosted policy the store listing requires)
- [x] Icon 512×512 — `docs/store-assets/icon-512.png` (generated baseline mark; owner may
      swap in commissioned branding — see `docs/store-assets/README.md`)
- [x] Feature graphic 1024×500 — `docs/store-assets/feature-graphic-1024x500.png`
- [x] ≥4 phone screenshots — 5 at 1080×2400 in `docs/store-assets/screenshots/` (synthetic
      data ONLY in every screenshot — never a real name or value; regenerate with
      `node scripts/generate-store-screenshots.mjs` from `frontend/`)
- [ ] Data Safety form filed from §2 (re-verified against the shipped build)
- [ ] Health apps declaration filed (§1)
- [ ] Content rating questionnaire (IARC)
- [ ] Internal-testing tester list (≤100 emails)
- [ ] Demo/review account (synthetic)
- [ ] versionCode bumped; signed AAB from the release workflow
- [x] Account/data **deletion flow shipped** (hard Play requirement — see §2; ADR-0027:
      Settings → Danger zone → `DELETE /auth/me`)
- [ ] Deletion flow **linked in the Data Safety form** at submission (steps/URL — see §2
      [verify at submission])

## 4. Known gaps before PRODUCTION (not internal testing)

1. ~~No deployed production backend / unset API base URL~~ **addressed** — the app is live on
   Azure Container Apps, and the Android release build now bakes the public API base URL at
   build time via `VITE_API_BASE_URL` in `release-android.yml` (default = the live frontend
   origin, whose nginx reverse-proxies the API; override with the repo variable
   `MOBILE_API_BASE_URL` for a custom domain). Cross-origin calls from the native shell are
   admitted by a scoped backend CORS allow-list (`settings.mobile_app_origins`). Still worth a
   final smoke of the built AAB against the live API before production.
2. **HIPAA validation + BAAs** (`docs/compliance/`) before any real patient data.
3. ~~Account/data deletion flow~~ **shipped** (ADR-0027, see §2) — only the Data Safety
   form linkage remains at submission.
4. **Counsel-approved privacy policy** at a public URL (draft: `docs/legal/privacy-policy-draft.md`).
5. ~~Support contact placeholder~~ **set** — `advancedhwg@outlook.com` (About screen + store listing).
6. **Target API level** — bump `targetSdkVersion` to 35+ (Play's current floor for new apps;
   36 required from 2026-08-31). Tracked as the follow-up toolchain change.
