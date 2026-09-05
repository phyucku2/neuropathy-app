# Multi-Tenant Wellness Platform (Hormones & Peptides) — Multi-Lens Brainstorm

**Date:** 2026-09-04
**Status:** Brainstorm (not a decision record — decisions graduate to `docs/decisions/` ADRs)
**Topic:** A tenant-based back end behind custom client websites (e.g. menopausal.me,
Kosar Wellness), with a patient dashboard, a CRM, and MSO middleware for API/webhooks;
per-client "templates" selecting the vertical (Hormones — men only; Peptides &
supplements; Men and women; …).

**Clean-room note (CLAUDE.md §1):** Everything below is derived from first principles
and public, industry-standard knowledge. The request referenced two repositories that
are **owned by or associated with this account** — `Mike-diamedics/menopausal-me`
(explicitly named in the §1 ban list) and `phyucku2/mso-marketing`. **Neither was
opened, read, or referenced**, and nothing here mirrors them. The owner's spoken
requirements in the request are legitimate design input (§3 inbound-brief rule); their
prior *code* is not. Two third-party public repositories were license-checked only
(see §21). If the owner wants prior-build patterns reused, that is a §1 waiver only the
owner can grant, and it should be recorded before any such reuse.

---

## 0. Framing, and the one reframe that matters

The request describes templates as a *website* concern: pick a vertical, get the right
site. That is the visible 20%. The load-bearing 80% of what differs between
"Hormones — men only" and "Peptides & supplements" is **clinical and regulatory**, not
visual: which molecules may be offered, in which states, after which labs, with which
contraindications, under which consent, with which claims allowed in marketing.

> **Reframe: a template is not a theme. A template is a versioned clinical program
> definition, and the brand skin is a thin layer on top of it.**

This matters because of the failure mode. If templates are built as presentation
config, the clinical guardrails get copy-pasted per tenant and then drift. The way that
failure presents in production is a patient in a state where the provider is not
licensed receiving a Schedule III prescription — a licensure action, not a bug report.

Everything below follows from that reframe.

---

## 1. The regulatory ground is moving *inside the build window*

Two facts were verified on 2026-09-04 rather than recalled, and both change the design.
Neither is legal advice; both are owner/counsel decisions (§8).

**(a) DEA telemedicine flexibilities expire 2026-12-31 — ~4 months out.**
The fourth temporary rule (published 2025-12-31) extends COVID-era flexibilities for
tele-prescribing Schedule II–V through **December 31, 2026**. The *Special Registrations
for Telemedicine* final rule entered OMB review on 2025-08-25 and is forecast for
**~November 2026**. **Testosterone and its esters are Schedule III** under the Anabolic
Steroid Control Act, so the entire "Hormones — men only" vertical sits directly on this
cliff.

*Design consequence:* prescribing pathway (tele-only vs. in-person-first vs.
special-registration) must be **per-state × per-molecule × per-effective-date
configuration**, evaluated at order time. It cannot be an `if` in the checkout code,
because it is guaranteed to change during the build.

**(b) Peptides are in an explicit gray zone, and FDA has signalled against them.**
On **2026-04-15** FDA removed BPC-157 and 11 other peptides from 503A **Category 2**,
but did **not** move them to Category 1. Ahead of the **July 23–24, 2026** Pharmacy
Compounding Advisory Committee meeting, FDA **proposed that BPC-157, KPV, TB-500,
MOTS-c, Emideltide, Epitalon, and Semax NOT be added** to the 503A bulks list. They are
neither FDA-approved nor USP/NF-monographed.

*Design consequence:* "removed from Category 2" is not a green light, and the business
risk here is materially higher than for hormones. The catalog must be **deny-by-default
against a sourced regulatory ledger** (§4), not a product list someone edits.

---

## 2. Architecture — four planes, two isolation axes

### The four planes

| Plane | Surface | Data class | Notes |
|---|---|---|---|
| **Brand** | Public marketing sites (menopausal.me, Kosar…) | Public + leads | Indexable. **No PHI. No condition-revealing URLs.** |
| **Patient** | Authenticated dashboard | PHI | Labs, dose, refills, messages |
| **Clinical** | Provider console | PHI (most restricted) | Owned by the **PC**, not the MSO |
| **Business** | CRM + MSO middleware | Commercial, PHI-*minimized* | Partner integrations, billing, campaigns |

The plane boundary is the primary security control. MSO staff must not hold standing
access to the clinical plane — that is simultaneously a HIPAA minimum-necessary control
and a corporate-practice-of-medicine (CPOM) posture (§19).

### Two isolation axes — the thing most DTC platforms get wrong

Tenancy is **not** one dimension:

- `tenant_id` — the **brand** (menopausal.me vs. Kosar Wellness)
- `pc_id` — the **professional corporation** holding the clinical record

These are **not 1:1**. One PC may serve several brands; one brand may need different PCs
in different states. Platforms that collapse these into one column cannot unwind it
later without a data migration across the clinical record. **Model both from day one**,
even if v1 ships with a single PC.

### Tenancy mechanism

Recommendation: **shared schema + `tenant_id` + Postgres Row-Level Security**, with the
tenant bound to a session-level GUC set in the request transaction, and
database-per-tenant reserved as a contractual escape hatch for an enterprise client that
demands physical isolation.

- Schema-per-tenant is a migration nightmare past ~20 tenants.
- DB-per-tenant does not scale operationally at this stage.
- RLS is the belt to the application layer's suspenders. The app already knows to
  **fail closed** (`docs/lessons.md`); the RLS default must be *deny*, and the test
  suite must prove a cross-tenant read returns **zero rows**, not "the right rows".

---

## 3. The template model

```
ProgramTemplate (IMMUTABLE, versioned)
  ├─ catalog            [ProgramOffering]     → joins the regulatory ledger (§4)
  ├─ intake             InstrumentVersion     → reuses the ADR-0049 instrument pattern
  ├─ eligibility        RuleSet               → declarative, server-evaluated (§5)
  ├─ required_labs      [LOINC panel]         → reuses ADR-0007 FHIR/LOINC intake
  ├─ consents           [ConsentDocVersion]
  ├─ dashboard_modules  [CapabilityKey]       → reuses the ADR-0013 registry
  └─ claims_pack        [ApprovedClaim]       → legal-reviewed marketing copy
```

`TenantProgram` binds `tenant × template_version × effective_range`. **Every Order and
Encounter permanently stores the `template_version_id` it was created under.** That is
the ADR-0006 provenance discipline applied to commerce: you must be able to answer, two
years later and under subpoena, "what exactly was this patient shown, asked, and
offered, on that day?"

Corrections are new versions, never edits (append-only, ADR-0006).

The three named verticals are then just template instances — "Hormones — men only",
"Peptides & supplements", "Men and women" — differing in catalog, intake, eligibility,
and claims, sharing one engine.

---

## 4. The regulatory ledger (the most defensible piece of the design)

Given §1, the catalog cannot be a static list.

```
RegulatoryStatus(substance, jurisdiction, pathway,
                 effective_from, effective_to,
                 source_url, reviewed_by, reviewed_at, review_due)
```

Rules:
- An offering is orderable **only** if a current, non-expired status row permits it in
  that jurisdiction. **Unknown ⇒ denied.**
- A substance whose `review_due` has passed **auto-suspends from ordering** rather than
  silently continuing on a stale assumption.
- Every row carries a **source URL and a human reviewer** — the same discipline
  `docs/lessons.md` already imposes on reimbursement figures ("never assert from
  memory; source every figure").

This converts "the FDA changed its position on BPC-157" from a fire drill into a data
update, and produces the audit trail that defends the business. **This is the piece most
worth a §2 novelty note.**

---

## 5. The eligibility engine

Declarative rules as **data**, versioned and server-evaluated — never client-side, never
a deploy to change a template.

- **Deny by default.** Unknown state × molecule × patient-attribute ⇒ not orderable.
- **One pure predicate**, unit-locked, mirroring ADR-0013's `is_effectively_active`.
  That pattern is already proven in this codebase and should not be re-invented.
- **Every evaluation is logged** with inputs, rule version, and outcome.

Hard clinical rules the engine must encode (illustrative, clinician sign-off required):
- **Unopposed estrogen + intact uterus ⇒ blocked** (endometrial cancer risk). This is
  the single most important rule in the women's vertical.
- TRT: hematocrit ceiling (erythrocytosis is the most common TRT adverse event),
  age-based PSA, and **fertility counselling gating** — TRT suppresses spermatogenesis,
  and starting a 30-year-old without documented counselling is real malpractice exposure.
- Provider must hold an active licence in the **patient's** state at encounter time.

Regulatory note: an engine that *recommends* a molecule drifts toward Clinical Decision
Support. Staying inside the 21st Century Cures CDS exemption requires the provider to be
able to independently review the basis for the recommendation — so the engine must
**show its reasoning**, not just its verdict. Explainability here is a compliance
requirement, not a nicety.

---

## 6. Physician lens (endocrinology / men's health / OB-GYN / primary care)

- **Men (TRT):** baseline total + free testosterone (two morning draws), LH/FSH,
  estradiol, hematocrit, PSA, lipids. Monitoring: hematocrit, PSA, symptom scales.
  Fertility counselling as above.
- **Women (menopause HRT):** transdermal vs. oral estrogen carries materially different
  VTE risk; endometrial protection is mandatory with an intact uterus. Contraindications:
  breast-cancer history, VTE history, CAD, undiagnosed vaginal bleeding.
- **Peptides:** blunt assessment — most have **no meaningful evidence base**. This is
  where clinical credibility is spent. Good providers will not want their licence
  attached to it, which becomes a **recruiting and retention problem**, not just a
  compliance one. Worth the owner's explicit decision before it is built.

## 7. Patient lens

Wants: fast, affordable, non-judgmental, and *real*. The recurring question is "is this
actual medicine or a pill mill?" The two dominant churn drivers in DTC hormones are
**lab friction** and **shipping delay** — so the dashboard's job is: my labs over time,
my current dose, my next refill, my next lab due, message my provider. Price
transparency and genuine cancel-anytime are trust features, not commerce features.

## 8. BioMech Health lens — **conflict flag**

BioMech Health is **not a stakeholder in this product**; they are the licensee of the
neuropathy app (ADR-0001). This lens's finding is therefore a warning, not a
requirement: **if the wellness platform ships from this repository, BioMech's licence —
written against "the product" — becomes ambiguous as to what it covers.** See §22.

## 9. Apple (iOS) lens

- **IAP:** prescriptions, consults, and physical supplements are real-world
  goods/services and fall outside the App Store's in-app-purchase requirement. A
  *digital-only* content subscription would not — keep that boundary clean.
- **Guideline 4.3 (spam/duplicate apps)** is the multi-brand trap: N near-identical
  white-label apps from one codebase invite rejection. The mitigation is that each
  client publishes under **their own developer account**, which is a contract term, not
  an engineering task.
- Account deletion is already a solved problem here (ADR-0027) — reuse it.

## 10. Android lens

Mirror of §9: Play's repetitive-content policy, a per-brand Data Safety declaration, and
the Health apps declaration. Note Play's restricted-content rules around unapproved
substances — a peptide-forward listing is at real risk.

## 11. HIPAA / privacy lens

**The marketing site is the biggest liability in this entire stack**, not the backend.
A third-party tracker on a page whose URL reveals a condition is precisely the fact
pattern behind the OCR tracking-technology enforcement and the well-publicised telehealth
actions.

- **Hard rule: zero third-party trackers on any authenticated surface, and no
  condition-revealing URLs anywhere on the brand plane.**
- The **PC is the covered entity; the MSO is a business associate.** That drives BAAs
  with every vendor — CRM included.
- Per-tenant BAA inventory, extending the ADR-0021 compliance pack.

## 12. SOC 2 / security lens

Tenant isolation is the control an auditor will hammer hardest. Beyond RLS: per-tenant
**secret scoping** in the existing encrypted vault (ADR-0017) — tenant A's pharmacy API
key must be unreachable from tenant B's request context — plus access reviews and
no standing MSO access to clinical notes.

## 13. Marketing lens

- **LegitScript certification is a hard gate** for paid acquisition on Google and Meta
  in telehealth/pharmacy. Without it, paid channels are closed. This should be started
  early; it has a lead time.
- Supplements: DSHEA structure/function claims only, with the disclaimer; no disease
  claims. FTC substantiation applies.
- Peptides are, practically speaking, **unadvertisable** on the major networks.
- The `claims_pack` exists so legal-approved copy is versioned and a brand cannot
  freelance its own claims.

## 14. Legal & regulatory lens

Consolidating: the DEA cliff and special registration (§1a); FDA peptide posture (§1b);
CPOM and fee-splitting (§19); state modality rules (some states require synchronous
audio-video before a first prescription); and the CDS boundary (§5). Every one of these
is an owner + counsel decision under §8 — none may be self-authorized.

## 15. Accessibility lens

WCAG 2.2 AA is binding (§7). **Multi-brand theming is an accessibility trap:** client
brand palettes will break contrast, and "it's their brand guide" is not a defence.
Enforce contrast **at the theme-token level in CI** so a non-conforming tenant theme
fails the build rather than shipping.

## 16. Payer / reimbursement lens

Cash-pay. Cheap high-value win: **superbill generation** plus HSA/FSA eligibility
flagging. Full insurance billing (eligibility, claims, clearinghouse) is a much larger
build and should be explicitly **out of scope for v1**. Per `docs/lessons.md`, no CPT
figures are asserted here; anything billing-adjacent is PENDING coder + compliance
validation.

## 17. Data science / ML lens

Cross-tenant learning is contractually fraught: tenant A's data improving a model that
serves tenant B requires explicit rights in the client agreement. **Separate
tenant-scoped from platform-scoped analytics in the schema from day one** — retrofitting
that boundary is not possible once the models are trained. The genuine ML opportunity is
**titration/dose-response**, not a chatbot.

## 18. Clinical research / validation lens

This platform will accumulate the largest longitudinal hormone + symptom dataset any of
these brands will ever hold. Research-grade capture (ADR-0006 discipline) makes it an
asset; sloppy capture makes it noise. IRB required before anything is published.

## 19. Caregiver / family lens

Lower salience than in neuropathy, but not empty: partners are heavily involved in
fertility and menopause decisions. **Explicitly out of scope for v1** — recorded rather
than dropped, per §6.

## 20. Agile lens

Do not build four planes at once. **One thin vertical slice: one tenant, one template,
one real order round-tripping to a pharmacy and back to the dashboard.** Everything else
is speculation until that works. Then add the second template — the second one is what
proves the abstraction, and it should be built early *precisely because* it will break
the first design.

## 21. DevOps lens

Per-tenant custom domains with automated certs; per-tenant config rollout with canaries;
and per ADR-0021, `tenant_id` is a safe, low-cardinality, PHI-free metric label —
`patient_id` never is.

## 22. Reimbursement (Medicare/Medicaid) lens — **explicitly nothing to add, and why**

Per §6 this lens is stated rather than dropped. This vertical is **cash-pay DTC
wellness**; Medicare and Medicaid do not cover the bulk of it, and the RTM/RPM/CCM
machinery developed for the neuropathy app (`docs/product/reimbursement-analysis.md`)
**does not transfer**. No billing-pathway work is proposed. If an insurance-covered HRT
path is ever pursued, it re-enters through the existing signoff packet process.

---

## New lenses added by this brainstorm (recorded per §6 so the canonical list grows)

## 23. Pharmacy / compounding lens

503A (patient-specific compounding) vs. 503B (outsourcing facility) is a structural
choice with different FDA obligations. Per-state pharmacy licensure, state-level shipping
restrictions, cold chain, and DEA registration for Schedule III all become **per-tenant,
per-molecule routing data** in the MSO middleware — not hardcoded partner logic.

## 24. MSO / corporate-structure lens

**CPOM and fee-splitting are load-bearing on the data model, not just the cap table.**
In CPOM states the MSO may not practise medicine or split clinical fees; the PC must own
the clinical record and the clinical decision. Concretely: the `pc_id` axis (§2), no
standing MSO access to the clinical plane, and an MSO fee structure that is defensible
as an administrative services fee. Getting this wrong is an existential risk to the
business, and it is cheap to model correctly at the start and near-impossible to
retrofit.

## 25. Payments / e-commerce lens

Card networks classify telehealth and pharmacy under high-risk MCCs. Processor selection,
subscription dunning, and chargeback exposure need early attention, and the processor's
acceptable-use terms must be read specifically against **compounded medications** —
several mainstream processors restrict them.

---

## 26. CRM: build vs. buy

`trycompai/crm` is **MIT** (license-checked 2026-09-04, §4-clean) but is recommended
**against** as a base, on two grounds:

1. **Second runtime.** It is Bun + Turborepo + NestJS + Next + Prisma. ADR-0004 commits
   this stack to Python/FastAPI/SQLAlchemy. Adopting it means operating two backend
   runtimes, two ORMs, and two migration systems for one product.
2. **Agentic-by-design is the wrong shape for PHI-adjacent data.** Its premise is an
   autonomous agent conducting independent research against records. That is difficult
   to reconcile with HIPAA minimum-necessary on a health CRM.

Recommendation: build a **thin CRM on the existing stack**, scoped to the business plane
only — leads, campaigns, subscriptions, tickets — with a hard, audited boundary to the
clinical plane. If a CRM is bought instead, the selection criterion is "will they sign a
BAA", and it integrates through the MSO middleware like any other partner.

`Kiranism/next-shadcn-dashboard-starter` is also **MIT** and is a reasonable *reference*.
But note the §4 tension: a starter template is adopted by **copying**, and §4 says
libraries are "consumed as dependencies, never vendored by copy-paste, unless the owner
approves a specific exception." **Using it as a starter needs an explicit owner
exception**; using shadcn/ui as a dependency does not.

## 27. MSO middleware — integration patterns

The middleware is the hub for pharmacy, lab, payments, shipping, e-sign, and comms.
Non-negotiables, several of which this codebase has already learned the hard way:

- **Idempotency keys on every inbound webhook** (cf. migration `0008_observation_import_idempotency`).
- **Per-partner signature verification**; reject unsigned.
- **Transactional outbox for outbound calls** — an order must not be lost because a
  pharmacy API blipped.
- **Replay + dead-letter queues**, because partner APIs will fail and the failure must be
  recoverable without a human reading logs.
- **Per-tenant partner routing** as data (§23).
- Per ADR-0021, every new egress seam ships **off by default and config-gated**.

---

## 28. What this stack can reuse from the existing codebase

This is the strongest technical argument for a shared core, and the reason the placement
question in §29 is worth deciding deliberately:

| Existing | Reused as |
|---|---|
| Auth — Argon2id + JWT + refresh rotation + MFA (ADR-0010) | Unchanged |
| Capability registry + `is_effectively_active` (ADR-0013) | Dashboard-module system per template |
| Audit events (ADR-0012/0021) | Tenant + PC scoped audit |
| FHIR/LOINC lab intake (ADR-0007) | Hormone panels are LOINC-coded already |
| Research-grade provenance (ADR-0006) | Template-version provenance on orders |
| Encrypted secret vault (ADR-0017) | Per-tenant partner credentials |
| PHI-free observability (ADR-0021) | Tenant-labelled metrics |
| Deployment, E2E harness, mobile shell | Unchanged |

That is a large fraction of a year's work already done.

---

## 29. The decisions this brainstorm forces

**Blocking, owner-only (CLAUDE.md §8 — do not self-authorize):**

- **D1 — Repository, IP, and licence placement.** Three options:
  - **(a) Separate repo, fresh build.** Cleanest IP story. Loses the §28 reuse entirely
    — and note the sharp second-order effect: **§1's clean-room rule would then forbid
    the new repo from reading *this* one**, making the reuse legally awkward as well as
    manually expensive.
  - **(b) Extend this repo, fenced module.** Fastest, maximum reuse. Entangles two
    clients' IP in one licensed codebase and strains "one product per repo" (§8).
  - **(c) Extract a shared platform core consumed by both.** Best destination, highest
    upfront cost, and requires the owner to decide how BioMech's licence attaches to the
    core versus the app.

  *Recommendation:* **(c) as the destination.** But this is an ADR-0001-level licensing
  question and needs the owner plus counsel before any code lands.
- **D2 — Is the peptide vertical in scope at all?** (§1b, §6, §13.) A product and legal
  decision with a genuine downside case.
- **D3 — Corporate structure** — MSO/PC, CPOM states, fee structure (§24). Gates the
  data model.
- **D4 — DEA posture after 2026-12-31** (§1a). Gates the entire men's hormone vertical.

**Engineering ADRs, once D1 is settled:**

| | Decision |
|---|---|
| A | Tenancy model — shared schema + RLS, dual `tenant_id` / `pc_id` axes (§2) |
| B | Program template as an immutable, versioned clinical artifact (§3) |
| C | Regulatory ledger + deny-by-default catalog gating (§4) |
| D | Eligibility rule engine — declarative, versioned, explainable (§5) |
| E | CRM build-vs-buy and the PHI boundary (§26) |
| F | MSO middleware integration patterns (§27) |
| G | Brand/theme layer with CI-enforced contrast (§15) |
| H | Tracking/analytics posture across brand and authenticated planes (§11) |

---

## 30. Suggested first slice

Once D1–D4 are answered: **one tenant, one template ("Men and women" — it exercises both
sex-specific rule paths), one molecule with a clean regulatory status, one pharmacy
partner, one real order round-tripping to the dashboard.** Then immediately build the
**second** template — that is what proves the abstraction, and it is cheaper to discover
the first design is wrong at template two than at tenant twelve.
