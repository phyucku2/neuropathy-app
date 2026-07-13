"""Build tiny synthetic PDFs in-test (no binary fixtures committed; CLAUDE.md §5).

`build_pdf` emits a minimal, standards-valid single-page PDF whose text layer is the
given text — one visual line per input line — so pypdf extracts it back verbatim. This
lets the BioMech tests exercise real text extraction without shipping any binary blob.
`blank_pdf` emits an N-page PDF with no text, for the page-cap guard.
"""

from __future__ import annotations


def _assemble(objects: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % index + obj + b"\nendobj\n"
    xref_pos = len(out)
    size = len(objects) + 1
    out += b"xref\n0 %d\n" % size
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (size, xref_pos)
    return bytes(out)


def build_pdf(text: str) -> bytes:
    """A one-page PDF whose extractable text layer is `text` (line per input line)."""
    content = ["BT", "/F1 12 Tf", "72 720 Td"]
    for i, line in enumerate(text.split("\n")):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if i:
            content.append("0 -16 Td")
        content.append(f"({escaped}) Tj")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    return _assemble(objects)


def blank_pdf(page_count: int) -> bytes:
    """A PDF with `page_count` empty pages (no text layer) for page-cap tests."""
    kids = " ".join(f"{3 + i} 0 R" for i in range(page_count))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids.encode("latin-1"), page_count),
    ]
    for _ in range(page_count):
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>")
    return _assemble(objects)
