"""Gunicorn config for the production server (ADR-0021).

The image runs the FastAPI app under Gunicorn with Uvicorn workers instead of bare
``uvicorn --workers`` for ONE reason: correct Prometheus metrics across workers. In
multiprocess mode (``PROMETHEUS_MULTIPROC_DIR`` set — see the Dockerfile/entrypoint) every
worker writes its samples to a shared dir and a ``/metrics`` scrape aggregates them
(app/core/metrics.py). For that to stay correct a dead worker's gauge files must be cleared,
and the reliable place to do that is Gunicorn's ``child_exit`` hook: it runs in the master
process whenever a worker exits — crash or graceful — which bare ``uvicorn --workers`` gives
no equivalent of. ``worker_class`` keeps Uvicorn's ASGI/HTTP stack unchanged.

Worker count still comes from ``WEB_CONCURRENCY`` (default 2), same env as before.
"""

from __future__ import annotations

import os
from typing import Any

# Bind all interfaces inside the container network, like the previous uvicorn CMD.
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
# Worker count from WEB_CONCURRENCY (sized by CPU in prod), matching the prior contract.
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
# Uvicorn's worker runs the same ASGI app (app.main:app) — only the supervisor changes.
worker_class = "uvicorn.workers.UvicornWorker"


def child_exit(server: Any, worker: Any) -> None:
    """Master-side hook: fires however a worker died. Clear its multiprocess metric files
    so the dead worker stops contributing to aggregated gauge sums (prometheus_client).

    Imported lazily so the app's metric objects are only constructed in the master if a
    worker actually dies — the common (no-death) path never materializes master-side files.
    """
    from app.core.metrics import mark_worker_dead

    mark_worker_dead(worker.pid)
