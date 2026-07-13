"""Model registry — import all models so Alembic autogenerate sees them."""

from app.models.audit import AuditEvent
from app.models.capability import Actor, Capability, PatientCapability
from app.models.clinic import Clinic
from app.models.connection import ClinicConnection, ConnectionStatus, Initiator
from app.models.emr_connection import EmrConnection, EmrConnectionStatus
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.models.patient import ConnectionMode, Patient
from app.models.user import User, UserRole

__all__ = [
    "AuditEvent",
    "Actor",
    "Capability",
    "PatientCapability",
    "Clinic",
    "ClinicConnection",
    "ConnectionStatus",
    "Initiator",
    "EmrConnection",
    "EmrConnectionStatus",
    "DataOrigin",
    "Observation",
    "ObservationStatus",
    "SourceType",
    "ConnectionMode",
    "Patient",
    "User",
    "UserRole",
]
