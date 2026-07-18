# FDA Regulatory-Consultant Brief — Device-Status Determination (Decision D2)

**Date:** 2026-07-18
**Status:** Engagement brief — **awaiting the written determination** (this document is the
vehicle for decision **D2**; the returned opinion becomes the *accepted* successor to
[ADR-0041](../decisions/2026-07-18-adr-0041-fda-device-status-framework.md))
**Reviewer:** a qualified **FDA regulatory professional** (with the owner)
**Governing record:** [ADR-0041](../decisions/2026-07-18-adr-0041-fda-device-status-framework.md)
(framework + deferral), [`../compliance/gap-register/fda.md`](../compliance/gap-register/fda.md)
(gap register), [`reimbursement-signoff-packet.md`](reimbursement-signoff-packet.md) §4
(the same question in the reimbursement context — do not duplicate; this brief is the
standalone, sendable version).

---

> ## ⚠️ READ THIS FIRST — SCOPE & CAVEAT
>
> This is **decision-support material for a qualified FDA regulatory professional. It is NOT
> a regulatory determination, legal advice, or a claim of FDA compliance**, and nothing in it
> classifies the software. The product is **NOT FDA-cleared, -listed, or -registered**, is
> **not clinically validated**, and processes **synthetic data only**. Every framing below is
> an **input for the consultant to adjudicate**, never a conclusion. Whether the software (or
> its trajectory / Neuropathy Status Index output) is a §201(h) device / SaMD is exactly the
> **open question this brief asks the consultant to answer.** Engineering has correctly
> refused to answer it since ADR-0003, and this brief preserves that refusal.

---

## 1. The exact decision requested (D2)

A single **written §201(h) / SaMD opinion** covering the questions in §4, selecting a posture
**per data stream**, stating the **obligations that follow**, and signing the sheet in §6.
The opinion becomes the accepted FDA-status ADR that supersedes ADR-0041 and **gates** any
billing-enabling, clinical-claim, or marketing build (ADR-0041 §2–§4).

**What we are NOT asking:** no FDA submission, no clearance, no claim approval. We ask for a
**classification determination and the resulting obligations**, so the product's gates
(ADR-0041 §3–§4) resolve from an expert opinion rather than an engineering assumption.

## 2. Product facts the consultant needs (verifiable in the repo)

| # | Fact | Pointer |
|---|---|---|
| 2.1 | **Working posture (unconfirmed hypothesis): non-device** — general-wellness or a non-device CDS function under Cures §520(o)(1)(E). Treated as a hypothesis, not a conclusion. | ADR-0041 §1 |
| 2.2 | **Deterministic, explainable trajectory**: per-signal direction + confidence + sourced drivers + data gaps — no black box; the clinician surface re-presents this, non-diagnostically. | ADR-0003/0016; `trajectory/directionality.py`, `schemas/trajectory.py` |
| 2.3 | **The NSI** is a single 0–100 non-diagnostic composite (Symptoms 45 / Function 40 / Physiologic 15), labeled **"non-diagnostic v1, pending clinical validation."** | ADR-0034 |
| 2.4 | **Non-diagnostic note co-located** with every surfaced direction; cross-unit deltas refused; no diagnosis/treatment/prediction claims in UI, store, or marketing. | ADR-0016; `NonDiagnosticNote.tsx` |
| 2.5 | **AI narration** is a warmth-rephrasing of the deterministic result — **BAA-gated, off by default, never in the request path**; validated to reject diagnosis/dosage/causation/new numbers. | ADR-0011/0020/0040; `ai/narrative.py` |
| 2.6 | **Two patient-facing data streams the "device" question attaches to:** (a) **ADL self-report** (patient-reported functional/symptom check-ins) and (b) **imported BioMech report data** (`document_imported` — PDF text-layer parse, closed metric registry, never fabricated); labs are point-in-time EMR/imported results. | ADR-0006/0014; `biomech-data-streams.md` |
| 2.7 | **BioMech is billed/regulated separately** (owner decision 2026-07-14); imported BioMech data keeps `document_imported` provenance and is **not** given device-grade weight in any claim. | signoff-packet §2.4 |
| 2.8 | **Record integrity** is ALCOA+/append-only with full provenance and dual timestamps (Part 11-aligned *in spirit*; no e-signature capability). | ADR-0006; `models/observation.py`, `models/audit.py` |

## 3. Draft intended-use statement of record (for the consultant to ratify or correct)

ADR-0041 §5 and the FDA gap register (P1) call for **one controlled intended-use statement**
as the anchor the claims gate checks against. This is the **draft** the consultant is asked to
ratify, correct, or replace — it is not yet adopted:

> *Draft — pending consultant + counsel sign-off.* **[Product] is a non-diagnostic digital
> health tool for adults that ingests, organizes, and visualizes a person's own
> neuropathy-related information — patient-reported daily symptom/function check-ins, imported
> balance/gait report data, and imported/EMR-pulled lab results — and presents a transparent,
> explainable *trend* ("improving / not improving") of that information over time, together
> with a single non-diagnostic status index. It does not diagnose, treat, cure, mitigate, or
> prevent any disease; it does not measure a physiological parameter itself; it does not
> recommend or alter treatment; and it is not a substitute for professional medical judgment.
> Any clinician-facing surface re-presents the same transparent, patient-sourced trend so the
> clinician can independently review its basis.**

**Consultant questions on §3:** Does this statement, as worded, support the intended posture
(§4)? What must change (scope, audience, the word "status," disease-specific framing) for the
statement to be defensible as the anchor for claims control?

## 4. The determinations requested (per stream)

### 4.a §201(h) / SaMD status of the software (PRIMARY)

Is the app — ADL capture + ingest/graph + deterministic trajectory/NSI, explicitly
non-diagnostic (§2) — **(i)** not a device, **(ii)** a device under enforcement discretion, or
**(iii)** a regulated SaMD? Answer **per stream** (ADL self-report vs. imported BioMech data),
because under the §2.7 separate-billing boundary the software is the only device-candidate for
the ADL stream. Governing guidances to apply:
[Policy for Device Software Functions and Mobile Medical Applications](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/policy-device-software-functions-and-mobile-medical-applications);
[Software as a Medical Device (SaMD)](https://www.fda.gov/medical-devices/digital-health-center-excellence/software-medical-device-samd).

### 4.b The four §520(o)(1)(E) CDS criteria (the non-device-CDS test)

Map the clinician-facing trend/NSI surface against **all four** Cures CDS criteria — with
particular attention to the two that are least obviously met:
[Clinical Decision Support Software guidance](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software).

1. **Not acquiring/processing a signal from a device** (the *device-derived-signal* prong) —
   does imported BioMech balance/gait data, or any lab, count as a "signal … from an in-vitro
   diagnostic device or a signal acquisition system," and does that pull the surface *into* the
   device definition?
2. **Displays/analyzes medical information** (patient-record/peer-reviewed basis).
3. **Provides recommendations, not a specific directive output.**
4. **Enables the HCP to independently review the basis** (the *independent-review* prong) —
   the surface is built for this (direction + confidence + sourced drivers + data gaps), but
   does the design actually satisfy the criterion, and does a **patient-facing** (non-HCP)
   audience change the analysis?

**Consultant question:** does the surface stay a **non-device CDS function**, and does the
answer differ for the clinician surface vs. the patient surface?

### 4.c General-wellness eligibility (patient surface)

Is the **patient-facing** function a low-risk **general-wellness** function, and **does that
survive the disease-specific, neuropathy-monitoring framing and the product name**?
[General Wellness: Policy for Low Risk Devices](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/general-wellness-policy-low-risk-devices).
Does naming/claims need adjustment to hold this posture?

### 4.d Accessory vs. standalone SaMD (relative to BioMech)

Is the app an **"accessory"** to the BioMech device (21 CFR 3 / Cures), or a **standalone**
function? The §2.7 separate-billing decision sharpens rather than removes this line wherever
imported BioMech data would carry device-grade weight. Answer explicitly.

### 4.e If any stream is a device — the obligations that follow

State which apply and at what depth (all currently **absent by design**, gated on this
finding — gap register): QMS/§820 (QMSR/ISO 13485), design controls + DHF (§820.30),
IEC 62304 lifecycle + safety class, ISO 14971 risk file, 21 CFR Part 11 e-records/signatures,
premarket pathway + establishment registration/listing (21 CFR 807), UDI (21 CFR 830),
postmarket (803 MDR / 820.198 / 806), §524B premarket cybersecurity + SBOM, IEC 62366 human
factors, GMLP + a Predetermined Change Control Plan (PCCP) for the AI/trajectory output, and a
clinical-evaluation/validation plan proportionate to the claims.

## 5. Triggers that would force the device path (context for the opinion)

Per ADR-0041 §4, any one of these converts the contingent obligations in §4.e from "deferred"
to "required-before-ship," and re-opens the product as a device program: attaching a
clinical/predictive claim to the NSI or trajectory; enabling reimbursement that requires a
device; marketing a reasonable reader would read as diagnosis/treatment; or giving
device-derived signals decision-grade weight in a patient-facing interpretation. The opinion
should note which of its findings are sensitive to these triggers.

## 6. Sign-off sheet (D2)

| Field | FDA regulatory consultant |
|---|---|
| Name / credential | ______________________ |
| **4.a** SaMD status — ADL stream (attach written opinion) | ☐ Not a device ☐ Enforcement discretion ☐ Regulated SaMD |
| **4.a** SaMD status — imported BioMech-data stream | ☐ Not a device ☐ Enforcement discretion ☐ Regulated SaMD |
| **4.b** Non-device CDS (§520(o)) — clinician surface | ☐ Qualifies ☐ Does not ☐ Qualifies w/ conditions |
| **4.b** Non-device CDS — patient surface | ☐ Qualifies ☐ Does not ☐ Qualifies w/ conditions |
| **4.c** General-wellness (patient) survives disease-specific framing | ☐ Yes ☐ No ☐ Yes w/ naming/claims changes |
| **4.d** Accessory vs. standalone | ☐ Accessory to BioMech ☐ Standalone ☐ Other (attach) |
| **§3** Intended-use statement | ☐ Ratified as drafted ☐ Ratified w/ edits (attach) ☐ Replaced (attach) |
| **4.e** Obligations that apply (attach list + depth) | ______________________ |
| Overall posture of record | ☐ Non-device (both streams) ☐ Device (which stream) ☐ Mixed (attach) |
| Signature / date | ______________________ |

---

> ## ⚠️ CAVEAT (bottom — same weight as the top)
>
> **Decision-support material for a qualified FDA regulatory professional — NOT a regulatory
> determination, legal advice, or a compliance claim.** Nothing here classifies the software or
> authorizes any clinical/marketing claim or FDA submission. The product is **not FDA-cleared,
> -listed, or -registered**, is **not clinically validated**, and processes **synthetic data
> only.** The returned written opinion — not this brief — is the determination, and it gates the
> product's claims/reimbursement/marketing per ADR-0041.
