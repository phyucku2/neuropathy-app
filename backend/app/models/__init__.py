"""Model registry — import all models so Alembic autogenerate sees them."""

from app.models.audit import AuditEvent
from app.models.capability import Actor, Capability, PatientCapability
from app.models.connection import ClinicConnection, ConnectionStatus, Initiator
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.models.patient import ConnectionMode, Patient

__all__ = [
    "AuditEvent",
    "Actor",
    "Capability",
    "PatientCapability",
    "ClinicConnection",
    "ConnectionStatus",
    "Initiator",
    "DataOrigin",
    "Observation",
    "ObservationStatus",
    "SourceType",
    "ConnectionMode",
    "Patient",
]
