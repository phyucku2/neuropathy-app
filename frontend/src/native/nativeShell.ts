/**
 * Native shell wiring (ADR-0025, extended by ADR-0028): status bar, splash screen, the
 * Android hardware back button, and the incoming-URL handler that returns the patient
 * from the system browser's SMART OAuth redirect. All of it is native-only — on web
 * `initNativeShell` is a no-op, so the browser build and the E2E suite are unaffected.
 */

import { App as CapApp } from '@capacitor/app';
import { SplashScreen } from '@capacitor/splash-screen';
import { Style, StatusBar } from '@capacitor/status-bar';
import { isNativePlatform } from '../auth/platform';

/**
 * What the Android hardware back button should do. The WebView reports whether it can go back
 * (there is in-app history); if so we navigate back, otherwise back at a root screen exits the
 * app (the platform-expected behavior) rather than trapping the user.
 */
export function backAction(canGoBack: boolean): 'back' | 'exit' {
  return canGoBack ? 'back' : 'exit';
}

/**
 * The SPA path (+query) an incoming deep-link URL should route to, or null when the
 * URL is unparseable (ADR-0028). Pure, so the routing decision is unit-locked.
 *
 * Two shapes arrive here (docs/mobile/emr-app-links.md):
 * - Android App Links — `https://<app-origin>/emr/callback?code=..&state=..` (the OS
 *   verified the origin against assetlinks.json before handing it to us): route to the
 *   URL's own path+query.
 * - Custom-scheme fallback — `com.ahwg.neuropathy://emr/callback?..`: the URL "host"
 *   is the first path segment (something must follow `://`, per the vendors' rules).
 *
 * Routing is INTERNAL only (React Router), so an unexpected path is harmless — the
 * router's catch-all redirects home; nothing here can navigate off-app.
 */
export function appUrlPath(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
    return `${parsed.pathname}${parsed.search}`;
  }
  if (parsed.host === '') {
    return null;
  }
  return `/${parsed.host}${parsed.pathname}${parsed.search}`;
}

/**
 * Initialize the native shell and return a cleanup that detaches the listeners.
 * `goBack` (hardware back) and `navigateTo` (incoming deep links, e.g. the SMART
 * OAuth return) are the app's router actions, injected so this stays
 * framework-agnostic and unit-testable (ADR-0024 seam lesson).
 * No-op (and a no-op cleanup) on web.
 */
export async function initNativeShell(
  goBack: () => void,
  navigateTo: (path: string) => void,
): Promise<() => void> {
  if (!isNativePlatform()) {
    return () => undefined;
  }

  // LIGHT status-bar content (Capacitor Style.Dark = "light text for dark backgrounds"):
  // the OS status bar overlays the header's dark navy gradient (--gradient-header), whose
  // own text is white. Cosmetic and safe to tune on-device; never fatal, so a surface that
  // lacks a status bar is ignored.
  try {
    await StatusBar.setStyle({ style: Style.Dark });
  } catch {
    // no status bar on this surface — ignore
  }

  // Reveal the app FIRST — with launchAutoHide:false the app owns dismissing the splash, so
  // hide() must not sit behind any await that could reject (a stuck splash is a total hang).
  try {
    await SplashScreen.hide();
  } catch {
    // splash already gone — ignore
  }

  const cleanups: (() => void)[] = [];

  // Incoming URLs (ADR-0028): the EMR's OAuth redirect re-enters the app as an App
  // Link (or the custom-scheme fallback); route the SPA to its path+query so the
  // /emr/callback relay handles it exactly as on web.
  try {
    const urlHandle = await CapApp.addListener('appUrlOpen', ({ url }) => {
      const path = appUrlPath(url);
      if (path !== null) {
        navigateTo(path);
      }
    });
    cleanups.push(() => {
      void urlHandle.remove();
    });
  } catch {
    // Registration failed: deep links fall back to a cold open of the app. Degraded
    // but never fatal.
  }

  try {
    const backHandle = await CapApp.addListener('backButton', ({ canGoBack }) => {
      if (backAction(canGoBack) === 'back') {
        goBack();
      } else {
        void CapApp.exitApp();
      }
    });
    cleanups.push(() => {
      void backHandle.remove();
    });
  } catch {
    // Listener registration failed: the OS default back behavior applies. Degraded but
    // never fatal — and the splash is already hidden above.
  }

  return () => {
    for (const cleanup of cleanups) {
      cleanup();
    }
  };
}
