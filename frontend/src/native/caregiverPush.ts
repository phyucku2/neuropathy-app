/**
 * Caregiver push registration (ADR-0047 Phase B2) — a NATIVE-ONLY seam that, for a
 * signed-in caregiver on a native platform, requests notification permission, registers
 * with FCM, obtains the device token, and POSTs it to `/caregiver/push-tokens`; a token
 * refresh re-POSTs (an idempotent upsert server-side); logout / permission-off
 * deregisters it.
 *
 * Follows the reminders/nativeShell seam pattern (ADR-0024/0029): pure logic + an
 * INJECTABLE plugin accessor and injectable endpoint fns, so every decision is
 * unit-testable off-device. jsdom is never the native platform, so on WEB this whole
 * module is a NO-OP — the plugin is never touched and no request is made, which is why
 * the web unit + Playwright suites are UNCHANGED by push.
 *
 * PHI-FREE by construction: the only thing that ever leaves this module is the opaque
 * FCM registration token (a routing identifier, not health data) and the fixed
 * `platform` string. No name/value/code/note is involved on the client side at all —
 * the notification CONTENT is minted server-side from fixed templates (ADR-0047 B2).
 *
 * The last-registered token is mirrored in `localStorage` (like the reminder preference)
 * so deregister-on-logout can name the exact token to delete without re-reading it from
 * the OS. A Firebase token refresh simply overwrites it and re-POSTs.
 */

import { PushNotifications } from '@capacitor/push-notifications';
import type { PermissionStatus, RegistrationError, Token } from '@capacitor/push-notifications';
import type { PluginListenerHandle } from '@capacitor/core';
import { deregisterCaregiverPushToken, registerCaregiverPushToken } from '../api/endpoints';
import type { CaregiverPushPlatform } from '../api/types';
import { isNativePlatform } from '../auth/platform';

/** localStorage key, following the token store / reminder `neuropathy.*` naming. */
export const CAREGIVER_PUSH_TOKEN_KEY = 'neuropathy.caregiver_push_token';

/** The only platform this app registers today — Android via FCM. */
export const CAREGIVER_PUSH_PLATFORM: CaregiverPushPlatform = 'android';

/**
 * The slice of the PushNotificationsPlugin this seam uses, injectable so unit tests pass
 * a fake instead of mocking the plugin across the import graph (ADR-0024 seam lesson).
 * The real `@capacitor/push-notifications` plugin satisfies this structurally.
 */
export interface CaregiverPushPlugin {
  checkPermissions(): Promise<PermissionStatus>;
  requestPermissions(): Promise<PermissionStatus>;
  register(): Promise<void>;
  addListener(
    eventName: 'registration',
    listenerFunc: (token: Token) => void,
  ): Promise<PluginListenerHandle>;
  addListener(
    eventName: 'registrationError',
    listenerFunc: (error: RegistrationError) => void,
  ): Promise<PluginListenerHandle>;
  removeAllListeners(): Promise<void>;
}

/** Injectable dependencies — the plugin plus the two endpoint fns — so the decision
 *  logic is exercised with plain mocks (no MSW, no network) in the unit suite. */
export interface CaregiverPushDeps {
  plugin?: CaregiverPushPlugin;
  registerToken?: (token: string, platform: CaregiverPushPlatform) => Promise<unknown>;
  deregisterToken?: (token: string) => Promise<void>;
}

export type RegisterCaregiverPushResult = 'registered' | 'permission-denied' | 'unavailable';

/** Module-scoped listener handles so deregister can detach exactly what register attached
 *  (mirrors nativeShell's per-handle cleanup). Only this module ever uses the plugin. */
let listenerHandles: PluginListenerHandle[] = [];

function readStoredToken(): string | null {
  try {
    return localStorage.getItem(CAREGIVER_PUSH_TOKEN_KEY);
  } catch {
    return null;
  }
}

function persistToken(token: string): void {
  try {
    localStorage.setItem(CAREGIVER_PUSH_TOKEN_KEY, token);
  } catch {
    // A storage fault must not break registration — the token still reached the server.
  }
}

function clearStoredToken(): void {
  try {
    localStorage.removeItem(CAREGIVER_PUSH_TOKEN_KEY);
  } catch {
    // Best-effort — nothing to do if storage is unavailable.
  }
}

async function detachListeners(plugin: CaregiverPushPlugin): Promise<void> {
  const handles = listenerHandles;
  listenerHandles = [];
  for (const handle of handles) {
    try {
      await handle.remove();
    } catch {
      // Swallowed — a failed detach must never surface; removeAllListeners is the backstop.
    }
  }
  try {
    await plugin.removeAllListeners();
  } catch {
    // Swallowed by design.
  }
}

/**
 * Request permission, register with FCM, and POST the device token (ADR-0047 B2).
 *
 * - `'registered'` — native + permission granted: listeners are attached and `register()`
 *   is invoked; the token arrives on the `'registration'` event and is POSTed (and
 *   re-POSTed on every subsequent refresh event, an idempotent upsert server-side).
 * - `'permission-denied'` — the OS refused (Android 13+ runtime permission). Nothing is
 *   registered. A denied prompt is a normal user choice, surfaced as a RESULT, never a throw.
 * - `'unavailable'` — web: push only exists in the native shell; a total no-op (the plugin
 *   is never touched, no request is made), so the web suites are unchanged.
 *
 * Registering is idempotent: any previously-attached listeners are detached first, so a
 * re-register (e.g. a re-mount) never accumulates duplicate handlers.
 */
export async function registerCaregiverPush(
  deps: CaregiverPushDeps = {},
): Promise<RegisterCaregiverPushResult> {
  if (!isNativePlatform()) {
    return 'unavailable';
  }
  const plugin = deps.plugin ?? PushNotifications;
  const registerToken = deps.registerToken ?? registerCaregiverPushToken;

  let permission = await plugin.checkPermissions();
  if (permission.receive !== 'granted') {
    permission = await plugin.requestPermissions();
  }
  if (permission.receive !== 'granted') {
    return 'permission-denied';
  }

  // Idempotent: never stack duplicate handlers across re-registers.
  await detachListeners(plugin);

  const registrationHandle = await plugin.addListener('registration', (token: Token) => {
    // A fresh token (first registration OR a Firebase refresh) is mirrored locally and
    // (re-)POSTed. The upsert is keyed on the token server-side, so a refresh replaces the
    // row rather than duplicating it. Network/registration faults are swallowed — a failed
    // POST must never crash the app; the next launch re-registers.
    persistToken(token.value);
    void registerToken(token.value, CAREGIVER_PUSH_PLATFORM).catch(() => undefined);
  });
  listenerHandles.push(registrationHandle);

  const errorHandle = await plugin.addListener('registrationError', () => {
    // PHI-free by construction (an FCM error string carries no health data) — but there is
    // nothing actionable and `no-console` is enforced, so it is swallowed. The device simply
    // has no token this session; the next launch retries.
  });
  listenerHandles.push(errorHandle);

  await plugin.register();
  return 'registered';
}

/**
 * Deregister this device's push token on logout / permission-off (ADR-0047 B2): DELETE the
 * last-registered token, drop the local mirror, and detach the listeners.
 *
 * The DELETE is issued FIRST (before any await that could yield), so a caller that runs
 * this immediately before clearing the session — the logout path — still holds a valid
 * access token when the request captures its Authorization header. Idempotent and
 * swallow-safe: a second call (e.g. the hook's unmount cleanup after logout already ran)
 * finds no stored token and only detaches listeners; a failed DELETE is swallowed (the
 * backend prunes a stale token via FCM `UNREGISTERED` regardless).
 *
 * On WEB this is a no-op: nothing was ever stored, so there is no token to delete and the
 * plugin is never touched.
 */
export async function deregisterCaregiverPush(deps: CaregiverPushDeps = {}): Promise<void> {
  const deregisterToken = deps.deregisterToken ?? deregisterCaregiverPushToken;
  const stored = readStoredToken();
  clearStoredToken();
  // Kick off the DELETE synchronously (no await before this) so the auth header is captured
  // against the still-live session on the logout path.
  const deletion = stored !== null ? deregisterToken(stored) : Promise.resolve();
  if (isNativePlatform()) {
    const plugin = deps.plugin ?? PushNotifications;
    await detachListeners(plugin);
  }
  try {
    await deletion;
  } catch {
    // Swallowed by design — deregistration is best-effort and must never block logout.
  }
}
