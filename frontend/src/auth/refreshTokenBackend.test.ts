import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NativeBackend, REFRESH_TOKEN_KEY, WebBackend, type SecureKv } from './refreshTokenBackend';

/** In-memory fake of the native secure store, injected into NativeBackend so the Keystore-backed
 * path is exercised off-device. A flag lets a single get/remove fail on demand. */
function makeFakeKv() {
  const store = new Map<string, string>();
  let failNextGet = false;
  let failRemoveTimes = 0; // number of upcoming remove() calls that should reject
  let removeCalls = 0;
  const kv: SecureKv = {
    getItem: async (key) => {
      if (failNextGet) {
        failNextGet = false;
        throw new Error('keystore unavailable');
      }
      return store.get(key) ?? null;
    },
    setItem: async (key, value) => {
      store.set(key, value);
    },
    remove: async (key) => {
      removeCalls += 1;
      if (failRemoveTimes > 0) {
        failRemoveTimes -= 1;
        throw new Error('remove failed');
      }
      return store.delete(key);
    },
  };
  return {
    kv,
    store,
    removeCalls: () => removeCalls,
    failGetOnce: () => {
      failNextGet = true;
    },
    failRemoveTimes: (n: number) => {
      failRemoveTimes = n;
    },
  };
}

describe('WebBackend (sessionStorage)', () => {
  beforeEach(() => sessionStorage.clear());

  it('round-trips the token and peeks it synchronously from live sessionStorage', async () => {
    const backend = new WebBackend();
    expect(backend.peek()).toBeNull();
    await backend.save('refresh-abc');
    // peek reads sessionStorage directly — the value is visible synchronously.
    expect(backend.peek()).toBe('refresh-abc');
    expect(sessionStorage.getItem(REFRESH_TOKEN_KEY)).toBe('refresh-abc');
    await expect(backend.load()).resolves.toBe('refresh-abc');
  });

  it('clear removes the token immediately and synchronously', async () => {
    const backend = new WebBackend();
    await backend.save('refresh-abc');
    backend.clear();
    expect(backend.peek()).toBeNull();
    expect(sessionStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
  });
});

describe('NativeBackend (Keystore-backed secure store)', () => {
  afterEach(() => sessionStorage.clear());

  it('peek is null until load() primes the in-memory mirror from the secure store', async () => {
    const fake = makeFakeKv();
    fake.store.set(REFRESH_TOKEN_KEY, 'keystore-token');
    const backend = new NativeBackend(fake.kv);
    // Not primed yet — the native restore flow must never trust a synchronous peek.
    expect(backend.peek()).toBeNull();
    await expect(backend.load()).resolves.toBe('keystore-token');
    expect(backend.peek()).toBe('keystore-token');
    // Never touches web sessionStorage.
    expect(sessionStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
  });

  it('save writes through to the secure store and mirrors synchronously', async () => {
    const fake = makeFakeKv();
    const backend = new NativeBackend(fake.kv);
    await backend.save('fresh-token');
    expect(fake.store.get(REFRESH_TOKEN_KEY)).toBe('fresh-token');
    expect(backend.peek()).toBe('fresh-token');
  });

  it('clear drops the mirror synchronously and schedules the durable removal', async () => {
    const fake = makeFakeKv();
    const backend = new NativeBackend(fake.kv);
    await backend.save('fresh-token');
    backend.clear();
    // Mirror is gone immediately — the app cannot use the token even before remove() resolves.
    expect(backend.peek()).toBeNull();
    await vi.waitFor(() => expect(fake.store.has(REFRESH_TOKEN_KEY)).toBe(false));
  });

  it('a secure-store read failure yields null, never a stale mirror', async () => {
    const fake = makeFakeKv();
    fake.store.set(REFRESH_TOKEN_KEY, 'unreadable');
    fake.failGetOnce();
    const backend = new NativeBackend(fake.kv);
    await expect(backend.load()).resolves.toBeNull();
    expect(backend.peek()).toBeNull();
  });

  it('clear retries a transient removal failure and still purges the durable token', async () => {
    const fake = makeFakeKv();
    fake.failRemoveTimes(2); // first two remove() calls reject; the third succeeds
    const backend = new NativeBackend(fake.kv);
    await backend.save('fresh-token');
    backend.clear();
    expect(backend.peek()).toBeNull();
    // The retry eventually removes the token — no resurrectable residue after a transient error.
    await vi.waitFor(() => expect(fake.store.has(REFRESH_TOKEN_KEY)).toBe(false));
  });

  it('clear never throws and bounds its retries when every removal fails', async () => {
    const fake = makeFakeKv();
    fake.failRemoveTimes(Number.POSITIVE_INFINITY);
    const backend = new NativeBackend(fake.kv);
    await backend.save('fresh-token');
    expect(() => backend.clear()).not.toThrow();
    expect(backend.peek()).toBeNull(); // mirror cleared → no in-process use
    // Retries are bounded (does not loop forever); the durable residue is the accepted rare case.
    await vi.waitFor(() => expect(fake.removeCalls()).toBe(3));
  });
});
