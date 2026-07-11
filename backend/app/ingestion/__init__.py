"""Ingestion adapters — one interface, one adapter per source.

- biomech: parse BioMech report PDFs (V1) -> normalized metrics; API/SDK feed (V2).
- labs: capture (photo/PDF) -> OCR/extract -> human-confirm -> normalized values.
- adl: functional-status capture (self-report and/or activity-derived).

Each adapter normalizes into Observation rows. Uploaded documents are untrusted input:
parse in a sandbox, validate, and never let document text reach the AI layer unsanitized
(Brainstorm #3, Security/AI-Safety lenses).
"""
