"""Settings-load validation (ADR-0017): security-sensitive values fail CLOSED at
startup with actionable errors, never at request time in a weaker posture.

Settings are constructed with _env_file=None so a developer's local .env can never
change what these tests see; kwargs also take precedence over ambient env vars.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import OPS_BOOTSTRAP_TOKEN_MIN_LENGTH, Settings

A_VALID_TOKEN = "synthetic-bootstrap-token-0123456789abcdef"  # ≥ the minimum length


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_short_bootstrap_token_is_rejected_at_load() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _settings(ops_bootstrap_token="short-token")
    assert f"at least {OPS_BOOTSTRAP_TOKEN_MIN_LENGTH}" in str(exc_info.value)


def test_boundary_bootstrap_token_lengths() -> None:
    minimum = "x" * OPS_BOOTSTRAP_TOKEN_MIN_LENGTH
    assert _settings(ops_bootstrap_token=minimum).ops_bootstrap_token == minimum
    assert _settings(ops_bootstrap_token=A_VALID_TOKEN).ops_bootstrap_token == A_VALID_TOKEN
    with pytest.raises(ValidationError):
        _settings(ops_bootstrap_token="x" * (OPS_BOOTSTRAP_TOKEN_MIN_LENGTH - 1))


def test_rejected_bootstrap_token_never_appears_in_the_error() -> None:
    """The startup failure lands in boot-loop logs — pydantic's default rendering
    would echo the rejected value back as `input_value=...`, printing a nearly-valid
    token verbatim (hide_input_in_errors, ADR-0017 review finding)."""
    leaked = "synthetic-distinctive-9f3a1c"  # < 32 chars, and unmistakable in output
    with pytest.raises(ValidationError) as exc_info:
        _settings(ops_bootstrap_token=leaked)
    assert leaked not in str(exc_info.value)
    assert leaked not in repr(exc_info.value)


def test_rejected_secret_store_key_never_appears_in_the_error() -> None:
    """A mistyped SECRET_STORE_KEY is one character away from the real key — the
    load-time error must never echo it (hide_input_in_errors, ADR-0017)."""
    leaked = "synthetic-almost-a-fernet-key-7b2d4e=="
    with pytest.raises(ValidationError) as exc_info:
        _settings(secret_store_key=leaked)
    assert leaked not in str(exc_info.value)
    assert leaked not in repr(exc_info.value)


def test_unset_and_empty_bootstrap_token_mean_disabled_not_invalid() -> None:
    """Unset stays the fail-closed 'provisioning disabled' posture; an empty env var
    means the same thing — it must not trip the length rule."""
    assert _settings().ops_bootstrap_token is None
    assert _settings(ops_bootstrap_token="").ops_bootstrap_token is None


def test_malformed_secret_store_key_is_rejected_at_load() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _settings(secret_store_key="not-a-fernet-key")
    assert "Fernet" in str(exc_info.value)


def test_generated_secret_store_key_is_accepted() -> None:
    key = Fernet.generate_key().decode()  # generated at runtime, never committed
    assert _settings(secret_store_key=key).secret_store_key == key


def test_unset_and_empty_secret_store_key_mean_in_memory_vault() -> None:
    assert _settings().secret_store_key is None
    assert _settings(secret_store_key="").secret_store_key is None


# ---- JWT_SECRET blank-is-unset normalization (sweep #5) ---------------------------------
# The DB-mode/multi-worker REQUIREMENT itself is enforced on the serving-startup path
# (app/main.py `_check_serving_secrets`), NOT at Settings construction — so that alembic and
# other tooling that has DATABASE_URL but never signs a token can still load config. Those
# startup semantics are tested in tests/test_health.py; config's only job here is to make a
# blank env read as unset so that guard sees "missing," not a zero-length signing key.


def test_blank_jwt_secret_reads_as_unset() -> None:
    # A blank JWT_SECRET= (shell var unset behind JWT_SECRET: ${JWT_SECRET}) must be None,
    # not a zero-length signing key, so the serving-startup guard treats it as missing.
    assert _settings().jwt_secret is None
    assert _settings(jwt_secret="").jwt_secret is None
