# Privacy Policy — DRAFT SCAFFOLD (not legal advice; counsel review REQUIRED)

> **STATUS: DRAFT.** This is an engineering-authored scaffold whose factual statements are
> grounded in the shipped codebase (references in brackets). It is NOT legal advice and MUST
> be reviewed, completed, and approved by qualified counsel before publication. Bracketed
> `[…]` items are placeholders the owner fills in. Statements about practices that are not
> yet live (e.g. the AI narrative vendor) must be re-verified at publication time.

**Advanced Health and Wellness Group** ("we") operates the Neuropathy app (the "App"). This policy describes what
the App collects and how it is handled.

## What we collect

- **Account information:** your name and email address, used to create and secure your
  account. Passwords are stored only as modern one-way hashes (Argon2id). [ADR-0010]
- **Health information you add:** your daily check-in, which by default covers both your
  neuropathy symptoms (pain and numbness, on a 0–10 scale) and your daily function (walking,
  stairs, balance confidence, on a 0–4 scale); patient-entered medications and supplements and
  changes to them; and between-visit notes and events you record (for example a fall, an
  emergency-department visit, or a new provider). The symptom questions default on but can be
  turned off, leaving a function-only check-in. [ADR-0006/0034/0049/0045]
- **Health information you import or enable:** laboratory results you import from your
  electronic medical record after you explicitly authorize the connection, and balance/gait
  measurements from reports you upload. Only when you turn them on: mobility data from your
  phone or watch's health store, clinician notes pulled from your medical record, and a
  food/nutrition log you enter yourself. These optional sources are off by default and
  collect nothing until you enable them. [ADR-0007/0009/0014/0035/0038/0042]
- **Nothing else.** The App does not collect location, contacts, photos (beyond the report
  file you explicitly choose), advertising identifiers, or usage analytics, and it contains
  no advertising or analytics SDKs.

## How your information is used

Your information is used solely to provide the App's features to you: showing your trends,
computing your explainable trajectory, and — only if you turn sharing on — making your data
visible to the clinic you authorized. We do not sell your information, and we do not share
it with third parties for marketing. [ADR-0012/0013/0020]

## Your controls

- **You hold the sharing switch.** Clinician access requires your consent and stops when you
  turn it off — your clinic cannot override it. [ADR-0020]
- **Connections can be revoked at any time**, and revocation is never blocked. [ADR-0013]
- **Account and data deletion:** [describe the in-app deletion flow when shipped — REQUIRED
  before store publication] or contact **[support email]**.

## Security

- All network traffic is encrypted in transit (TLS only; the App refuses cleartext).
- On your device, the session credential is stored in the operating system's hardware-backed
  secure storage and, where available, protected by your biometric or device credential.
  App data is excluded from device backups. [ADR-0023/0024]
- On our servers, access to your information is consent-gated and audited. [ADR-0012]

## What the App is not

The App is a tracking and decision-support tool. It does not diagnose, treat, or prevent any
disease, and it is not a substitute for professional medical advice.

## [Sections for counsel to complete]

- Legal bases / jurisdiction-specific rights (HIPAA authorization language if the deployment
  is under a covered entity's program; state privacy laws; GDPR if ever applicable)
- Data retention schedule
- Breach notification commitments (align with docs/compliance/incident-response-runbook.md)
- Children's privacy statement (the App is not directed at children under 18)
- Contact details: **Advanced Health and Wellness Group, [address], [support email]**
- Effective date and change-notification policy
