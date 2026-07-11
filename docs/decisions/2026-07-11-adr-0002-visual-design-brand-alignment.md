# ADR-0002: Visual Design — Brand Alignment with BioMech Lab

**Date:** 2026-07-11
**Status:** Accepted (owner decision)

## Context

The neuropathy app is a product licensed to BioMech Health and lives alongside their
existing **BioMech Lab** clinician portal and PDF reports. The owner directed that our
app use a **similar font and color scheme** so the two products read as one family —
clinicians and patients moving between our recordings and BioMech Lab should feel
visual continuity.

Reference material: `docs/requirements/biomech-health/` (portal + report screenshots).
Observed BioMech Lab visual language:
- Deep **navy → blue gradient** header; two-tone blue "BioMech Lab" wordmark.
- Light blue-grey app background; white content cards.
- **Blue** section header bars in reports; charcoal-navy body text.
- A **status palette** on the dashboard: red (urgent), amber (warning), sky blue
  (info), navy (neutral/expired).
- **Green** primary action buttons ("Run Custom Report").
- Friendly, slightly geometric sans-serif for UI headings; standard sans for report
  tables.

## Decision

Adopt a **BioMech-aligned design system**, captured as platform-neutral design tokens
in `docs/design/` (source of truth: `tokens.json`; `tokens.css` for web/prototype;
`brand.md` for the human reference). Specifically:

- **Color:** a navy/blue primary palette with a green primary-action accent and a
  red/amber/sky/navy status set, matching BioMech Lab's usage semantics.
- **Type:** **Poppins** for display/headings (friendly geometric sans that mirrors
  BioMech's heading feel) and **Inter** for body/UI/data (a highly legible screen
  face — chosen deliberately for our low-vision/elderly primary persona, Accessibility
  lens). Both are **SIL Open Font License** — permissive, satisfying hard rule §4. We
  do **not** license or embed BioMech's exact typefaces.

## Boundaries (clean-room / IP)

- **Trade dress vs. trademark.** Matching a color scheme and typographic *character*
  is permissible and here it is *authorized by the owner* for a licensed sibling
  product. But BioMech's **logo/wordmark is their trademark** — we create our own
  neuropathy-app wordmark; we never reproduce theirs.
- We do **not** copy BioMech Lab's screen layouts, report templates, or component
  designs pixel-for-pixel (that would also violate our clean-room rule). We share a
  *palette and type system*; we design our own screens.
- Fonts are our own OFL-licensed choices that approximate the feel — not their font
  files.
- Exact hex values below are **estimated from screenshots** and are placeholders to be
  reconciled against BioMech Health's official brand guide if/when they provide one
  (logged here with a received-date at that time).

## Consequences

- Design tokens exist before any UI is scaffolded, so every future screen (B2C and
  clinical, iOS and Android and any web) draws from one source — no per-platform drift.
- Accessibility is enforced at the token layer: text/background pairings are chosen to
  meet WCAG 2.2 AA contrast (verified in `brand.md`); this is non-negotiable given the
  primary persona.
- When the platform ADR lands, tokens.json is transformed to the target
  (Swift/Kotlin/Tailwind) — the JSON stays canonical.

## Options considered

- **Fully independent brand:** rejected — owner wants continuity with BioMech Lab.
- **Pixel-match BioMech Lab (fonts, layouts, logo):** rejected — trademark/clean-room
  risk and no added value over a shared token system.
- **BioMech-aligned token system with our own OFL fonts and screens:** chosen.
