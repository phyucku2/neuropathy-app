/**
 * Native shell wiring (ADR-0025): status bar, splash screen, and the Android hardware back
 * button. All of it is native-only — on web `initNativeShell` is a no-op, so the browser build
 * and the E2E suite are unaffected.
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
 * Initialize the native shell and return a cleanup that detaches the back-button listener.
 * `goBack` is the app's in-history navigation (injected so this stays framework-agnostic).
 * No-op (and a no-op cleanup) on web.
 */
export async function initNativeShell(goBack: () => void): Promise<() => void> {
  if (!isNativePlatform()) {
    return () => undefined;
  }

  // Dark status-bar content (icons/text) over the app's light header. Cosmetic and safe to
  // tune on-device; never fatal, so a surface that lacks a status bar is ignored.
  try {
    await StatusBar.setStyle({ style: Style.Light });
  } catch {
    // no status bar on this surface — ignore
  }

  const handle = await CapApp.addListener('backButton', ({ canGoBack }) => {
    if (backAction(canGoBack) === 'back') {
      goBack();
    } else {
      void CapApp.exitApp();
    }
  });

  // Reveal the app only once React has mounted and requested init — no white flash.
  try {
    await SplashScreen.hide();
  } catch {
    // splash already gone — ignore
  }

  return () => {
    void handle.remove();
  };
}
