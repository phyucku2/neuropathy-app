"""EmrClinicalNote — an append-only clinical-note record pulled from a patient's EMR
via SMART on FHIR ``DocumentReference`` (ADR-0045 P2, task #27).

NON-DIAGNOSTIC (CLAUDE.md house rules): a row carries only the note's EXISTENCE and its
METADATA — type, author, date, and opaque references (document id, encounter, Binary
attachment url). The note BODY is never a column here: it is fetched lazily from the
FHIR ``Binary`` on demand and, if ever cached, only ENCRYPTED via the SecretStore
(default: not persisted). The text is never summarized, scanned for findings, or fed to
the AI narrator/trajectory/alert copy.

A SEPARATE store from ``Observation`` by design: clinical notes are large, sensitive
free-text that may mention unrelated conditions — not analyzable, research-grade data —
so they never ride the unified longitudinal record. Import idempotency is a DB-level
invariant via a partial UNIQUE index on ``(patient_id, import_key) WHERE import_key IS
NOT NULL`` (mirrors ``uq_observation_patient_import_key``), so a re-pull of the same
DocumentReference can never create a duplicate row.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.observation import DataOrigin


class EmrClinicalNote(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "emr_clinical_note"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )
    # The connection the note was pulled through — notes FK the connection (account
    # deletion must remove them BEFORE the emr_connection rows, ADR-0027).
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emr_connection.id"), nullable=False, index=True
    )
    # Always ehr_imported for a note (provenance class); reuses the shared data_origin enum.
    origin: Mapped[DataOrigin] = mapped_column(
        Enum(DataOrigin, name="data_origin"),
        nullable=False,
        default=DataOrigin.ehr_imported,
    )
    source_system: Mapped[str | None] = mapped_column(String(400), nullable=True)

    # FHIR references / metadata — NEVER note text.
    document_fhir_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    type_code: Mapped[str | None] = mapped_column(String(80), nullable=True)  # LOINC note type
    type_display: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="clinical-note")
    # DocumentReference.date — when the note was authored.
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Free text as the EHR provided it (a name/role); surfaced verbatim, never interpreted.
    author_display: Mapped[str | None] = mapped_column(String(200), nullable=True)
    encounter_fhir_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Body handle only — the content is fetched lazily and never stored on this row.
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attachment_url: Mapped[str | None] = mapped_column(String(600), nullable=True)  # Binary ref
    has_inline_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Import idempotency key (content identity — the source DocumentReference id when the
    # EMR provides one). A real indexed column so existence probes are index hits.
    import_key: Mapped[str | None] = mapped_column(String(300), nullable=True)

    __table_args__ = (
        # Import idempotency as a DB-LEVEL INVARIANT: a partial UNIQUE index on
        # (patient_id, import_key) makes re-importing the same source note impossible in
        # storage, not just in application code (mirrors uq_observation_patient_import_key).
        # WHERE import_key IS NOT NULL scopes it to import-keyed rows only.
        Index(
            "uq_emr_note_patient_import_key",
            "patient_id",
            "import_key",
            unique=True,
            postgresql_where=text("import_key IS NOT NULL"),
        ),
    )
