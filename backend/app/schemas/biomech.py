"""API schema for the BioMech report upload (ADR-0014).

The endpoint receives a report PDF (multipart), extracts its text layer, parses it
against the closed metric registry, and persists the accepted metrics as research-grade
Observations. The response reports what was recognized and imported plus every
defensive skip, so the uploader sees exactly what happened without any value leaving
in the audit log.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BiomechImportOut(BaseModel):
    """Outcome of one report upload."""

    report_kind: str | None = Field(
        default=None, description="balance | gait, or null when the kind was not recognizable"
    )
    assessment_at: datetime | None = Field(
        default=None, description="The report's assessment datetime (null when not found)"
    )
    imported: int = Field(..., ge=0, description="Metrics persisted as new Observations")
    skipped: int = Field(..., ge=0, description="Metrics already on file (same content identity)")
    warnings: list[str] = Field(
        default_factory=list,
        description="Per-metric and structural skips (non-numeric, out of range, missing date)",
    )
