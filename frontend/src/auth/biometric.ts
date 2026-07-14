/**
 * Biometric unlock gate for a persisted native session (ADR-0024).
 *
 * On native, a refresh token restored from the Keystore is only revealed after the user passes a
 * biometric (or device-credential) check — a second factor on top of at-rest encryption, so a
 * stolen-but-unlocked-later device does not hand over an authenticated session.
 *
 * Policy:
 *   - Web has no biometric layer → always allowed (`true`); the whole path is native-only.
 *   - If the device has NO enrolled biometry, we do not lock the user out of their own
 *     device-secured session (`true`) — the Keystore already protects the token at rest, and the
 *     app should not be less usable than the platform it runs on.
 *   - Only an ACTUAL failed or cancelled biometric prompt denies (`false`), which sends the user
 *     back to password sign-in for this launch. The token is left in the Keystore so a fat-finger
 *     can be retried on the next launch; an explicit logout is what clears it.
 */

import { BiometricAuth } from '@aparajita/capacitor-biometric-auth';
import { isNativePlatform } from './platform';

export async function requireBiometricUnlock(): Promise<boolean> {
  if (!isNativePlatform()) {
    return true;
  }

  let available = false;
  try {
    const info = await BiometricAuth.checkBiometry();
    available = info.isAvailable;
  } catch {
    available = false;
  }
  if (!available) {
    return true;
  }

  try {
    await BiometricAuth.authenticate({
      reason: 'Unlock your health data',
      androidTitle: 'Unlock',
      androidSubtitle: "Confirm it's you to open your health data",
      cancelTitle: 'Use password instead',
      // Allow the device PIN/pattern/password as a fallback so a temporary biometric failure
      // (wet finger, sensor glitch) does not strand a user who can still prove device ownership.
      allowDeviceCredential: true,
    });
    return true;
  } catch {
    return false;
  }
}
