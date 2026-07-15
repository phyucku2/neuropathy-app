"""The frontend nginx access log is PHI-free (ADR-0018 §4).

nginx's built-in ``combined`` format logs the raw request line and query string, which
would leak patient UUIDs (``/clinic/patients/<uuid>/...``) and the single-use OAuth
``code``+``state`` (``/emr/callback?...``) into captured stdout — re-introducing exactly
what the backend logging whitelist excludes. This test is the enforcement seam for the
frontend ``phi_free`` ``log_format``: it asserts the access-log path names none of the
request-line / URI / query variables. Kept in the backend suite so the PHI-free logging
contract is guarded by the same ``pytest`` gate that guards app/core/logging.py.
"""

from __future__ import annotations

import re
from pathlib import Path

_TEMPLATE = Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf.template"

# nginx variables that carry the request path or query string — none may appear in the
# access-log format. Matched as whole variable names so `$request_method`/`$request_time`
# (which merely start with `$request`) are never false positives.
_FORBIDDEN_VARS = ("$request", "$request_uri", "$query_string", "$uri")


def _read_template() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


def _log_format_block(config: str) -> str:
    """The `log_format phi_free ... ;` definition (may span several quoted lines)."""
    match = re.search(r"log_format\s+phi_free\b.*?;", config, re.DOTALL)
    assert match, "expected a `log_format phi_free` definition in nginx.conf.template"
    return match.group(0)


def test_active_access_log_uses_the_phi_free_format() -> None:
    """Every access_log that actually WRITES (not `off`) must name the phi_free format —
    the built-in `combined` default would log the raw request line."""
    config = _read_template()
    writing = re.findall(r"access_log\s+(?!off\b)(\S+)\s+(\S+?);", config)
    assert writing, "expected an active access_log directive"
    for _target, fmt in writing:
        assert fmt == "phi_free", f"active access_log must use phi_free, got {fmt!r}"


def test_phi_free_format_names_no_path_or_query_variable() -> None:
    block = _log_format_block(_read_template())
    for var in _FORBIDDEN_VARS:
        pattern = re.escape(var) + r"(?![A-Za-z0-9_])"
        assert not re.search(pattern, block), f"{var} must not appear in the access log format"


def test_phi_free_format_keeps_correlatable_safe_fields() -> None:
    """Meaningful, not merely empty: it still logs method/status and the request id so a
    line correlates with the backend's X-Request-ID."""
    block = _log_format_block(_read_template())
    for var in ("$request_method", "$status", "$http_x_request_id"):
        assert var in block, f"expected {var} in the phi_free format"


def test_emr_callback_splits_spa_redirect_from_authenticated_relay() -> None:
    """/emr/callback is BOTH the SPA relay route and the backend API route (ADR-0028).

    The EMR's redirect is a bare document navigation (no Authorization header) and MUST
    receive the SPA shell — a blanket `/emr/` proxy would hand the patient the backend's
    401 JSON and the handshake could never complete. The relay's own fetch carries the
    bearer and MUST reach the backend. This locks the exact-match split."""
    config = _read_template()
    match = re.search(r"location = /emr/callback \{(.*?)\n    \}", config, re.DOTALL)
    assert match, "expected an exact-match location for /emr/callback"
    block = match.group(1)
    # Unauthenticated document navigation -> the SPA shell...
    assert re.search(r'if \(\$http_authorization = ""\)', block)
    assert "rewrite ^ /index.html last;" in block
    # ...and the bearer'd relay fetch -> the backend.
    assert "proxy_pass http://$backend_origin$request_uri;" in block
