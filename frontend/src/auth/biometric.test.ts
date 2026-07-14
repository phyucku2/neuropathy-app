import { beforeEach, describe, expect, it, vi } from 'vitest';

const isNativePlatform = vi.fn(() => false);
vi.mock('./platform', () => ({
  isNativePlatform: () => isNativePlatform(),
}));

const checkBiometry = vi.fn();
const authenticate = vi.fn();
vi.mock('@aparajita/capacitor-biometric-auth', () => ({
  BiometricAuth: {
    checkBiometry: () => checkBiometry(),
    authenticate: (options: unknown) => authenticate(options),
  },
}));

import { requireBiometricUnlock } from './biometric';

describe('requireBiometricUnlock', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    isNativePlatform.mockReturnValue(false);
  });

  it('web: allowed without ever invoking the biometric plugin', async () => {
    await expect(requireBiometricUnlock()).resolves.toBe(true);
    expect(checkBiometry).not.toHaveBeenCalled();
    expect(authenticate).not.toHaveBeenCalled();
  });

  it('native + no enrolled biometry: allowed (never locks the user out of their device session)', async () => {
    isNativePlatform.mockReturnValue(true);
    checkBiometry.mockResolvedValue({ isAvailable: false });
    await expect(requireBiometricUnlock()).resolves.toBe(true);
    expect(authenticate).not.toHaveBeenCalled();
  });

  it('native + available + successful prompt: allowed', async () => {
    isNativePlatform.mockReturnValue(true);
    checkBiometry.mockResolvedValue({ isAvailable: true });
    authenticate.mockResolvedValue(undefined);
    await expect(requireBiometricUnlock()).resolves.toBe(true);
    expect(authenticate).toHaveBeenCalledOnce();
  });

  it('native + available + failed/cancelled prompt: denied', async () => {
    isNativePlatform.mockReturnValue(true);
    checkBiometry.mockResolvedValue({ isAvailable: true });
    authenticate.mockRejectedValue(new Error('user cancelled'));
    await expect(requireBiometricUnlock()).resolves.toBe(false);
  });

  it('native + checkBiometry throws: treated as unavailable, allowed', async () => {
    isNativePlatform.mockReturnValue(true);
    checkBiometry.mockRejectedValue(new Error('no native bridge'));
    await expect(requireBiometricUnlock()).resolves.toBe(true);
    expect(authenticate).not.toHaveBeenCalled();
  });
});
