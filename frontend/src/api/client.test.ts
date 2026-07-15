import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import {
  getAccessToken,
  getRefreshToken,
  onSessionExpired,
  setAccessToken,
  storeSession,
} from '../auth/tokenStore';
import {
  clearQueuedCheckIns,
  enqueueCheckIn,
  listQueuedCheckIns,
} from '../features/checkin/offlineQueue';
import {
  TEST_ACCESS_TOKEN,
  TEST_REFRESH_TOKEN,
  TEST_REFRESHED_ACCESS_TOKEN,
} from '../test/fixtures';
import { server } from '../test/server';
import { ApiError, messageFor, request } from './client';
import { getMe, revokeConnection } from './endpoints';

describe('request', () => {
  it('sends the Authorization header from the in-memory access token', async () => {
    storeSession({ access_token: TEST_ACCESS_TOKEN, refresh_token: TEST_REFRESH_TOKEN });
    const me = await getMe();
    expect(me.display_name).toBe('Pat Example');
  });

  it('refreshes once on 401 and retries with the new access token', async () => {
    // Refresh token only — the first /auth/me is a 401, the retry succeeds.
    sessionStorage.setItem('neuropathy.refresh_token', TEST_REFRESH_TOKEN);
    const me = await getMe();
    expect(me.email).toContain('@example.com');
    expect(getAccessToken()).toBe(TEST_REFRESHED_ACCESS_TOKEN);
  });

  it('expires the session when the refresh itself fails', async () => {
    storeSession({ access_token: 'stale-token', refresh_token: 'stale-refresh' });
    const expired = vi.fn();
    const unsubscribe = onSessionExpired(expired);
    await expect(getMe()).rejects.toThrow(ApiError);
    expect(expired).toHaveBeenCalledTimes(1);
    expect(getRefreshToken()).toBeNull();
    expect(getAccessToken()).toBeNull();
    unsubscribe();
  });

  it('does NOT expire the session when the refresh itself NETWORK-fails (offline is not a session end)', async () => {
    // Restore-shaped state: refresh token stored, no access token yet.
    sessionStorage.setItem('neuropathy.refresh_token', TEST_REFRESH_TOKEN);
    enqueueCheckIn('owner-1', {
      walking: 1,
      stairs: 2,
      balance_confidence: 3,
      check_in_date: '2026-07-01',
    });
    // The 401 → refresh dance starts, but the refresh POST never reaches the
    // server (offline): the fetch TypeError must propagate to the caller WITHOUT
    // notifySessionExpired — storage (token + queue) stays intact for a retry.
    server.use(http.post('/auth/refresh', () => HttpResponse.error()));
    const expired = vi.fn();
    const unsubscribe = onSessionExpired(expired);

    await expect(getMe()).rejects.toThrow(TypeError);

    expect(expired).not.toHaveBeenCalled();
    expect(getRefreshToken()).toBe(TEST_REFRESH_TOKEN);
    expect(listQueuedCheckIns('owner-1')).toHaveLength(1);
    clearQueuedCheckIns();
    unsubscribe();
  });

  it('expires the session on 401 when no refresh token is stored', async () => {
    setAccessToken('stale-token');
    const expired = vi.fn();
    const unsubscribe = onSessionExpired(expired);
    await expect(getMe()).rejects.toThrow('Not authenticated');
    expect(expired).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it('does not retry anonymous requests', async () => {
    let calls = 0;
    server.use(
      http.post('/auth/login', () => {
        calls += 1;
        return HttpResponse.json({ detail: 'Invalid email or password' }, { status: 401 });
      }),
    );
    await expect(
      request('/auth/login', { method: 'POST', body: {}, anonymous: true }),
    ).rejects.toMatchObject({ status: 401, detail: 'Invalid email or password' });
    expect(calls).toBe(1);
  });

  it('returns undefined for 204 responses', async () => {
    storeSession({ access_token: TEST_ACCESS_TOKEN, refresh_token: TEST_REFRESH_TOKEN });
    await expect(revokeConnection('any-id')).resolves.toBeUndefined();
  });

  it('falls back to a generic message for non-JSON and unusable error bodies', async () => {
    storeSession({ access_token: TEST_ACCESS_TOKEN, refresh_token: TEST_REFRESH_TOKEN });
    server.use(http.get('/trajectory', () => new HttpResponse('boom', { status: 500 })));
    await expect(request('/trajectory')).rejects.toThrow('Something went wrong');

    // An array detail without msg strings has nothing to surface.
    server.use(
      http.get('/trajectory', () =>
        HttpResponse.json({ detail: [{ loc: ['body'] }, null] }, { status: 422 }),
      ),
    );
    await expect(request('/trajectory')).rejects.toThrow('Something went wrong');

    server.use(http.get('/trajectory', () => HttpResponse.json({ detail: 42 }, { status: 500 })));
    await expect(request('/trajectory')).rejects.toThrow('Something went wrong');
  });

  it('surfaces FastAPI 422 validation messages verbatim', async () => {
    storeSession({ access_token: TEST_ACCESS_TOKEN, refresh_token: TEST_REFRESH_TOKEN });
    server.use(
      http.get('/trajectory', () =>
        HttpResponse.json(
          {
            detail: [
              { type: 'value_error', loc: ['body'], msg: 'Value error, expiry needs active=true' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    await expect(request('/trajectory')).rejects.toThrow('Value error, expiry needs active=true');
  });
});

describe('messageFor', () => {
  it('uses the ApiError detail and a generic line for anything else', () => {
    expect(messageFor(new ApiError(409, 'Feature is turned off'))).toBe('Feature is turned off');
    expect(messageFor(new Error('TypeError: fetch failed'))).toBe(
      'Something went wrong. Please try again.',
    );
  });
});
