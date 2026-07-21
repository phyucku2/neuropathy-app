"""Unit tests for the stdlib TOTP/HOTP primitives (§1B C6) — RFC vectors first.

Every assertion runs on FIXED instants/counters (the ADR-0013 CI-flake rule): nothing
here reads the wall clock.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from app.core.totp import (
    TOTP_DIGITS,
    TOTP_STEP_SECONDS,
    generate_totp_secret,
    hotp,
    otpauth_uri,
    totp_at,
    verify_totp,
)

# RFC 4226 Appendix D secret ("12345678901234567890" in ASCII), base32-encoded the way
# our functions consume it.
_RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()

# RFC 4226 Appendix D: the first ten 6-digit HOTP values for counters 0..9.
_RFC4226_HOTP = [
    "755224",
    "287082",
    "359152",
    "969429",
    "338314",
    "254676",
    "287922",
    "162583",
    "399871",
    "520489",
]

# RFC 6238 Appendix B (SHA-1 rows): unix time -> 8-digit TOTP for the same secret.
_RFC6238_TOTP = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]

_AT = datetime(2026, 7, 13, 12, 0, 15, tzinfo=UTC)  # mid-step, so ±1 step is symmetric


def test_hotp_matches_the_rfc4226_appendix_d_vectors() -> None:
    assert [hotp(_RFC_SECRET, counter) for counter in range(10)] == _RFC4226_HOTP


def test_totp_matches_the_rfc6238_appendix_b_sha1_vectors() -> None:
    for unix_time, expected in _RFC6238_TOTP:
        at = datetime.fromtimestamp(unix_time, tz=UTC)
        assert totp_at(_RFC_SECRET, at, digits=8) == expected


def test_generated_secrets_are_base32_160_bit_and_unique() -> None:
    first, second = generate_totp_secret(), generate_totp_secret()
    assert first != second
    assert len(base64.b32decode(first)) == 20  # RFC 4226 §4 recommended length
    assert first == first.upper() and first.isalnum()


def test_verify_accepts_the_current_step_and_one_neighbor_each_way() -> None:
    secret = generate_totp_secret()
    step = timedelta(seconds=TOTP_STEP_SECONDS)
    assert verify_totp(secret, totp_at(secret, _AT), at=_AT) is True
    assert verify_totp(secret, totp_at(secret, _AT - step), at=_AT) is True  # clock skew
    assert verify_totp(secret, totp_at(secret, _AT + step), at=_AT) is True
    # Never wider: two steps out is a stale/premature code, refused.
    assert verify_totp(secret, totp_at(secret, _AT - 2 * step), at=_AT) is False
    assert verify_totp(secret, totp_at(secret, _AT + 2 * step), at=_AT) is False


def test_verify_refuses_malformed_codes_by_shape() -> None:
    secret = generate_totp_secret()
    assert verify_totp(secret, "", at=_AT) is False
    assert verify_totp(secret, "12345", at=_AT) is False  # wrong length
    assert verify_totp(secret, "1234567", at=_AT) is False
    assert verify_totp(secret, "12345a", at=_AT) is False  # not digits


def test_verify_refuses_a_code_from_another_secret() -> None:
    secret, other = generate_totp_secret(), generate_totp_secret()
    assert verify_totp(secret, totp_at(other, _AT), at=_AT) is False


def test_otpauth_uri_carries_the_scannable_defaults_and_escapes_the_label() -> None:
    uri = otpauth_uri(
        "SYNTHETICBASE32SECRET234", account_name="dr@example.com", issuer="Neuropathy"
    )
    assert uri.startswith("otpauth://totp/Neuropathy:dr%40example.com?")
    assert "secret=SYNTHETICBASE32SECRET234" in uri
    assert "issuer=Neuropathy" in uri
    assert f"digits={TOTP_DIGITS}" in uri
    assert f"period={TOTP_STEP_SECONDS}" in uri
    assert "algorithm=SHA1" in uri
