# Mockups

Static HTML mockups built on the approved design tokens (`docs/design/`, ADR-0002).
**Synthetic data only** — no real patients (CLAUDE.md §5). Names/values are invented.

- **`patient-app.html`** — patient core flow: Connect (self vs. with a clinic —
  ADR-0005), Home (trajectory answer up top), Data sources (every feature toggleable),
  Connect EMR (pull labs via SMART on FHIR — ADR-0008), Lab import (snap → confirm →
  save), Trend detail (sourced + plain-language).
- **`clinician-app.html`** — clinical version: panel review, cross-source trend table
  (AI-assisted, non-diagnostic, clinician-in-the-loop), and per-patient monitoring
  toggles modeled as renewable orders (RTM-friendly).

Open either file in a browser. These are throwaway visuals to react to, not production
code — they encode the product decisions from the brainstorms so we can see them.

## What they deliberately express
- The trajectory answer ("Improving / Needs attention") leads; graphs support it.
- Every AI statement is **sourced** and framed as review material, never a diagnosis.
- Toggles are first-class and differ by version (patient-controlled vs. clinician-
  controlled with renewal), per the capability model.
- Accessibility: 17px+ text, large tap targets, plain language, color never the only
  signal (arrows + labels accompany every red/green).
