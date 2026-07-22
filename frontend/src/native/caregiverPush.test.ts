/**
 * The caregiver push registration seam (ADR-0047 B2): permission → register → POST the
 * FCM token on the 'registration' event; a refresh re-POSTs (idempotent upsert); a denied
 * permission is a RESULT, never a throw; logout deregisters the stored token; WEB is a
 * total no-op. The plugin and the endpoint fns are injected (ADR-0024 seam lesson), so the
 * exact Cap-6 push contract is pinned here off-device with no network.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../auth/platform', () => ({ isNativePlatform: vi.fn(() => false) }));

import { isNativePlatform } from '../auth/platform';
import {
  CAREGIVER_PUSH_PLATFORM,
  CAREGIVER_PUSH_TOKEN_KEY,
  deregisterCaregiverPush,
  registerCaregiverPush,
} from './caregiverPush';
import type { CaregiverPushDeps, CaregiverPushPlugin } from './caregiverPush';

const nativeMock = vi.mocked(isNativePlatform);

const TOKEN = 'fcm-device-token-abc123';
const REFRESHED_TOKEN = 'fcm-device-token-def456';

type Receive = 'prompt' | 'prompt-with-rationale' | 'granted' | 'denied';

/**
 * A fake PushNotifications plugin that captures the registered listener callbacks so a
 * test can drive the async 'registration' / 'registrationError' events by hand, and
 * counts remove()/removeAllListeners() so detach is observable.
 */
function fakePlugin(
  check: Receive = 'granted',
  request: Receive = check,
): CaregiverPushPlugin & {
  fireRegistration: (value: string) => void;
  fireRegistrationError: (error: string) => void;
  removeHandleCount: () => number;
  removeAllCount: () => number;
  spies: Record<string, ReturnType<typeof vi.fn>>;
} {
  let onRegistration: ((token: { value: string }) => void) | null = null;
  let onError: ((error: { error: string }) => void) | null = null;
  let removeHandleCount = 0;
  let removeAllCount = 0;

  const checkPermissions = vi.fn(async () => ({ receive: check }));
  const requestPermissions = vi.fn(async () => ({ receive: request }));
  const register = vi.fn(async () => undefined);
  const removeAllListeners = vi.fn(async () => {
    removeAllCount += 1;
  });
  const addListener = vi.fn(
    async (event: 'registration' | 'registrationError', cb: (arg: never) => void) => {
      if (event === 'registration') {
        onRegistration = cb as unknown as (token: { value: string }) => void;
      } else {
        onError = cb as unknown as (error: { error: string }) => void;
      }
      return {
        remove: async () => {
          removeHandleCount += 1;
        },
      };
    },
  );

  return {
    checkPermissions,
    requestPermissions,
    register,
    // The fake's addListener is a single impl; the structural interface's overloads are
    // satisfied by the cast at the call sites below.
    addListener: addListener as unknown as CaregiverPushPlugin['addListener'],
    removeAllListeners,
    fireRegistration: (value: string) => onRegistration?.({ value }),
    fireRegistrationError: (error: string) => onError?.({ error }),
    removeHandleCount: () => removeHandleCount,
    removeAllCount: () => removeAllCount,
    spies: { checkPermissions, requestPermissions, register, addListener, removeAllListeners },
  };
}

function deps(plugin: CaregiverPushPlugin): Required<Pick<CaregiverPushDeps, 'plugin'>> & {
  registerToken: ReturnType<typeof vi.fn>;
  deregisterToken: ReturnType<typeof vi.fn>;
} {
  return {
    plugin,
    registerToken: vi.fn(async () => ({
      id: 'row-1',
      platform: 'android',
      last_seen_at: '2026-07-22T00:00:00Z',
      created_at: '2026-07-22T00:00:00Z',
    })),
    deregisterToken: vi.fn(async () => undefined),
  };
}

beforeEach(() => {
  nativeMock.mockReset();
  nativeMock.mockReturnValue(true);
  localStorage.clear();
});

describe('registerCaregiverPush', () => {
  it('native + granted: registers, and POSTs + persists the token on the registration event', async () => {
    const plugin = fakePlugin('granted');
    const d = deps(plugin);
    await expect(registerCaregiverPush(d)).resolves.toBe('registered');
    expect(plugin.spies['register']).toHaveBeenCalledTimes(1);
    // The token has not arrived yet — it is delivered asynchronously via the event.
    expect(d.registerToken).not.toHaveBeenCalled();

    plugin.fireRegistration(TOKEN);
    expect(d.registerToken).toHaveBeenCalledWith(TOKEN, CAREGIVER_PUSH_PLATFORM);
    expect(CAREGIVER_PUSH_PLATFORM).toBe('android');
    expect(localStorage.getItem(CAREGIVER_PUSH_TOKEN_KEY)).toBe(TOKEN);
  });

  it('already-granted: does not pop the permission dialog, still registers', async () => {
    const plugin = fakePlugin('granted');
    await expect(registerCaregiverPush(deps(plugin))).resolves.toBe('registered');
    expect(plugin.spies['checkPermissions']).toHaveBeenCalledTimes(1);
    expect(plugin.spies['requestPermissions']).not.toHaveBeenCalled();
  });

  it('prompt then granted: requests permission and registers', async () => {
    const plugin = fakePlugin('prompt', 'granted');
    await expect(registerCaregiverPush(deps(plugin))).resolves.toBe('registered');
    expect(plugin.spies['requestPermissions']).toHaveBeenCalledTimes(1);
    expect(plugin.spies['register']).toHaveBeenCalledTimes(1);
  });

  it('permission denied: returns the result (no throw), registers nothing, POSTs nothing', async () => {
    const plugin = fakePlugin('denied', 'denied');
    const d = deps(plugin);
    await expect(registerCaregiverPush(d)).resolves.toBe('permission-denied');
    expect(plugin.spies['register']).not.toHaveBeenCalled();
    expect(d.registerToken).not.toHaveBeenCalled();
    expect(localStorage.getItem(CAREGIVER_PUSH_TOKEN_KEY)).toBeNull();
  });

  it('token refresh: a second registration event re-POSTs the new token (idempotent upsert)', async () => {
    const plugin = fakePlugin('granted');
    const d = deps(plugin);
    await registerCaregiverPush(d);
    plugin.fireRegistration(TOKEN);
    plugin.fireRegistration(REFRESHED_TOKEN);
    expect(d.registerToken).toHaveBeenNthCalledWith(1, TOKEN, CAREGIVER_PUSH_PLATFORM);
    expect(d.registerToken).toHaveBeenNthCalledWith(2, REFRESHED_TOKEN, CAREGIVER_PUSH_PLATFORM);
    expect(localStorage.getItem(CAREGIVER_PUSH_TOKEN_KEY)).toBe(REFRESHED_TOKEN);
  });

  it('registrationError: swallowed — no POST, no throw, no token stored', async () => {
    const plugin = fakePlugin('granted');
    const d = deps(plugin);
    await registerCaregiverPush(d);
    expect(() => plugin.fireRegistrationError('SERVICE_NOT_AVAILABLE')).not.toThrow();
    expect(d.registerToken).not.toHaveBeenCalled();
    expect(localStorage.getItem(CAREGIVER_PUSH_TOKEN_KEY)).toBeNull();
  });

  it('a failed POST is swallowed — the registration event never crashes the app', async () => {
    const plugin = fakePlugin('granted');
    const d = deps(plugin);
    d.registerToken.mockRejectedValueOnce(new Error('network fault'));
    await registerCaregiverPush(d);
    expect(() => plugin.fireRegistration(TOKEN)).not.toThrow();
    // The local mirror is still written (registration reached the OS); the server sync retries.
    expect(localStorage.getItem(CAREGIVER_PUSH_TOKEN_KEY)).toBe(TOKEN);
  });

  it('re-register detaches the previous listeners first (never stacks duplicate handlers)', async () => {
    const plugin = fakePlugin('granted');
    await registerCaregiverPush(deps(plugin));
    expect(plugin.removeHandleCount()).toBe(0);
    await registerCaregiverPush(deps(plugin));
    // The two handles attached by the first register were removed before the second attached.
    expect(plugin.removeHandleCount()).toBe(2);
  });

  it('web: total no-op — plugin never touched, nothing persisted', async () => {
    nativeMock.mockReturnValue(false);
    const plugin = fakePlugin('granted');
    const d = deps(plugin);
    await expect(registerCaregiverPush(d)).resolves.toBe('unavailable');
    expect(plugin.spies['checkPermissions']).not.toHaveBeenCalled();
    expect(plugin.spies['register']).not.toHaveBeenCalled();
    expect(d.registerToken).not.toHaveBeenCalled();
    expect(localStorage.getItem(CAREGIVER_PUSH_TOKEN_KEY)).toBeNull();
  });
});

describe('deregisterCaregiverPush', () => {
  it('DELETEs the stored token, clears the local mirror, and detaches listeners', async () => {
    const plugin = fakePlugin('granted');
    const d = deps(plugin);
    await registerCaregiverPush(d);
    plugin.fireRegistration(TOKEN);

    await deregisterCaregiverPush(d);
    expect(d.deregisterToken).toHaveBeenCalledWith(TOKEN);
    expect(localStorage.getItem(CAREGIVER_PUSH_TOKEN_KEY)).toBeNull();
    expect(plugin.removeAllCount()).toBeGreaterThanOrEqual(1);
  });

  it('idempotent: a second deregister finds no token and issues no DELETE', async () => {
    const plugin = fakePlugin('granted');
    const d = deps(plugin);
    localStorage.setItem(CAREGIVER_PUSH_TOKEN_KEY, TOKEN);
    await deregisterCaregiverPush(d);
    expect(d.deregisterToken).toHaveBeenCalledTimes(1);
    await deregisterCaregiverPush(d);
    expect(d.deregisterToken).toHaveBeenCalledTimes(1);
  });

  it('never throws: a failed DELETE is swallowed and the local mirror is still cleared', async () => {
    const plugin = fakePlugin('granted');
    const d = deps(plugin);
    localStorage.setItem(CAREGIVER_PUSH_TOKEN_KEY, TOKEN);
    d.deregisterToken.mockRejectedValueOnce(new Error('bridge fault'));
    await expect(deregisterCaregiverPush(d)).resolves.toBeUndefined();
    expect(localStorage.getItem(CAREGIVER_PUSH_TOKEN_KEY)).toBeNull();
  });

  it('web: no token was ever stored, so nothing is deleted and the plugin is untouched', async () => {
    nativeMock.mockReturnValue(false);
    const plugin = fakePlugin('granted');
    const d = deps(plugin);
    await deregisterCaregiverPush(d);
    expect(d.deregisterToken).not.toHaveBeenCalled();
    expect(plugin.removeAllCount()).toBe(0);
  });
});
