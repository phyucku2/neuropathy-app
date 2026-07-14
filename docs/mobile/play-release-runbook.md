# Google Play release runbook (Android)

Operator guide for taking the Android app from a green build to the Play Store. Written for
the app owner (the LLC's Play Console organization account). The repo never contains a
keystore, password, or Play credential — every secret lives on your machine, in Play Console,
or in GitHub Actions secrets. (ADR-0026; app id `com.biomech.neuropathy` — **permanent after
the first upload**, confirm before Step 4.)

## 0. One-time: Play Console organization account

1. Create the account at <https://play.google.com/console/signup> → **Organization** →
   your LLC. You will need: the LLC's **D-U-N-S number**, legal name/address, a website,
   and a support email. $25 one-time fee. Identity + DUNS verification can take days —
   start it early.
2. In **Users & permissions**, add any additional admins.
3. No Apple/Google credential is ever needed by the development tooling — do not share them.

## 1. One-time: generate the UPLOAD keystore (your machine, never committed)

```bash
keytool -genkeypair -v \
  -keystore ~/neuropathy-upload.keystore \
  -alias neuropathy-upload \
  -keyalg RSA -keysize 4096 -validity 9125 \
  -storepass '<STRONG-PASSWORD>' -keypass '<STRONG-PASSWORD>'
```

- Store the keystore + password in your password manager, and keep an offline backup.
- This is only the **upload** key: with **Play App Signing** (Step 4) Google holds the real
  app-signing key, so a lost upload key is recoverable via a Play support reset — but treat
  it as a production secret anyway.
- The repo's `.gitignore` blocks `*.keystore` / `keystore*.properties` and CI's secret scan
  matches `storePassword=`/`keyPassword=` — but simply never copy it into the repo tree.

## 2. Local signed build (optional — CI can do this instead)

Create `frontend/android/keystore.properties` (git-ignored):

```properties
storeFile=/absolute/path/to/neuropathy-upload.keystore
storePassword=<STRONG-PASSWORD>
keyAlias=neuropathy-upload
keyPassword=<STRONG-PASSWORD>
```

Then:

```bash
cd frontend && npm ci && npm run build && npx cap sync android
cd android && ./gradlew bundleRelease
# → app/build/outputs/bundle/release/app-release.aab
```

## 3. CI signed build (recommended)

Add four repo secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | `base64 -w0 ~/neuropathy-upload.keystore` |
| `ANDROID_KEYSTORE_PASSWORD` | the store password |
| `ANDROID_KEY_ALIAS` | `neuropathy-upload` |
| `ANDROID_KEY_PASSWORD` | the key password |

Run the **Release — Android AAB** workflow (Actions tab → workflow_dispatch). It builds the
web bundle, syncs, signs with the upload key, shreds the keystore material, and uploads the
`.aab` as an artifact. Without the secrets it still runs and produces an **unsigned** smoke
AAB (not uploadable).

## 4. First Play upload

1. Play Console → **Create app** (name: Neuropathy — or the go-to-market name, category:
   Medical, free).
2. Accept **Play App Signing** (default) — Google generates and escrows the app-signing key;
   your uploads authenticate with the upload key from Step 1.
3. Upload the `.aab` to **Internal testing** first. Internal testing needs only a tester
   list (up to 100 emails) and has the lightest review.
4. Every subsequent upload must bump `versionCode` in `frontend/android/app/build.gradle`
   (bump `versionName` when the app version changes; it tracks `package.json`).

## 5. Store listing requirements (health app)

Work through `docs/mobile/play-listing-pack.md` — it drafts the Data Safety form answers
from the app's actual data flows, the health-apps declaration, and the listing checklist.
Two hard gates to know about:

- **Privacy policy URL is mandatory** (health app). A draft to adapt is in
  `docs/legal/privacy-policy-draft.md` — it MUST be reviewed by your counsel before
  publication; it is a scaffold, not legal advice.
- **Production release of a real-data health app is gated on the compliance work** in
  `docs/compliance/` (HIPAA validation, BAAs, live backend). Internal testing with
  synthetic/test accounts does not process real PHI and can proceed before that.

## 6. Sequencing reality check

| Track | Needs | Status |
|---|---|---|
| Internal testing (test accounts, synthetic data) | Signed AAB + listing basics + privacy policy URL | Buildable NOW |
| Closed/Open testing | + Data Safety form approved, health declaration | After listing pack |
| Production | + deployed production backend, HIPAA validation + BAAs signed, counsel-approved policy | Gated on compliance work |
