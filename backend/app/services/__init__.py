"""Business logic layer.

Planned services (thin routers call into these):
- capabilities: server-side toggle authority + enforcement (B2C vs clinical).
- ingestion: orchestrates source adapters -> Observation rows + audit.
- trajectory: computes per-signal trend stats in code, then calls the AI layer to
  synthesize an explainable, sourced, confidence-scored Trajectory.
- audit: append-only audit-event writes for PHI access and config changes.
"""
