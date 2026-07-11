"""AI trajectory-analysis layer.

Design contract (ADR-0003, Brainstorm #3):
- Trend numbers (slopes, change-points, reference-range crossings) are computed IN CODE.
- The model only synthesizes/explains over those computed stats; it never eyeballs raw
  values (hallucination control).
- Output is explainable, sourced, and confidence-scored, degrading gracefully when
  sources are sparse or toggled off.
- PHI only ever reaches a BAA-covered provider (or on-device / de-identified).
"""
