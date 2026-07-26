# ADR-0042 — AI photo food logging (V2): GPT-4o-vision + free-DB hybrid

- **Status:** Phase 1 implemented (the deterministic spine) — capability-gated `log_food`, OFF by
  default, so it stays dormant until product/clinical sign-off enables it. Phase 1 is manual,
  confirm-required, ranged entry stored as NSI-excluded `patient_estimated` Observations, with a
  `NutritionSource` seam. Deferred behind that seam: the free-DB paths (barcode → Open Food Facts,
  text → USDA) and the BAA-gated photo → GPT-4o path.
- **Date:** 2026-07-18
- **Builds on:** ADR-0006 (append-only research-grade Observations), ADR-0013/0020 (enforced
  capability toggles), ADR-0011/0040 (BAA-gated AI; Azure OpenAI narrator), ADR-0016
  (non-diagnostic framing), ADR-0038 (glucose context). Evidence base:
  `docs/product/food-ai-build-vs-buy.md`.

> **Non-diagnostic, non-dosing.** Food logging produces **ranged estimates for self-tracking**,
> never clinical-grade nutrition and **never** input to insulin dosing. This ADR keeps that
> guardrail structural, not just copy.

## Context

V2 adds patient food logging. The build-vs-buy analysis
(`docs/product/food-ai-build-vs-buy.md`) concluded that for a cost-conscious, non-diagnostic
product already on Azure with GPT-4o, a **GPT-4o-vision + free-nutrition-database hybrid** beats
both dedicated food-AI APIs and a build-your-own model on cost, accuracy, and compliance
(Microsoft's BAA covers Azure OpenAI). The critical, verified caveat: **no** option — paid API,
DIY, or GPT-4o — is clinical-grade at portion/macro estimation (energy MAPE ~35%+, protein MAPE
60%+). So the feature must be positioned and *engineered* as estimation, not measurement.

## Decision

**Ship food logging as a capability-gated, human-confirmed, ranged-estimate feature over the
existing Observation model — image recognition reserved for plated meals; barcode and text carry
the rest.**

**1. Architecture (three inputs, cheapest-accurate-first):**
- **Barcode → Open Food Facts (free).** Packaged foods: exact label macros, near-zero cost,
  highest accuracy. The default path where a barcode exists.
- **Text / natural-language → USDA FoodData Central (free).** The long tail of nameable foods.
- **Photo → GPT-4o-vision (Azure, under Microsoft's BAA)** for prepared/plated meals only.
  GPT-4o returns **food items + estimated portions**; items are mapped to **USDA / Open Food
  Facts** for macros (RAG-style grounding — the DietAI24 result showed the accuracy comes from
  DB grounding, not the model). Prompts are enriched with cheap context (meal time, prior logs)
  for the modest documented accuracy lift.

**2. Guardrails (structural, not just copy):**
- **Always a human confirm/edit step.** The estimate is a *draft* the patient edits and accepts;
  nothing is stored as an Observation until confirmed.
- **Ranged, not point, estimates.** Surface a range (e.g. "carbs ~30–45 g"), never false
  precision; no micronutrient breakdown the method can't support.
- **Never for dosing.** No insulin/medication guidance is derived from a food log; a persistent
  non-dosing note co-locates with the feature (ADR-0016 pattern).
- **Provenance.** Stored as Observations with a distinct source/origin marking them
  patient-estimated (not `device_measured`/`ehr_imported`), so they never carry lab-grade weight
  and are **excluded from the NSI** (like CGM glucose in ADR-0038 until validated).

**3. Capability + AI gating (reuse existing seams):**
- A new enforced capability (e.g. `log_food`) gates the feature (ADR-0013), OFF by default,
  patient-controlled.
- The GPT-4o call reuses the **BAA gate** (ADR-0011/0040): no photo leaves the device to Azure
  OpenAI unless `ai_baa_confirmed` + provider configured. Without it, **barcode + text still
  work** (free DBs, no PHI-to-LLM) — the photo path degrades gracefully to manual entry.
- The food photo is treated as PHI-adjacent: kept out of PHI-free logs (ADR-0021), not retained
  beyond what the confirm step needs.

**4. Cost posture** (from the evidence doc, our estimate — confirm against current Azure
pricing): ~$0.006–0.01 per photo-log; ~$6–10/mo at 1k photos, ~$60–100 at 10k — dramatically
cheaper than dedicated APIs' flat monthly floors because barcode/text logs cost ≈$0 and only
plated-meal photos hit the paid model.

## Consequences

- **Reuses everything:** the Observation store, capability enforcement, the BAA gate, and the
  Azure OpenAI seam already shipped (ADR-0040) — the net-new is the food pipeline + a confirm UI,
  not new infrastructure.
- **Honest by construction:** ranged estimates + human confirm + NSI-exclusion + non-dosing note
  make the "estimation not measurement" stance structural, matching the app's non-diagnostic
  posture and the FDA framework (ADR-0041 — no clinical/dosing claim attaches).
- **Graceful degradation:** with the AI gate off, the feature is still useful (barcode + text)
  and sends no photo to any LLM — a clean privacy/compliance fallback.
- **Deferred:** on-device recognition (Passio-style) as a future privacy upgrade at scale;
  folding food/glucose interplay into any score — only after validation, never in v1.

## Alternatives considered

- **Dedicated food-AI API (Passio/LogMeal/Nutritionix/Calorie Mama).** Rejected: enterprise/
  subscription-priced, no confirmed BAA, and no better (often worse) accuracy than GPT-4o —
  `food-ai-build-vs-buy.md`.
- **Build/host our own model.** Rejected: zero-shot GPT-4o already matches/beats dedicated models
  with no training; a from-scratch build isn't justified for a cost-conscious V2.
- **Point estimates with micronutrients.** Rejected: the accuracy evidence forbids that precision;
  it would misrepresent the feature and risk drift toward a clinical claim.
