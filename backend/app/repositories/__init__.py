"""Repositories — persistence contracts (Protocols) with in-memory and Postgres
implementations. Services depend on the Protocols; storage is injected.
"""

from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.emr_connection import (
    ConnectionRecord,
    EmrConnectionRepository,
    InMemoryEmrConnectionRepository,
)
from app.repositories.observation import InMemoryObservationRepository, ObservationRepository
from app.repositories.postgres import (
    PostgresAuditEventRepository,
    PostgresEmrConnectionRepository,
    PostgresObservationRepository,
    PostgresPendingAuthStore,
    PostgresSecretStore,
    PostgresUserRepository,
)
from app.repositories.user import InMemoryUserRepository, UserRecord, UserRepository

__all__ = [
    "AuditEventRepository",
    "ConnectionRecord",
    "EmrConnectionRepository",
    "InMemoryAuditEventRepository",
    "InMemoryEmrConnectionRepository",
    "InMemoryObservationRepository",
    "InMemoryUserRepository",
    "ObservationRepository",
    "PostgresAuditEventRepository",
    "PostgresEmrConnectionRepository",
    "PostgresObservationRepository",
    "PostgresPendingAuthStore",
    "PostgresSecretStore",
    "PostgresUserRepository",
    "UserRecord",
    "UserRepository",
]
