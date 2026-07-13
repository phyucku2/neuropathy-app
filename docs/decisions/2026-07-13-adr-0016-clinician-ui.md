# ADR-0016: Clinician UI — Role-Aware Routing and Non-Diagnostic Presentation

**Date:** 2026-07-13
**Status:** Accepted
**Builds on:** ADR-0012 (clinician surface semantics), ADR-0013 (toggle authority),
ADR-0015 (frontend stack + hardening addendum), mockups/clinician-app.html (approved
design).

## Context

The clinician console from the approved mockup — panel, per-patient views, renewable
capability orders — against the existing `/clinic/*` API. The open questions: is this
a second app or the same SPA, and how do ADR-0012's privacy postures (404-over-403,
non-enumeration) and the product's non-diagnostic requirement show up in the UI?

## Decision

1. **One SPA, role-aware routing.** A separate clinician build (second Vite app or
   subdomain) was rejected: it doubles CI, duplicates the API client/auth/token
   handling, and the backend already keys everything on the JWT role. Instead
   `/auth/me` decides the area after sign-in: `role='clinician'` lives under
   `/clinic`, everyone else under the patient routes. Each area guard redirects
   ONLY to the other area's home (clinician on a patient route → `/clinic`;
   non-clinician on `/clinic` → `/`), so the guard pair can never loop. The
   AppShell gains a clinician variant (marked top bar with the signed-in name,
   wider working area, no patient tab bar) per the mockup.
2. **Non-diagnostic posture (product requirement).** No clinician screen presents a
   computed direction as a diagnosis. The trajectory view and the cross-source
   trend table both carry the fixed disclaimer ("Trends support clinical judgment;
   they are not a diagnosis."), the trajectory is the shared DETERMINISTIC
   computation (never the AI narrator — ADR-0012; the hero/signals components are
   extracted from the patient Home so the two renderings cannot drift), and
   unjudgeable metrics (unknown/in-range polarity, single readings) say
   "not judged" — the word "stable" is never fabricated (same rule as the patient
   UI, ADR-0015).
3. **404-over-403 UX mirror.** Any 404 under `/clinic/patients/{id}/*` — and an id
   absent from the panel — renders one neutral "Patient not found" screen that
   never mentions access or permissions, mirroring the backend's existence-privacy
   posture instead of re-introducing the distinction it hides.
4. **Non-enumeration in the UI.** The invite flow shows ONE fixed sentence on every
   accepted send ("If that email belongs to a patient account, they'll receive an
   invitation.") — the UI must not imply it knows whether the email matched, even
   though the backend's 202 is already byte-identical.
5. **Capability orders, verbatim errors.** Feature rows follow ADR-0013 exactly:
   toggle + optional renewal date (expiry only ever sent alongside the row's
   current active state; the backend's 422 for expiry-without-enable is surfaced
   verbatim — the typed client now unpacks FastAPI's array-shaped validation
   `detail` into its `msg` strings). `enforced=false` rows render read-only
   ("Not wired yet"): offering a dead switch would be a false promise.
6. **No new dependencies.** The clinician area reuses the ADR-0015 stack wholesale
   (react-router routes, the typed client, `useApi` — extended with the error
   status so 404s are distinguishable, tokens.css, msw test harness). New colors
   reuse already-verified AA pairs and are locked by the same contrast test.

## Consequences

- The dev proxy gains the `/clinic` prefix; still no third-party requests at
  runtime.
- Tests cover role routing both directions, the panel + empty state, the
  same-message-both-ways invite, all four patient-detail views (including the 422
  surfaced verbatim and pagination), the neutral 404 screen, disclaimer presence,
  and the new contrast pairs; the 90% coverage gate is unchanged.
- The patient UI's Home now composes the shared `TrajectoryView` components;
  its rendered markup is unchanged (locked by the existing HomePage tests).

## Addendum (2026-07-13): adversarial-review hardening

- **Renewal = enable-with-expiry.** "Set renewal" no longer echoes the row's
  possibly stale `active` value (which made renewing an expired order 422
  every time): a renewal is an ORDER action that sends `{active: true,
  expires_at}` explicitly, preceded by a fresh read of the capability list so
  the UI acts on — and re-renders — current state. A past `expires_at` is
  labeled "expired", never "renews", and the renewal date input is floored at
  tomorrow (local) so a past date cannot instantly deactivate the order.
- **Trend table completeness.** The cross-source table pages through ALL
  observations (hard cap: 10 pages / 1,000 rows) instead of judging from the
  newest 100; when the cap truncates, the table states "Based on the most
  recent 1,000 of N records" explicitly. Rows are named by the backend display
  (same as the Observations tab), so unregistered codes never render raw.
- **404s collapse the whole detail view.** A 404 from ANY tab fetch (e.g.
  mid-session consent revocation) replaces the entire page — header, consent
  date, and tab chips included — with the neutral not-found screen; no
  post-revocation PHI stays on screen.
- **Unit-change honesty (shared with the patient UI).** When a metric's latest
  two readings carry different unit strings (HbA1c as '%' then 'mmol/mol'),
  neither surface computes a delta or a better/worse verdict: both show a
  "unit changed" note and "not judged". The trend-table judgment words use the
  strong green/red pair, locked at AA by the contrast tests.
