"""Bridge for driving repository coroutines from synchronous service methods.

The repository protocols are async so the Postgres implementations can use
``AsyncSession``. A few service entry points are synchronous public API (kept stable
for the existing routes and tests); they may only be backed by repositories that
resolve without suspending — i.e. the in-memory implementations. When the request
path itself moves onto the async DB session, these call sites are awaited instead.
"""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any, TypeVar, cast

T = TypeVar("T")


# The TypeVar spelling (not PEP 695 type parameters) keeps 3.11-based tooling working.
def resolve_now(coro: Coroutine[Any, Any, T]) -> T:  # noqa: UP047
    """Run a coroutine that completes without suspending and return its result.

    In-memory repository methods never await real I/O, so they finish on the first
    step. A repository that suspends (e.g. a Postgres implementation awaiting the
    driver) cannot be used behind a synchronous method — that is a wiring error, so
    it fails loudly instead of blocking or silently dropping work.
    """
    try:
        coro.send(None)
    except StopIteration as stop:
        # StopIteration.value carries the coroutine's return value (typed Any).
        return cast(T, stop.value)
    coro.close()
    raise RuntimeError(
        "repository coroutine suspended in a synchronous context; "
        "async repositories must be awaited"
    )
