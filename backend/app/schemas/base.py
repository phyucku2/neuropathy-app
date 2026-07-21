"""Shared base for request-facing API models (readiness plan §1B C3).

``hide_input_in_errors=True``: a failed validation must never echo the submitted value —
pydantic's default ValidationError rendering appends ``input_value=...``, which would
print a mistyped email, a password posted in the wrong field, or a lab value verbatim
into whatever log line renders the exception. config.py's ``Settings`` set the precedent
(ADR-0017 review finding); this base extends it to every request body model. The 422
RESPONSE body is scrubbed separately by the RequestValidationError handler in
app/main.py — both are needed: this config covers the logged message, the handler covers
the serialized ``exc.errors()`` payload.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base for every request-facing (In) schema: input values never echo in errors."""

    model_config = ConfigDict(hide_input_in_errors=True)
