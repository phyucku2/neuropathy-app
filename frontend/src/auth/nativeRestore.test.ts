import { beforeEach, describe, expect, it, vi } from 'vitest';

// Local-module mocks — reliable and free of the native plugins' ESM quirks.
vi.mock('./tokenStore', () => ({ primeRefreshToken: vi.fn() }));
vi.mock('./biometric', () => ({ requireBiometricUnlock: vi.fn() }));

import { requireBiometricUnlock } from './biometric';
import { resolveNativeRestore } from './nativeRestore';
import { primeRefreshToken } from './tokenStore';

const primeMock = vi.mocked(primeRefreshToken);
const unlockMock = vi.mocked(requireBiometricUnlock);

describe('resolveNativeRestore (native startup decision, ADR-0024)', () => {
  beforeEach(() => {
    primeMock.mockReset();
    unlockMock.mockReset();
  });

  it('no persisted token → anonymous, and biometrics are never prompted', async () => {
    primeMock.mockResolvedValue(null);
    await expect(resolveNativeRestore()).resolves.toBe('anonymous');
    expect(unlockMock).not.toHaveBeenCalled();
  });

  it('token present + biometric unlock succeeds → restore', async () => {
    primeMock.mockResolvedValue('refresh-token');
    unlockMock.mockResolvedValue(true);
    await expect(resolveNativeRestore()).resolves.toBe('restore');
    expect(unlockMock).toHaveBeenCalledOnce();
  });

  it('token present + biometric unlock denied → anonymous', async () => {
    primeMock.mockResolvedValue('refresh-token');
    unlockMock.mockResolvedValue(false);
    await expect(resolveNativeRestore()).resolves.toBe('anonymous');
  });
});
