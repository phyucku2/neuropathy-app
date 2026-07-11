# neuropathy-app — Hard Rules

These rules are **binding** on every contributor to this repository, human or AI agent.
If a task conflicts with a rule here, the rule wins — stop and ask the repository owner.

## 0. Priority: build a great product

The goal is an excellent, trustworthy product patients and clinicians love — clear,
fast, accessible, safe. That is the objective every decision serves. The rules below
are guardrails that keep us original, private, and safe **while** we build; they are
not the point of the work. When in doubt, optimize for product quality and user trust,
not for legal ceremony. Originality and confidentiality (§1, §3) protect the owner's
options and are cheap to maintain, so we keep them — but they should never slow down or
distort good product decisions. If a rule ever feels like it's fighting the product,
raise it rather than lawyering around it.

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

## 2. Decision Records (good engineering practice)

Load-bearing decisions get written down so the team stays aligned and future
contributors understand *why*, not just *what*.

- Significant design decisions live in `docs/decisions/` as dated ADRs: the date, the
  problem, the options considered, and why we chose what we chose. Keep them short.
- This is for engineering clarity first. If something genuinely looks novel and worth
  protecting, a one-line note in the ADR is enough to revisit later with counsel — no
  need to hunt for "inventions" or let patent framing shape the design.
- Small, descriptive commits; don't rewrite shared history.

## 3. Confidentiality (keep options open, don't obsess)

The repo is a private, licensed product, so we keep it private — this is low-effort and
protects the owner's choices (including any future filing).

- This repository stays **private** until the owner says otherwise.
- Don't publicly publish, demo, app-store-submit, or describe the product's distinctive
  functionality before the owner says it's time. Pre-launch deployments are auth-gated,
  not indexable.
- Don't paste the repo's code or designs into external services beyond the approved
  development workflow.
- That's it — normal good hygiene for an unreleased product. No need to treat every
  design note as a state secret.

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
- Every brainstorm is captured as a dated file in `docs/brainstorm/` and should call
  out the decisions it forces (which then become ADRs). If something looks genuinely
  novel, a light note is fine — but the goal of a brainstorm is a better product, not
  an inventory of claims.
- A brainstorm that silently omits a listed lens is incomplete — state explicitly if
  a lens has nothing new to add rather than dropping it.

## 7. Engineering Standards (highest quality & performance, always)

We build to professional standards and let recognized external standards settle
questions wherever one exists. Full detail: [`docs/engineering/standards.md`](docs/engineering/standards.md).
The essentials, binding on every change:

- **Quality is enforced, not hoped for.** Ruff (lint + format), mypy **strict**, and
  pytest with a **≥85% coverage** bar on business logic all run in CI; failing checks
  don't merge. Bug fixes ship with a regression test.
- **Performance is budgeted and measured.** Read p95 < 200 ms, write p95 < 500 ms;
  AI/OCR/parsing run as async jobs, never in the request path; hot-path queries indexed;
  no N+1; list endpoints paginate.
- **We follow the named standards:** WCAG 2.2 AA (accessibility), OWASP ASVS L2 /
  Top 10 (security), HIPAA Security Rule + SOC 2 habits (health data), HL7 FHIR R4 +
  LOINC/UCUM (interoperability), OpenAPI 3.1 (API), Twelve-Factor, SemVer, Conventional
  Commits.
- **Definition of Done** (from the standards doc) is the merge checklist: green CI +
  coverage, tests for new behavior, accessibility + privacy + performance checks, docs/
  ADR updated, PR-reviewed and single-concern.
- Prefer the boring, correct, well-supported approach over the clever one. Simplicity
  and clarity are quality.

## 8. Working Agreements

- All development happens on feature branches; nothing is committed directly to `main`.
- Pull requests are the unit of review. Keep them scoped to one concern.
- If a requirement is ambiguous and the ambiguity touches disclosure or health-data
  handling, **ask — don't assume.**

---

*Nothing in this file is legal advice. Patentability, filing timing, and disclosure
strategy are decisions for the owner and qualified patent counsel; these rules exist to
keep those options open.*
