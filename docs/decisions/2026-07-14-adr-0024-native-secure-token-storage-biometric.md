# ADR-0024 — Native secure token storage + biometric unlock

- **Status:** Accepted (Wave 2, portion 2)
- **Date:** 2026-07-14
- **Relates to / extends:** ADR-0015 (web token posture), ADR-0023 (Capacitor, Android-first)

## Context

On web the refresh token lives in `sessionStorage` (ADR-0015: tab-scoped, the documented
XSS tradeoff). Inside the native shell (ADR-0023) that posture is wrong: a phone app is
expected to survive process restarts, and `sessionStorage` is neither durable nor
hardware-protected. A native session should be (a) encrypted at rest and (b) gated by a
biometric check so a persisted session is not revealed just because someone is holding an
unlocked-later device.

The constraint: the web target must not change at all — the same SPA and the same 29-spec
browser E2E suite ship unchanged — and native storage APIs are asynchronous while the
current `getRefreshToken()` is read synchronously in React's initial render.

## Decision

Add a **platform-selected durable backend** for the refresh token and a **biometric gate**
on native restore. The access token stays memory-only on every platform (unchanged).

- **Storage** (`refreshTokenBackend.ts`): `WebBackend` (sessionStorage, unchanged posture)
  vs `NativeBackend` (Android Keystore-backed `EncryptedSharedPreferences` via
  `@aparajita/capacitor-secure-storage`). Selected once by `isNativePlatform()`.
  - `peek()` is a **synchronous** best-effort read: web reads `sessionStorage` directly (so
    the restore-vs-anonymous decision keeps its exact original timing); native returns an
    in-memory mirror that is `null` until `load()` primes it from the Keystore — the native
    restore flow starts in `restoring` and awaits the load, never trusting a native peek.
  - `NativeBackend` takes an injectable `SecureKv` so the Keystore path is unit-tested
    off-device; `clear()` drops the mirror synchronously and fire-and-forgets the durable
    delete (the app cannot use the token even if the async remove is slow/fails); a load
    failure yields `null`, never a stale mirror.
- **Biometric** (`biometric.ts`, `@aparajita/capacitor-biometric-auth`): `requireBiometricUnlock()`
  is a no-op (allow) on web and when no biometry is enrolled (never lock a user out of their
  own device-secured session — the Keystore already protects the token at rest). Only an
  actual failed/cancelled prompt denies; device credential (PIN) is allowed as a fallback.
- **Wiring** (`nativeRestore.ts` → `AuthContext`): `resolveNativeRestore()` = prime the token,
  then (only if present) require unlock → `restore | anonymous`. A denied/cancelled unlock or
  a missing token → anonymous, and the token is **left in the Keystore** for a retry next
  launch (a denied prompt grants no access either way; only explicit logout clears it). The
  decision logic is factored out of React so it is unit-tested directly.

### Platform detection is centralized

`isNativePlatform()` lives in one module (`platform.ts`) so the app reads platform uniformly
and tests mock a single reliable local module rather than `@capacitor/core` across the whole
import graph.

### Dependency compatibility

Both plugins are pinned to their **Capacitor-6** line — secure-storage `^6.0.1`, biometric
`~9.0.0` (the biometric `9.1.x`/`10.x` and secure-storage `7.x`/`8.x` lines target Capacitor 7;
`cap sync` runs clean on the pinned versions). Both are MIT; the production `npm audit` and
license allowlist stay green.

## Verification boundary (honest)

- **Verified here (jsdom + real browser):** the web target is byte-for-byte unregressed —
  145 unit tests + the 29-spec Playwright/Chromium suite pass; the `NativeBackend`,
  `requireBiometricUnlock`, and `resolveNativeRestore` logic are unit-tested via injected /
  locally-mocked seams (the security decision — token-present + unlock → restore; denied →
  anonymous + token kept — is covered directly).
- **Proven by CI:** the plugins compile into the APK (`mobile` job / `gradlew assembleDebug`).
- **User's step (not possible here):** the actual on-device Keystore round-trip and biometric
  prompt — `npx cap run android` on a device with enrolled biometrics. jsdom is never the
  native platform, so the real native calls cannot execute in this environment.

## Alternatives considered

- **`@capacitor/preferences`** — rejected: not encrypted; it is plain SharedPreferences.
- **Encrypt-in-JS then store in Preferences** — rejected: key management in the WebView is
  weaker than delegating to the OS Keystore.
- **Clear the token on a failed biometric prompt** — rejected: a denied prompt grants no
  access anyway, so wiping only punishes a fat-finger; keeping it (Keystore-encrypted) with a
  retry-next-launch is standard and equally safe.
- **Biometric on every foreground** — deferred: this portion gates restore-at-launch; a
  foreground re-lock can be a later refinement.
