"""Unit tests for clinician identity: provisioning (AuthService.create_clinician),
the require_clinician dependency, and the clinic linkage on user records (ADR-0012).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.api.deps import CurrentUser, require_clinician
from app.core.security import verify_password
from app.models.user import UserRole
from app.services.auth import AuthApiError, AuthService


def _current(role: UserRole, clinic_id: uuid.UUID | None) -> CurrentUser:
    return CurrentUser(
        user_id=uuid.uuid4(),
        role=role,
        patient_id=uuid.uuid4() if role is UserRole.patient else None,
        email="who@example.com",
        display_name="Who",
        clinic_id=clinic_id,
    )


def test_require_clinician_rejects_patient() -> None:
    with pytest.raises(HTTPException) as exc:
        require_clinician(_current(UserRole.patient, None))
    assert exc.value.status_code == 403
    assert exc.value.detail == "Clinician account required"


def test_require_clinician_rejects_clinician_without_clinic() -> None:
    with pytest.raises(HTTPException) as exc:
        require_clinician(_current(UserRole.clinician, None))
    assert exc.value.status_code == 403


def test_require_clinician_passes_clinic_bound_clinician_through() -> None:
    current = _current(UserRole.clinician, uuid.uuid4())
    assert require_clinician(current) is current


def test_current_user_clinic_id_defaults_to_none() -> None:
    # The field is defaulted last so every pre-existing construction keeps working.
    current = CurrentUser(
        user_id=uuid.uuid4(),
        role=UserRole.patient,
        patient_id=uuid.uuid4(),
        email="pat@example.com",
        display_name="Pat",
    )
    assert current.clinic_id is None


async def test_create_clinician_binds_clinic_and_hashes_password() -> None:
    auth = AuthService(secret="unit-test-secret")
    clinic_id = uuid.uuid4()
    user = await auth.create_clinician(
        email="  DR@Example.com ",
        password="a-strong-password",
        display_name="Dr. Rivera",
        clinic_id=clinic_id,
    )
    assert user.role is UserRole.clinician
    assert user.clinic_id == clinic_id
    assert user.patient_id is None  # clinicians hold no Patient record (ADR-0010)
    assert user.email == "dr@example.com"  # normalized
    assert user.password_hash != "a-strong-password"
    assert verify_password(user.password_hash, "a-strong-password")


async def test_create_clinician_duplicate_email_is_409() -> None:
    auth = AuthService(secret="unit-test-secret")
    await auth.create_clinician(
        email="dr@example.com",
        password="a-strong-password",
        display_name="Dr",
        clinic_id=uuid.uuid4(),
    )
    with pytest.raises(AuthApiError) as exc:
        await auth.create_clinician(
            email="dr@example.com",
            password="another-pass-1",
            display_name="Dr 2",
            clinic_id=uuid.uuid4(),
        )
    assert exc.value.status_code == 409


async def test_clinician_login_surfaces_clinic_id() -> None:
    auth = AuthService(secret="unit-test-secret")
    clinic_id = uuid.uuid4()
    await auth.create_clinician(
        email="dr@example.com",
        password="a-strong-password",
        display_name="Dr",
        clinic_id=clinic_id,
    )
    user, _ = await auth.login(email="dr@example.com", password="a-strong-password")
    assert user.clinic_id == clinic_id


async def test_get_by_patient_id_finds_the_owning_user() -> None:
    auth = AuthService(secret="unit-test-secret")
    patient = await auth.register_patient(
        email="pat@example.com", password="a-strong-password", display_name="Pat"
    )
    assert patient.patient_id is not None
    found = await auth.users.get_by_patient_id(patient.patient_id)
    assert found is not None and found.id == patient.id
    assert await auth.users.get_by_patient_id(uuid.uuid4()) is None
