# neuropathy-app — Patient UI

The patient graphing/trends web app (ADR-0015), built from the approved design in
`mockups/patient-app.html` on the brand tokens in `docs/design/` (ADR-0002). Talks
ONLY to the backend API; no third-party requests at runtime (fonts are self-hosted).

## Screens

- **Auth** — register / sign in (`/auth`).
- **Home** — the trajectory hero (direction, plain-language summary, confidence,
  AI-narrative badge), sourced signal list, data gaps.
- **Trends** — per-code line charts from `GET /observations`, direction-of-better
  stated per measure, accessible chart summaries.
- **Check-in** — the three 0-4 ADL questions (`POST /adl`), superseded notice on
  same-day re-submission.
- **Add data** — BioMech report PDF upload (`POST /biomech/reports`) and the EMR
  connect stub with the clinic connections list.
- **Sources** — capability toggles (`GET/PUT /capabilities`, optimistic with 409
  rollback) and connection consent grant/revoke.

## Run

Requires Node 22.

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173, proxies API paths to localhost:8000
```

Start the backend first (`cd backend && uvicorn app.main:create_app --factory`).
`VITE_API_BASE_URL` overrides the API origin for non-proxied deployments.

## Quality gates (all must pass; CI enforces)

```bash
npm run typecheck      # tsc --noEmit (strict)
npm run lint           # eslint, zero warnings
npm run format:check   # prettier
npm run test:coverage  # vitest, 90%+ lines/branches enforced
npm run build          # vite production build
```

Tests run against an msw-mocked API with synthetic data only (CLAUDE.md §5).

## Browser E2E (ADR-0022 — the Definition-of-Done real-browser gate)

A committed Playwright/Chromium smoke suite drives the **built** production bundle
(`vite build` → `vite preview`) in a real browser, asserts key patient + clinician
flows render and work, and FAILS on any new console error. A passing unit/msw test is
NOT sufficient proof that a UI works (CLAUDE.md Definition of Done); this suite is.

```bash
cd frontend
npm ci
npm run e2e            # builds, previews, runs all specs in Chromium (headless)
npm run e2e:report     # open the last HTML report
```

- The API is intercepted **in-browser** with `page.route`, fulfilled from fixtures
  that mirror `src/test/server.ts`; there is no live backend. A test `/config.js`
  (ADR-0018 runtime config) is written into `dist/` so the built app boots.
- The browser is the pre-installed Chromium at `PLAYWRIGHT_BROWSERS_PATH`
  (`/opt/pw-browsers`); the pinned `@playwright/test` version matches it, so no
  `playwright install` / download is needed locally. CI installs the browser itself.

## Security posture (ADR-0015)

Access token in memory only; refresh token in sessionStorage (tab-scoped); typed
fetch client with a single refresh-on-401 retry; no tokens or PHI on the console
(`no-console` is a lint error); no analytics; no external network calls at runtime.
