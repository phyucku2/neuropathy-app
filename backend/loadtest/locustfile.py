"""Load / soak test for the Neuropathy backend API (Locust).

Purpose
-------
Make "the foundation can carry N× the load" a *measured* number instead of a
belief. This drives the **hot read paths** a patient session actually exercises —
the ones that must stay fast under fan-out — and records throughput + latency
percentiles so a run can be judged against the SLOs in
``docs/ops/observability.md`` (p95 read < 200 ms, write < 500 ms).

What it does
------------
Each simulated user self-seeds once (``POST /auth/register`` is open, so no
fixture data or shared credential is needed), holds its bearer token, then loops
over the read endpoints weighted the way a real session hits them. A small slice
writes (a daily check-in) so the write path is represented, not just reads.

Honesty
-------
- Synthetic accounts and synthetic input only — no real PHI, matching the repo's
  synthetic-only posture.
- Run this against a **representative deployment** (staging on Postgres) for a
  production-meaningful number. Against the in-memory build it measures the
  **application layer** (routing, auth, serialization, compute) without the
  database — a useful upper-bound baseline, clearly not a DB-bound result.

Run
---
    pip install locust
    # headless, 200 users, ramp 20/s, 1 minute, against a running API:
    locust -f backend/loadtest/locustfile.py --headless \
        -u 200 -r 20 -t 1m --host http://127.0.0.1:8099

    # or open the web UI:
    locust -f backend/loadtest/locustfile.py --host http://127.0.0.1:8099
"""

from __future__ import annotations

import uuid

from locust import HttpUser, between, task

# The registration passphrase is synthetic and obviously not a secret.
_PASSWORD = "loadtest-synthetic-passphrase-123"


class PatientSession(HttpUser):
    """One simulated signed-in patient exercising the hot read paths."""

    # Think-time between requests: a real user is not a tight loop.
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        """Self-seed a unique synthetic account and hold its bearer token."""
        email = f"loadtest+{uuid.uuid4().hex}@example.com"
        with self.client.post(
            "/auth/register",
            json={"email": email, "password": _PASSWORD, "display_name": "Load Test"},
            name="POST /auth/register (seed)",
            catch_response=True,
        ) as resp:
            if resp.status_code != 201:
                resp.failure(f"register returned {resp.status_code}")
                self._headers = None
                return
            token = resp.json().get("access_token")
            self._headers = {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, name: str) -> None:
        if self._headers is None:
            return
        # 200 and the designed 404 (insufficient data for a fresh account) are both
        # healthy under load; a 5xx is the real failure we are hunting.
        with self.client.get(path, headers=self._headers, name=name, catch_response=True) as resp:
            if resp.status_code >= 500:
                resp.failure(f"{name} -> {resp.status_code}")
            else:
                resp.success()

    @task(5)
    def whoami(self) -> None:
        self._get("/auth/me", "GET /auth/me")

    @task(4)
    def trajectory(self) -> None:
        self._get("/trajectory", "GET /trajectory")

    @task(4)
    def observations(self) -> None:
        self._get("/observations?limit=50", "GET /observations")

    @task(3)
    def visit_summary(self) -> None:
        self._get("/me/visit-summary", "GET /me/visit-summary")

    @task(1)
    def check_in(self) -> None:
        """A small write slice so the write path is under load too."""
        if self._headers is None:
            return
        with self.client.post(
            "/adl",
            headers=self._headers,
            json={"walking": 3, "stairs": 2, "balance_confidence": 3},
            name="POST /adl (write)",
            catch_response=True,
        ) as resp:
            if resp.status_code >= 500:
                resp.failure(f"POST /adl -> {resp.status_code}")
            else:
                resp.success()
