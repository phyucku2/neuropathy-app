# ADR-0040 — Azure OpenAI as a narrator provider (HIPAA-eligible AI layer)

- **Status:** Accepted
- **Date:** 2026-07-18
- **Builds on:** ADR-0011 (validated, BAA-gated, fail-safe AI narrative layer), ADR-0003
  (external providers must be BAA-covered before any PHI), ADR-0020 (`ai_narrative` toggle
  ANDs with the BAA gate). Relates to the Azure deployment path (ADR — `infra/azure/`).

## Context

The AI narrative layer (ADR-0011) rephrases the **computed** trajectory into warmer plain
language. It never sees raw observations or document text — only the computed `Trajectory` —
and its output is validated (no new numbers, no direction contradiction, bounded length),
with the deterministic template as the always-available fallback. Until now the only shipped
narrator called the **Anthropic** Messages API.

Two things changed:

1. **Claude is no longer available for our PHI layer** — the provider now requires PHI
   handling terms we cannot rely on for the direct API in this deployment, so the Anthropic
   Messages path cannot be the PHI-facing narrator here.
2. **We chose Azure.** Microsoft signs a **BAA that covers Azure OpenAI Service**, making
   GPT-4o on Azure the HIPAA-eligible path for the narrator on our own infrastructure.

The narrator is provider-agnostic at the call site: `routes/trajectory.py` keys the narrative
cache and the disclosure-audit label off `settings.ai_model` (a logical label), not off any
provider object. So adding a provider is a **seam swap**, not an endpoint change.

## Decision

**Add an `AzureOpenAINarrator` alongside `AnthropicNarrator`, selected by `ai_provider`.**
Everything else about ADR-0011 is unchanged — same prompt, same `narrative_is_safe`
validation, same negative-cached background execution, same BAA gate.

- **Shared flow.** Both narrators extend a small `_HttpNarrator` base that owns the flow
  (build facts → send the one fixed prompt → validate → fall back to `None` on ANY error).
  Subclasses implement only `_complete(prompt)` — the provider request/response shape. The
  Anthropic narrator's public surface (constructor, `_model`, `narrate`, `aclose`) is
  unchanged.
- **Azure specifics.** Azure OpenAI routes by **deployment**, not model id, and authenticates
  with an `api-key` header. The request URL is
  `{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={version}`; the
  reply is read from `choices[0].message.content`. The `deployment` doubles as the narrator's
  `_model` so the cache key / audit label stays stable and provider-neutral.
- **Selection (`app/api/deps.py`).** The gate is unchanged and checked **first**: a narrator
  activates ONLY with a key **AND** the operator's `ai_baa_confirmed` attestation. Then
  `ai_provider` routes: unset/`"anthropic"` → Anthropic; `"azure_openai"`/`"azure"` → Azure.
  A misconfigured Azure provider (no `ai_azure_endpoint`) or an unknown provider **stays
  OFF** — fail-safe, never a half-configured provider call.
- **Config (`app/core/config.py`).** New settings, read only on the Azure path:
  `ai_azure_endpoint` (`https://<resource>.openai.azure.com`), `ai_azure_deployment`
  (defaults to `ai_model` when blank), `ai_azure_api_version` (default `2024-10-21`, a GA
  data-plane version; override as needed). For Azure, set `ai_model` to the underlying model
  (e.g. `gpt-4o`) so disclosure audits read cleanly.

## Consequences

- **Non-breaking.** With `ai_provider` unset the behavior is byte-for-byte the prior Anthropic
  path. No route, schema, cache, or audit change. The BAA attestation still binds to the
  provider actually called (the gate runs before any provider is constructed).
- **Fail-safe preserved.** Every ADR-0011 guarantee holds regardless of provider: the LLM is
  never in the request path, any provider error falls back to the deterministic template, and
  the validator rejects invented numbers / dosage-shaped assertions / direction contradictions
  identically (the Azure path is covered by the same validation tests).
- **PHI posture.** Turning the narrator on for Azure still requires the operator to (a) sign
  Microsoft's BAA covering Azure OpenAI and (b) set `ai_baa_confirmed=true`. Until both, the
  layer is off and `/trajectory` is fully deterministic.
- **Deferred.** Azure AD / managed-identity auth for Azure OpenAI (instead of `api-key`) and
  streaming are out of scope; the decorative, sub-6s, cached narration does not need them.

## Alternatives considered

- **Keep only Anthropic.** Rejected: not usable for our PHI layer under the new terms, and we
  deploy on Azure.
- **Azure via an OpenAI-SDK dependency.** Rejected: a direct `httpx` call (as the Anthropic
  narrator already does) keeps the dependency surface minimal and the request/response shape
  explicit and testable with `httpx.MockTransport`.
- **A general OpenAI (non-Azure) narrator.** Not added here — the BAA-covered path we need is
  Azure OpenAI; a public-OpenAI narrator would be another provider behind the same seam if a
  future need arises.
