# Launch submission checklist — App Store + Google Play

Cross-store submission runbook for **Neuropathy** (`com.ahwg.neuropathy`, Advanced Health
and Wellness Group). Companion to `play-listing-pack.md` (Play listing detail) and
`play-release-runbook.md` (Play release mechanics). **Preparation material, not legal or
regulatory advice** — the privacy policy and any health claims need counsel review. Items
marked **[verify]** must be re-checked against the shipped build and the live console at
submission time (store flows change).

App facts (from the codebase): app id `com.ahwg.neuropathy` · name **Neuropathy** ·
support `advancedhwg@outlook.com` · version `0.1.0` (versionCode 1) · Android
target/compile SDK 35 · iOS greenfield (compiles via CI build-check; no App Store record
or signed build yet).

---

## 0. Gating items (block BOTH stores)

- [ ] **Disclosures match the shipped app.** As of ADR-0049, the daily check-in collects
      **pain + numbness symptoms by default**, and the app also collects patient-entered
      medications and between-visit events; optional wearable, imported clinician notes, and
      food logging exist (off by default). The in-app Privacy summary, the hosted policy, and
      both stores' data forms must list all health data the shipped build can collect.
      *(In-app + policy-draft copy updated to match; the store forms are filled from this.)*
- [ ] **Counsel-reviewed privacy policy live at a public, logged-out-reachable URL.** Draft:
      `docs/legal/privacy-policy-draft.md`. Then set the real URL + `privacy@` contact in
      `frontend/src/features/about/PrivacyPage.tsx` (currently placeholders).
- [ ] **Synthetic demo/review account** that reaches the main screens against the live API.
      Never a real patient login.
- [ ] **Smoke-test a packaged build** (not just the browser): sign-in, a check-in, and
      account deletion.

---

## A. Apple App Store

### The D-U-N-S number — where to change it
You do **not** edit the D-U-N-S at Apple. It is an identifier **issued and owned by Dun &
Bradstreet (D&B)**; Apple only *looks it up* to verify your organization during Developer
Program enrollment. First, confirm what's on file at
<https://developer.apple.com/enroll/duns-lookup/> — that's exactly what Apple verifies against.

- **Case A — wrong D-U-N-S number on the account (or wrong number entered).** Apple-side fix;
  the portal won't self-edit it. Get the correct number from the lookup tool (free; issuance
  can take up to ~5 business days), then open an **Apple Developer Program Support** case at
  <https://developer.apple.com/contact/> → *Membership & Account* → *Enrollment*. Have your
  Apple ID, exact legal entity name, registered address, and the correct D-U-N-S ready. Start
  early — support is not instant.
- **Case B — number is right, but the name/address behind it is wrong.** Fix it at the
  **source (D&B), not Apple**, via **iUpdate** (<https://iupdate.dnb.com/>) or D&B support.
  Allow days–weeks to propagate; Apple re-verifies against the updated record. The legal name
  D&B holds becomes your public **“seller”** name on the App Store, so it must be exactly
  right before enrollment completes. **[verify]**

### Apple track
- [ ] Enroll as an **Organization** (needs the D-U-N-S, legal authority, an entity website,
      ~$99/yr); pass entity verification. **[verify]** seller name is correct before proceeding.
- [ ] Register App ID `com.ahwg.neuropathy`; create the app in **App Store Connect**.
- [ ] Produce a **signed** archive (Mac + Xcode: distribution cert + provisioning profile);
      upload via Xcode Organizer or Transporter. *(CI proves it compiles; it does not produce
      a signed, uploadable build.)*
- [ ] **App Privacy “nutrition labels”** — Health & Fitness data (incl. the new symptom data),
      Contact info (name, email); **not** used for tracking; no ads/analytics SDKs.
- [ ] Screenshots, description, keywords, support URL, privacy-policy URL, age rating —
      non-diagnostic wording only, synthetic data in every screenshot.
- [ ] App Review notes: demo account + non-diagnostic tracking/decision-support framing.
      Submit (review typically ~24–48h+). Optionally push to **TestFlight** in parallel.

---

## B. Google Play

- [ ] Play Console **organization** developer account registered & verified.
- [ ] Create the app; confirm signing (Play App Signing). ⚠️ `applicationId
      com.ahwg.neuropathy` is **permanent** after the first publish.
- [ ] **Data Safety** form from `play-listing-pack.md` §2 (now includes symptoms, meds,
      events; optional wearable/notes/food). Encryption-in-transit = yes; deletion flow shipped
      (`DELETE /auth/me`). **[verify]** whether Play wants a web deletion URL for logged-out users.
- [ ] **Health apps declaration** (non-diagnostic; 18+), content rating (IARC), privacy-policy
      URL + support email.
- [ ] Signed **AAB** with `versionCode` bumped; listing assets (icon 512², feature graphic
      1024×500, ≥4 phone screenshots — all synthetic data).
- [ ] Upload to **Internal testing** (≤100 testers).
- [ ] **Production access:** new developer accounts must run **closed testing (12+ testers,
      14 days)** before production unlocks. **[verify]** whether this applies to the org
      account — if so, production is not same-day; internal testing still is.

---

## Suggested order for the day
1. **Kick off the D-U-N-S fix** (Case A → Apple Support case; Case B → D&B iUpdate) — the long pole.
2. **Fix + publish the disclosures** (in-app copy, hosted policy URL, both data forms).
3. **Android in parallel** — Play app record, forms, signed AAB to Internal testing.
4. **Apple as enrollment clears** — App ID, App Store Connect record, privacy labels + metadata.
5. **Signed builds** — AAB to Play internal test; iOS archive to TestFlight.
6. **Submit for review** once accounts, forms, and the demo account are in place.

> Reality check: internal/TestFlight builds and the paperwork are a-day-achievable if the
> accounts are ready. Public production release usually is not same-day (Apple review
> ~24–48h+; Play's new-account testing window). Getting to **submitted** is the realistic win.
