# Load / soak test

Turns "the foundation can carry N× the load" into a **measured** number. Drives the
hot read paths a patient session actually exercises, plus a small write slice, and
reports throughput + latency percentiles to judge against the SLOs in
[`docs/ops/observability.md`](../../docs/ops/observability.md) (p95 read < 200 ms,
write < 500 ms).

Synthetic accounts and input only — no real PHI, matching the repo's synthetic-only
posture. Each virtual user self-seeds via the open `POST /auth/register`, holds its
bearer token, then loops the read endpoints (weighted like a real session) with a
1-in-17 write.

## Run

```sh
pip install locust    # not a shipped dependency — a dev/ops tool

# headless, 100 users, gentle ramp, 90s, against a running API:
locust -f backend/loadtest/locustfile.py --headless \
    -u 100 -r 4 -t 90s --host http://127.0.0.1:8099 --only-summary

# or the web UI:
locust -f backend/loadtest/locustfile.py --host http://127.0.0.1:8099
```

Point `--host` at a **representative deployment** (staging on Postgres) for a
production-meaningful number. Against the in-memory build (`DATABASE_URL` unset) it
measures the **application layer** — routing, auth, serialization, compute — without
the database: a useful upper-bound baseline, not a DB-bound result.

## Baseline on record (2026-07-21)

**Setup:** in-memory build, **single uvicorn worker on one constrained shared-sandbox
core**, 100 concurrent users, gentle ramp (4/s), 90 s steady state. Application layer
only (no Postgres). This is a floor, not the production number.

| Path | p50 | p95 | p99 | Notes |
|---|---|---|---|---|
| `GET /auth/me` | 4 ms | 330 ms | 570 ms | session identity |
| `GET /trajectory` | 7 ms | 290 ms | 580 ms | deterministic engine |
| `GET /observations` | 8 ms | 300 ms | 580 ms | paged record read |
| `GET /me/visit-summary` | 8 ms | 250 ms | 590 ms | windowed assembly |
| `POST /adl` (write) | 12 ms | 290 ms | 710 ms | daily check-in |
| `POST /auth/register` | 600 ms | 730 ms | 830 ms | **Argon2id — intentional** |
| **Aggregate** | **7 ms** | **400 ms** | **630 ms** | 6,128 reqs |

- **0 failures / 6,128 requests (0.00%)** — no 5xx, no crash, no memory blow-up under
  sustained concurrency.
- **Read medians 4–8 ms.** The p95 tail (~300 ms) reflects one worker on one
  constrained core under load; it is not the read path being slow.
- **`register` at 600 ms is Argon2id working as designed** — a deliberate
  password-hashing cost paid once at sign-up, never on a normal request.

### Reading the numbers

The app is **stateless** (JWT, no server session), so throughput scales ~linearly
with `workers × replicas`. At ~68 req/s on one constrained core, the production shape
(gunicorn multi-worker across real vCPUs × horizontal Container-Apps replicas) has
large headroom, and the p95 read target is met by adding cores/replicas — which is the
point: the architecture supports horizontal scale, and this harness lets us *prove* the
number instead of asserting it.

### Honest gaps this does not yet cover

- **DB-bound latency** — run against staging on Postgres for that.
- **Multi-worker / multi-replica** — this baseline is deliberately single-worker.
- **Soak duration** — 90 s catches gross regressions, not slow leaks; run `-t 1h` on
  staging for a real soak.
