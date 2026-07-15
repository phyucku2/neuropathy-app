/**
 * Opening the SMART authorize URL (ADR-0028), platform-selected:
 *
 * - Web: a full-page redirect (`window.location.assign`) — the standard SMART pattern.
 *   The EMR redirects back to this origin's /emr/callback in the same tab, so the
 *   sessionStorage pending state and refresh token survive the round trip.
 * - Native: the SYSTEM browser via the official `@capacitor/browser` plugin (a Custom
 *   Tab on Android) — NEVER the in-app WebView: EMRs and identity providers block
 *   WebView OAuth (RFC 8252), and the system browser keeps the patient's portal
 *   session/password manager available. The EMR's redirect then re-enters the app
 *   through the App-Links / custom-scheme handler (nativeShell's appUrlOpen).
 *
 * The web navigation is injectable (`assign`) because jsdom cannot perform real
 * navigations — tests pass a spy; callers use the default (ADR-0024 seam lesson).
 */

import { Browser } from '@capacitor/browser';
import { isNativePlatform } from '../auth/platform';

function assignLocation(url: string): void {
  window.location.assign(url);
}

export async function openAuthorizeUrl(
  url: string,
  assign: (url: string) => void = assignLocation,
): Promise<void> {
  if (isNativePlatform()) {
    await Browser.open({ url });
  } else {
    assign(url);
  }
}
