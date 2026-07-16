# How we built this

A durable record of *how* the Neuropathy Care Platform was built — the architecture, the
working method, the phases, and an honest map of what is real versus what is still ahead. It
complements the point-in-time artifacts (the ADRs, the brainstorms, the compliance gap
register) with the story that ties them together. If you are picking this project up, read
[`handoff.md`](handoff.md) first for the operational spine; this doc is the narrative.

> **Honesty up front.** Everything below describes a system built and validated against
> **synthetic data only**, deployed as a **public demo on synthetic data**. It is **not**
> FDA-cleared, **not** HIPAA-certified, and processes **no real PHI**. Where something is a
> plan, a gate, or a pending decision, it is labeled as such. See
> [`../compliance/gap-register/`](../compliance/gap-register/).

## 1. What it is

A non-diagnostic tracking and decision-support platform for neuropathy patients. It fuses
three kinds of signal into one explainable, patient-owned picture:

- **Patient-reported function & symptoms** — a short daily check-in (walking, stairs, balance
  confidence; and, behind a feature toggle, validated-aligned pain and numbness items).
- **Objective measures** — balance/gait metrics from BioMech assessment reports (the V1 PDF
  parser targets an assumed export format; ingesting real BioMech reports is pending an
  API-first rebuild — see `../product/biomech-data-streams.md` §3).
- **Labs** — imported from the patient's EMR via SMART-on-FHIR with the patient's consent.

The headline surface is the **Neuropathy Status Index** — a composite 0–100 score with a
30-day direction and a confidence indicator — presented as a non-diagnostic v1 measure. The
patient owns and controls every data stream; a clinician sees only what a patient has actively
shared.

IP is owned by **Advanced Health and Wellness Group**; **BioMech Health** is the licensee.

## 2. Architecture

**Backend** — FastAPI (async, Python 3.12), PostgreSQL via SQLAlchemy 2.0 async, Alembic
migrations (files-only, append-only), Pydantic v2. Auth is Argon2id + JWT with memory-only
access tokens and a refresh-on-401 path. Layered: `api/` (routes + deps) → `services/` →
`repositories/` (a repository seam with an in-memory and a Postgres implementation kept at
parity) → `models/`. Domain logic lives in pure modules — the trajectory engine
(`trajectory/`) and the composite index (`trajectory/composite.py`) are deterministic and
recomputed on read, never stored as a mutable rollup.

**Frontend** — React 18 + TypeScript (strict), Vite, Recharts. Capacitor 6 wraps it as an
Android app. The design is token-driven (`styles/tokens.css`) with hand-rolled CSS and
AA-contrast locks enforced by a test.

**Platform seams** — the native/web split is isolated behind small injectable modules
(`platform.ts`, `refreshTokenBackend.ts`, `nativeShell.ts`, `reminders.ts`, `exportData.ts`)
so the web and E2E paths never touch native plugins and every decision is unit-testable. The
API base URL resolves at runtime (`/config.js`) so one immutable frontend image serves many
environments.

**Data model — research-grade by construction (ADR-0006).** Every datum is an append-only
`Observation` carrying full provenance (source, origin, who recorded it), dual UTC timestamps,
and standardized coding; corrections are new rows that supersede prior ones via `revises_id`
(never in-place edits). "A datum without its provenance is a bug." Audit events log reads and
writes of health data as **counts and references only — never values**.

## 3. The working method — and why it worked

Every change shipped through one disciplined loop, **one portion per pull request**:

> **build → adversarial review → fix → full gates → merge**

- **Build** the smallest coherent portion.
- **Adversarial review** — independent reviewer(s), prompted to *refute*, verifying each claim
  against the code (a security lens and a correctness lens for anything non-trivial). They ran
  the gates themselves, including bringing up a live Postgres for integration tests.
- **Fix** every real finding; re-review when the fix was non-trivial.
- **Gates** — the full Definition of Done, green, locally before merge.
- **Merge**, then record a preventive rule in [`../lessons.md`](../lessons.md) for any new
  class of mistake and an ADR for any decision or contract change.

**This is not process theater — it repeatedly caught severe bugs that had passing test
suites.** A few real examples from the record:

- An **offline check-in queue** that would have flushed one patient's queued check-ins into
  another patient's record on a shared browser (and a second bug that wiped the queue on an
  offline app boot). Both caught in review; both had green tests.
- An **EMR-connect** change whose nginx proxy rule would have 401'd the OAuth redirect at
  deploy time.
- A **manualChunks** split that created a circular chunk crashing React at runtime — the build
  only *warned*; the E2E console gate is what failed it.
- A **score card** whose color (overall direction) could contradict its arrow (score delta),
  and a later **decline-masking** threshold that quietly hid real declines for higher-scoring
  patients — both caught by adversarial review of the Neuropathy Status Index.

The lesson: green tests prove the code does what the tests assume; an adversary proves the
assumptions.

## 4. The gates (Definition of Done)

Binding merge gate (`../engineering/standards.md`), enforced in a 6-job CI:

- **Backend:** ruff lint + format, mypy `--strict`, pytest with coverage (≥85% on logic; new
  code trends to ~100%), a live-Postgres integration suite, and an Alembic upgrade-head +
  autogenerate-parity check.
- **Frontend:** `tsc`, eslint `--max-warnings 0`, prettier, vitest with coverage (≥90), a
  `vite build` that must be warning- and circular-chunk-free, and a Playwright E2E suite that
  drives the **built** app and fails on any `pageerror` or non-network `console.error` (with a
  self-check spec proving the gate itself works).
- **Mobile:** `cap sync android` warning-free; the CI mobile job proves the APK compiles.
- **Cross-cutting:** no secrets in the diff, PHI-free logs/metrics/audit, permissive licenses
  only (exact SPDX added to the allowlist per dependency).

## 5. The phases

Roughly chronological; each item is one or more merged PRs with its ADRs.

1. **Foundation** — auth, the observation data model, consent, the deterministic trajectory
   engine, the patient home + trends, research-grade data standards.
2. **Clinician surface** — a consent-gated panel and shared patient view (a patient-held
   share-with-clinic that clinicians cannot override).
3. **EMR connect** — SMART-on-FHIR OAuth/PKCE (public client, per-provider client IDs), with
   the native deep-link handler deferred until its UI existed.
4. **Account & data lifecycle** — account/data deletion (password re-auth, rate-limited,
   audit-preserving), a patient data export ("Download my data") proven token-free by
   structure, check-in reminders, and an offline check-in queue.
5. **Mobile** — Capacitor Android scaffold, secure token storage + biometric gate, a signed-AAB
   release workflow, and a Play-listing pack.
6. **Store-readiness polish** — in-app About/Privacy, route-level code-splitting, and a
   top-level ErrorBoundary for lazy-chunk failures.
7. **Compliance gap register** — a five-lens (HIPAA / SOC 2 / Security / FDA / FTC),
   adversarially-verified, **docs-only** gap register with a prioritized remediation roadmap —
   honest about what code satisfies versus what needs organizational action.
8. **Handoff & hosting** — a SessionStart hook, a handoff doc, a funding-strategy memo, a
   narrated screenshot walkthrough, an interactive single-file demo, and **Vercel hosting** so
   the real app runs publicly on synthetic data at a shareable URL that auto-redeploys.
9. **The Neuropathy Status Index (clinical-grade, phased)** — driven by the mandatory
   brainstorming protocol into ADR-0034, then built in two phases:
   - **Phase 1** — validated-aligned symptom capture (pain + numbness) added to the check-in,
     behind an enforced feature toggle, stored with correct higher-is-worse polarity.
   - **Phase 2** — the composite 0–100 index (Symptoms 45 / Function 40 / Physiologic 15 with
     missing-domain renormalization), a Confidence indicator (coverage + recency; adherence
     never enters the number), and the redesigned card (one composite delta drives color,
     arrow, and word; direction in words, not color alone; an explicit `as of` date).

## 6. Decision records & the brainstorm protocol

Every non-trivial choice is an **ADR** (33+ in [`../decisions/`](../decisions/)) — the durable
"why," including the ones that reversed a prior decision (ADR-0034 replaced the earlier
function-only "30 Day Score" design — which was never recorded as its own ADR). Anything product-shaped goes through a **mandatory brainstorming
protocol** (CLAUDE.md §6) that applies 17 stakeholder lenses (physician, patient, BioMech,
HIPAA, SOC 2, FDA/legal, accessibility, reimbursement, data science, clinical validation, …)
and is captured as a dated file in [`../brainstorm/`](../brainstorm/). The clinical-grade score
began as exactly such a brainstorm before any code was written.

## 7. The honesty invariants

These held throughout and are non-negotiable:

- **Synthetic data only** — no real patient data in fixtures, tests, seeds, or screenshots.
- **No secrets in the repo**; PHI-free by construction in logs, metrics, error events, and
  audit detail.
- **Non-diagnostic** — the product does not diagnose or dictate treatment; disclaimers
  co-locate with every clinical-adjacent surface; the Neuropathy Status Index is a v1 index
  **pending validation**, never a diagnosis or severity claim.
- **The gap register is a gap register, not a certification** — it separates "the code
  demonstrably does X" from "this requires your policies, signed BAAs, a deployed environment,
  or professional sign-off."
- **Permissive licenses only**; new native plugins pinned to the Capacitor-6 line.
- Claims match reality: when a validated instrument (e.g., NTSS-6) is only *aligned* and not
  licensed/confirmed, the code stores `validated_instrument: false` and says so.

## 8. Demo & hosting

The real app runs publicly on synthetic data at a Vercel URL that rebuilds on every merge to
`main` (see [`../business/demo/`](../business/demo/) and `frontend/vercel.json`). The bundle
uses an in-browser mock (the E2E mock-API layer) so there is no backend and no PHI risk, plus a
Demo switch for the patient and clinician experiences. A separate self-contained **narrated
walkthrough** (`../business/demo/app-demo.html`) exists for sending to people who won't run it.

## 9. What's real vs. what's pending (the honest map)

**Real today:**
- A feature-complete web app + async backend, exercised end-to-end against synthetic data with
  a comprehensive, adversarially-reviewed test suite and green CI.
- The Neuropathy Status Index (composite score + Confidence + card), computed deterministically.
- A public, auto-updating demo on synthetic data.
- An Android build that compiles in CI (on-device verification is `npx cap run android`).

**Pending (mostly organizational, per the gap register's P0s):**
- **Clinical validation** of the index — instrument licensing, composite psychometrics, and a
  prospective study — before any "validated"/clinical claim.
- **Regulatory** — the FDA §201(h)/SaMD device determination (an open question for a qualified
  consultant); the HIPAA-covered-entity vs FTC-HBNR regime question.
- **A deployed production environment** — TLS in transit and at-rest encryption are coded but
  not operating until a host is chosen; signed **BAAs** (Anthropic AI seam, hosting, metrics).
- **Auth hardening** at the edge (rate-limiting on login/refresh, MFA), and the reimbursement
  (RTM/RPM) build, which is gated on the compliance sign-off.

## 10. Continuing the work

- Operational spine and the "what a new session must handle" section: [`handoff.md`](handoff.md).
- Living status board: [`../roadmap-status.md`](../roadmap-status.md).
- The rules distilled from mistakes: [`../lessons.md`](../lessons.md).
- The honest control posture and the prioritized to-do: [`../compliance/gap-register/`](../compliance/gap-register/).
- Funding sequence (SBIR-first): [`../business/funding-strategy.md`](../business/funding-strategy.md).

The through-line: **build to professional and clinical standards, verify adversarially, and
state plainly what is proven versus what is still ahead.** That discipline is the asset.
