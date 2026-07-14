# Observability & alerting

How to scrape the app's metrics, what to alert on, and how to point the error reporter at
a self-hosted collector. Decisions and rationale: **ADR-0021** (builds on ADR-0018's
PHI-free logging). Everything here keeps the health-data posture: **metrics and error
events are PHI-free by construction** — route *templates*, fixed vocabularies, and
aggregate counters only, never a raw path, patient id, email, value, or exception message.

## Signals at a glance

| Signal | Source | PHI-free because |
|---|---|---|
| Structured request logs | stdout JSON, one line/request (ADR-0018) | whitelist fields; `path` is the route template |
| Metrics | `GET /metrics` (Prometheus text) | labels are method/route-template/status; app counters are subject-free |
| Error events | error-reporting seam → self-hosted collector (opt-in) | scrubbed event: exception *type*, route template, request id, status, timestamp only |

## Metrics endpoint

`GET /metrics` renders Prometheus text (`text/plain; version=0.0.4`). It is
**unauthenticated** like `/healthz`/`/readyz` and exposes nothing sensitive. Exposed
series:

| Metric | Type | Labels | Use |
|---|---|---|---|
| `http_requests_total` | counter | `method`, `route`, `status` | request rate, error rate, per-route status mix |
| `http_request_duration_seconds` | histogram | `method`, `route`, `status` | latency SLOs (p95 read < 200ms, write < 500ms) |
| `app_up` | gauge | — | process liveness (presence + value `1`) |
| `db_connection_pool_in_use` | gauge | — | pool saturation (0 in in-memory mode) |
| `app_ai_narrative_events_total` | counter | `event` | AI-disclosure volume by type (subject-free) |
| `process_*`, `python_info` | collectors | — | cpu/memory/open-fds/start-time, runtime version (single-process only — see multiprocess note below) |

`route` is always the matched **route template** (`/clinic/patients/{patient_id}/trajectory`),
never the raw path — a raw path carries patient ids. An unmatched request is recorded under
the `__unmatched__` sentinel. **Auth-denials and rate-limits are read off the `status`
label** (401/403/429) — they need no separate PHI-bearing counter; the request counter is
the single source of truth.

### Multi-worker exposition (multiprocess mode) — read this before scraping

The production image runs **several workers behind one port** (`WEB_CONCURRENCY`, default 2).
A scrape reaches one worker at random, so a naive per-process registry would expose only that
worker's series — as Prometheus round-robins the workers, counters appear to reset, and
`rate()`/alerts are corrupted. The image fixes this with `prometheus_client` **multiprocess
mode**:

- The container sets **`PROMETHEUS_MULTIPROC_DIR`** (default `/tmp/prometheus-multiproc`).
  Every worker writes its samples to that shared directory, and a `/metrics` scrape builds a
  fresh registry with a `MultiProcessCollector` that **aggregates all workers' files** — so
  counters/histograms sum and the gauges aggregate across workers, regardless of which worker
  the scrape hits. Counters aggregate automatically; `db_connection_pool_in_use` uses
  `multiprocess_mode="livesum"` (total in-use across all live workers' pools) and `app_up`
  uses `"livemax"` (a single `app_up 1` while any worker lives).
- **`process_*` / `python_info` are per-process** and cannot be aggregated, so they are
  **absent from the aggregated scrape** — they render only in single-process/dev mode (var
  unset). Use `app_up` and the request/latency series for multi-worker liveness and load; if
  you need per-process CPU/RSS, scrape the container's node/cAdvisor exporter instead.
- **Server = Gunicorn + Uvicorn workers.** The image runs `gunicorn app.main:app --config
  gunicorn.conf.py` (Uvicorn `worker_class`) rather than bare `uvicorn --workers` for one
  reason: Gunicorn's master-side `child_exit` hook calls `mark_process_dead(pid)` whenever a
  worker exits — crash or graceful — so a dead worker's `live*` gauge files stop skewing the
  aggregated sums. `uvicorn --workers` exposes no equivalent per-worker-death hook.
- **Fresh start = clean dir.** The container entrypoint (`docker-entrypoint.sh`) wipes and
  recreates `PROMETHEUS_MULTIPROC_DIR` on every start, so stale files from a previous boot
  can never be summed into the new process's metrics.

If you deploy with a **single worker** (or run bare `uvicorn` in dev), leave
`PROMETHEUS_MULTIPROC_DIR` unset: `/metrics` renders the in-process registry (including the
`process_*`/`python_info` collectors) with no extra setup.

### Wiring a scraper (Prometheus)

Scrape on the internal network (in K8s: a `ServiceMonitor`/`PodMonitor`, or a static
target). Because `/metrics` is PHI-free, internal exposure carries no PHI risk regardless
of binding; still, do not publish it on a public ingress (it aids fingerprinting).

```yaml
# prometheus.yml — static example (adapt to your service discovery)
scrape_configs:
  - job_name: neuropathy-backend
    metrics_path: /metrics
    scrape_interval: 15s
    static_configs:
      - targets: ["neuropathy-backend.internal:8000"]
```

## Alert rules (examples)

Starting rules for Prometheus Alertmanager. **Tune thresholds to your traffic and SLOs**;
these are illustrative, not validated for a specific deployment. Route them to your
on-call channel via Alertmanager.

```yaml
groups:
  - name: neuropathy-backend
    rules:
      # High 5xx rate — server errors as a fraction of all requests.
      - alert: HighServerErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
            / sum(rate(http_requests_total[5m])) > 0.05
        for: 10m
        labels: { severity: critical }
        annotations:
          summary: ">5% of requests are 5xx over 10m"

      # Readiness flapping — an instance repeatedly reporting not-ready (503 on /readyz).
      - alert: ReadinessFlapping
        expr: |
          sum(rate(http_requests_total{route="/readyz",status="503"}[5m])) > 0
        for: 10m
        labels: { severity: warning }
        annotations:
          summary: "/readyz returning 503 — an instance cannot reach its database"

      # DB pool exhaustion — connections in use at/above the configured pool_size (10).
      - alert: DbPoolNearExhaustion
        expr: max_over_time(db_connection_pool_in_use[5m]) >= 10
        for: 5m
        labels: { severity: warning }
        annotations:
          summary: "DB connection pool at capacity (pool_size=10; +20 overflow headroom)"

      # Elevated auth-denials / rate-limits — read off the status label, no PHI counter.
      - alert: ElevatedAuthDenials
        expr: |
          sum(rate(http_requests_total{status=~"401|403"}[5m])) > 5
        for: 10m
        labels: { severity: warning }
        annotations:
          summary: "Sustained 401/403 — possible credential stuffing or misconfig"

      - alert: ElevatedRateLimiting
        expr: sum(rate(http_requests_total{status="429"}[5m])) > 1
        for: 10m
        labels: { severity: warning }
        annotations:
          summary: "Sustained 429s — a client is hitting a rate limit"

      # Latency SLO burn — read p95 over its 200ms budget (CLAUDE.md §7).
      - alert: ReadLatencySloBurn
        expr: |
          histogram_quantile(
            0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
          ) > 0.2
        for: 15m
        labels: { severity: warning }
        annotations:
          summary: "p95 request latency > 200ms over 15m"

      # Process down — no series / app_up absent (dead man's switch style).
      - alert: BackendDown
        expr: absent(app_up) or app_up < 1
        for: 2m
        labels: { severity: critical }
        annotations:
          summary: "Backend not exposing app_up — process down or unscrapable"
```

## Error reporting (self-hosted collector)

The error-reporting seam (ADR-0021) is **off by default**. It activates only when
`ERROR_REPORTING_DSN` is set to a **self-hosted, permissive** collector URL you run (e.g.
GlitchTip/Sentry self-hosted, or a small HTTP intake) under your own control / BAA. When
an unhandled exception occurs, the app POSTs a **PHI-scrubbed** JSON event and never
changes the client-facing response:

```json
{
  "exception_type": "ValueError",
  "route": "/clinic/patients/{patient_id}/trajectory",
  "method": "GET",
  "status": 500,
  "request_id": "trace-abc-123",
  "timestamp": "2026-07-14T12:00:00+00:00",
  "env": "production"
}
```

The exception **message**, query string, body, headers, and every patient datum are
**never** included. A reporter failure is swallowed (fail-safe) — it can never break a
request.

**Correlation always works, including for 500s.** The request-logging middleware resolves a
`request_id` for **every** request up front — the inbound `X-Request-ID` if present, else a
generated one — and stashes it on the request before the handler runs. So an unhandled
exception produces **both** a request-log line (status 500, that id) **and** an error event
carrying the **same** id: `request_id` joins the two even when the client sent no header.
(Because the 500 is rendered by the framework's error handler, the `X-Request-ID` response
header is only echoed on non-500 responses; the log line and error event remain the durable
correlation point for a 500.)

```bash
# Point the app at your self-hosted collector (config env var; never a committed value).
ERROR_REPORTING_DSN="https://errors.internal.example/intake"
ERROR_REPORTING_TIMEOUT_SECONDS=3.0   # short: a slow collector never drags a failed request
```

Why a pluggable seam and not a hardcoded SaaS: a covered entity may only send PHI-adjacent
telemetry to a BAA-covered or self-hosted destination. Hardcoding a SaaS DSN would create
surprise egress; the seam keeps the destination the operator's explicit choice and the
event PHI-free regardless. See ADR-0021.

## Not covered here

Dashboards (Grafana), log aggregation/retention, tracing, and the Alertmanager receiver
config are deployment-specific and owned by the covered entity's ops platform. This doc
provides the app-side contract (what is exposed and how it stays PHI-free); the collector,
scraper, and notification wiring are operated externally.
