/**
 * The authorize-URL opener (ADR-0028): system browser on native — NEVER the in-app
 * WebView (EMRs block WebView OAuth) — and a full-page redirect on web. The web
 * navigation is injected because jsdom cannot perform real navigations.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../auth/platform', () => ({ isNativePlatform: vi.fn(() => false) }));

const { browserOpen } = vi.hoisted(() => ({ browserOpen: vi.fn() }));
vi.mock('@capacitor/browser', () => ({
  Browser: { open: (options: unknown) => browserOpen(options) },
}));

import { isNativePlatform } from '../auth/platform';
import { openAuthorizeUrl } from './externalBrowser';

const nativeMock = vi.mocked(isNativePlatform);

describe('openAuthorizeUrl', () => {
  beforeEach(() => {
    nativeMock.mockReset();
    browserOpen.mockReset().mockResolvedValue(undefined);
  });

  it('web: performs a full-page redirect (the standard SMART pattern), not a plugin call', async () => {
    nativeMock.mockReturnValue(false);
    const assign = vi.fn();
    await openAuthorizeUrl('https://ehr.example/oauth/authorize?state=xyz', assign);
    expect(assign).toHaveBeenCalledWith('https://ehr.example/oauth/authorize?state=xyz');
    expect(browserOpen).not.toHaveBeenCalled();
  });

  it('native: opens the SYSTEM browser (Custom Tab) — never navigates the WebView', async () => {
    nativeMock.mockReturnValue(true);
    const assign = vi.fn();
    await openAuthorizeUrl('https://ehr.example/oauth/authorize?state=xyz', assign);
    expect(browserOpen).toHaveBeenCalledWith({
      url: 'https://ehr.example/oauth/authorize?state=xyz',
    });
    expect(assign).not.toHaveBeenCalled();
  });
});
