<!-- Keep PRs scoped to one concern. Definition of Done: docs/engineering/standards.md -->

## What & why

<!-- What changed and the reason. Link the issue/ADR if there is one. -->

## Definition of Done

- [ ] CI green: ruff lint + format, mypy strict, tests + coverage (≥85% on logic)
- [ ] New/changed behavior has tests (regression test for any bug fix)
- [ ] Accessibility checked for UI (contrast, targets, screen-reader, plain language) — or N/A
- [ ] Privacy/PHI checked (no new unlogged PHI path, no secrets, least privilege) — or N/A
- [ ] Performance considered (no new N+1, hot-path query indexed, no blocking I/O in request path) — or N/A
- [ ] Docs/ADR updated if a decision or contract changed
