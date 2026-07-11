# Engineering Standards

Highest quality and performance, always. These standards are binding (CLAUDE.md §7) and
enforced in CI — code that doesn't meet them doesn't merge. They lean on recognized
professional standards rather than house opinion wherever one exists.

## Recognized standards we follow
- **Accessibility:** WCAG 2.2 AA (primary persona is older adults with low vision /
  reduced sensation — this is a hard floor, not a nice-to-have).
- **Security:** OWASP ASVS L2 and the OWASP Top 10 as the review checklist; least
  privilege; secure-by-default.
- **Privacy/health data:** HIPAA Security Rule technical safeguards; SOC 2 control
  habits from day one (change mgmt, access control, logging, monitoring).
- **Interoperability:** HL7 FHIR R4 as the modeling reference for clinical data
  (labs → Observation/LOINC); units normalized (UCUM) before trending.
- **API:** REST + OpenAPI 3.1; semantic, versioned, documented.
- **Operational:** the Twelve-Factor App for config/deploy; SemVer for versioning;
  Conventional Commits for history.

## Code quality (enforced in CI)
- **Lint + format:** Ruff (lint + formatter) for Python; zero warnings. No disabled
  rules without an inline justification comment.
- **Types:** mypy in **strict** mode; no `Any` escapes without a comment explaining why.
  Full type coverage on new code.
- **Tests:** pytest; **≥85% line coverage** on business logic (services, ingestion, ai),
  and every bug fix ships with a regression test. Tests are deterministic and isolated
  (no network, no real PHI — synthetic fixtures only).
- **No dead code, no commented-out code, no TODOs without an issue link.**
- **Readability:** code matches the surrounding style; names say intent; functions do
  one thing. Comments explain *why*, not *what*.

## Performance (budgets, measured not guessed)
- **API latency:** p95 < 200 ms for read endpoints, p95 < 500 ms for write endpoints
  (excluding intentionally-async work like AI analysis and document parsing, which run
  in background workers and are never in the request path).
- **AI / ingestion** are asynchronous jobs with progress states — never block a user
  request on an LLM or OCR call.
- **Database:** every query the app runs in a hot path is indexed; no N+1 (eager-load or
  batch); all list endpoints paginate; connection pooling tuned. Slow-query logging on.
- **Mobile:** cold start < 2 s target; 60 fps scrolling; images/assets sized and lazy;
  offline-tolerant with last-known state.
- **Regression guard:** performance-sensitive paths get a benchmark; CI flags
  significant regressions.

## Security & data handling
- No secrets in the repo — ever. Config via env / secrets manager (Twelve-Factor).
- All input validated at the boundary (Pydantic); uploaded documents are untrusted —
  sandboxed parsing, size/type limits, malware scan, sanitize before the AI layer.
- Every patient-scoped query filters by `patient_id` (and clinic in the clinical
  version). PHI reads/writes and config changes are audit-logged.
- Dependencies: permissive licenses only (§4); automated vulnerability + license
  scanning in CI; pinned versions; prompt updates on advisories.

## Definition of Done (every PR)
1. Lint, format, type-check, and tests green in CI; coverage bar met.
2. New/changed behavior has tests (incl. a regression test for fixes).
3. Accessibility checked for any UI (contrast, targets, screen-reader, plain language).
4. Privacy/PHI checked (no new unlogged PHI path; no secrets; least privilege).
5. Performance considered (no new N+1, hot-path query indexed, no blocking I/O in
   request path); budget-affecting changes measured.
6. Docs/ADR updated if a decision or contract changed.
7. Reviewed via PR; scoped to one concern; Conventional Commit messages.

## How it's enforced
- **CI (`.github/workflows/ci.yml`)** runs ruff (lint+format check), mypy strict,
  pytest+coverage, and dependency/license/secret scanning on every PR.
- **Branch protection** on `main`: PRs only, CI must pass. (Configure in repo settings.)
- Local parity: `ruff check`, `ruff format`, `mypy`, `pytest` all runnable before push.
