# neuropathy-app — Hard Rules

These rules are **binding** on every contributor to this repository, human or AI agent.
They exist to keep this build clean-room, original, and patent-eligible. If a task
conflicts with a rule here, the rule wins — stop and ask the repository owner.

---

## 1. Clean-Room / Fresh Build (non-negotiable)

This is a **from-scratch build**. It shares no lineage with any prior project.

- **Do NOT read, reference, copy, adapt, or mirror** anything from any other repository
  owned by or associated with this account — including but not limited to
  `menopause-portal`, `menopausal-me`, `Diametrics.ai`, `Equine-Directory`, or any other
  prior work. Not code, not schemas, not folder structures, not design specs, not docs,
  not naming conventions, not "proven patterns."
- Prior repos may not be opened even "for pattern reference only." There is no
  read-only exception.
- If you realize mid-task that you have been exposed to prior-project material in the
  current session, say so explicitly, discard that context, and design independently
  from first principles.
- Generic, industry-standard practices (e.g. REST conventions, OWASP guidance, WCAG
  accessibility) are fine — they are public knowledge, not prior-project IP. The line:
  if it came from *our* earlier work, it stays out; if it's in any textbook, it's fine.

## 2. IP Provenance & Invention Record

Everything novel must be traceable to its origin **inside this repo**.

- All design decisions live in `docs/decisions/` as dated Architecture Decision Records
  (ADRs): one file per decision, with the date, the problem, the options considered, and
  why the chosen approach was selected.
- Novel mechanisms — algorithms, scoring methods, data models, interaction flows that
  may be claimable — get flagged in their ADR with a `> INVENTION CANDIDATE` note so
  patent counsel can find them.
- Commits are small and descriptive. The git history is part of the invention record;
  never squash away or rewrite history on shared branches.

## 3. Confidentiality / No Public Disclosure

Premature disclosure can destroy patent rights (immediately in most non-US
jurisdictions; a 12-month clock in the US).

- This repository stays **private** until the owner says otherwise.
- No part of the app's novel functionality may be published, demoed publicly, posted to
  forums/social media, submitted to app stores, or described in public issue trackers
  before the owner confirms a patent filing strategy with counsel.
- Deployments before filing must be access-controlled (auth-gated, not indexable).
- Do not paste novel code or designs from this repo into external services beyond what
  the owner has already approved for the development workflow.

### Client / licensee relationship (BioMech Health)

The app is built at the request of **BioMech Health**. **We own all IP; BioMech
Health is a licensee** (see `docs/decisions/2026-07-11-adr-0001-ip-ownership-and-licensing.md`).

- Sharing anything from this repo with BioMech Health is third-party disclosure:
  NDA/agreement first, minimum necessary before patent filing, and mechanisms only
  with counsel's clearance.
- Their inbound briefs/requirements are legitimate design inputs (the clean-room rule
  bars *our own prior builds*, not client input). Store them under
  `docs/requirements/biomech-health/` with received-dates so provenance is auditable.
- If their personnel suggest inventive concepts, flag it immediately — inventorship
  affects ownership and counsel must paper it.

## 4. Third-Party Code & Licensing

- Every dependency added must have a permissive license (MIT, Apache-2.0, BSD, ISC).
  **No GPL/AGPL/SSPL** or unlicensed code.
- No copy-pasting code from blog posts, Stack Overflow, or other projects. Write it
  fresh. Libraries are consumed as dependencies, never vendored by copy-paste, unless
  the owner approves a specific exception.
- Record every dependency addition in the commit message that introduces it.

## 5. Health Data & Safety

This is a health application. Even before any real user data exists:

- Design every schema and endpoint assuming the data will be Protected Health
  Information: least-privilege access, per-user record isolation, audit logging on
  reads and writes of health data.
- **No secrets in the repo.** Credentials, API keys, and connection strings live only
  in local `.env` files (gitignored) or a secrets manager. No sample secrets in docs.
- No real patient/user data in fixtures, tests, seeds, or screenshots — synthetic data
  only.
- The app must not present itself as providing diagnosis or treatment decisions without
  the owner's explicit direction and appropriate disclaimers; wording of any clinical
  claims is an owner-level decision.

## 6. Brainstorming Protocol (mandatory)

Whenever brainstorming is performed in this project (the user asks to "brainstorm,"
invokes a brainstorming skill, or requests ideation/review of a feature, product, or
plan), **every lens below must be applied — no skipping** — plus any additional
lenses relevant to the specific topic being brainstormed:

1. Physician (neurology / endocrinology / podiatry / primary care)
2. Patient
3. BioMech Health (the client/licensee — their stated requirements and fit)
4. Apple developer (iOS)
5. Android developer
6. HIPAA / privacy
7. SOC 2 / security
8. Marketing
9. Legal & regulatory (incl. FDA SaMD, licensing, patents)
10. Accessibility
11. Payer / reimbursement
12. Data science / ML
13. Clinical research / validation
14. Caregiver / family
15. Agile (operating model, phasing, backlog impact)
16. DevOps (CI/CD, infra, release, observability impact)

Rules of engagement:
- Add topic-specific lenses beyond this list whenever the subject warrants it (e.g.
  hardware partner, pharmacist, health-economics), and record any newly added lens
  here so the canonical list grows.
- Every brainstorm is captured as a dated file in `docs/brainstorm/` (it is part of
  the invention record) and must flag `> INVENTION CANDIDATE` items and the decisions
  it forces (which then become ADRs).
- A brainstorm that silently omits a listed lens is incomplete — state explicitly if
  a lens has nothing new to add rather than dropping it.

## 7. Working Agreements

- All development happens on feature branches; nothing is committed directly to `main`.
- Pull requests are the unit of review. Keep them scoped to one concern.
- If a requirement is ambiguous and the ambiguity touches patentability, disclosure,
  or health-data handling, **ask — don't assume.**

---

*Nothing in this file is legal advice. Patentability, filing timing, and disclosure
strategy are decisions for the owner and qualified patent counsel; these rules exist to
keep those options open.*
