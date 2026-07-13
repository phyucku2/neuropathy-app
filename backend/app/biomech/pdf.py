"""BioMech report PDF text extraction — text layer only, never render or execute.

V1 ingests the digitally generated PDFs BioMech's lab portal exports; they carry a
real text layer, so we read that text and nothing else. The extractor NEVER rasterizes
a page, runs embedded JavaScript, follows a link, or resolves an external reference —
a malformed or hostile upload must surface as a typed error (the route maps it to 422),
never a 500 and never a path that treats the bytes as anything but a document to read.

Guards, all before or during a read that stays in memory:
- size cap (settings.biomech_max_pdf_bytes) — reject oversized uploads;
- magic-byte check — reject anything that is not a PDF;
- page cap (settings.biomech_max_pdf_pages) — bound the number of streams read;
- extracted-text cap (settings.biomech_max_pdf_text_chars) — bound the OUTPUT: a
  well-formed PDF under both caps can still be a decompression bomb whose content
  streams inflate to gigabytes of text (review finding), so accumulation aborts past
  the cap;
- any pypdf failure is caught and re-raised as BiomechPdfError, so a broken document
  is a client error, not a server fault.
"""

from __future__ import annotations

import io

from pypdf import PdfReader

from app.core.config import settings

# Every PDF begins with this header (PDF 32000-1 §7.5.2). A cheap, decisive gate that
# rejects images, text, HTML, or truncated junk before pypdf ever touches the bytes.
_PDF_MAGIC = b"%PDF-"


class BiomechPdfError(Exception):
    """A PDF that cannot be safely text-extracted (bad header, too big, too many pages,
    or unparseable). The route maps this to 422 — a bad upload is a client error, never
    a 500."""


def extract_text(data: bytes) -> str:
    """Extract the text layer from a BioMech report PDF, with strict guards.

    Returns the concatenated page text (pages joined by newlines). Raises
    BiomechPdfError for a non-PDF, an oversized file, too many pages, or any pypdf
    parse failure. Text extraction only: nothing in the document is rendered or run.
    """
    max_bytes = settings.biomech_max_pdf_bytes
    if len(data) > max_bytes:
        raise BiomechPdfError(f"PDF exceeds the {max_bytes}-byte size cap")
    if not data.startswith(_PDF_MAGIC):
        raise BiomechPdfError("Upload is not a PDF (missing %PDF- header)")

    max_pages = settings.biomech_max_pdf_pages
    max_chars = settings.biomech_max_pdf_text_chars
    try:
        reader = PdfReader(io.BytesIO(data))
        page_count = len(reader.pages)
        if page_count == 0:
            raise BiomechPdfError("PDF has no pages")
        if page_count > max_pages:
            raise BiomechPdfError(f"PDF has {page_count} pages; the cap is {max_pages}")
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            piece = page.extract_text() or ""
            total += len(piece)
            if total > max_chars:
                # Decompression bomb posture: bound the OUTPUT, abort mid-document.
                raise BiomechPdfError(f"PDF text exceeds the {max_chars}-character cap")
            parts.append(piece)
    except BiomechPdfError:
        raise
    except Exception as exc:
        # pypdf raises a wide family of errors (encryption, truncation, malformed
        # objects). A bad upload is a 422, never an uncaught 500 (ADR-0014).
        raise BiomechPdfError(f"Could not read PDF: {exc}") from exc
    return "\n".join(parts)
