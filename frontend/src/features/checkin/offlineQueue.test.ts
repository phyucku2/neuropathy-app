import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearSession } from '../../auth/tokenStore';
import { renderApp } from '../../test/renderApp';
import { TEST_PASSWORD } from '../../test/fixtures';
import {
  clearQueuedCheckIns,
  enqueueCheckIn,
  getQueuedCheckIn,
  listQueuedCheckIns,
  OFFLINE_CHECKIN_QUEUE_KEY,
  removeQueuedCheckIn,
} from './offlineQueue';

const FIXED_NOW = () => new Date('2026-07-15T18:30:00Z');

const JUL_14 = { walking: 1, stairs: 2, balance_confidence: 3, check_in_date: '2026-07-14' };
const JUL_15 = { walking: 4, stairs: 4, balance_confidence: 4, check_in_date: '2026-07-15' };

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  localStorage.clear();
});

describe('offlineQueue', () => {
  it('stores an entry with the injected clock as queued_at', () => {
    const entry = enqueueCheckIn(JUL_15, FIXED_NOW);
    expect(entry).toEqual({ ...JUL_15, queued_at: '2026-07-15T18:30:00.000Z' });
    expect(listQueuedCheckIns()).toEqual([entry]);
  });

  it('keeps at most ONE entry per calendar date — a newer same-day capture replaces it', () => {
    enqueueCheckIn(JUL_15, FIXED_NOW);
    const replacement = enqueueCheckIn(
      { walking: 0, stairs: 1, balance_confidence: 2, check_in_date: '2026-07-15' },
      () => new Date('2026-07-15T21:00:00Z'),
    );
    const entries = listQueuedCheckIns();
    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual(replacement);
    expect(entries[0]?.queued_at).toBe('2026-07-15T21:00:00.000Z');
  });

  it('keeps distinct dates and lists them oldest day first regardless of insert order', () => {
    enqueueCheckIn(JUL_15, FIXED_NOW);
    enqueueCheckIn(JUL_14, FIXED_NOW);
    expect(listQueuedCheckIns().map((e) => e.check_in_date)).toEqual(['2026-07-14', '2026-07-15']);
  });

  it('getQueuedCheckIn finds one day and misses another', () => {
    enqueueCheckIn(JUL_14, FIXED_NOW);
    expect(getQueuedCheckIn('2026-07-14')?.stairs).toBe(2);
    expect(getQueuedCheckIn('2026-07-15')).toBeNull();
  });

  it('removeQueuedCheckIn drops only the named day (and empties storage when last)', () => {
    enqueueCheckIn(JUL_14, FIXED_NOW);
    enqueueCheckIn(JUL_15, FIXED_NOW);
    removeQueuedCheckIn('2026-07-14');
    expect(listQueuedCheckIns().map((e) => e.check_in_date)).toEqual(['2026-07-15']);
    removeQueuedCheckIn('2026-07-15');
    expect(localStorage.getItem(OFFLINE_CHECKIN_QUEUE_KEY)).toBeNull();
  });

  it('reads corrupt JSON, non-array payloads, and malformed entries as an empty/filtered queue', () => {
    localStorage.setItem(OFFLINE_CHECKIN_QUEUE_KEY, '{not json');
    expect(listQueuedCheckIns()).toEqual([]);
    localStorage.setItem(OFFLINE_CHECKIN_QUEUE_KEY, JSON.stringify({ nope: true }));
    expect(listQueuedCheckIns()).toEqual([]);
    // Out-of-range answers, wrong date shape, and missing fields are all filtered.
    localStorage.setItem(
      OFFLINE_CHECKIN_QUEUE_KEY,
      JSON.stringify([
        { ...JUL_14, queued_at: '2026-07-14T10:00:00Z' },
        { ...JUL_15, walking: 9, queued_at: 'x' },
        { ...JUL_15, check_in_date: 'July 15', queued_at: 'x' },
        { walking: 1 },
        null,
      ]),
    );
    expect(listQueuedCheckIns()).toEqual([{ ...JUL_14, queued_at: '2026-07-14T10:00:00Z' }]);
  });

  it('returns null (never throws) when storage writes fail', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });
    expect(enqueueCheckIn(JUL_15, FIXED_NOW)).toBeNull();
    setItem.mockRestore();
  });

  it('survives storage read/remove failures without throwing', () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage unavailable');
    });
    const removeItem = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('storage unavailable');
    });
    expect(listQueuedCheckIns()).toEqual([]);
    expect(() => {
      clearQueuedCheckIns();
    }).not.toThrow();
    getItem.mockRestore();
    removeItem.mockRestore();
  });

  it('is cleared by tokenStore.clearSession (the shared logout/expiry path)', () => {
    enqueueCheckIn(JUL_15, FIXED_NOW);
    clearSession();
    expect(listQueuedCheckIns()).toEqual([]);
  });

  it('is cleared by the account-deletion flow (DeleteAccountCard → logout → clearSession)', async () => {
    enqueueCheckIn(JUL_15, FIXED_NOW);
    const user = userEvent.setup();
    renderApp('/settings');
    await user.click(await screen.findByRole('button', { name: 'Delete my account' }));
    await user.type(screen.getByLabelText('Confirm your password'), TEST_PASSWORD);
    await user.click(screen.getByRole('checkbox'));
    // Two-tap confirm.
    await user.click(screen.getByRole('button', { name: 'Delete my account and data' }));
    await user.click(screen.getByRole('button', { name: 'Tap again to permanently delete' }));
    // The deletion landed on /login — and the queued health answers are gone with
    // the session (ADR-0030: the queue never outlives the session).
    expect(await screen.findByText('Your account and data were deleted.')).toBeInTheDocument();
    expect(listQueuedCheckIns()).toEqual([]);
  });
});
