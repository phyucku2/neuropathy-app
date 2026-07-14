import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../auth/platform', () => ({ isNativePlatform: vi.fn(() => false) }));

import { isNativePlatform } from '../auth/platform';
import { backAction, initNativeShell } from './nativeShell';

const nativeMock = vi.mocked(isNativePlatform);

describe('backAction (Android hardware back)', () => {
  it('navigates back when the WebView has in-app history', () => {
    expect(backAction(true)).toBe('back');
  });

  it('exits the app at a root screen with no history (never traps the user)', () => {
    expect(backAction(false)).toBe('exit');
  });
});

describe('initNativeShell', () => {
  beforeEach(() => nativeMock.mockReset());

  it('is a no-op on web and returns a no-op cleanup (never invokes goBack or native plugins)', async () => {
    nativeMock.mockReturnValue(false);
    const goBack = vi.fn();
    const cleanup = await initNativeShell(goBack);
    expect(goBack).not.toHaveBeenCalled();
    expect(() => cleanup()).not.toThrow();
  });
});
