# Caregiver push notifications (ADR-0047 Phase B2)

Native-only (Android/FCM) push that tells a caregiver a new alert was raised. The
notification **content is minted server-side from fixed templates** and is **PHI-free by
contract** — the client only ever handles the opaque FCM registration token (a routing
identifier, never health data).

## Architecture

- **Backend** owns delivery: FCM HTTP v1 sender, the `caregiver_push_token` store, and an
  emit-on-commit fan-out that pushes to a caregiver's devices only **after** a newly-raised
  alert row is committed. See `backend/app/services/push.py`,
  `backend/app/services/caregiver_push_dispatch.py`, and the `POST/DELETE
  /caregiver/push-tokens` routes.
- **Frontend** owns registration only, native-only:
  - `frontend/src/native/caregiverPush.ts` — the injectable seam: permission → register →
    POST token (`/caregiver/push-tokens`); a Firebase token refresh re-POSTs (an idempotent
    upsert server-side); logout / permission-off DELETEs the token.
  - `frontend/src/native/useCaregiverPush.ts` — the React hook, mounted in the caregiver
    area (`CaregiverArea` in `App.tsx`). Registers for a signed-in **caregiver on a native
    platform** and deregisters on unmount.
  - `frontend/src/api/endpoints.ts` — `registerCaregiverPushToken` /
    `deregisterCaregiverPushToken`.
- **Web is a NO-OP.** Everything gates on `isNativePlatform()`, so the browser build and the
  Playwright + unit suites are unchanged: the plugin is never touched and no request is made.

## CI-safe Android build (no `google-services.json` required)

The mobile CI job runs `npm ci` → `npx cap sync android` → `./gradlew assembleDebug` with
**no `google-services.json` present**, and stays green. Why:

1. `cap sync` registers `@capacitor/push-notifications` as a Gradle module
   (`android/capacitor.settings.gradle`, `android/app/capacitor.build.gradle` — both
   generated). Its `build.gradle` pulls
   `com.google.firebase:firebase-messaging:$firebaseMessagingVersion`.
2. `firebase-messaging` is an ordinary AAR dependency — it **compiles** with no
   `google-services.json`. That file is consumed only at **build time by the
   `com.google.gms.google-services` Gradle plugin**, to generate the `google_app_id` string
   resource, and only at **runtime by `FirebaseApp.initializeApp`**.
3. The google-services plugin is applied **conditionally** in `android/app/build.gradle`:

   ```gradle
   try {
       def servicesJSON = file('google-services.json')
       if (servicesJSON.text) {
           apply plugin: 'com.google.gms.google-services'
       }
   } catch(Exception e) {
       logger.info("google-services.json not found, google-services plugin not applied. Push Notifications won't work")
   }
   ```

   With the file absent, the plugin is simply **not applied** — the `try/catch` logs and
   continues; assembly proceeds.
4. `assembleDebug` only **compiles and packages** — it never launches the app, so the
   runtime `FirebaseApp` init that would need `google_app_id` is never exercised. Result:
   **green** with no credential in the repo.

Real / release builds place `google-services.json` at `frontend/android/app/` → the plugin
applies → the `google_app_id` resource is generated → push works.

`android/variables.gradle` pins `firebaseMessagingVersion = '23.4.1'` so CI and release
builds compile a fixed version rather than the plugin's floating default.

## Security: never commit `google-services.json`

`frontend/android/app/google-services.json` carries a Firebase/Google API key (`AIza…`) and
is **gitignored** (`frontend/android/.gitignore`). It is placed locally for release builds
and injected at build time only — never committed, never printed. The backend FCM
service-account JSON is injected at **runtime** as a secret (`FCM_CREDENTIALS_JSON` or
`GOOGLE_APPLICATION_CREDENTIALS`) — see `backend/.env.example`.

## Go-live steps (owner-owned)

1. Create the Firebase project + Android app (`com.ahwg.neuropathy`); download the real
   `google-services.json` and place it at `frontend/android/app/` (gitignored) for release
   builds.
2. Deploy the backend with the FCM service-account JSON injected as a secret
   (`FCM_CREDENTIALS_JSON`, or `GOOGLE_APPLICATION_CREDENTIALS` path), scope
   `firebase.messaging`.
3. Set `CAREGIVER_PUSH_ENABLED=true`.
4. Native rebuild: `npx cap sync android` + a signed release build so the push plugin and
   the google-services resources ship.
5. On-device test: a caregiver signs in on Android, grants permission, and the token
   registers; trigger a new alert → the device receives the PHI-free push; verify
   `UNREGISTERED` cleanup after uninstall.
