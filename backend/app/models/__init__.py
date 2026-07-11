"""Model registry — import all models so Alembic autogenerate sees them."""
from app.models.audit import AuditEvent
from app.models.capability import Actor, Capability, PatientCapability
from app.models.observation import Observation, SourceType
from app.models.patient import Patient

__all__ = [
    "AuditEvent",
    "Actor",
    "Capability",
    "PatientCapability",
    "Observation",
    "SourceType",
    "Patient",
]
