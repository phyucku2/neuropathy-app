/**
 * Single source of truth for "are we running inside the native (Capacitor) shell?" (ADR-0024).
 *
 * Centralised in one tiny module so the whole app reads platform the same way AND so tests can
 * reliably mock a local relative module (mocking `@capacitor/core` across the full app import
 * graph is fragile). Returns false on web and in jsdom.
 */

import { Capacitor } from '@capacitor/core';

export function isNativePlatform(): boolean {
  return Capacitor.isNativePlatform();
}
