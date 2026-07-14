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
from app.repositories.user import InMemoryUserRepository, UserRecord
from app.services.auth import AuthApiError, AuthService

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
    with pytest.raises(AuthApiError) as exc:
        await auth.login(email="ops@example.com", password=SYNTHETIC_PASSWORD)
    assert exc.value.status_code == 401  # same 401 as unknown email — no enumeration


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
    with pytest.raises(AuthApiError):
        await auth.login(email="pat@example.com", password=SYNTHETIC_PASSWORD)


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
