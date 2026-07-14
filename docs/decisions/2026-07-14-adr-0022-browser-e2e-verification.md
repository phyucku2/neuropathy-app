# ADR-0022: Browser E2E Verification — Playwright/Chromium Smoke Suite for the Shipped UIs

**Date:** 2026-07-14
**Status:** Accepted
**Builds on:** ADR-0015 (patient UI: fetch client, refresh-on-401, runtime config
consumption), ADR-0016 (clinician UI), ADR-0018 (runtime `/config.js` — deploy-time
`window.__APP_CONFIG__`), ADR-0012 (404-over-403 existence privacy; deterministic-only
clinician trajectory; non-enumerating invite), ADR-0013 (feature toggles: `enforced`
flag, optimistic-with-rollback, 409 verbatim), ADR-0020 §3(b) (patient-held
`share_with_clinic` is read-only in the clinician console).

## Context

The Definition of Done in `CLAUDE.md` is explicit: **UI portions require real-browser
inspection** — the *built* frontend must render, key flows must actually work, and there
must be **ZERO new browser console errors**, and **"a passing unit or msw test is NOT
sufficient proof."** ADR-0015 and ADR-0016 shipped the patient and clinician UIs with
strong Vitest + msw suites (130 tests), but those run in jsdom against a mocked module
graph. jsdom cannot catch a blank screen, a broken production build, a runtime import
error, a recharts render fault, or a thrown exception — precisely the failures the DoD
clause exists to catch. This portion (Wave 1 #5) retroactively closes that gap for the
already-merged ADR-0015/0016 UIs. No new product surface.

## Decision

Add a committed **Playwright + Chromium** end-to-end smoke suite (`frontend/e2e/`) that
drives the **real production build** (`vite build` → `vite preview`) in a headless real
browser and asserts visible outcomes plus a hard zero-console-errors gate.

### 1. Real build, real browser, mocked API

- **`webServer`** runs `vite build && node e2e/write-test-config.mjs && vite preview`, so
  every spec hits the SAME immutable artifact we ship — not the dev server.
- **Runtime config (ADR-0018):** `write-test-config.mjs` overwrites `dist/config.js` with
  an explicit `window.__APP_CONFIG__ = { apiBaseUrl: 'http://localhost:4318' }`, so the
  boot path genuinely exercises reading a per-deployment API base from `/config.js` — the
  same mechanism the container entrypoint uses. (Base points back at the preview origin,
  so requests stay same-origin.) No secrets — a local base URL only.
- **No live backend.** Every API call is intercepted in-browser with Playwright
  `page.route` and fulfilled from fixtures that **mirror `src/test/fixtures.ts` +
  `src/test/server.ts`** (the msw contract the unit suite already trusts). Identical
  shapes mean the browser exercises the same response bodies the real API returns.
- **Pinned browser.** `@playwright/test@1.56.0` matches the pre-installed Chromium
  (revision 1194, Chromium 141) at `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`; no
  `playwright install` / download is needed locally. CI installs the browser explicitly.
- **SPA vs. API prefix collision.** The client routes `/clinic` and
  `/clinic/patients/{id}` share a prefix with the API path space, and `vite preview`
  proxies those prefixes to the (absent) dev backend. Document navigations to them are
  therefore served the real built `dist/index.html` by the mock (its `/assets/*.js` +
  `/config.js` still load from the real preview build); only `fetch`/`xhr` calls are
  answered as API.

### 2. Zero-console-errors gate (the core DoD requirement)

An **auto fixture** attaches to every page's `console` (`type==='error'`) and `pageerror`
streams and FAILS the test if any genuine app error surfaced. This is the reason the
suite exists.

- **Allowlist is one documented pattern:** the browser's own automatic
  *"Failed to load resource: the server responded with a status of N"* network log.
  Chromium emits this for every 4xx/5xx response regardless of whether the app handles it,
  and in this app those statuses are all **designed, handled paths** — the 401 on the
  restore `GET /auth/me` (the access token is memory-only, ADR-0015, so a restored session
  always does one 401 → refresh → retry), the 409 optimistic-rollback / feature-off
  handling (ADR-0013), the neutral 404-over-403 screen (ADR-0012), and the 422
  expiry-without-enable validation. The allowlist is pinned to **exactly those status
  codes (401/404/409/422)** — a `500` (including the mock's own "Unmocked path" 500) or any
  other status still fails the gate. Each spec's positive assertions verify the app rendered
  the correct outcome for these. A GENUINE fault (uncaught exception, failed module load,
  React render error, or any app-origin `console.error`) is not an allowlisted line — it
  arrives as a `pageerror`, a different `console.error`, or a non-designed status and still
  fails the gate. `/favicon.ico` is fulfilled `204` by the mock so it never appears at all.
  A **self-check spec** (`e2e/support/self-check.spec.ts`) proves the gate in both
  directions: `isAllowed` classifies the designed statuses as benign and a 500/403/pageerror
  as a fault, and a real thrown error is shown to actually surface on the streams the gate
  listens to — so a regression that weakened the gate would itself be caught.

### 3. Coverage — 29 specs across both areas

- **Patient:** register/login/invalid-login; Home hero (improving/declining/insufficient
  variants + the sourced-signal "not enough data" state); Trends chart (axis/units summary,
  the <2-point empty state, the no-readings empty state, and the delta better/worse/
  unit-changed states); Check-in (0–4 ADL answers driven via the **keyboard radiogroup**,
  superseded notice, feature-off 409); Add-data (BioMech upload + warnings-as-text); Sources
  (toggle flip optimistic, `enforced=false` read-only, clinically-managed 409 verbatim +
  rollback, connection consent controls).
- **Clinician:** Panel (consented patients, empty state, non-enumerating invite sentence);
  Patient detail — Trajectory (non-diagnostic disclaimer + deterministic-only), Trend table
  (cross-source rows incl. "not judged"), Observations (real pagination across pages),
  **Features (the ADR-0020 §3(b) property proven in a real browser: `share_with_clinic`
  renders "Controlled by the patient" read-only with NO switch/renewal, while a
  clinic-managed key shows the switch)**, and the neutral 404 "Patient not found" screen.

### 4. CI — an isolated, blocking job

A dedicated **`e2e`** job in `.github/workflows/ci.yml` (Node 22) installs deps, then
`npx playwright install --with-deps chromium` (CI-only — locally the browser is
pre-installed and this is never run), builds, and runs the suite. It is a **separate,
blocking** job so its browser download + runtime are isolated from the fast `frontend`
gate and a flake can be diagnosed without touching the existing gates, which stay
untouched and green. `@playwright/test` is a **devDependency** (Apache-2.0), so the
production `npm audit`/license scans are unaffected.

## Alternatives considered

- **Rely on the existing msw/Vitest suite** — rejected: it is exactly what the DoD clause
  names as insufficient (jsdom, mocked module graph, no real build).
- **Test the dev server** — rejected: the DoD requires the *built* app; the dev server can
  paper over build-only failures (asset paths, minification, `import.meta.env` inlining).
- **A live backend in CI** — rejected for this smoke suite: it couples the frontend gate to
  backend/Postgres provisioning and slows/flakes the loop; in-browser mocks mirroring the
  msw contract give deterministic render coverage. (A future contract/integration lane can
  layer on a live backend without changing this suite.)

## Consequences

- The DoD **real-browser inspection** requirement for the shipped patient + clinician UIs
  is now met by a committed, repeatable suite (`npm run e2e`), not a one-off manual check.
- Fixtures live in two places (`src/test/` for Vitest, `e2e/support/mock-api.ts` for
  Playwright) because the two runners cannot share a module graph; they are kept in lockstep
  by mirroring the same shapes, and drift would surface as an E2E failure.
- Adds `@playwright/test` (dev-only, Apache-2.0) and the browser install step in CI only.
