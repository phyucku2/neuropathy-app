/**
 * Platform-selected DURABLE store for the refresh token (ADR-0024).
 *
 * - Web: `sessionStorage` — tab-scoped, synchronous, exactly the ADR-0015 posture. Unchanged.
 * - Native (Android/iOS): the OS secure store — Android Keystore-backed EncryptedSharedPreferences
 *   via `@aparajita/capacitor-secure-storage`. Survives app restarts and is hardware-protected at
 *   rest, which `sessionStorage` cannot be on a device.
 *
 * The ACCESS token is never durably stored on any platform (memory only — see tokenStore.ts).
 *
 * `peek()` is a SYNCHRONOUS best-effort read for the very first render:
 *   - web reads `sessionStorage` directly, so the restore-vs-anonymous decision is made with the
 *     exact same timing as before native support existed.
 *   - native returns an in-memory mirror, which is `null` until `load()` has primed it from the
 *     Keystore. The native restore flow (AuthContext) therefore starts in `restoring` and awaits
 *     `load()` before deciding — it never trusts a synchronous native peek.
 */

import { SecureStorage } from '@aparajita/capacitor-secure-storage';
import { isNativePlatform } from './platform';

export const REFRESH_TOKEN_KEY = 'neuropathy.refresh_token';

export interface RefreshTokenBackend {
  /** Read the durable token and (native) prime the sync mirror. */
  load(): Promise<string | null>;
  /** Persist the token durably. */
  save(token: string): Promise<void>;
  /** Drop the token from the sync layer immediately + best-effort durable delete. */
  clear(): void;
  /** Synchronous best-effort read (see module doc). */
  peek(): string | null;
}

/** The subset of the secure-store plugin NativeBackend needs, injected so it can be unit-tested
 * without the native module (which only truly functions on a device). */
export interface SecureKv {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  remove(key: string): Promise<boolean>;
}

const keystoreKv: SecureKv = {
  getItem: (key) => SecureStorage.getItem(key),
  setItem: (key, value) => SecureStorage.setItem(key, value),
  remove: (key) => SecureStorage.remove(key),
};

export class WebBackend implements RefreshTokenBackend {
  async load(): Promise<string | null> {
    return this.peek();
  }

  async save(token: string): Promise<void> {
    sessionStorage.setItem(REFRESH_TOKEN_KEY, token);
  }

  clear(): void {
    sessionStorage.removeItem(REFRESH_TOKEN_KEY);
  }

  peek(): string | null {
    return sessionStorage.getItem(REFRESH_TOKEN_KEY);
  }
}

export class NativeBackend implements RefreshTokenBackend {
  private mirror: string | null = null;

  constructor(private readonly kv: SecureKv = keystoreKv) {}

  async load(): Promise<string | null> {
    try {
      this.mirror = await this.kv.getItem(REFRESH_TOKEN_KEY);
    } catch {
      // A read failure (corrupt entry, keystore reset) must never leave a stale value in the
      // mirror — treat it as "no session" and let the user re-authenticate.
      this.mirror = null;
    }
    return this.mirror;
  }

  async save(token: string): Promise<void> {
    this.mirror = token;
    await this.kv.setItem(REFRESH_TOKEN_KEY, token);
  }

  clear(): void {
    // Clear the mirror synchronously so the app cannot use the token even if the async durable
    // delete is slow or fails; then fire-and-forget the durable removal.
    this.mirror = null;
    void this.kv.remove(REFRESH_TOKEN_KEY).catch(() => undefined);
  }

  peek(): string | null {
    return this.mirror;
  }
}

/**
 * Chosen once at module load. `isNativePlatform()` is false on web and in jsdom, so unit tests
 * and the browser E2E always exercise the `sessionStorage` backend — the native plugin methods
 * are never called off-device.
 */
export const refreshTokenBackend: RefreshTokenBackend = isNativePlatform()
  ? new NativeBackend()
  : new WebBackend();
