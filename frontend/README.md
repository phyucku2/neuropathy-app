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

## Security posture (ADR-0015)

Access token in memory only; refresh token in sessionStorage (tab-scoped); typed
fetch client with a single refresh-on-401 retry; no tokens or PHI on the console
(`no-console` is a lint error); no analytics; no external network calls at runtime.
