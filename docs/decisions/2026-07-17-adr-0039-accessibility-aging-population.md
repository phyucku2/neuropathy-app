# ADR-0039 — Accessibility-first for the aging (60+) diabetic population

- **Status:** Accepted
- **Date:** 2026-07-17
- **Relates to:** the design system (`docs/design/brand.md`, `tokens.css`), the existing
  contrast tests, and every UI portion (ADR-0015/0016 and the forthcoming Learn / Your Records
  surfaces). This is a standing design principle, not a one-feature decision.

## Context

Our primary users are patients **aged 60 and older** with diabetes and peripheral neuropathy.
That population has age- and disease-specific constraints that most consumer health-app designs
(bright, dense, gradient-heavy — e.g. the competitor apps we reviewed) actively work against:

- **Vision** — presbyopia and reduced contrast sensitivity, and in *this* population specifically
  a meaningful rate of **diabetic retinopathy**. Small type, thin fonts, and low-contrast text on
  gradients are failure modes, not style choices.
- **Dexterity** — reduced fine motor control, and — importantly — **peripheral neuropathy affects
  the hands, not only the feet**, so precise small-target tapping is hard.
- **Cognitive load** — slower processing favors simple, single-purpose screens over dense
  dashboards.

## Decision

**Accessibility for the 60+ user is a first-class product constraint** that every new UI must
meet — not a later "a11y pass."

- **Type & contrast.** Large, legible type; no thin weights for body text; strong contrast that
  clears WCAG AA (and AAA for primary content where practical). No essential text on gradients or
  low-contrast fills. The repo's existing **contrast tests** are the enforced floor for new colors.
- **Targets & spacing.** Large tap targets (comfortably above the 44×44 px minimum) with generous
  spacing and forgiving controls — designed for imprecise taps.
- **Simplicity.** One primary action per screen where possible; plain language (6th–8th-grade);
  minimal clutter; never rely on color alone to carry meaning (pair it with text/icon), consistent
  with the existing direction-of-better-in-words rule.
- **Motion & timing.** No essential information conveyed only by motion; respect
  `prefers-reduced-motion`; no auto-advancing content the user can't pause.

## Consequences

- New surfaces (starting with **Learn** and **Your Records**) are built to this bar from the first
  commit and must pass the contrast tests; a visually denser design is rejected even if "prettier."
- It is a genuine differentiator: the honest, focused, legible design is *better for our users* than
  the saturated, dense competitor pattern — and reinforces the trust posture (NSI clarity,
  non-diagnostic honesty).

## Honesty invariant

Accessibility claims are only as good as what's tested — we assert AA-contrast where the contrast
tests cover it and do not claim full WCAG conformance until an audit backs it; that audit is a
recorded follow-up, not an assumed state.
