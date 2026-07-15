import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../auth/platform', () => ({ isNativePlatform: vi.fn(() => false) }));

const { setStyle, addListener, exitApp, hide, removeListener } = vi.hoisted(() => ({
  setStyle: vi.fn(),
  addListener: vi.fn(),
  exitApp: vi.fn(),
  hide: vi.fn(),
  removeListener: vi.fn(),
}));
vi.mock('@capacitor/status-bar', () => ({
  StatusBar: { setStyle: (o: unknown) => setStyle(o) },
  // Mirror the real enum contract (definitions.d.ts): Style.Dark = light text for DARK
  // backgrounds, Style.Light = dark text for light backgrounds.
  Style: { Dark: 'DARK', Light: 'LIGHT' },
}));
vi.mock('@capacitor/splash-screen', () => ({
  SplashScreen: { hide: () => hide() },
}));
vi.mock('@capacitor/app', () => ({
  App: {
    addListener: (event: string, cb: unknown) => addListener(event, cb),
    exitApp: () => exitApp(),
  },
}));

import { isNativePlatform } from '../auth/platform';
import { appUrlPath, backAction, initNativeShell } from './nativeShell';

const nativeMock = vi.mocked(isNativePlatform);

describe('backAction (Android hardware back)', () => {
  it('navigates back when the WebView has in-app history', () => {
    expect(backAction(true)).toBe('back');
  });

  it('exits the app at a root screen with no history (never traps the user)', () => {
    expect(backAction(false)).toBe('exit');
  });
});

describe('appUrlPath (incoming deep links — ADR-0028)', () => {
  it('routes an App-Links https URL to its own path+query', () => {
    expect(appUrlPath('https://app.example.org/emr/callback?code=abc&state=xyz')).toBe(
      '/emr/callback?code=abc&state=xyz',
    );
  });

  it('routes the custom-scheme fallback (host = first path segment)', () => {
    expect(appUrlPath('com.ahwg.neuropathy://emr/callback?code=abc&state=xyz')).toBe(
      '/emr/callback?code=abc&state=xyz',
    );
  });

  it('still routes an allowlisted path from an unexpected https host (Android only delivers verified hosts; the relay state check guards the rest)', () => {
    // The host is deliberately NOT checked in appUrlPath: App Links are only handed
    // to the app after the OS verified the host against assetlinks.json, and the
    // /emr/callback relay refuses any state this app did not start. The PATH
    // allowlist is the layer this function owns.
    expect(appUrlPath('https://anything.example.net/emr/callback?code=abc&state=xyz')).toBe(
      '/emr/callback?code=abc&state=xyz',
    );
  });

  it('ignores non-allowlisted paths — arbitrary-route deep links never steer the SPA', () => {
    expect(appUrlPath('https://anything/settings')).toBeNull();
    expect(appUrlPath('https://app.example.org/emr/callbackevil?x=1')).toBeNull(); // prefix, not a subpath
    expect(appUrlPath('https://app.example.org')).toBeNull(); // origin-only: not allowlisted either
    expect(appUrlPath('com.ahwg.neuropathy://settings')).toBeNull(); // custom scheme too
  });

  it('routes an allowlisted subpath (query preserved)', () => {
    expect(appUrlPath('https://app.example.org/emr/callback/extra?code=abc')).toBe(
      '/emr/callback/extra?code=abc',
    );
  });

  it('returns null for an unparseable URL or a bare scheme', () => {
    expect(appUrlPath('not a url')).toBeNull();
    expect(appUrlPath('com.ahwg.neuropathy://')).toBeNull();
  });
});

describe('initNativeShell', () => {
  beforeEach(() => {
    nativeMock.mockReset();
    setStyle.mockReset().mockResolvedValue(undefined);
    hide.mockReset().mockResolvedValue(undefined);
    exitApp.mockReset().mockResolvedValue(undefined);
    addListener.mockReset().mockResolvedValue({ remove: () => removeListener() });
    removeListener.mockReset();
  });

  it('is a no-op on web and returns a no-op cleanup (never invokes goBack or native plugins)', async () => {
    nativeMock.mockReturnValue(false);
    const goBack = vi.fn();
    const cleanup = await initNativeShell(goBack, vi.fn());
    expect(goBack).not.toHaveBeenCalled();
    expect(setStyle).not.toHaveBeenCalled();
    expect(hide).not.toHaveBeenCalled();
    expect(addListener).not.toHaveBeenCalled();
    expect(() => cleanup()).not.toThrow();
  });

  it('native: light status-bar content over the dark header, splash hidden, back listener wired', async () => {
    nativeMock.mockReturnValue(true);
    const goBack = vi.fn();
    const cleanup = await initNativeShell(goBack, vi.fn());
    // Style.Dark = LIGHT text for the app's DARK navy header (the enum names are inverted
    // relative to intuition — this assertion pins the correct choice).
    expect(setStyle).toHaveBeenCalledWith({ style: 'DARK' });
    expect(hide).toHaveBeenCalledOnce();
    expect(addListener).toHaveBeenCalledWith('backButton', expect.any(Function));
    // Back with history navigates; back at a root exits.
    const cb = addListener.mock.calls.find((call) => call[0] === 'backButton')?.[1] as (e: {
      canGoBack: boolean;
    }) => void;
    cb({ canGoBack: true });
    expect(goBack).toHaveBeenCalledOnce();
    cb({ canGoBack: false });
    expect(exitApp).toHaveBeenCalledOnce();
    // Cleanup detaches BOTH listeners (appUrlOpen + backButton).
    cleanup();
    expect(removeListener).toHaveBeenCalledTimes(2);
  });

  it('native: an incoming OAuth-return URL routes the SPA to the callback relay (ADR-0028)', async () => {
    nativeMock.mockReturnValue(true);
    const navigateTo = vi.fn();
    await initNativeShell(vi.fn(), navigateTo);
    expect(addListener).toHaveBeenCalledWith('appUrlOpen', expect.any(Function));
    const cb = addListener.mock.calls.find((call) => call[0] === 'appUrlOpen')?.[1] as (e: {
      url: string;
    }) => void;
    // App Link (https, OS-verified) — the EMR redirect back into the app.
    cb({ url: 'https://app.example.org/emr/callback?code=abc&state=xyz' });
    expect(navigateTo).toHaveBeenCalledWith('/emr/callback?code=abc&state=xyz');
    // Custom-scheme fallback routes identically.
    cb({ url: 'com.ahwg.neuropathy://emr/callback?code=abc&state=xyz' });
    expect(navigateTo).toHaveBeenCalledWith('/emr/callback?code=abc&state=xyz');
    // An unparseable URL never navigates.
    navigateTo.mockClear();
    cb({ url: '::::' });
    expect(navigateTo).not.toHaveBeenCalled();
  });

  it('native: the splash is hidden even when back-listener registration fails (no permanent hang)', async () => {
    nativeMock.mockReturnValue(true);
    addListener.mockRejectedValue(new Error('bridge failure'));
    const cleanup = await initNativeShell(vi.fn(), vi.fn());
    // launchAutoHide is false, so a stuck splash would be a total hang — hide() must not sit
    // behind the listener await.
    expect(hide).toHaveBeenCalledOnce();
    expect(() => cleanup()).not.toThrow();
  });

  it('native: a status-bar failure is non-fatal — splash still hides, listener still wires', async () => {
    nativeMock.mockReturnValue(true);
    setStyle.mockRejectedValue(new Error('no status bar'));
    await initNativeShell(vi.fn(), vi.fn());
    expect(hide).toHaveBeenCalledOnce();
    expect(addListener).toHaveBeenCalledWith('backButton', expect.any(Function));
  });
});
