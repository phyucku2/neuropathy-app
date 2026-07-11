# BioMech Lab Portal — Reference Review

**Received:** 2026-07-11 (screenshots provided by owner; taken from a signed-in
session on biomechhealth.com, account "Mike Christiansen — Advanced Health and
Wellness Group")
**Artifacts:** `2026-07-11-biomech-lab-screenshots/` (overview dashboard, nav menu)
**Provenance note:** This is the client/licensee's existing product ("BioMech Lab"),
reviewed as inbound context per CLAUDE.md §3. It informs *requirements and
integration fit*. Their portal's UI/design is **their IP** — we design our own
surfaces fresh; we align on workflow concepts and data hand-offs, not on copied
screens.

---

## What the screenshots show (observations, not assumptions)

1. **BioMech Lab is a clinician-facing web portal** (responsive web, viewed in a
   mobile browser) with nav: Overview, Patients, RKM Orders, Utilization (split
   into **RKM** and **In Clinic**), Admin, Support, Profile.
2. **The operating unit is the "RKM Order."** The Overview dashboard is built
   around order lifecycle: *Expires today / in 1 week / in 2 weeks / recently
   expired (last 14 days)*. Orders expire and need renewal — strongly consistent
   with 30-day remote-monitoring billing cycles.
3. **"RKM Patient Records Not Accessed (past 30 days)"** is a first-class dashboard
   widget. Clinician *review* of transmitted records is tracked — consistent with
   RTM/RPM billing requirements where clinician review time/interaction must be
   documented.
4. **Utilization is split RKM vs. In Clinic** — they measure patients both remotely
   and in-clinic, and track utilization of both service lines.
5. **Multi-clinic:** the signed-in footer shows a clinic organization ("Advanced
   Health and Wellness Group") — BioMech Lab serves third-party clinics; the clinic
   context is displayed per session.
6. Brand: "BioMech Lab" wordmark, navy/steel-blue palette.

*(Open: what "RKM" stands for — owner to confirm. Reads as their branded
remote-monitoring program, functionally in the RTM/RPM family.)*

## Implications for our product (updates to Brainstorm #2)

### Confirmed
- **The "clinic providing the services" ecosystem is real and order-driven.** Our
  clinical version's data almost certainly lands with clinics that already live in
  BioMech Lab. The V1 **PDF's most likely destination is the BioMech Lab workflow**
  (attached to an RKM order / patient record); V2 API/SDK would integrate our
  recordings directly into their portal.
- **Payer-lens bet confirmed:** expiring orders + records-not-accessed tracking is
  exactly the RTM/RPM compliance shape we predicted. Our recording metadata should
  carry what their billing workflow needs (transmission days, completion counts,
  review-ready summaries).

### Changed / sharpened
- **The clinician "toggle" should be modeled as an ORDER, not a switch.** Their
  world already thinks in orders with parameters and **expiration dates**. So the
  capability-registry design (ADR queue #1) gains a clinical activation type:
  `order{capability, parameters, start, expiry, renewals, ordering clinician}`.
  Expiry-driven deactivation and renewal prompts come with it. This *strengthens*
  the "digital assessment prescription" invention candidate — and our version
  remains independently designed: their orders govern their devices/services; ours
  govern in-app capabilities on the patient's own phone.
- **Our clinical story is "extend In-Clinic to home":** their Utilization split
  (RKM vs In Clinic) suggests in-clinic assessments they'd love to see continued at
  home between visits. That's precisely our phone-as-instrument layer.
- **A patient-fronting app may be the missing piece of their ecosystem** (their
  visible product is clinician-side). That positions our B2C app as genuinely
  complementary rather than competitive — good for the license relationship.

### New questions for the owner / BioMech Health
1. What does **RKM** stand for, and what does an RKM order concretely order today
   (a device? a service? which measurements)?
2. Does an RKM order involve **BioMech Health hardware** the patient takes home? If
   so, does our app coexist with, replace, or ingest from that hardware?
3. For V1: should the PDF be **delivered into BioMech Lab** (upload/inbox), emailed
   via their existing channels, or handed to clinics directly?
4. Do they want our clinical version's activations to **appear as RKM orders** in
   their portal eventually (V2 API), and is their order model documented anywhere
   we can receive under the agreement?
5. Which billing codes do they operate under today (RTM 98975–98981, RPM
   99453–99458, other)? Shapes our counters and PDF summary blocks.

### IP hygiene reminders triggered by this material
- Do not reproduce BioMech Lab screens, layouts, or branding in our product.
- The order-lifecycle *concept* (expiring prescriptions/orders) is generic
  healthcare practice; our implementation is designed independently in this repo.
- If BioMech Health later shares their order schema/API docs for V2, that arrives
  under the written agreement and gets filed here with received-dates.
