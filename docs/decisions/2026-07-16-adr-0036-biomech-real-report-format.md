# ADR-0036 — BioMech ingestion rebuilt to the real report format

- **Status:** Accepted
- **Date:** 2026-07-16
- **Supersedes the format assumptions of:** ADR-0014 (BioMech PDF ingest). ADR-0014's
  ingest architecture (capability-gated route, closed metric registry, content-identity
  idempotency, `source=biomech`/`document_imported`, PHI-free audit) **stands**; only its
  assumption about the *report text format and metric set* is corrected here.
- **Builds on / relates to:** ADR-0006 (research-grade Observations), ADR-0034 (NSI
  composite), the data-streams review (`docs/product/biomech-data-streams.md` §2–§3).

## Context

The V1 BioMech parser was written against an **assumed** report format — `label: value unit`
rows with metrics `sway_velocity`, `sway_area`, `gait_speed`, `step_time_symmetry`. When we
received **real** BioMech reports (Balance and Gait "Individual Test Report" PDFs), two facts
emerged (verified by extracting the real PDFs with the production **pypdf** path):

1. **The metric set was fictional.** Real reports contain Balance Score, Average
   Speed/Movement/Position (+ their "% Normal" population-referenced 0–100 values), Tilt and
   Rotation; and for gait: Gait Score, Total Steps, Step Length (in **feet**), Cadence,
   Impact Symmetry, Support Ratio, Single-Support Symmetry, and Pelvic Tilt % Neutral. None
   of the assumed codes exist.
2. **The text is not `label: value`.** pypdf emits each field on its **own line** — label,
   then unit, then value — with bold rows (composite scores, "% Normal") **duplicated**. The
   only colons are in the header (`Patient:`, `Test ID:`).

As written, the parser extracted **nothing** from a real report, and the fictional codes had
propagated into the directionality registry and the NSI composite. This blocked the entire
clinical Function tier from ingesting real data.

## Decision

**Rebuild the parser to the real format and realign the metric catalog**, verified against
the three real sample reports (synthetic "Test Test" patient; **not** committed — CLAUDE.md §5).

- **Parsing.** Collapse adjacent duplicate lines (removing the bold duplication), which turns
  each metric into a clean `label → unit → value → [range]` sequence. A known metric label is
  followed by its expected unit, then its value; the value is a clean number (optionally with
  a direction tag like `4.1 (RF)`). Defensive as before: `N/A`, split values (`47 / 53`),
  ranges, mis-units, out-of-range numbers, and repeats are **skipped with a warning**, never
  coerced. The report kind, **Date of Service**, and the **balance condition** (e.g. eyes
  open / eyes closed) are captured.
- **Real metric catalog.** The closed registry now carries the real codes:
  `biomech_balance_score`, `biomech_balance_{speed,movement,position}_normal`,
  `biomech_gait_score`, `biomech_cadence`, `biomech_step_length` (feet, `[ft_i]`),
  `biomech_total_steps`, `biomech_impact_symmetry`, `biomech_support_ratio`,
  `biomech_single_support_symmetry`, `biomech_pelvic_tilt_neutral`. The directionality
  registry mirrors these (parity test enforced).
- **Balance condition as provenance.** The eyes-open/eyes-closed condition is stored in
  `quality`/`payload` and folded into the idempotency key, so two same-day balance tests
  under different protocols never collide even when a value coincides. (The eyes-open −
  eyes-closed gap is a neuropathy-relevant proprioceptive signal; capturing the condition now
  is what makes that a future sub-signal.)
- **NSI composite.** The Function domain now uses the two **device-grade composite scores**
  (`biomech_balance_score`, `biomech_gait_score`, both 0–100, higher = better). Their
  component metrics (speed/movement/position, impact/support/pelvic) surface as trajectory
  signals but are **not** summed into the Index — that would double-count each test against
  its own parts (the same rule that excludes `adl_daily_score`).

## Relationship to the API-first recommendation

The data-streams review recommends BioMech ingestion move to a **structured API/SDK**
(`device_measured`) when available. This ADR does **not** reverse that: the **metric catalog**
here (real codes, units, polarities) is needed **regardless** of transport, and a working PDF
parser is the correct **fallback** and the only path that ingests real reports **today** (no
API exists yet). When the API lands, it delivers the same catalog; the PDF path remains the
fallback.

## Consequences

- Real BioMech reports now ingest correctly (verified: balance → 4 metrics + condition; gait →
  7 metrics; `N/A` step length correctly skipped).
- The fictional-code audit findings (parser / directionality / composite) are closed.
- Step length is in **feet** (`[ft_i]`), matching the report — not the earlier assumed cm.
- Not yet modeled: the eyes-open − eyes-closed **gap** as a derived signal, and the raw
  L/R split metrics (Impact L/R, Single-Support L/R) — deferred.

## Honesty invariants (unchanged)

Synthetic data only; no real report PDFs committed; displays come only from the closed
registry (never document free text); PHI-free audit (counts + kind, never values);
non-diagnostic.
