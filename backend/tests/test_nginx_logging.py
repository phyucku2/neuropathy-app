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
    bearer and MUST reach the backend.

    STRUCTURAL, not string-presence (review finding): the rewrite must sit INSIDE the
    no-Authorization `if` braces (conditional) and the proxy_pass OUTSIDE/after them
    (unconditional for the authenticated fetch). A regression that unconditionally
    rewrites — or reorders the two so the proxy never runs — must fail here, even
    though both directive strings would still be present in the block."""
    config = _read_template()
    match = re.search(r"location = /emr/callback \{(.*?)\n    \}", config, re.DOTALL)
    assert match, "expected an exact-match location for /emr/callback"
    block = match.group(1)

    if_open = re.search(r'if \(\$http_authorization = ""\)\s*\{', block)
    assert if_open, "expected the no-Authorization `if` split inside the callback location"
    before_if = block[: if_open.start()]
    # The `if` body ends at its first closing brace (nginx `if` blocks don't nest here).
    if_body, closing, after_if = block[if_open.end() :].partition("}")
    assert closing == "}", "the no-Authorization `if` block never closes"

    # The SPA rewrite is CONDITIONAL: inside the if braces, and nowhere else.
    assert re.search(r"rewrite\s+\^\s+/index\.html\s+last;", if_body), (
        "the SPA-shell rewrite must sit INSIDE the no-Authorization if-block"
    )
    assert "rewrite" not in before_if and "rewrite" not in after_if, (
        "an unconditional rewrite would ALSO shell-swap the authenticated relay fetch"
    )
    # The backend proxy is UNCONDITIONAL: outside (after) the if braces, and never inside.
    assert re.search(r"proxy_pass\s+http://\$backend_origin\$request_uri;", after_if), (
        "proxy_pass must follow the if-block so the bearer'd fetch reaches the backend"
    )
    assert "proxy_pass" not in if_body and "proxy_pass" not in before_if, (
        "proxy_pass inside/before the if would proxy the bare EMR redirect to the "
        "backend's 401 JSON"
    )
