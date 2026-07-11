# Product Requirements — v1 (as stated by owner)

**Received:** 2026-07-11
**Source:** Owner (project commissioned by BioMech Health; owner relays direction)
**Status:** Authoritative input — supersedes assumptions in earlier brainstorms where
they conflict.

## Stated requirements (verbatim intent)

1. **Start with a patient-fronting app.**
2. **Multiple versions:**
   - **B2C** version (direct to consumer).
   - **Clinical** version, where the data is transmitted to the clinic providing the
     services.
3. **Biometrics** are required.
4. **Neuropathy-specific features** are required.
5. **BioMech data recordings** are required:
   - **V1:** delivered as **PDF**.
   - **V2:** delivered via **API or SDK**.
6. **B2C app:** every feature must be able to be toggled on/off.
7. **Clinic app:** the clinician must be able to toggle everything on and off.

## Open clarifications (owner to confirm)

- **"Biometrics" scope:** physiological measurements (heart rate, HRV, steps, sleep,
  etc. from phone/wearable), biometric *authentication* (Face ID / fingerprint), or
  both? Brainstorm assumes **both** until told otherwise.
- **Toggle authority in B2C:** user-controlled toggles, owner/ops-controlled, or both
  (ops gates availability, user gates activation)? Brainstorm assumes **both layers**.
- **Clinic toggles:** per-patient, per-clinic defaults, or both? Brainstorm assumes
  **both (clinic default + per-patient override)**.
- **PDF recipient in V1:** the clinic, BioMech Health, the patient, or all three?
- Is the "clinic providing the services" BioMech Health itself, or third-party
  clinics BioMech Health serves?
- Sequencing: B2C ships first, clinical second (implied by ordering) — confirm.
