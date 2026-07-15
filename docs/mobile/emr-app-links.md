# Android App Links for the EMR OAuth return path (ADR-0028)

How the patient gets **back into the Android app** after approving the EMR connection
in the system browser (the SMART OAuth round trip — runbook §3, Option A). The code
half shipped with ADR-0028; this page documents the **owner-side** pieces that need
the deployed app origin and the release keystore, which do not exist yet.

## How the return path works (shipped)

1. The connect UI opens the EMR's authorize URL in the **system browser**
   (`@capacitor/browser` → Custom Tab). Never the in-app WebView — EMRs and identity
   providers block WebView OAuth (RFC 8252).
2. The patient approves at the EMR; the EMR redirects to
   `https://<app-origin>/emr/callback?code=…&state=…`.
3. Android routes that URL to the app — **App Links** (preferred, verified against
   `assetlinks.json`) or the **custom-scheme fallback** (`com.ahwg.neuropathy://…`,
   intent-filter already in `AndroidManifest.xml`).
4. The `appUrlOpen` handler (`frontend/src/native/nativeShell.ts`) parses the URL and
   routes the SPA to its path+query — the same authenticated `/emr/callback` relay
   route the web uses, which forwards `code`+`state` to the bearer-only backend
   callback.

On devices where the app is not installed or App Links verification fails, the same
https URL simply opens in the browser — the web relay route handles it there, so the
flow degrades gracefully instead of dead-ending.

## Owner-side requirement 1: `assetlinks.json` at the app origin

App Links only verify if the app's web origin serves a digital asset link binding the
domain to the app's **release signing certificate**:

- **URL (exact):** `https://<app-origin>/.well-known/assetlinks.json`
- **Served as:** `Content-Type: application/json`, HTTP 200, no redirect, publicly
  readable.

Template (replace the placeholder fingerprint):

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.ahwg.neuropathy",
      "sha256_cert_fingerprints": [
        "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"
      ]
    }
  }
]
```

- The fingerprint is the **RELEASE** certificate's SHA-256 — it can only be produced
  once the release keystore exists (ADR-0026):
  `keytool -list -v -keystore <release-keystore> | grep SHA256`.
  With **Play App Signing**, use the *app signing key* certificate shown in Play
  Console (Release → Setup → App signing) — that is the certificate on the delivered
  APK, not the upload key. Both can be listed (JSON array) to cover local
  release-keystore installs too.
- Debug builds verify only if the debug certificate's fingerprint is *also* listed —
  optional, dev convenience only; never ship a debug fingerprint alone.

## Owner-side requirement 2: the App Links intent-filter

The https intent-filter needs the real deployed origin, so it is **not** committed yet
(a placeholder host would fail verification and mislead). When the origin exists, add
to `frontend/android/app/src/main/AndroidManifest.xml` inside `MainActivity`:

```xml
<intent-filter android:autoVerify="true">
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="https" android:host="APP_ORIGIN_HOST_PLACEHOLDER" />
</intent-filter>
```

`android:autoVerify="true"` makes Android check `assetlinks.json` at install time —
verified links open the app directly, with no chooser dialog and no way for another
app to hijack the URL.

Verify on a device:
`adb shell pm get-app-links com.ahwg.neuropathy` (expect `verified` for the domain).

## The custom-scheme fallback (shipped)

`AndroidManifest.xml` already carries the `com.ahwg.neuropathy` scheme intent-filter
(the value in `res/values/strings.xml` `custom_url_scheme`). It is the fallback for
devices where App Links verification fails, per the runbook: Oracle Health explicitly
accepts custom schemes for native apps ("something must follow `://`", e.g.
`com.ahwg.neuropathy://emr/callback`), and our `appUrlOpen` handler routes
`com.ahwg.neuropathy://emr/callback?…` identically to the https form. Note custom
schemes are user-hijackable by other apps claiming the same scheme (the OS shows a
chooser) — that is why App Links are the preferred path. With the current backend-https
redirect architecture (runbook §3 Option A), vendors never see either form — only the
final browser→app hop uses them.

## Verification boundary (honest)

- **Verified here:** the `appUrlOpen` routing logic (unit tests over `appUrlPath` +
  the listener wiring via the platform mock) and that the manifest compiles (CI
  `mobile` job).
- **NOT verifiable here:** actual App Links verification and the browser→app hop —
  they need a deployed https origin serving `assetlinks.json`, a release-signed
  build, and a device. Owner-side, after deployment + keystore (see the runbook
  checklist).
- **Known caveat to test explicitly in the sandbox smoke:** some browsers keep a
  server-issued HTTP *redirect* inside the browser instead of firing the App Link
  (App Links reliably intercept link *clicks*/intents; a 302 chain inside a Custom Tab
  may not leave the browser). If the sandbox smoke shows the redirect staying in the
  browser, the fixes are (i) an interstitial "Return to app" page at
  `/emr/callback` on the web origin whose tap is a normal link (App Links then fire),
  or (ii) making the final hop the custom scheme (`com.ahwg.neuropathy://emr/callback?…`),
  which the shipped handler already routes. Either is a small follow-up, decided on
  observed sandbox behavior rather than guessed now.
