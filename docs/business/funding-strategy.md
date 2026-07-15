# Funding strategy

> Prepared by engineering as an orientation for the owner. **Not investment, securities,
> tax, or legal advice.** Grant strategy, any securities offering, and cap-table decisions
> should involve qualified professionals (counsel, an accountant, and — for SBIR — a grants
> advisor). Dollar figures below are order-of-magnitude planning numbers, not quotes;
> confirm current amounts against the funder's live program announcements.

## Where the company is (the honest baseline)

This determines which doors are open. As of this writing:

- **Pre-revenue, pre-deployment.** No production environment, synthetic data only, no real
  PHI processed. The app builds and its CI is green, but nothing is live.
- **IP owned** by Advanced Health and Wellness Group (the owner's entity); **BioMech Health**
  is the licensee. BioMech's own device/assessment billing is scoped **separately** (owner
  decision, 2026‑07‑14).
- **Regulatory status unresolved.** FDA §201(h)/SaMD device determination is an open question
  routed to a qualified consultant; not FDA‑cleared or ‑listed. See
  [`../compliance/gap-register/fda.md`](../compliance/gap-register/fda.md).
- **Reimbursement is a thesis, not a fact.** The RTM/RPM path is analyzed and gated on a
  compliance sign‑off (see [`../product/reimbursement-signoff-packet.md`](../product/reimbursement-signoff-packet.md)),
  not yet validated by a coder/compliance professional.
- **Waiting on DUNS/AWS access** before a production stand‑up can begin.

Read plainly: this is a **pre‑seed, pre‑pilot** company with unusually strong engineering
rigor for its stage. That rigor is a fundraising asset — but it does not substitute for a
deployed pilot or the FDA answer, and honest fundraising says so.

## The ladder (ordered by fit *today*)

### 1. Non‑dilutive grants — start here

Best fit at this stage: they fund the science, take no equity, and reward exactly the rigor
already built (audit trail, consent model, ALCOA+ provenance, the honest gap register).

**NIH SBIR/STTR** is the primary target. The neuropathy + balance/gait + fall‑risk framing
maps cleanly to several institutes — apply to the one whose mission best fits the specific
aim:

| Institute | Why it fits |
|---|---|
| **NINDS** (neurological disorders/stroke) | Peripheral neuropathy is squarely in scope. |
| **NIDDK** (diabetes/digestive/kidney) | Diabetic peripheral neuropathy — very large population; strong disease‑burden narrative. |
| **NIA** (aging) | Balance/gait metrics, fall risk, and function‑tracking in older adults. |
| **NIBIB** (biomedical imaging & bioengineering) | The measurement/analytics technology angle. |

- **Mechanics:** Phase I ≈ $150–300k (feasibility, ~6–12 mo), Phase II ≈ $1–2M (development).
  SBIR = the company does the work; STTR = formal partnership with a research institution
  (useful if you want an academic clinical collaborator for validation).
- **Fast Track / Direct‑to‑Phase‑II** exist if feasibility is already strong — worth asking a
  grants advisor whether the current build qualifies.
- **Prerequisites:** SAM.gov + SBIR company registration (DUNS/UEI — the item already in
  flight), and a Specific Aims page. The build‑inventory and CTO briefs are most of the
  "innovation + feasibility" narrative already.

**Also non‑dilutive:**
- **NSF SBIR/STTR** — deep‑tech/health, no disease‑specific requirement; different review lens.
- **State & regional programs** — many states offer SBIR match grants and early‑stage
  innovation funds; low effort, stacks on top of a federal award.
- **Disease foundations** — diabetes/neuropathy patient foundations sometimes fund digital
  tools or pilots; smaller checks but strong validation + patient access.

### 2. Strategic & partnership capital — run in parallel

- **BioMech Health (the licensee)** is the natural first strategic conversation. The platform
  drives utilization of their assessments, so a **strategic investment** or **expanded
  commercial terms** (e.g., co‑development funding, a data‑access agreement) can align
  interests without a traditional raise. Keep the "billed separately" scoping intact; this is
  about funding the platform, not merging the billing.
- **Clinic / health‑system design partners.** Pilot **Letters of Intent** are not cash, but
  they are the single highest‑leverage de‑risking move: they prove demand, unlock real
  (consented) data for validation, and make every grant and equity conversation stronger.
  Target PT clinics and neurology/endocrinology practices already oriented to RTM/RPM.

### 3. Angel / pre‑seed (dilutive) — realistic now, modest size

- Healthcare/digital‑health **angel groups** and individual angels; instruments are typically
  **SAFEs or convertible notes** (defer valuation to the priced round).
- Founders / friends‑and‑family.
- Use this to bridge to the first pilot + the FDA determination, not to fund the whole plan.

### 4. Digital‑health accelerators

Capital + the thing money can't easily buy: **payer/provider BD connections** and
reimbursement expertise — directly relevant to the RTM path. Worth an application in parallel
with grants.

### 5. Seed VC — **not yet**

Institutional seed unlocks after: a **deployed pilot with real consented data**, the **FDA
determination**, and **early reimbursement evidence**. Raising today would be on a deck at a
low valuation. Grants + a pilot get you to a materially better round. Revisit once two of
those three exist.

### 6. The reimbursement engine (eventual, self‑funding)

Once live and validated, RTM/RPM billing is **revenue**, which reduces how much equity you
ever need to sell. That is the point of the sign‑off packet — it is upstream of this line.

## Sequencing (next ~2 quarters)

1. **Finish the DUNS/UEI + SAM.gov + SBIR registration** (already in flight) — it unblocks the
   entire non‑dilutive track.
2. **Line up one clinical/design partner** (LOI) — for demand proof and a validation data path.
3. **Pick one NIH institute + one specific aim** and draft the Specific Aims page; reuse the
   CTO and build‑inventory briefs.
4. **Open the BioMech strategic conversation** on funding the platform.
5. **Get the FDA determination scoped** with a consultant — it is a gate for grants, partners,
   and any equity round, and it is a named P0 in the gap register.
6. Keep angel/accelerator options warm as a bridge; hold institutional seed until the pilot +
   FDA answer exist.

## What investors and grant reviewers will ask (and where the answer lives)

| Question | Where it's answered / what's missing |
|---|---|
| Is it real and well‑built? | [`briefs/cto-brief.html`](./briefs/cto-brief.html), [`briefs/build-inventory.html`](./briefs/build-inventory.html), green CI. **Strong.** |
| Is the data handled responsibly? | [`../compliance/gap-register/`](../compliance/gap-register/) — honest posture; P0s are the known gaps. |
| What's the regulatory status? | **Open** — FDA determination not yet made. Fundraising gate. |
| Is reimbursement proven? | **Thesis, gated** — [`../product/reimbursement-signoff-packet.md`](../product/reimbursement-signoff-packet.md). |
| Is there demand / traction? | **The current gap** — a pilot LOI is the highest‑leverage fix. |
| Who owns the IP? | Advanced Health and Wellness Group; BioMech is licensee. Clean. |

The pattern: **engineering and rigor are ahead; regulatory clarity and market traction are the
gaps.** Grants and a pilot are the cheapest, least‑dilutive way to close them.
