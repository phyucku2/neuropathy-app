"""TOTP (RFC 6238) over stdlib hmac/struct — pure and fully unit-tested (§1B C6).

No new dependency: HOTP (RFC 4226) is one HMAC-SHA1 + dynamic truncation, and TOTP is
HOTP over a time counter. SHA-1 with 30-second steps and 6 digits is exactly what every
authenticator app (Google Authenticator, Authy, 1Password, ...) implements from an
``otpauth://totp/`` URI, so interoperability needs nothing more. Verification compares
with ``hmac.compare_digest`` and accepts ±1 time step (clock skew), per the RFC's
resynchronization guidance. Tested against the RFC 6238 Appendix B vectors.

Time is always injected (``at=``): nothing here reads the wall clock, so tests assert
code generation and verification on fixed instants (the CI-flake rule, ADR-0013).
"""

from __future__ import annotations

import base64
import hmac
import secrets
import struct
from datetime import datetime
from urllib.parse import quote

__all__ = [
    "TOTP_DIGITS",
    "TOTP_STEP_SECONDS",
    "generate_totp_secret",
    "hotp",
    "otpauth_uri",
    "totp_at",
    "verify_totp",
]

# The authenticator-app defaults: 30-second steps, 6 digits, HMAC-SHA1 (RFC 6238 §4).
TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6

# 160-bit secrets — the RFC 4226 §4 recommended length (and SHA-1's block-friendly size).
_SECRET_BYTES = 20

# Verify at counter-1/counter/counter+1 (one step of transmission delay or clock skew
# either way — RFC 6238 §6). Never wider: each extra step is another guessable window.
_VERIFY_WINDOW = 1


def generate_totp_secret() -> str:
    """A fresh base32-encoded 160-bit secret (the otpauth:// alphabet, no padding)."""
    return base64.b32encode(secrets.token_bytes(_SECRET_BYTES)).decode()


def hotp(secret: str, counter: int, *, digits: int = TOTP_DIGITS) -> str:
    """RFC 4226 HOTP: HMAC-SHA1 over the 8-byte big-endian counter, dynamically
    truncated to a 31-bit integer, rendered mod 10^digits with leading zeros."""
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), "sha1").digest()
    offset = digest[-1] & 0x0F
    (code,) = struct.unpack(">I", digest[offset : offset + 4])
    return str((code & 0x7FFFFFFF) % (10**digits)).zfill(digits)


def totp_at(secret: str, at: datetime, *, digits: int = TOTP_DIGITS) -> str:
    """The TOTP code for the time step containing ``at`` (RFC 6238: T = unix // step)."""
    return hotp(secret, int(at.timestamp()) // TOTP_STEP_SECONDS, digits=digits)


def verify_totp(secret: str, code: str, *, at: datetime) -> bool:
    """Whether ``code`` matches the step containing ``at`` or its ±1 neighbors.

    Constant-time comparison per candidate (``hmac.compare_digest``); every candidate is
    always checked (no early accept-shape short-circuit beyond the trivial length gate,
    which depends only on the submitted code's public shape)."""
    if len(code) != TOTP_DIGITS or not code.isdigit():
        return False
    counter = int(at.timestamp()) // TOTP_STEP_SECONDS
    matched = False
    for step in range(counter - _VERIFY_WINDOW, counter + _VERIFY_WINDOW + 1):
        if hmac.compare_digest(hotp(secret, step), code):
            matched = True
    return matched


def otpauth_uri(secret: str, *, account_name: str, issuer: str) -> str:
    """The ``otpauth://totp/`` provisioning URI authenticator apps scan (label +
    issuer per the de-facto Key Uri Format; parameters spell out the RFC defaults)."""
    label = f"{quote(issuer)}:{quote(account_name)}"
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_STEP_SECONDS}"
    )
