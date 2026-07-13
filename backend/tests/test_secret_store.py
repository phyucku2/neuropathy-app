"""Unit tests for the token vault (ADR-0017): the in-memory store contract and the
Fernet codec under the Postgres vault. Keys are generated at runtime — a committed
key would be a secret in the repo (CLAUDE.md §5).
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from app.emr.service import InMemorySecretStore
from app.repositories.postgres import decrypt_tokens, encrypt_tokens

SYNTHETIC_TOKENS = {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh"}


async def test_in_memory_store_round_trips_and_mints_unique_refs() -> None:
    store = InMemorySecretStore()
    ref_a = await store.put(SYNTHETIC_TOKENS)
    ref_b = await store.put({"access_token": "other"})
    assert ref_a != ref_b and ref_a.startswith("secret::")
    assert await store.get(ref_a) == SYNTHETIC_TOKENS
    assert await store.get("secret::never-issued") is None


def test_fernet_codec_round_trips() -> None:
    fernet = Fernet(Fernet.generate_key())
    ciphertext = encrypt_tokens(fernet, SYNTHETIC_TOKENS)
    assert decrypt_tokens(fernet, ciphertext) == SYNTHETIC_TOKENS


def test_ciphertext_never_contains_the_plaintext() -> None:
    """What lands in the DB row must be opaque — no token material recoverable by
    reading the column."""
    fernet = Fernet(Fernet.generate_key())
    ciphertext = encrypt_tokens(fernet, SYNTHETIC_TOKENS)
    for fragment in (b"synthetic-access", b"synthetic-refresh", b"access_token"):
        assert fragment not in ciphertext


def test_wrong_key_fails_closed_to_none() -> None:
    """A rotated/wrong key yields None — treated exactly like a missing secret
    (the pull path answers 409 'reconnect'), never an exception or plaintext."""
    ciphertext = encrypt_tokens(Fernet(Fernet.generate_key()), SYNTHETIC_TOKENS)
    assert decrypt_tokens(Fernet(Fernet.generate_key()), ciphertext) is None
