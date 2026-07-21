"""Unit tests for the ops-auth surface (ADR-0019): ops-operator provisioning
(AuthService.create_ops), the require_ops dependency, per-operator deactivation, and
the user-repository primitives the surface relies on (count_with_role, set_active).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.api.deps import CurrentUser, require_ops
from app.core.security import verify_password
from app.models.user import UserRole
from app.repositories.user import (
    InMemoryUserRepository,
    OpsAlreadyExistsError,
    OpsDeactivateOutcome,
    UserRecord,
)
from app.services.auth import AuthApiError, AuthService, LoginDenied

# Uppercase constants keep the CI secret scanner from matching synthetic credentials.
SYNTHETIC_PASSWORD = "a-strong-password"
OTHER_SYNTHETIC_PASSWORD = "another-pass-1"


def _current(role: UserRole, *, active: bool = True) -> CurrentUser:
    return CurrentUser(
        user_id=uuid.uuid4(),
        role=role,
        patient_id=uuid.uuid4() if role is UserRole.patient else None,
        email="who@example.com",
        display_name="Who",
        clinic_id=uuid.uuid4() if role is UserRole.clinician else None,
        active=active,
    )


# ---------------------------------------------------------------- require_ops


def test_require_ops_rejects_patient() -> None:
    with pytest.raises(HTTPException) as exc:
        require_ops(_current(UserRole.patient))
    assert exc.value.status_code == 403
    assert exc.value.detail == "Ops account required"


def test_require_ops_rejects_clinician() -> None:
    with pytest.raises(HTTPException) as exc:
        require_ops(_current(UserRole.clinician))
    assert exc.value.status_code == 403


def test_require_ops_rejects_deactivated_ops() -> None:
    # A live JWT can outlast a deactivation by up to the access-token TTL; the gate
    # must re-check active, not trust that login already refused.
    with pytest.raises(HTTPException) as exc:
        require_ops(_current(UserRole.ops, active=False))
    assert exc.value.status_code == 403


def test_require_ops_passes_active_ops_through() -> None:
    current = _current(UserRole.ops)
    assert require_ops(current) is current


# ---------------------------------------------------------------- create_ops


async def test_create_ops_is_role_ops_with_no_patient_or_clinic() -> None:
    auth = AuthService(secret="unit-test-secret")
    user = await auth.create_ops(
        email="  OPS@Example.com ", password=SYNTHETIC_PASSWORD, display_name="Ops One"
    )
    assert user.role is UserRole.ops
    assert user.patient_id is None  # an ops principal carries neither...
    assert user.clinic_id is None  # ...a patient record nor a clinic
    assert user.active is True
    assert user.disabled_at is None
    assert user.email == "ops@example.com"  # normalized
    assert user.password_hash != SYNTHETIC_PASSWORD
    assert verify_password(user.password_hash, SYNTHETIC_PASSWORD)  # Argon2id


async def test_create_ops_duplicate_email_is_409() -> None:
    auth = AuthService(secret="unit-test-secret")
    await auth.create_ops(email="ops@example.com", password=SYNTHETIC_PASSWORD, display_name="Ops")
    with pytest.raises(AuthApiError) as exc:
        await auth.create_ops(
            email="ops@example.com", password=OTHER_SYNTHETIC_PASSWORD, display_name="Ops 2"
        )
    assert exc.value.status_code == 409


async def test_ops_login_surfaces_role_ops() -> None:
    auth = AuthService(secret="unit-test-secret")
    await auth.create_ops(email="ops@example.com", password=SYNTHETIC_PASSWORD, display_name="Ops")
    user, tokens = await auth.login(email="ops@example.com", password=SYNTHETIC_PASSWORD)
    assert user.role is UserRole.ops
    assert tokens.access_token  # the same JWT machinery, role=ops


# ------------------------------------------------------------- first-ops guard (create_first_ops)


async def test_create_first_ops_succeeds_when_zero_ops() -> None:
    auth = AuthService(secret="unit-test-secret")
    user = await auth.create_first_ops(
        email="ops@example.com", password=SYNTHETIC_PASSWORD, display_name="Ops"
    )
    assert user.role is UserRole.ops
    assert await auth.ops_account_exists() is True


async def test_create_first_ops_refuses_when_an_ops_already_exists() -> None:
    """The single documented 'first operator' invariant (ADR-0019): a second first-ops
    insert is a 409 even with a distinct email the unique index would not catch — the
    guard, not the email index, is what enforces exactly-one."""
    auth = AuthService(secret="unit-test-secret")
    await auth.create_first_ops(
        email="ops@example.com", password=SYNTHETIC_PASSWORD, display_name="Ops"
    )
    with pytest.raises(AuthApiError) as exc:
        await auth.create_first_ops(
            email="ops2@example.com", password=OTHER_SYNTHETIC_PASSWORD, display_name="Ops 2"
        )
    assert exc.value.status_code == 409


async def test_create_first_ops_duplicate_email_is_409() -> None:
    auth = AuthService(secret="unit-test-secret")
    await auth.register_patient(
        email="taken@example.com", password=SYNTHETIC_PASSWORD, display_name="Pat"
    )
    with pytest.raises(AuthApiError) as exc:
        await auth.create_first_ops(
            email="taken@example.com", password=OTHER_SYNTHETIC_PASSWORD, display_name="Ops"
        )
    assert exc.value.status_code == 409


async def test_add_first_ops_raises_when_ops_exists() -> None:
    """The in-memory twin of the advisory-lock guard: with an ops already present, a
    first-ops insert raises rather than minting a second 'first' operator."""
    repo = InMemoryUserRepository()
    first = UserRecord(
        id=uuid.uuid4(),
        email="a@example.com",
        password_hash="h",
        display_name="A",
        role=UserRole.ops,
        patient_id=None,
    )
    await repo.add_first_ops(first)
    second = UserRecord(
        id=uuid.uuid4(),
        email="b@example.com",
        password_hash="h",
        display_name="B",
        role=UserRole.ops,
        patient_id=None,
    )
    with pytest.raises(OpsAlreadyExistsError):
        await repo.add_first_ops(second)


# ---------------------------------------------------------------- existence / counts


async def test_ops_account_exists_tracks_any_ops() -> None:
    auth = AuthService(secret="unit-test-secret")
    assert await auth.ops_account_exists() is False
    await auth.register_patient(
        email="pat@example.com", password=SYNTHETIC_PASSWORD, display_name="Pat"
    )
    assert await auth.ops_account_exists() is False  # a patient is not an ops
    ops = await auth.create_ops(
        email="ops@example.com", password=SYNTHETIC_PASSWORD, display_name="Ops"
    )
    assert await auth.ops_account_exists() is True
    # A DEACTIVATED ops still counts — the bootstrap gate never reopens (ADR-0019).
    await auth.deactivate_ops(ops.id)
    assert await auth.ops_account_exists() is True
    assert await auth.active_ops_count() == 0


# ---------------------------------------------------------------- deactivation


async def test_deactivate_ops_blocks_login() -> None:
    auth = AuthService(secret="unit-test-secret")
    ops = await auth.create_ops(
        email="ops@example.com", password=SYNTHETIC_PASSWORD, display_name="Ops"
    )
    updated = await auth.deactivate_ops(ops.id)
    assert updated is not None
    assert updated.active is False
    assert updated.disabled_at is not None
    denied = await auth.login(email="ops@example.com", password=SYNTHETIC_PASSWORD)
    assert isinstance(denied, LoginDenied)  # returned, not raised — its audit row commits
    assert denied.status_code == 401  # same 401 as unknown email — no enumeration


async def test_deactivate_ops_returns_none_for_unknown_id() -> None:
    auth = AuthService(secret="unit-test-secret")
    assert await auth.deactivate_ops(uuid.uuid4()) is None


async def test_deactivated_account_of_any_role_cannot_log_in() -> None:
    """The active flag is general (ADR-0019): a deactivated patient is refused too."""
    auth = AuthService(secret="unit-test-secret")
    pat = await auth.register_patient(
        email="pat@example.com", password=SYNTHETIC_PASSWORD, display_name="Pat"
    )
    await auth.users.set_active(pat.id, active=False, disabled_at=datetime.now(UTC))
    denied = await auth.login(email="pat@example.com", password=SYNTHETIC_PASSWORD)
    assert isinstance(denied, LoginDenied)
    assert denied.status_code == 401


# ---------------------------------------------------------------- repository primitives


async def test_count_with_role_active_only() -> None:
    repo = InMemoryUserRepository()
    first = UserRecord(
        id=uuid.uuid4(),
        email="a@example.com",
        password_hash="h",
        display_name="A",
        role=UserRole.ops,
        patient_id=None,
    )
    second = UserRecord(
        id=uuid.uuid4(),
        email="b@example.com",
        password_hash="h",
        display_name="B",
        role=UserRole.ops,
        patient_id=None,
    )
    await repo.add(first)
    await repo.add(second)
    assert await repo.count_with_role(UserRole.ops) == 2
    assert await repo.count_with_role(UserRole.ops, active_only=True) == 2
    assert await repo.count_with_role(UserRole.clinician) == 0
    await repo.set_active(second.id, active=False, disabled_at=datetime.now(UTC))
    assert await repo.count_with_role(UserRole.ops) == 2  # still exists...
    assert await repo.count_with_role(UserRole.ops, active_only=True) == 1  # ...but only one active


async def test_set_active_on_missing_user_returns_none() -> None:
    repo = InMemoryUserRepository()
    assert await repo.set_active(uuid.uuid4(), active=False, disabled_at=None) is None


async def test_deactivate_ops_guarded_outcomes() -> None:
    """The atomic guard's four outcomes (ADR-0019): unknown -> not_found, the last active
    -> refused, an active non-last -> deactivated, and a second call -> already_inactive."""
    repo = InMemoryUserRepository()
    when = datetime.now(UTC)
    a = UserRecord(
        id=uuid.uuid4(),
        email="a@example.com",
        password_hash="h",
        display_name="A",
        role=UserRole.ops,
        patient_id=None,
    )
    await repo.add(a)
    # Only one active ops: refuse to remove the last one.
    assert (
        await repo.deactivate_ops_guarded(a.id, disabled_at=when)
    ).outcome is OpsDeactivateOutcome.refused_last_active
    # Unknown id: not found.
    assert (
        await repo.deactivate_ops_guarded(uuid.uuid4(), disabled_at=when)
    ).outcome is OpsDeactivateOutcome.not_found
    # A second active ops makes `a` deactivatable.
    b = UserRecord(
        id=uuid.uuid4(),
        email="b@example.com",
        password_hash="h",
        display_name="B",
        role=UserRole.ops,
        patient_id=None,
    )
    await repo.add(b)
    first = await repo.deactivate_ops_guarded(a.id, disabled_at=when)
    assert first.outcome is OpsDeactivateOutcome.deactivated
    assert first.record is not None and first.record.active is False
    # Idempotent: deactivating the already-inactive `a` again is a quiet no-op.
    assert (
        await repo.deactivate_ops_guarded(a.id, disabled_at=when)
    ).outcome is OpsDeactivateOutcome.already_inactive


async def test_reactivate_ops_restores_and_is_recoverable() -> None:
    auth = AuthService(secret="unit-test-secret")
    ops = await auth.create_ops(
        email="ops@example.com", password=SYNTHETIC_PASSWORD, display_name="Ops"
    )
    await auth.deactivate_ops(ops.id)
    restored = await auth.reactivate_ops(ops.id)
    assert restored is not None
    assert restored.active is True
    assert restored.disabled_at is None
    # Login works again after reactivation.
    user, _ = await auth.login(email="ops@example.com", password=SYNTHETIC_PASSWORD)
    assert user.active is True
    # Unknown id -> None.
    assert await auth.reactivate_ops(uuid.uuid4()) is None
