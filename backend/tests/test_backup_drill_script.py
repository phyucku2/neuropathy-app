"""The backup drill keeps DB credentials out of argv (ADR-0021 review finding).

Passwords in a DSN passed on a command line are visible via `ps`/`/proc/<pid>/cmdline`.
This is the regression guard for `scripts/pg_backup_drill.sh`: it must hand credentials to
the Postgres tools only via libpq's PGPASSFILE/PG* environment (a 0600 `.pgpass`), never as
a `--dbname=<DSN>` argument, and must not pass a credential-bearing DSN to the parser on
argv either. The drill's functional behaviour is exercised live against a scratch database
(not wired into CI — no destructive DB ops in the unit suite), so this test locks in the
argv-safety property that a functional run alone would not catch.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pg_backup_drill.sh"


def _source() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def test_drill_script_exists_and_is_the_backup_drill() -> None:
    assert _SCRIPT.is_file()
    assert "pg_backup_drill.sh" in _source()


def test_credentials_are_passed_via_pgpassfile_not_argv() -> None:
    src = _source()
    # Credentials go through libpq's env/PGPASSFILE mechanism.
    assert "PGPASSFILE" in src
    assert "PGHOST=" in src and "PGUSER=" in src
    # A 0600 .pgpass is the only place the password is written.
    assert "0o600" in src or "chmod 600" in src


def test_no_credential_bearing_dsn_is_placed_on_a_command_line() -> None:
    """No pg_* tool nor the parser may receive a whole DSN (which embeds the password) as an
    argument — only plain database NAMES via --dbname."""
    src = _source()
    # The pre-fix leak shapes: DSNs handed to the tools / to python as argv.
    assert '--dbname="$SOURCE_DSN"' not in src
    assert '--dbname="$ADMIN_DSN"' not in src
    assert '--dbname="$SCRATCH_DSN"' not in src
    assert '--dbname="$ADMIN_DSN"' not in src
    assert 'python3 - "$SOURCE_DSN"' not in src
    assert 'python3 - "$ADMIN_DSN"' not in src
    # --dbname is used only with plain, non-secret database-name variables.
    assert '--dbname="$SRC_DB"' in src
    assert '--dbname="$SCRATCH_DB"' in src


def test_header_comment_states_credentials_are_never_in_argv() -> None:
    """The header must describe the credential handling accurately (the old comment
    overstated safety by claiming the password was never written to disk)."""
    src = _source()
    assert "never in argv" in src.lower() or "never on a command line" in src.lower()
