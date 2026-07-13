"""Unit tests for the BioMech PDF text extractor guards (ADR-0014).

Synthetic PDFs are built in-test (tests/synthetic_pdf.py) — no binary fixtures. Every
bad-upload path must be a typed BiomechPdfError (the route maps it to 422), never a 500.
"""

from __future__ import annotations

import pytest

from app.biomech.pdf import BiomechPdfError, extract_text
from app.core.config import settings
from tests.synthetic_pdf import blank_pdf, build_pdf


def test_extracts_text_layer_verbatim() -> None:
    text = extract_text(build_pdf("Balance Score: 82\nSway Velocity: 12.4 mm/s"))
    assert "Balance Score: 82" in text
    assert "Sway Velocity: 12.4 mm/s" in text


def test_non_pdf_bytes_are_rejected() -> None:
    with pytest.raises(BiomechPdfError, match="not a PDF"):
        extract_text(b"this is definitely not a pdf")


def test_empty_upload_is_rejected() -> None:
    with pytest.raises(BiomechPdfError, match="not a PDF"):
        extract_text(b"")


def test_size_cap_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "biomech_max_pdf_bytes", 64)
    oversized = build_pdf("Balance Score: 82\n" * 50)
    assert len(oversized) > 64
    with pytest.raises(BiomechPdfError, match="size cap"):
        extract_text(oversized)


def test_page_cap_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "biomech_max_pdf_pages", 2)
    with pytest.raises(BiomechPdfError, match="pages"):
        extract_text(blank_pdf(3))


def test_pages_within_cap_extract_without_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "biomech_max_pdf_pages", 5)
    # Blank pages carry no text layer, but extraction must not raise.
    assert extract_text(blank_pdf(3)) == "\n\n"


def test_pdf_header_but_corrupt_body_is_a_typed_error() -> None:
    with pytest.raises(BiomechPdfError, match="Could not read PDF"):
        extract_text(b"%PDF-1.4\nnot really a pdf body at all")


def test_zero_page_pdf_is_rejected() -> None:
    with pytest.raises(BiomechPdfError, match="no pages"):
        extract_text(blank_pdf(0))
