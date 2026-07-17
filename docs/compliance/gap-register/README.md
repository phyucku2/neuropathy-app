# Compliance Gap Register & Remediation Plan

> **THIS IS A GAP REGISTER AND REMEDIATION PLAN — NOT A CERTIFICATION, ATTESTATION, AUDIT, OR CLAIM OF COMPLIANCE.**
> It is prepared by **engineering** to inventory what the codebase demonstrably does, what is missing, and who owns each remaining action. **Nothing in this register should be read as a claim that the product is HIPAA-compliant, SOC 2-compliant, FDA-cleared, or otherwise certified.** All regulatory, legal, clinical, and quality-system determinations rest with **qualified professionals** (counsel, an FDA regulatory consultant, a licensed CPA firm, and the covered entity). Where a requirement is satisfied "met-in-code," that describes control *design in source*, not a control *operating in production* — and no production environment exists.

## Honest product status (as of 2026-07-15)

- **Synthetic data only.** No real Protected Health Information has ever been processed. CLAUDE.md §5, fixtures, and tests are built on synthetic-only discipline.
- **No deployed production environment.** Deployment exists as code, containers, compose files, and runbooks (ADR-0018); CI proves the images build. No cloud/hosting provider has been selected and no production instance runs. Consequently **storage-layer encryption at rest and TLS in transit are documented-but-unconfigured**, not operating.
- **No Business Associate Agreements signed.** The Anthropic AI-narrative BAA, the hosting-provider BAA, and any error/metrics-collector arrangement are all open covered-entity items (see [baa-inventory.md](../baa-inventory.md)). The app is engineered to keep every PHI-to-third-party seam **OFF** until the covered entity executes those agreements and attests.
- **Not FDA-cleared, -listed, or -registered.** Whether the AI trajectory output is Software as a Medical Device is an **open regulatory question routed to qualified counsel/regulatory review** (ADR-0003); the FDA device-status ADR is deferred behind professional sign-off.
- **Many controls are demonstrably met-in-code**, but several obligations (written policies, workforce training, risk analysis, signed BAAs, a configured production environment, and legal/clinical/regulatory sign-off) are **organizational actions outside this codebase** that have not been completed.

## Legend

**Status**

| Status | Meaning |
|---|---|
| **met-in-code** | The control is demonstrably implemented in source at a cited path. Does NOT assert it is deployed, configured, or operating in production. |
| **partial** | Partly satisfied — typically a technical control exists in code but a policy, deployment, or procedural component is missing. |
| **gap** | Not satisfied; the control/capability is absent in code and docs. |
| **organizational** | Satisfied (if at all) only by action outside the codebase: written policy, signed contract, deployed/configured environment, or professional sign-off. |
| **not-applicable** | Considered and judged out of scope for the current feature set (applicability to be confirmed by a qualified professional where noted). |

**Owner**

| Owner | Meaning |
|---|---|
| **engineering** | Can be completed within the codebase by the engineering team. |
| **organizational** | Requires policy, legal, regulatory, vendor, auditor, or covered-entity action outside the codebase. |
| **both** | Requires an engineering change AND an organizational action to be fully satisfied. |

## Per-lens summary counts

| Lens | met-in-code | partial | gap | organizational | not-applicable | Total |
|---|---|---|---|---|---|---|
| [HIPAA](./hipaa.md) | 4 | 16 | 3 | 12 | 0 | 35 |
| [SOC 2](./soc2.md) | 4 | 16 | 2 | 6 | 0 | 28 |
| [Security](./security.md) | 16 | 9 | 5 | 4 | 0 | 34 |
| [FDA](./fda.md) | 0 | 7 | 9 | 5 | 0 | 21 |
| [FTC](./ftc.md) | 2 | 8 | 6 | 1 | 2 | 19 |
| **Total** | **26** | **56** | **25** | **28** | **2** | **137** |

> "met-in-code" is counted separately from operating effectiveness. A high met-in-code count reflects strong technical design in source; it does **not** imply the product is compliant, since the largest categories remaining are `partial` and `organizational`, which require deployment and off-codebase action.

## Prioritized remediation roadmap

Priorities: **P0** = prerequisite blocker before any real PHI; **P1** = required for a defensible posture; **P2/P3** = important hardening / documentation. Items are split into **engineering** work (completable in the codebase) and **organizational** work (policy, legal, regulatory, vendor, auditor, deployment).

### P0 — Prerequisite blockers (must complete before any real PHI is processed)

**Organizational**
- Commission a formal HIPAA §164.308(a)(1) **risk analysis** of the deployed environment (HIPAA).
- Execute **BAAs** with Anthropic and the chosen hosting provider (and any error/metrics collector) before enabling those seams (HIPAA §164.308(b)/§164.314; SOC 2 CC9.2; Security).
- Select and configure a **production hosting environment** — no provider is chosen; TLS and disk/DB encryption cannot operate until one is (HIPAA cross-cutting; SOC 2 prerequisite).
- **Classify the FTC regime** (HIPAA covered-entity vs FTC HBNR PHR vendor) for each operating model, given the live B2C self-registration path; build the HBNR notification pathway if applicable (FTC).
- Engage an **FDA regulatory consultant** to render the §201(h)/SaMD **device determination** and record the deferred FDA-status ADR (FDA).
- Engage a **licensed CPA firm** and define a SOC 2 audit period/system description (SOC 2 prerequisite).

**Engineering (blockers that also need deployment/config)**
- Enable **storage-layer encryption at rest** for the PHI datastore + backups, and **require `SECRET_STORE_KEY`** in production config, gating deploys on it (HIPAA §164.312(a)(2)(iv); Security).
- Terminate **TLS 1.2+** at the gateway for all environments with HTTP→HTTPS redirect and HSTS; verify no plaintext ingress (HIPAA §164.312(e); SOC 2 CC6.7; Security).

### P1 — Required for a defensible posture

**Engineering**
- Add **rate limiting / lockout on `POST /auth/login` and `/auth/refresh`** (answer 429 before the Argon2 verify) — the primary auth surface is currently unthrottled (Security).
- Add a **SAST gate** (bandit + semgrep or CodeQL) to CI (Security).
- Enable and evidence **branch protection** (required reviews + status checks) and add CODEOWNERS (SOC 2 CC8.1; Security).
- Add **HSTS + security-header** completion and confirm nginx is the sole ingress (Security).
- Add security-header / transport middleware in-app as defense-in-depth (HIPAA §164.312(e)).

**Organizational**
- Appoint and document a named **Security Official / Privacy Officer** and fill incident roles (HIPAA §164.308(a)(2); SOC 2 CC1).
- Stand up **workforce security-awareness training** with tracked completion (HIPAA §164.308(a)(5)).
- Produce a **written information-security program + risk-assessment methodology** and risk register (SOC 2 CC3/CC5; FTC §5 unfairness).
- Assemble a formal **HIPAA policy-and-procedure set** and the Privacy Rule §164.530 administrative requirements (HIPAA §164.316/§164.530).
- Have counsel complete a **compliant Notice of Privacy Practices** and publish the **full privacy policy** at a real URL (HIPAA §164.520; FTC).
- Make the "**refuses unencrypted connections**" UI claim true (or soften it) before publication (FTC §5).
- Substantiate or narrow the **health-outcome / trajectory claims** (FTC §5).
- Deploy **operating monitoring/alerting** and vendor risk-management once production exists (SOC 2 CC4/CC6.6/CC7; HIPAA).
- Route the **CDS carve-out / general-wellness / intended-use** questions and BioMech provenance dependency to the FDA consultant (FDA).

### P2 / P3 — Hardening and documentation

**Engineering (P2)**: JTI/session revocation list, breached-password screening, refresh-token rotation, MFA for ops/clinician, a secure password-reset flow, registration anti-automation, cross-tenant authorization test matrix, PHI-read-access audit-coverage test, DB-level audit immutability / tamper-evidence, inactivity timeout, a CI guard against analytics SDK drift, backup-scoped erasure. (Security, HIPAA, SOC 2, FTC)

**Organizational (P2/P3)**: sanction / workforce authorization / access-recertification / evaluation / secrets-rotation / retention-schedule / media-disposal policies; access-control matrix; DR plan with RPO/RTO; COPPA applicability determination + age screen; FTC biometric & ROSCA applicability notes; the full suite of device-contingent FDA artifacts (QMS, design controls/DHF, IEC 62304, ISO 14971, Part 11 e-signatures, registration/listing, UDI, postmarket MDR/complaints, §524B SBOM, clinical validation) — each triggered only IF the device determination lands as "device." (All lenses)

## Per-lens registers

- [HIPAA](./hipaa.md) — Security Rule §164.308/310/312/314/316, Privacy Rule, Breach Notification §164.400–414
- [SOC 2](./soc2.md) — Trust Services Criteria (Security, Availability, Confidentiality, Processing Integrity; Privacy scoped out pending decision)
- [Security](./security.md) — OWASP ASVS / OWASP Top 10 / MASVS
- [FDA](./fda.md) — SaMD, device determination (open question), Quality System — **no device classification asserted**
- [FTC](./ftc.md) — Health Breach Notification Rule, FTC Act §5, COPPA

## Existing compliance & legal artifacts referenced (not duplicated here)

- [../baa-inventory.md](../baa-inventory.md) — PHI-flow surfaces and BAA/gating status
- [../hipaa-ops-checklist.md](../hipaa-ops-checklist.md) — HIPAA Security Rule operational checklist
- [../incident-response-runbook.md](../incident-response-runbook.md) — incident/breach response scaffold
- [../../legal/privacy-policy-draft.md](../../legal/privacy-policy-draft.md) — engineering-authored privacy policy DRAFT (counsel review required)
- [../../ops/backup-restore.md](../../ops/backup-restore.md), [../../ops/observability.md](../../ops/observability.md), [../../ops/deployment.md](../../ops/deployment.md) — operational runbooks
- [../../engineering/data-standards.md](../../engineering/data-standards.md), [../../engineering/standards.md](../../engineering/standards.md) — engineering standards
- [../../product/reimbursement-signoff-packet.md](../../product/reimbursement-signoff-packet.md) — routes the FDA/reimbursement sign-off (D2)
- [../../decisions/](../../decisions/) — the Architecture Decision Records (ADR-0001 … ADR-0035)
- [../../roadmap-status.md](../../roadmap-status.md) — Wave status, incl. the deferred FDA device-status ADR
