# ADR-0032: In-app About + Privacy screens and route-level code-splitting

**Date:** 2026-07-15
**Status:** Accepted
**Builds on:** ADR-0015 (patient UI stack, frame patterns, no third-party requests),
ADR-0016 (non-diagnostic posture + wording), ADR-0022 (browser E2E DoD + the
zero-console-error gate), ADR-0026 (Play listing needs a privacy policy),
ADR-0001 (IP ownership: owner holds the IP, BioMech Health is a licensee),
ADR-0027 (in-app account/data deletion).

## Context

Two store-readiness gaps remained on the shipped SPA:

1. **No in-app About or Privacy screens.** A Play listing requires a privacy policy
   (ADR-0026), and a store reviewer plus any logged-out user must be able to read
   what the app is and how it handles data *without an account*. The privacy scaffold
   existed only as `docs/legal/privacy-policy-draft.md`.
2. **One 615 KB JS chunk.** The production build emitted a single
   `index-*.js` of **615.11 KB (gzip 180.48 KB)** and tripped Vite's 500 KB
   chunk-size warning — the whole app (every route + recharts) downloaded before the
   first paint.

## Decision

### A. About + Privacy screens (new `frontend/src/features/about/`)

- **`AboutPage`** — app name, the build-time **version** (see below), the fixed
  non-diagnostic disclaimer mirroring ADR-0016 ("Trends support clinical judgment;
  they are not a diagnosis."), a plain-language description of what the app does, a
  cross-link to Privacy, a support-contact placeholder, and the IP/licensee line
  (ADR-0001: owned by Advanced Health and Wellness Group; BioMech Health is a
  licensee).
- **`PrivacyPage`** — an in-app rendering of `docs/legal/privacy-policy-draft.md`
  adapted into readable summary copy. It states plainly that it is a **summary** and
  points to the full policy URL placeholder, preserving the draft's honesty: the full
  policy is **counsel-reviewed before publication** and governs. PHI-free; no data
  calls.
- **Auth-less routes.** `/about` and `/privacy` sit **outside `RequireAuth`** in
  `App.tsx`, alongside `/login`, so a logged-out patient and a store reviewer reach
  them. Both reuse the existing `app-frame` / `status-bar` / `app-body` classes via a
  small shared `InfoLayout`, inheriting the brand header, the scrolling body, the
  safe-area insets (ADR-0025), and the AA contrast tokens with **no new CSS**.
- **Version source.** `package.json` `version` is injected at build time as a
  `__APP_VERSION__` global via Vite `define` (read with `fs` in `vite.config.ts`) —
  a single source of truth with no runtime data call. Ambient type declared in
  `features/about/appVersion.d.ts`.
- **Cross-links.** About ↔ Privacy link to each other; the **LoginPage footer** gains
  an "About · Privacy" link row. The Settings "About & privacy" link row is
  **deferred** (see below).

### B. Route-level code-splitting (`App.tsx`, `vite.config.ts`)

- Every major route element (Login, Register, About, Privacy, Home, Trends, CheckIn,
  AddData, Settings, EmrCallback, clinic Panel, PatientDetail) is now `React.lazy`
  behind a single `<Suspense fallback={<Loading />}>` boundary. The fallback reuses
  the existing `Loading` component — a plain `role="status"` line — so a chunk
  resolving mid-navigation renders cleanly with **zero console errors** (the ADR-0022
  gate would catch a bad boundary).
- **Vendor split** via `build.rollupOptions.output.manualChunks` — deliberately just
  **two buckets**: `recharts` (+ its d3 deps via `victory-vendor`) → a `charts` chunk
  loaded only when a charting route lazy-loads; **everything else** in `node_modules`
  (React, react-dom, react-router and their shared deps) → one `vendor` chunk. App
  code stays route-split by `React.lazy`. A first attempt split React into a THIRD
  chunk and produced a **circular chunk** (`vendor -> react -> vendor`, via
  react-router → `@remix-run/router` and react-is → react) that broke React at runtime
  (`Cannot read properties of undefined (reading 'PureComponent')` on every page,
  caught by the E2E console gate). Collapsing React into the single `vendor` chunk is
  acyclic because no library imports recharts — simple and correct over clever.

### Before / after bundle (production `vite build`)

| | Before | After |
|---|---|---|
| Entry `index-*.js` | **615.11 KB** (gzip 180.48) | **15.70 KB** (gzip 5.64) |
| Largest chunk | 615.11 KB (the entry) | `charts` 299.51 KB (gzip 77.44) |
| `vendor` chunk (React + router) | — | 268.01 KB (gzip 88.44) |
| Per-route chunks | — | 0.5–10.8 KB each (Home 1.26, Settings 9.50, PatientDetail 10.76, About 2.28, Privacy 3.66) |
| 500 KB warning | **present** | **gone** |
| Circular-chunk warning | — | **none** (two-bucket split) |

The landing download is now the shell + `vendor` + the one landing route, and
`charts` (the old bulk) loads only on Trends / clinician detail.

## Deferred (sibling-surface collision)

The Settings "About & privacy" link row was in scope but **`SettingsPage.tsx` is a
sibling agent's surface** in this parallel wave; editing it would collide. The links
were added only to the LoginPage footer and the About/Privacy cross-links. **Follow-up:
add a small "About & privacy" link row to the Settings page** (both `/about` and
`/privacy` are live and auth-less, so it is a one-line addition).

## Consequences

- `frontend` gates unchanged in shape: tsc, eslint `--max-warnings 0`, prettier,
  vitest ≥90% (about feature 100%), `vite build` (now split, no warning), Playwright
  (a new `e2e/patient/about-privacy.spec.ts` drives both auth-less pages in the built
  bundle with zero console errors — which also exercises the lazy + Suspense path in a
  real browser). No new dependencies; backend untouched.
- Existing auth unit tests were updated to `await` the first form field: with the
  route element now `React.lazy`, a synchronous query races the Suspense fallback
  (React.lazy caches resolution, so it was order-dependent). See `docs/lessons.md`.
