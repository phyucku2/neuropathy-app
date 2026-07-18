# Roadmap status board

The single source of truth for what remains and where each portion stands.
Updated every development-loop cycle; one portion = one small PR (working
agreement). States: **Built** (code complete on a branch), **Tested** (full gate
green: ruff + mypy --strict + pytest incl. live-Postgres integration, adversarial
review findings fixed), **Merged** (on `main`).

## Shipped

| Portion | Built | Tested | Merged |
|---|---|---|---|
| Auth — Argon2id + JWT access/refresh (ADR-0010) | ✅ | ✅ | ✅ |
| FHIR/LOINC lab intake + reference ranges (ADR-0007) | ✅ | ✅ | ✅ |
| EMR patient pull — SMART on FHIR OAuth/PKCE (ADR-0008/0009) | ✅ | ✅ | ✅ |
| ADL daily check-ins + supersede-by-revision (ADR-0006) | ✅ | ✅ | ✅ |
| Trajectory engine — explainable direction/confidence/signals | ✅ | ✅ | ✅ |
| Postgres durability — repositories, migrations, request transactions | ✅ | ✅ | ✅ |
| AI narrative layer — validated, BAA-gated, off-request-path (ADR-0011) | ✅ | ✅ | ✅ |
| Clinician surface — consent-gated panel/views, invitations (ADR-0012) | ✅ | ✅ 100% cov | ✅ PR #3 |
| Feature toggles API — server-enforced capabilities, B2C + clinician-managed, consent-aware (ADR-0013) | ✅ | ✅ 100% cov | ✅ PR #4 |
| BioMech PDF ingest module — balance/gait report PDFs into research-grade Observations (ADR-0014; **rebuilt to the real report format in ADR-0036**) | ✅ | ✅ | ✅ PR #5 (V1) → **ADR-0036** rebuild. V1 was built against an *assumed* format; ADR-0036 rebuilt the parser to the **real** pypdf line structure + real metric set (balance/gait scores + components), so it now parses real BioMech reports. See biomech-data-streams.md §3 + ADR-0036 |
| Patient graphing/trends UI — from mockups/patient-app.html against the existing API (ADR-0015) | ✅ | ✅ | ✅ PR #6 |
| Clinician UI — from mockups/clinician-app.html (panel, cross-source trend table, non-diagnostic) (ADR-0016) | ✅ | ✅ | ✅ PR #7 |
| Hardening pass — invitation rate limiting, durable pending-auth store, encrypted token vault with deletion-on-revoke, hardened ops gate, blocking Python security/license scans (ADR-0017) | ✅ | ✅ 100% cov | ✅ PR #8 |

## Remaining (build order) — V2

**Wave 1 — Production readiness** ✅ **COMPLETE** (decision 2026-07-14: V1 becomes
deployable and operable before new surface area). All five portions built, adversarially
reviewed, and merged (PRs #9, #10, #12, #14, #15).

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Deployment & infrastructure — backend/frontend containers (multi-stage, non-root, secret-free), health/readiness endpoints, PHI-free structured request logging, runtime-config frontend, staging compose, deploy + backup/restore runbooks, image-build CI (ADR-0018) | ✅ | ✅ 100% cov | ✅ PR #9 | |
| 2 | Ops-auth surface — replace OPS_BOOTSTRAP_TOKEN with real ops identities for provisioning (ADR-0019) | ✅ | ✅ 100% cov | ✅ PR #10 | per-operator ops accounts + require_ops; clinician provisioning needs an ops bearer (real actor attribution); OPS_BOOTSTRAP_TOKEN narrowed to self-closing first-ops bootstrap; per-operator deactivation; migration 0005 |
| 3 | Wire the remaining toggles — `emr_connect` gating /emr connect flow, `ai_narrative` gating narrator scheduling, `share_with_clinic` gating clinician reads; each flips enforced=True with its own consent-interaction decision (ADR-0013/ADR-0020) | ✅ | ✅ 100% cov | ✅ PR #12 | All three wired in one PR (ADR-0020): emr_connect gates connect+callback (connect-vs-pull split; revoke never blockable); ai_narrative ANDs with the BAA gate as an in-handler branch (200 stays deterministic, no disclosure audit when off); share_with_clinic is a patient-held consent control gating clinician reads via ONE `_may_read_patient` predicate (panel drop + neutral 404 + capability-write 404), carved out of clinician toggle-authority so the patient always controls it even when clinically managed. Frontend fixtures/tests updated (reads `enforced` from API). |
| 4 | Observability & ops — error tracking (self-hosted-friendly), metrics, alerting hooks, Postgres backup drill; compliance pack (HIPAA ops checklist, BAA inventory, incident-response runbook) | ✅ | ✅ 100% cov | ✅ PR #14 | ADR-0021. PHI-free `GET /metrics` (prometheus_client; method/route-template/status labels — never raw path; app_up, DB pool, subject-free AI-disclosure counter; auth-denials/rate-limits read off the status label). `MetricsMiddleware` + `ErrorReportingMiddleware` compose inside the outermost logging middleware (logging stays index 0). Error seam mirrors the Narrator: off-by-default, self-hostable, PHI-scrubbing (whitelist event — never the exception message), fail-safe. Alert rules + scrape/collector wiring in `docs/ops/observability.md`. Tested backup drill script + `SECRET_STORE_KEY` trap reinforced. Compliance pack under `docs/compliance/` with honest [CE] boundaries. |
| 5 | Browser-verify the shipped patient + clinician UIs (Playwright/Chromium: built app renders + key flows work + ZERO new console errors) — retroactive Definition-of-Done closure for ADR-0015/0016 UI portions (msw/unit tests are not sufficient proof) | ✅ | ✅ | ✅ PR #15 | ADR-0022. 29 committed Playwright specs (patient + clinician + 2 gate self-checks) drive the REAL `vite build`/`vite preview` bundle in the pre-installed Chromium (rev 1194), API mocked in-browser mirroring `src/test/server.ts`, runtime `/config.js` (ADR-0018) exercised. Auto zero-console-errors gate (`pageerror` + `console.error`, allowlist pinned to the designed 401/404/409/422 only — a 500 fails) on every spec, with a self-check proving the gate fails on a real fault. Proves the ADR-0020 §3(b) `share_with_clinic` read-only property in a real browser. Dedicated blocking CI `e2e` job (browser installed CI-only). Existing gates untouched. |

**Wave 2 — Mobile app** ✅ **COMPLETE (Android)** (PRs #17, #18, #19): Capacitor wrap of the existing SPA (ADR-0023 —
professional staged approach; revisit trigger recorded: native rebuild only if
device/HealthKit/BLE integration lands). **Android-first per user (ready to go); iOS
PENDING the user's DUNS + Apple-ID switch — do not collect Apple credentials until iOS
submission.**

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Capacitor scaffolding + Android platform — `@capacitor/core` (prod, MIT) + cli/android (dev), `capacitor.config.ts`, generated `android/` native project, cap npm scripts, keystore-safe `.gitignore`, ESLint/Prettier exclude the native tree; CI `mobile` job assembles a debug APK (ADR-0023) | ✅ | ✅ | ✅ PR #17 | Scaffolding only — no web behavior change. Web target unregressed (29 Playwright specs green), `cap sync` works, prod audit + license gates pass, no secret-scan hits; CI `mobile` job assembled the debug APK. Security-review fixes: allowBackup=false, uncommented google-services/keystore ignores, secret-scan hardened, setup-android pinned to a SHA. |
| 2 | Secure token storage + biometric unlock — move the refresh token off web `sessionStorage` into the OS secure store (Keystore) on native, biometric gate before revealing the session; web posture (ADR-0015) unchanged as the fallback so the E2E suite is unaffected | ✅ | ✅ | ✅ PR #18 | ADR-0024. Platform-selected refresh-token backend (WebBackend sessionStorage / NativeBackend Keystore via @aparajita/capacitor-secure-storage, Cap-6-pinned); sync `peek` + async `load` prime so the sync restore-decision timing is unchanged on web. Biometric gate (@aparajita/capacitor-biometric-auth) via `resolveNativeRestore` (unit-tested decision logic). Access token stays memory-only. Review fixes: biometric gate fails CLOSED on a gate error (open only for genuinely-unenrolled devices), durable logout-delete retries, and `fileParallelism:false` removes a parallel-worker unit-test flake. Verified: web unregressed (146 unit + 29 E2E green, deterministic), native building blocks unit-tested via injection/local mocks; APK-compile proven by the CI `mobile` job; on-device Keystore/biometric is the user's `npx cap run android`. |
| 3 | Native shell — status bar / splash / safe-area insets / hardware back button (ADR-0025). **OAuth-callback handling DEFERRED to Wave 3** (no EMR connect UI exists yet to hook it to; the native app-scheme/appUrlOpen handler ships with the connect UI, after sandbox registration). | ✅ | ✅ | ✅ PR #19 | ADR-0025. Official Cap-6 plugins (@capacitor/status-bar, splash-screen, app; all MIT). `useNativeShell`/`initNativeShell` no-op on web (gated by `isNativePlatform`), so the 29 E2E specs are unchanged; hardware back navigates history / exits at root (`backAction` unit-tested); splash hidden on React mount (no white flash); safe-area via `viewport-fit=cover` + `env(safe-area-inset-*)` (0 on web). Verified: 149 unit + 29 E2E green, `cap sync` warning-free, prod audit + license clean; APK-compile is the CI `mobile` job; on-device look is the user's `npx cap run android`. |

| 4 | Play release prep — release signing (git-ignored `keystore.properties` + Play App Signing, unsigned fallback), manual `release-android.yml` AAB workflow (optional signing secrets, keystore shredded), Play runbook + listing pack (Data Safety draft from actual data flows) + privacy-policy scaffold (ADR-0026) | ✅ | ⏳ | ⏳ | Publisher decided 2026-07-14: **the Advanced Health and Wellness Group org account** (needs the org's DUNS at signup — user-side). No credential collected. Known gaps recorded: account/data **deletion flow REQUIRED before store submission** (hard Play rule — new roadmap item below), production backend deployment, HIPAA validation + BAAs before real data. Internal testing possible before those. |

**Wave 2 Android done: the app installs, stores tokens in the Keystore + biometric-unlocks, and has a polished native shell; Play release prep staged.** iOS still PENDING the user's DUNS + Apple-ID switch; the SMART OAuth native handler rides with Wave 3's EMR-connect UI.

**Required pre-store portion (from ADR-0026):** patient-facing **account & data deletion flow** (in-app + API) — a hard Google Play requirement for apps collecting user data, and good HIPAA hygiene regardless. **Built ✅ / Tested ✅ (100% cov on new code; live-Postgres integration green) / Merged ✅ PR #27** (review fixes: vault purge ordered last, bounded rate-limited denial audit, narrative-cache flush, keyed-vault requirement documented) — ADR-0027: `DELETE /auth/me` with password re-auth (Argon2id), transactional FK-safe destruction of every patient-owned row (vault secrets purged via the ADR-0017 revoke seam), audit history RETAINED anonymous via `audit_event.patient_id` ON DELETE SET NULL (migration 0006), never blockable by toggles/kill switches; Settings "Danger zone" card (password + acknowledgment + two-tap confirm) landing on `/login` with a transient deleted notice; 30th Playwright spec drives the built bundle with zero console errors.

**Wave 3 — EMR registrations**: Epic/Cerner sandbox enrollment — operator runbook at
[`docs/emr/sandbox-registration-runbook.md`](emr/sandbox-registration-runbook.md)
(signup → app registration → redirect URIs → smoke test) — plus the code the runbook
surfaced and the patient EMR-connect UI + native OAuth handler deferred from Wave 2
Portion 3.

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Patient EMR-connect UI + per-provider client ids + native OAuth return path (ADR-0028) — Sources "Health record connections" card (picker/search/connect), authenticated `/emr/callback` SPA relay (backend auth unchanged), system-browser OAuth on native (`@capacitor/browser`, never the WebView), `appUrlOpen` App-Links/custom-scheme routing + manifest scheme filter (assetlinks template in `docs/mobile/emr-app-links.md`), `SMART_CLIENT_ID_<VENDOR>` per registry entry, scope trim to `launch/patient patient/Observation.read offline_access` — closes runbook code rows 7/8/9/10 | ✅ | ✅ | ⏳ | Backend 100% cov (live-Postgres green); frontend unit ≥90% all four; 31 Playwright specs incl. the full connect→callback→pull→revoke round trip in the built bundle, zero console errors; `cap sync` warning-free; prod audit + license + secret scans clean. Known gap (recorded in ADR-0028): no EMR-connections LIST endpoint yet — post-connect confirmation carries pull/revoke; list endpoint + card list is a follow-up portion. |
| 2 | Vendor registrations + sandbox smoke (runbook §§1–5: Epic + Oracle accounts, app registrations, client ids into env, §5 smoke both vendors — record `granted_scope` + the Epic refresh-token outcome) | — | — | — | **USER-side** (owner credentials; see runbook checklist rows 1–6, 11–12). The app side is ready: the smoke test can now run through the UI end-to-end. |
| 3 | Production enrollment (per-org FHIR bases, Epic mark-live/distribution, Oracle per-tenant provisioning, deployed HTTPS origin + `assetlinks.json`) | — | — | — | USER + ops; after #2. Refresh-token rotation job (runbook row 13) is informed by #2's outcomes. |

**Patient experience** — quality-of-life portions on the shipped patient app
(each row is one portion = one PR; appended per-portion, merge keep-both).

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Offline check-in queue (ADR-0030) — an offline ADL submission is captured on-device (localStorage, one entry per day mirroring ADR-0006 supersede; cleared on sync AND on every session clear incl. account deletion) and flushed automatically on boot / 'online' / post-submit with its TRUE local capture date (POST /adl accepts a client `check_in_date` — confirmed in backend schemas/route); 409/422 refusals drop with a one-time verbatim notice; network-vs-API error split keeps existing 4xx/5xx handling | ✅ | ✅ | ⏳ | Frontend-only (backend untouched). 20 new unit tests (203 total, coverage ≥90 all four); 32nd Playwright spec drives offline→queued→online→synced in the built bundle with zero console errors (allowlist gains only the pinned `net::ERR_INTERNET_DISCONNECTED` line for this designed scenario, self-check-proven). |

**Wave 4 — Reimbursement-enabling features (RTM-first)** — build the app capture/export
that could enable a covered entity to pursue a compliant claim, pending compliance
validation, prioritized for RTM given the
BioMech musculoskeletal/gait/balance + ADL self-report streams (see
[`docs/product/reimbursement-analysis.md`](product/reimbursement-analysis.md) §7 for the
prioritized backlog: parameterized ≥N-day adherence counter, interactive-time ledger,
episode/setup event, billing-consent scope, PHI-safe billing-evidence export, BioMech
device-provenance strengthening, and the FDA device-status ADR). **PENDING compliance
validation** of the reimbursement analysis by a certified professional coder +
compliance/legal **before any build** — this Wave enables billing pathways, it does not
authorize billing, and nothing starts until that sign-off exists. The review packet for
that sign-off is
[`docs/product/reimbursement-signoff-packet.md`](product/reimbursement-signoff-packet.md)
(the exact decisions requested, reviewable assertions, the FDA device-status question, and
the sign-off sheet); market context on products already billing these codes is in
[`docs/product/reimbursed-apps-comparison.md`](product/reimbursed-apps-comparison.md).

**Wave 5 — Patient experience** — small patient-facing quality-of-life portions that
need no new backend surface.

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Daily check-in reminder (ADR-0029) — patient-configurable daily local notification (native-only; honest web fallback), `@capacitor/local-notifications` pinned to the Cap-6 line, injectable reminders seam (`src/native/reminders.ts`), "Daily reminder" card in Sources (toggle + time, permission-denied guidance), device-local preference (localStorage — no server state), fixed PHI-free content, launch re-assert against OEM alarm drops (fire-and-forget after splash hide) | ✅ | ✅ | ⏳ | Seam + card fully unit-tested off-device (exact Cap-6 `schedule.on {hour, minute}` repeating shape pinned); 212 unit tests ≥90% all four; 32 Playwright specs (new: the card's web fallback in the built bundle) zero console errors; `cap sync` warning-free; prod audit + license + secret scans clean. Real delivery is on-device only: `npx cap run android`, enable, let it fire. |
| 2 | Store-readiness polish (ADR-0032) — in-app **About + Privacy** screens (auth-less `/about` `/privacy`, reachable by a store reviewer + logged-out user; non-diagnostic disclaimer, build-time version, IP/licensee line, in-app privacy summary pointing to the counsel-reviewed full policy) + **route-level code-splitting** (`React.lazy`/`Suspense` per route + recharts/react vendor `manualChunks`) + top-level **ErrorBoundary** for lazy-chunk rejections | ✅ | ✅ | ✅ | Merged in PR #32. New `frontend/src/features/about/**` (exclusive surface); links added to the LoginPage footer + About/Privacy cross-links. Two-bucket vendor split (`charts` recharts/d3 + `vendor` React/router), largest chunk 299 KB; 500 KB warning gone (a first three-bucket split hit a circular chunk that broke React at runtime — caught by the E2E gate, fixed to two buckets); ErrorBoundary added so a post-deploy stale-chunk 404 offers a reload instead of white-screening. 275 unit tests ≥90% all four; 37 Playwright specs incl. `about-privacy.spec.ts` + the console-gate self-check; tsc/eslint/prettier clean; backend untouched; secret scan clean. |
| 3 | Patient data export — "Download my data" (ADR-0031) — right-of-access sibling to account deletion: `GET /me/export` (patient-only, rate-limited per actor, `Cache-Control: no-store`, one PHI-free `export_account` audit event) returns the patient's **current** record (account/patient rows, current observations w/ provenance, trajectory snapshot, capability states, clinic + EMR connection metadata) as a typed `ExportOut` envelope (`exported_at`/`schema_version`/`subject_id`). NO secrets EVER — token-free projections, proven by ABSENCE (payload scanned for the token/`token_ref`/hash fixtures). "Download my data" card ABOVE the danger zone; web = JSON download + observations CSV (pure flattener), native = Filesystem cache write (deleted after Share) + OS Share sheet with cancel-is-not-error handling (`@capacitor/filesystem` + `@capacitor/share`, Cap-6 line, injectable seam). | ✅ | ✅ | ⏳ | Backend 100% coverage on new code (unit + live-Postgres, no-secrets proven over real vault ciphertext); 292 unit tests ≥90% all four; 38 Playwright specs (card renders + both `.json`/`.csv` downloads fire in the built bundle) zero console errors; `cap sync` warning-free (2 new MIT plugins registered in gradle); prod audit + license + secret scans clean. On-device Share-sheet UX is `npx cap run android` only. Analyzable-only export set is the documented boundary (ADR-0031). |

## Recent additions — measurement science, data streams, modules & platform (2026-07-15 → 07-17)

The wave after the reimbursement/patient-experience work, grounded in the owner's real BioMech
materials and adversarially-verified research. One portion = one small PR, merged between each.

| Portion | Decision | Merged | Notes |
|---|---|---|---|
| **Neuropathy Status Index (NSI)** — deterministic 0–100 composite (Symptoms/Function/Physiologic), per-measure normalization, missing-domain renormalization, fixed-point direction floor, Confidence from coverage+recency; hero card | ADR-0034 | ✅ | The single honest status number on top of the streams |
| **BioMech real-report rebuild** — parser + metric catalog realigned to real balance/gait reports (pypdf line structure, real codes, eyes-open/closed condition) | ADR-0036 | ✅ | Closed the fictional-code audit findings across parser/directionality/composite |
| **Phone-base ADL health bridge (Phase 1)** — wearable/phone mobility ingestion via Apple HealthKit / Android Health Connect; fidelity tiers; `ingest_wearable` opt-in; native seam | ADR-0035 | ✅ | Phone-base ADLs, watch optional; verified phone-gait reliability split |
| **Frontend signal-registry realignment** — UI registry mirrored to the real ADR-0036 BioMech + ADR-0035 wearable codes; demo refreshed | (ADR-0036 follow) | ✅ PR #47 | Retired the fictional `sway_velocity` etc. from the UI/demo |
| **CGM blood-glucose ingestion** — glucose via the health bridge (mg/dL, in-range polarity, excluded from NSI v1, no alarms/dosing) | ADR-0038 | ✅ PR #51 | Path A (platform-first); direct Dexcom/Abbott SDKs deferred |
| **Education-module framework** — closed clinician-reviewed registry, `education` opt-in, PHI-free progress, general-not-individualized guardrail; DSMES-not-DPP framing | ADR-0037 | ✅ | Evidence-informed first module = exercise/balance |
| **Backend deploy-readiness** — Render blueprint + vendor-neutral runbook (real login-and-use app; release-phase migrations) | `render.yaml` / `docs/ops/DEPLOY.md` | ✅ | Provisioning needs the owner's host account |
| **Cited research** — AI-fusion evidence review + DPN→ADL/falls & module evidence | `docs/product/ai-fusion-evidence-review.md`, `dpn-adl-falls-and-education-evidence.md` | ✅ | Honest framing: association not validated prediction; moat = dataset, not model |
| **Accessibility-first for the 60+ population** — standing design constraint (type/contrast/targets/simplicity), enforced by contrast tests | ADR-0039 | ✅ (this PR) | Records that all new UI is built to this bar |

**Measurement-rigor groundwork (ADR-0043):** symptom items now live in a single-source
`psychometrics` item-bank with honest ADA construct mapping (Rec 12.17/12.18 — "related to,"
not equivalent) and an uncalibrated IRT/CAT administration seam (Spec 4). Deterministic, no
score change; honesty guards keep it from overclaiming. The #1 product gap from
[`docs/product/market-position-and-gaps.md`](product/market-position-and-gaps.md).

**Onboarding + clinician loop (ADR-0044):** shipped a first-run 60+ **welcome wizard**
(full-screen, accessible, per-user localStorage flag). The **clinician feedback loop** (in-app
data-gap signal + PRO-to-EHR write-back) is **specced** — a phased, gated design; trajectory
"alerts" and write-back are deferred behind the FDA framework (ADR-0041) and per-vendor write
support, not built blind.

**In progress / next:** NSI Function two-tier (fold fidelity-weighted wearable data into the
score); BioMech eyes-open−closed gap; Android Health Connect connector; iOS + HealthKit
(pending Mac + Apple account). Backlog detail in
[`docs/product/roadmap-buildout-specs.md`](product/roadmap-buildout-specs.md).
**V2:** AI photo food logging (honest ranged-estimate) — architecture decided (**ADR-0042**):
**GPT-4o-vision (Azure, under Microsoft's BAA) + free nutrition DBs** (Open Food Facts barcode /
USDA text), image recognition reserved for plated meals, always a human confirm/edit step;
capability-gated, NSI-excluded, never for dosing; not clinical-grade, positioned as estimation
not measurement. Build-vs-buy analysis in
[`docs/product/food-ai-build-vs-buy.md`](product/food-ai-build-vs-buy.md). Also: derived glucose
time-in-range → NSI Physiologic.

**Regulatory gate:** the FDA device-status decision is now framed and governed by **ADR-0041**
(decision framework; classification itself deferred to a qualified FDA regulatory professional,
decision D2) — the single highest-leverage owner action per
[`docs/product/market-position-and-gaps.md`](product/market-position-and-gaps.md).

## Deferred (not scheduled)

- BioMech API/SDK live ingestion — the recommendation remains **API-first** (`device_measured`)
  when the owner's API access lands; the **PDF path is no longer a gap** (rebuilt to the real
  report format in **ADR-0036**, so it ingests real reports today as the fallback). See
  biomech-data-streams.md §3/§7 + ADR-0036.
