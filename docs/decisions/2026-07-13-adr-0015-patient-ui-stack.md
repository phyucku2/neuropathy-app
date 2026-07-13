# ADR-0015: Patient UI — Frontend Stack, Token Handling, and Chart Quality Bar

**Date:** 2026-07-13
**Status:** Accepted
**Builds on:** ADR-0002 (brand tokens), ADR-0010 (auth), ADR-0013 (toggles),
ADR-0014 (BioMech ingest), mockups/patient-app.html (approved design).

## Context

The repo's first frontend: the patient graphing/trends UI from the approved mockup,
talking ONLY to the existing backend surface (auth, observations/adl, labs, biomech
reports, trajectory, capabilities, connections). Regulated-health constraints apply:
WCAG 2.2 AA, no PHI leaks (console/analytics/third parties), permissive licenses only
(CLAUDE.md §4), and the brand system in `docs/design/` (our own wordmark in Poppins —
never BioMech's logo or pixel-copied layouts).

## Decision

### Stack (options considered)

- **Build tool: Vite** (chosen) vs Next.js vs CRA. Next.js brings a server runtime and
  routing conventions we don't need for a fully client-side app against our own API;
  CRA is unmaintained. Vite is the boring, fast, well-supported default for a React SPA.
- **UI library: React 18 + TypeScript strict** (chosen) vs Vue/Svelte. React has the
  deepest accessibility/testing ecosystem and the team's tooling (testing-library, msw)
  is first-class there. `strict` + `noUncheckedIndexedAccess` — the frontend gets the
  same "quality is enforced" posture as mypy strict on the backend.
- **Routing: react-router v6** (chosen) vs TanStack Router — smaller surface, stable,
  MIT, enough for five routes.
- **Charts: recharts** (chosen) vs visx vs Chart.js vs D3-by-hand. Recharts is MIT,
  React-idiomatic (charts as JSX we can wrap in accessible containers), and small
  enough in scope for single-series line charts. visx is lower-level than we need;
  Chart.js is canvas-first (worse for our aria/role=img wrapper approach).
- **State/data: no client-cache library.** The app is five screens with simple reads;
  a 40-line `useApi` hook keeps the dependency count down. React Query can be adopted
  later if invalidation complexity appears.
- **Styling: hand-rolled CSS on `docs/design/tokens.css`** (copied verbatim into
  `frontend/src/styles/tokens.css`, the single source of truth per ADR-0002) vs
  Tailwind/CSS-in-JS. No CSS framework: the mockup's visual language is small, and the
  tokens file IS the design system.
- **Tests: Vitest + @testing-library/react + user-event + msw**, jsdom. API mocked at
  the network boundary (msw) so components exercise the real client, including the
  refresh-on-401 retry. Coverage thresholds 90% lines/branches enforced in config.
- **Lint/format: eslint (typescript-eslint strict + react-hooks + jsx-a11y) +
  prettier**, `--max-warnings 0`. `no-console` is an error: tokens and PHI must never
  reach the console.

### Token handling (security-critical)

- **Access token: in memory only** (module closure). Never in storage, never logged;
  it dies with the tab.
- **Refresh token: sessionStorage.** Tab-scoped and cleared on tab close, survives an
  in-tab reload. **XSS tradeoff, documented:** any script running in our origin could
  read it. Mitigations: no third-party scripts at all (see below), React's default
  escaping everywhere (no `dangerouslySetInnerHTML`), and short-lived refresh scope.
- **httpOnly cookies rejected** for now: the API is a pure bearer-token surface
  (ADR-0010) with no cookie session, no CSRF token issuance, and no cookie-aware
  middleware. Introducing cookies would add a CSRF surface the backend doesn't defend
  and same-site/deployment coupling, without removing the XSS concern for the access
  token. Revisit if/when the API grows a cookie/CSRF layer.
- **Refresh-on-401-once:** the typed client retries a failed request exactly once
  after a single-flight `POST /auth/refresh`; a failed refresh clears the session and
  returns the user to sign-in. localStorage was rejected (persists across tabs and
  survives the browser session — larger theft window on shared machines).

### No third-party requests at runtime

This is a health app: at runtime the browser talks to our API and nothing else. Fonts
(Poppins/Inter, SIL OFL 1.1) are self-hosted via `@fontsource/*` packages and bundled
— no Google Fonts CDN, no analytics, no error-reporting SaaS, no CDN scripts. The OFL
license text ships inside the installed packages.

### Chart quality bar (Trends)

- One series per chart; brand-token colors; no gridline clutter, no 3D, **never** dual
  axes.
- x is a real time axis on `effective_at` with a handful of evenly spaced ticks; y
  ticks carry the unit (UCUM annotations like `{score}` display de-braced).
- **Direction-of-better is stated in plain language** under every chart, from a UI
  mirror of the backend directionality registry (e.g. lower sway velocity is better);
  unknown codes are tracked but never judged — same no-silent-clinical-claims rule as
  the backend.
- **Accessible:** the chart container is `role="img"` with an aria-label that
  summarizes the trend in words ("Balance score: 3 readings from May 6, 2026 to
  Jul 2, 2026, rising from 57 to 65 score"); tooltips show value + unit + date; a code
  with fewer than 2 points gets a visible empty state instead of a fake line.

### Dependency licenses (CLAUDE.md §4 — all permissive)

Runtime: react, react-dom (MIT); react-router-dom (MIT); recharts (MIT);
@fontsource/inter, @fontsource/poppins (packages MIT; font files SIL OFL 1.1).

Dev: vite (MIT); @vitejs/plugin-react (MIT); typescript (Apache-2.0); vitest,
@vitest/coverage-v8 (MIT); jsdom (MIT); @testing-library/react, /dom, /user-event,
/jest-dom (MIT); msw (MIT); eslint, @eslint/js (MIT); typescript-eslint (MIT);
eslint-plugin-react-hooks (MIT); eslint-plugin-jsx-a11y (MIT); eslint-config-prettier
(MIT); prettier (MIT); @types/react, @types/react-dom (MIT).

## Adversarial-review hardening

Addendum (same day) for the adversarial-review findings on this portion.

- **Derived contrast token.** Brand green `#2F8F5B` is only 4.04:1 against white —
  fine for non-text accents, failing WCAG 2.2 AA (4.5:1) for normal text. Rather than
  darken the brand green everywhere, `tokens.css` gains a derived token
  `--color-action-green-strong: #277A4D` (same hue family, 5.28:1 with white) used on
  TEXT-BEARING surfaces only: the primary button and the improving-hero gradient stops
  (`--color-action-green-hover` deepens to `#1F6F44`, 6.15:1). The declining hero's
  light stop darkens `#C25A37` → `#B34E2D` (4.36 → 5.19:1) and `.pill.warn` text
  darkens `#9A6423` → `#8A5313` (4.26 → 5.41:1 on `#F7ECDD`). Brand green stays for
  icons, toggle tracks, and other non-text accents (docs/design/brand.md unchanged as
  the brand source). `frontend/src/styles/contrast.test.ts` computes the WCAG
  relative-luminance contrast for these pairs from the shipped CSS and fails CI below
  4.5:1, so regressions cannot land silently.
- **Toggle-knob convention (mockup correction).** `mockups/patient-app.html` — the
  approved design source — drew the switch inverted: ON with the knob LEFT, OFF with
  the knob RIGHT, and the app CSS copied it. Patients read knob position as on/off
  (universal convention: right = on), so an inverted switch misreports consent-bearing
  states like "Share with clinic". Both the mockup and `app.css` are corrected:
  `aria-checked=true` puts the knob RIGHT on the green track. Locked by the same test
  file.

## Consequences

- CI gains a frontend job (node 22): `npm ci`, `tsc --noEmit`, `eslint
  --max-warnings 0`, `prettier --check`, `vitest run --coverage` (90% thresholds),
  `vite build`.
- The API types in `frontend/src/api/types.ts` mirror the Pydantic schemas 1:1 and
  must move in lockstep with backend contract changes.
- Manual lab entry (mockup screen 3) and the live EMR OAuth redirect are follow-ups;
  the Add-data screen ships the BioMech upload and an EMR stub until a client is
  registered (ADR-0009).
