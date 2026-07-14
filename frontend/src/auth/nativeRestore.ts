/**
 * Native startup decision (ADR-0024), factored out of AuthContext so the security-critical
 * logic is unit-testable without React or the native plugins.
 *
 * Loads the durable refresh token from the Keystore, then — only if one exists — requires a
 * biometric unlock. Returns whether the persisted session should be restored.
 */

import { requireBiometricUnlock } from './biometric';
import { primeRefreshToken } from './tokenStore';

export type NativeRestoreDecision = 'restore' | 'anonymous';

export async function resolveNativeRestore(): Promise<NativeRestoreDecision> {
  const token = await primeRefreshToken();
  if (token === null) {
    // No persisted session — nothing to unlock, go straight to anonymous.
    return 'anonymous';
  }
  const unlocked = await requireBiometricUnlock();
  return unlocked ? 'restore' : 'anonymous';
}
