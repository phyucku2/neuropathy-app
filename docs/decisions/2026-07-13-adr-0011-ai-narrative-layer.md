# ADR-0011: AI Narrative Layer

**Date:** 2026-07-13
**Status:** Accepted
**Builds on:** ADR-0003 (AI analyzes; numbers computed in code) and Brainstorm #3
(AI-safety lens: hybrid deterministic-stats + LLM synthesis).

## Context

The trajectory engine is deterministic and already produces a plain-language template
summary. The AI layer's job — per ADR-0003 — is to make that narration warmer and more
specific **without ever being the source of a number or a judgment**. The direction,
signals, confidence, and gaps stay computed in code; the model only rephrases them.

## Decision

A **Narrator** seam on top of the computed `Trajectory`:

1. **Input discipline.** The model receives ONLY the computed trajectory (direction,
   per-signal plain-language details, data gaps, confidence) — never raw observations,
   never ingested document text (prompt-injection surface stays closed), never
   identifiers.
2. **Fail-safe AND off the request path.** The deterministic template summary is
   always computed first and is the response whenever the narrator is unconfigured,
   errors, or fails validation. The LLM call itself NEVER runs inside a request
   (standards.md: AI is asynchronous jobs only — and in DB mode a request holds a
   transaction): a request either serves a previously accepted **cached** narrative
   for the identical computed trajectory, or ships the template now and schedules
   narration as a background task after the response. Polling an unchanged
   trajectory therefore never repeats the provider call or the disclosure.
3. **Output validation before use.** The narrative is rejected (falling back to the
   template) if it: contains any number — digits or spelled out — not present in its
   input; contains dosage/medication-directive/cause/diagnosis language; contradicts
   the computed direction (terms exempted when the facts themselves contain them,
   so mixed trajectories still narrate); exceeds a length cap; contains URLs or
   code-shaped tokens; or is empty. These checks are heuristic defense-in-depth
   behind the prompt; the deterministic fallback bounds the cost of any miss.
   Input-side, the injection surface is closed where it starts: lab codes are
   LOINC-shape-validated at intake and unknown-code labels are sanitized before
   they can reach signal details or the prompt.
4. **BAA gate.** The computed trajectory derives from PHI, so sending it to a model
   provider is a disclosure: the LLM path activates only when BOTH `AI_API_KEY` is set
   AND `AI_BAA_CONFIRMED=true` (operator's explicit attestation that a BAA covers the
   provider account — Anthropic offers BAAs for API/enterprise customers). Key without
   attestation = narrator stays off (fail-safe, ADR-0003 hard line).
5. **Auditability.** Scheduling a provider call is the disclosure, so the
   `ai_narrative` audit event (model, event="requested" — never content) is written
   in the same request/transaction that schedules it — error and rejection paths are
   never unaccounted. The response carries `narrative_source: "ai" | "deterministic"`
   so clients and clinicians always know which they are reading.
6. **Provider.** Anthropic Messages API, default model `claude-haiku-4-5-20251001`
   (fast/cheap fits a one-sentence rephrase; configurable via `AI_MODEL`). Behind a
   `Narrator` protocol so providers are swappable.

## Consequences

- `Trajectory` schema gains additive `narrative_source` (default "deterministic") —
  no breaking change to the locked contract.
- Config: `ai_api_key` (existing), `ai_baa_confirmed` (new, default false),
  `ai_model` (new). No secrets in repo; `.env.example` documents them.
- Tests cover: off-by-default, BAA gating, validation rejections (numbers,
  contradiction, length, URL), provider error/timeout fallback, request shape against
  a mock transport, and the audit event.

## Options considered

- **LLM reads raw observations and writes the whole answer:** rejected — hallucinated
  trends, FDA posture risk, prompt-injection surface (Brainstorm #3).
- **No AI at all:** viable (template summaries are honest) but leaves the planned
  differentiator unbuilt; the seam keeps AI strictly decorative over computed facts.
- **Deterministic-first with validated, BAA-gated narration (chosen).**
