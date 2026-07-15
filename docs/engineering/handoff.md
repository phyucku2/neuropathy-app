# Handoff & onboarding

The one page a new contributor — human **or** an AI agent (Claude Code) — reads first to
continue this project without losing context. It points at the living records; it does not
duplicate them.

## What this project is

A non‑diagnostic tracking and decision‑support platform for neuropathy patients: patient‑
reported daily function (ADL check‑ins), lab results imported from the patient's EMR via
SMART‑on‑FHIR with the patient's consent, and balance/gait metrics from BioMech assessment
reports — fused into an explainable trend (direction, confidence, named signals). IP is owned
by **Advanced Health and Wellness Group**; **BioMech Health** is the licensee.

Read `CLAUDE.md` (hard rules) before anything else.

## Repo map — where things live

| Area | Path |
|---|---|
| Hard rules & working agreements | `CLAUDE.md` |
| Backend (FastAPI, async, Postgres, SQLAlchemy 2.0, Alembic) | `backend/app/` |
| Frontend (React 18 + TS strict, Vite; Capacitor 6 for Android) | `frontend/src/`, `frontend/android/` |
| Decision records (ADRs, 0001→) | `docs/decisions/` |
| Living status board (waves/portions) | `docs/roadmap-status.md` |
| Preventive rules (mistakes → one‑line rules) | `docs/lessons.md` |
| Compliance posture (honest gap register) | `docs/compliance/gap-register/` |
| Reimbursement analysis + sign‑off packet | `docs/product/` |
| Business briefs + funding strategy | `docs/business/` |
| Engineering standards + Definition of Done | `docs/engineering/standards.md` |
| Ops runbooks (deploy, backup, observability) | `docs/ops/` |

## How work is done here (the build loop)

Work ships **one portion per PR** through a disciplined loop:

1. **Build** the smallest coherent portion on the designated branch (see below).
2. **Adversarially review** it — at least a security lens and a correctness lens, each
   prompted to *refute*, verifying every finding against the code (not the commit message).
   This loop has repeatedly caught severe bugs that had passing test suites; it is not
   optional theater.
3. **Fix** every real finding; re‑review if the fix is non‑trivial.
4. **Gate** — run the full Definition of Done locally and make it green.
5. **Merge** — draft PR, CI green, then merge. Record a lesson in `docs/lessons.md` for any
   new class of mistake, and an ADR for any decision or contract change.

## The gates (Definition of Done — binding merge gate)

Authoritative copy: `docs/engineering/standards.md` and the PR template. In short:

- **Backend:** `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` with coverage
  (≥85% on logic; new code trends to 100%). Postgres‑backed tests use a `pg_ctl`‑started
  `neuropathy_test` DB — follow the existing pattern.
- **Frontend:** `tsc --noEmit`, `eslint . --max-warnings 0`, `prettier --check .`,
  `vitest run --coverage` (≥90 all four metrics), `vite build` (no circular‑chunk / 500 KB /
  any warning), and `CI=1 playwright test` (drives the **built** app; zero `pageerror` /
  non‑network `console.error`).
- **Mobile:** `cap sync android` warning‑free. No Android SDK here → the CI mobile job proves
  the APK compiles; true on‑device behavior is verified by the owner via `npx cap run android`.
- **Cross‑cutting:** no secrets in the diff; PHI‑free logs/metrics/audit; permissive licenses
  only (exact SPDX string added to the CI allowlist when a dep is introduced).

## Invariants that must never be broken

- **Synthetic data only.** No real patient data in fixtures, tests, seeds, or screenshots.
- **No secrets in the repo.** Credentials live in the environment's secrets manager / local
  gitignored `.env`.
- **PHI‑free by construction** in logs, metrics labels, error events, and audit `detail`
  (counts/references, never values).
- **Permissive licenses only**; pin new Capacitor plugins to the Cap‑6 line.
- **Compliance docs are a gap register, not a certification.** Never claim the product is
  compliant/certified/cleared. Separate "code satisfies X" from what needs organizational
  action (policies, BAAs, a deployed environment, professional sign‑off).
- **Wave 4 (reimbursement‑enabling features) is gated** on the compliance sign‑off packet
  coming back and the FDA device‑status determination — do not build it speculatively.
- **Branch discipline:** develop on `claude/neuropathy-app-repo-nthuy6`; never push to another
  branch without explicit permission. If that branch's PR is already merged, restart it from
  the latest default branch for follow‑up work (a merged PR is finished).
- **Commit trailer:** end commits with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (and the session trailer when
  present). Do **not** put internal model identifiers in repo artifacts.

## Current state (update this as it changes)

- **Web app + backend:** feature‑complete through the patient + clinician surfaces, EMR
  connect (SMART/PKCE), account deletion, check‑in reminders, offline check‑in queue, and
  patient data export.
- **Mobile:** Capacitor Android scaffold + signed‑AAB release workflow; store‑listing pack
  drafted; on‑device verification pending the owner.
- **Compliance:** the five‑lens gap register is in `docs/compliance/gap-register/` (137 items;
  the P0s are the blockers before real PHI).
- **Blocked on the owner:** DUNS/UEI (→ SBIR registration + production stand‑up), a chosen
  hosting provider, signed BAAs, and the FDA device‑status determination. These are the P0s in
  the gap register and the sequencing in `docs/business/funding-strategy.md`.

## What a Claude Code session needs to handle when it picks this up

1. **Boot & verify green first.** A `SessionStart` hook (`.claude/settings.json` →
   `.claude/hooks/session-start.sh`) installs deps and prints how to run the gates. Confirm the
   toolchain works before making changes; if the hook reports a problem, fix that before
   building.
2. **Read the spine, in order:** `CLAUDE.md` → this file → `docs/roadmap-status.md` →
   `docs/lessons.md` → the relevant ADRs. Then the gap register if the task is compliance‑
   adjacent.
3. **Confirm the task and its wave.** Check `roadmap-status.md` for where it fits and whether
   it's gated (esp. anything Wave 4 / reimbursement / FDA — those need owner sign‑off, not
   autonomous building).
4. **Run the loop above** — build → adversarial review → fix → gate → merge, one portion per
   PR, on the designated branch. Use background subagents for the reviews; verify their
   findings.
5. **Stop for genuine decisions only.** Business/product/regulatory choices (org identity,
   pricing, what to bill, FDA posture, publishing anything outward‑facing) are the owner's.
   Engineering defaults are yours to pick and note.
6. **Keep the records honest and current** in the same PR as the change: `roadmap-status.md`,
   a new ADR for decisions/contracts, a `lessons.md` rule for any new mistake‑class, and the
   relevant brief in `docs/business/briefs/` if the facts it states have changed.
7. **Never** commit secrets or real PHI, claim compliance, or push to a non‑designated branch.
