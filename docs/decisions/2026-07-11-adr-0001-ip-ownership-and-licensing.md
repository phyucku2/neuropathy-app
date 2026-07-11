# ADR-0001: IP Ownership and Licensing Model

**Date:** 2026-07-11
**Status:** Accepted (owner decision)

## Context

The neuropathy app is being built at the request of **BioMech Health**. Because the
project's central goal includes patentable, original IP (see `CLAUDE.md`), the
ownership structure had to be settled before any requirements flow between the
parties or any novel mechanism is disclosed to them.

## Decision

- **We (the repository owner) own all intellectual property** produced in this
  project: code, designs, data models, measurement methods, and any patent
  applications and resulting patents.
- **BioMech Health is a licensee**, not an owner or co-owner. They receive rights to
  use the product under a license whose scope/exclusivity/territory/term are to be
  defined in the written agreement — those license terms are a business decision
  outside this ADR.

## Consequences

1. **Paper it before deep exchange.** A written development + license agreement (with
   NDA and IP-assignment language) should be in place before novel mechanisms are
   disclosed to BioMech Health and before their detailed requirements are ingested.
   Counsel drafts this; this ADR just records the intent.
2. **Inventorship hygiene.** If BioMech Health personnel contribute inventive
   concepts (not just requirements/feedback), they may qualify as co-inventors under
   patent law, which can undermine sole ownership. Mitigations: the agreement must
   include assignment of any of their contributions; inbound material from them is
   logged with date and source (see provenance rule); invention candidates are
   conceived and documented in this repo.
3. **Inbound requirements are allowed inputs.** Client-provided briefs/requirements
   from BioMech Health are legitimate design inputs and do NOT violate the clean-room
   rule (which bars reuse of *our own prior builds*). They must be stored under
   `docs/requirements/biomech-health/` with received-date so provenance is auditable.
4. **Outbound disclosure stays gated.** Sharing with BioMech Health is disclosure to
   a third party: NDA first, and pre-filing, share the minimum necessary — behavior
   and outcomes, not mechanisms, unless counsel clears it.
5. **Patent filings** proceed in the owner's name on the owner's timeline; BioMech
   Health's launch wishes do not override the file-before-public-disclosure rule.

## Options considered

- **Work-for-hire (they own):** rejected — conflicts with the project's core goal of
  owner-held patentable IP.
- **Joint ownership:** rejected — joint patent ownership lets each party exploit and
  license independently (in the US, without accounting to the other), which guts
  exclusivity and complicates enforcement.
- **We own / they license:** chosen — preserves the patent estate and keeps one
  commercial gatekeeper, while giving BioMech Health the usage rights they need.
