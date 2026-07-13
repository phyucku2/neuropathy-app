"""BioMech PDF ingest module (V1) — a self-contained ingest+graph surface (ADR-0014).

BioMech Health runs their own phone/clinic apps; we only INGEST and GRAPH the balance
and gait assessment reports their lab portal exports as digitally generated PDFs (a
text layer, no scanning). This module extracts that text (`pdf`), parses it into a
typed report against a closed metric registry (`parser`), and maps the report to
research-grade Observations (`ingest`). The V2 API/SDK path is out of scope.
"""

from __future__ import annotations
