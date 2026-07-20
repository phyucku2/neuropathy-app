/**
 * The print seam (ADR-0045): web calls the injected print fn; native is a safe no-op that
 * never throws (the Capacitor webview has no system print dialog). Both branches are unit-locked
 * off-device — jsdom has no real `window.print`, so the real dialog is proven only in Playwright.
 */

import { describe, expect, it, vi } from 'vitest';
import { printHandout } from './printHandout';

describe('printHandout', () => {
  it('web: calls the injected print function', () => {
    const print = vi.fn();
    printHandout({ isNative: () => false, print });
    expect(print).toHaveBeenCalledTimes(1);
  });

  it('native: routes to a no-op and never calls print or throws', () => {
    const print = vi.fn();
    expect(() => {
      printHandout({ isNative: () => true, print });
    }).not.toThrow();
    expect(print).not.toHaveBeenCalled();
  });

  it('falls back to window.print on web when print is not injected (covers the default dep)', () => {
    const spy = vi.fn();
    // jsdom leaves window.print undefined; install a spy so the default dep is exercised.
    window.print = spy as unknown as typeof window.print;
    printHandout({ isNative: () => false });
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
