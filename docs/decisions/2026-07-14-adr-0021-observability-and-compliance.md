# ADR-0021: Observability & Compliance — PHI-Free Metrics, an Error-Reporting Seam, and the Compliance Pack

**Date:** 2026-07-14
**Status:** Accepted
**Builds on:** ADR-0011 (AI narrative seam — the swappable, off-by-default, config-gated
pattern mirrored here), ADR-0017 (fail-closed config; encrypted token vault; blocking
scans), ADR-0018 (deployment; PHI-free structured request logging; health/readiness; the
`SECRET_STORE_KEY` backup trap), ADR-0019 (per-operator ops accounts / deactivation),
ADR-0020 (toggle enforcement wiring).

## Context

The app was deployable (ADR-0018) but not yet **operable**: there were no metrics for a
scraper, no error-tracking path, no alerting guidance, no verified backup procedure, and no
compliance pack tying the health-data posture to HIPAA operations. This portion adds that —
under the same non-negotiable constraint as every other portion: **PHI-free by
construction**. Observability is exactly where PHI leaks (a raw path with a patient id in a
metric label; an exception message with an email in an error report), so the design work is
mostly about what we deliberately **exclude**.

## Decision

### 1. Metrics endpoint — `GET /metrics`, PHI-free Prometheus text

A new `app/core/metrics.py` exposes Prometheus metrics via `prometheus_client`
(Apache-2.0 AND BSD-2-Clause — both permissive; no transitive deps; added to
`backend/pyproject.toml` with a license comment, and its exact SPDX string
`Apache-2.0 AND BSD-2-Clause` added to the CI Python license allowlist so the blocking scan
stays green). `GET /metrics` lives beside `/healthz`/`/readyz` in `app/api/routes/health.py`,
is **unauthenticated** like them, and renders `text/plain; version=0.0.4`.

**PHI-exclusion rules (the whole point):**

- The request counter (`http_requests_total`) and latency histogram
  (`http_request_duration_seconds`) are labelled by **method**, **route template**, and
  **status** — never the raw path. The `route` label reuses the exact route-template
  extraction the logging middleware uses (`request.scope["route"].path`, or the
  `__unmatched__` sentinel), because a raw path can embed a patient id/email/token in a
  segment. Method and status are fixed vocabularies, safe to label.
- App metrics carry only **aggregate, subject-free** facts: `app_up`,
  `db_connection_pool_in_use` (read cheaply off the in-process pool at scrape time),
  `app_ai_narrative_events_total{event}` (disclosures counted **by type**, never by
  subject), and the `process_*`/`python_info` collectors. No metric is ever keyed by who a
  request was about, or by any value.
- **Auth-denials and rate-limits need no PHI-bearing counter** — they are read off the
  `status` label (401/403/429). The request counter is the single source of truth; a
  separate per-subject counter would only add leakage surface.

**Endpoint exposure posture.** `/metrics` is unauthenticated for scraper simplicity, exactly
like the health probes. Because it is **PHI-free by construction**, its exposure is not a PHI
risk regardless of where it is bound. In a K8s deployment it is scraped on the internal
network (a `ServiceMonitor`/static target); operators should keep it off a public ingress to
avoid fingerprinting, but that is defense-in-depth, not a PHI control. We deliberately did
**not** add a second bind-address/port for it (that is an infra concern the deployment owns)
— keeping the payload PHI-free is the durable guarantee, not network placement.

**Middleware ordering (composes with ADR-0018).** A `MetricsMiddleware` records each request.
The onion is now (outermost → innermost): `RequestLoggingMiddleware` → `MetricsMiddleware` →
`ErrorReportingMiddleware` → the upload guard → router. Logging **stays outermost** (the
ADR-0018 §4 guarantee and its test are untouched). Metrics sits just inside it so it counts
every request including upload-guard short-circuits, and records in a `finally` so an
**unhandled 5xx is still counted** — which is what makes the high-5xx alert measurable —
before the exception propagates to the normal error handling. The client-facing response is
never altered by any of these middleware.

### 2. Error-reporting seam — off by default, self-hostable, PHI-scrubbing, fail-safe

`app/core/errors.py` adds an `ErrorReporter` **Protocol**, mirroring the Narrator seam
(ADR-0011): swappable, **off by default**, config-gated. It activates only when
`ERROR_REPORTING_DSN` is set to a self-hosted, permissive collector URL. `deps.py` grows
`get_error_reporter()` alongside `get_narrator()` (same lru-cached, fail-closed shape).

- **PHI scrub by construction.** The emitted `ErrorEvent` is a frozen whitelist:
  exception **type name**, **route template**, method, status, request id, ISO timestamp,
  env. The exception **message is never included** (it could echo a patient id/email/value),
  nor is the query string, body, headers, or any path-parameter value. `build_error_event`
  touches the exception only for `type(exc).__name__`.
- **Capture without changing the response.** `ErrorReportingMiddleware` catches an unhandled
  exception on its way to the normal 500 handler, forwards a scrubbed event, and **re-raises
  unchanged** — the client still gets the app's normal error, and only truly-unhandled
  exceptions (not `HTTPException`s already handled inside the router) are reported.
- **Fail-safe.** A reporter that raises, times out, or is misconfigured is swallowed (logged
  PHI-free) and can never break the request. The transport (`HttpErrorReporter`) POSTs the
  event as JSON over the **existing** `httpx` dependency with a short timeout.

**Why a pluggable seam over a hardcoded SaaS.** A covered entity may only send
PHI-adjacent telemetry to a **self-hosted** or **BAA-covered** destination. Hardcoding a SaaS
DSN would create surprise egress and a licensing/BAA entanglement we cannot make on the
owner's behalf. We deliberately prefer a **tiny dependency-free HTTP reporter** (no new
dependency, no SaaS SDK, no `sentry-sdk`) so the permissive-license + no-surprise-egress
posture stays clean; the payload is PHI-scrubbed regardless of where the operator points it,
and a self-hosted GlitchTip/Sentry-compatible intake is a drop-in target.

### 3. Alerting hooks — documented, code only where cheap

`docs/ops/observability.md` documents how to scrape `/metrics`, example Prometheus alert
rules (high 5xx rate, readiness flapping, DB-pool exhaustion, elevated auth-denials/
rate-limits, latency SLO burn, process-down), and how to point the error reporter at a
self-hosted collector. Code exists only where an alert needs it: the counters above are
exposed; no live third-party integration is added (Alertmanager receivers, Grafana, and log
aggregation are covered-entity infra).

### 4. Postgres backup drill — a concrete, tested procedure + a script

`scripts/pg_backup_drill.sh` performs a `pg_dump` → `pg_restore`-to-scratch roundtrip with a
read-back check and safe teardown; it never writes to the source DB and refuses to clobber an
existing scratch database. `docs/ops/backup-restore.md` is extended with the scripted drill,
a full end-to-end (app + key) drill, and a manual-verification checklist. It **reinforces the
`SECRET_STORE_KEY`-separate-from-DB trap** (ADR-0018 §6): the script proves the DB half and
prints the manual key-pairing step it cannot automate. The drill was executed here against a
scratch database; it is **not** wired into the unit suite (no destructive DB ops in CI).

### 5. Compliance pack — `docs/compliance/`

Three operational docs, accurate to what the app **does**, with honest gaps and explicit
covered-entity boundaries: `hipaa-ops-checklist.md` (Security Rule mapped to
audit-on-read+write [done], token-vault encryption at rest [ADR-0017], consent-scoped access
[ADR-0012/0020], PHI-free logs/metrics [done], backup drill, BAA gating [ADR-0011], incident
response), `baa-inventory.md` (every third party that could receive PHI — Anthropic gated
OFF until attested, EMR providers patient-authorized, hosting/cloud [CE prerequisite], the
error/metrics collector must be self-hosted or BAA-covered), and
`incident-response-runbook.md` (detect → contain → assess → notify per HIPAA timelines →
remediate → post-mortem). Every item requiring the covered entity's own policies/legal is
marked **[CE]**; the pack is explicitly **not legal advice or an attestation**.

## Consequences

- **New code:** `app/core/metrics.py`, `app/core/errors.py`; `GET /metrics` in
  `app/api/routes/health.py`; `MetricsMiddleware` + `ErrorReportingMiddleware` wired in
  `app/main.py` (logging stays outermost); `get_error_reporter` in `app/api/deps.py`;
  `ERROR_REPORTING_DSN` / `ERROR_REPORTING_TIMEOUT_SECONDS` in `app/core/config.py`; an
  AI-disclosure counter increment in `app/api/routes/trajectory.py`. New tests
  (`test_metrics.py`, `test_errors.py`) are the PHI-free enforcement seam — a request to
  `/clinic/patients/<uuid>/trajectory` is asserted to produce a metric labelled with the
  **template**, and the uuid appears **nowhere** in `/metrics`; an exception whose message
  carries a fake patient id/email is asserted **absent** from the emitted error event.
- **New dependency:** `prometheus-client` (Apache-2.0 AND BSD-2-Clause; no transitive deps).
  CI license allowlist updated with that exact SPDX string; all other CI jobs unchanged.
- **New docs:** `docs/ops/observability.md`, `docs/compliance/{hipaa-ops-checklist,
  baa-inventory,incident-response-runbook}.md`; `scripts/pg_backup_drill.sh`; extensions to
  `docs/ops/backup-restore.md` and `docs/ops/deployment.md`.
- **Posture preserved:** all backend gates green (ruff, ruff format, mypy --strict, pytest at
  **100%** incl. live Postgres); secret scan clean (the error DSN is a config env var, never
  a committed value); frontend untouched.
- **Deferred to the covered entity / later portions:** TLS in transit and full-disk
  encryption at rest (hosting), the cloud-provider BAA, Alertmanager/Grafana/log-aggregation
  wiring, DR RPO/RTO targets, and enabling either egress seam (AI narrative, error reporting)
  — each is off until an explicit operator/BAA action.
