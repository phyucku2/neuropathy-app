import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearSession } from '../../auth/tokenStore';
import { renderApp } from '../../test/renderApp';
import { ME, TEST_PASSWORD } from '../../test/fixtures';
import {
  clearQueuedCheckIns,
  enqueueCheckIn,
  getQueuedCheckIn,
  listQueuedCheckIns,
  OFFLINE_CHECKIN_QUEUE_KEY,
  purgeExpiredQueuedCheckIns,
  purgeQueuedCheckInsForOtherOwners,
  removeQueuedCheckIn,
} from './offlineQueue';

const FIXED_NOW = () => new Date('2026-07-15T18:30:00Z');

/** The signed-in account's user id (MeOut.user_id) — the queue's owner key. */
const OWNER = ME.user_id;
const OTHER_OWNER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

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
    const entry = enqueueCheckIn(OWNER, JUL_15, FIXED_NOW);
    expect(entry).toEqual({ ...JUL_15, queued_at: '2026-07-15T18:30:00.000Z' });
    expect(listQueuedCheckIns(OWNER)).toEqual([entry]);
  });

  it('keeps at most ONE entry per calendar date — a newer same-day capture replaces it', () => {
    enqueueCheckIn(OWNER, JUL_15, FIXED_NOW);
    const replacement = enqueueCheckIn(
      OWNER,
      { walking: 0, stairs: 1, balance_confidence: 2, check_in_date: '2026-07-15' },
      () => new Date('2026-07-15T21:00:00Z'),
    );
    const entries = listQueuedCheckIns(OWNER);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual(replacement);
    expect(entries[0]?.queued_at).toBe('2026-07-15T21:00:00.000Z');
  });

  it('keeps distinct dates and lists them oldest day first regardless of insert order', () => {
    enqueueCheckIn(OWNER, JUL_15, FIXED_NOW);
    enqueueCheckIn(OWNER, JUL_14, FIXED_NOW);
    expect(listQueuedCheckIns(OWNER).map((e) => e.check_in_date)).toEqual([
      '2026-07-14',
      '2026-07-15',
    ]);
  });

  it('getQueuedCheckIn finds one day and misses another', () => {
    enqueueCheckIn(OWNER, JUL_14, FIXED_NOW);
    expect(getQueuedCheckIn(OWNER, '2026-07-14')?.stairs).toBe(2);
    expect(getQueuedCheckIn(OWNER, '2026-07-15')).toBeNull();
  });

  it('removeQueuedCheckIn drops only the named day (and empties storage when last)', () => {
    enqueueCheckIn(OWNER, JUL_14, FIXED_NOW);
    enqueueCheckIn(OWNER, JUL_15, FIXED_NOW);
    removeQueuedCheckIn(OWNER, '2026-07-14');
    expect(listQueuedCheckIns(OWNER).map((e) => e.check_in_date)).toEqual(['2026-07-15']);
    removeQueuedCheckIn(OWNER, '2026-07-15');
    expect(localStorage.getItem(OFFLINE_CHECKIN_QUEUE_KEY)).toBeNull();
  });

  it('binds entries to their owner: one account never sees or touches another account’s queue', () => {
    enqueueCheckIn(OWNER, JUL_14, FIXED_NOW);
    enqueueCheckIn(OTHER_OWNER, JUL_15, FIXED_NOW);

    // Reads are owner-scoped in both directions.
    expect(listQueuedCheckIns(OWNER).map((e) => e.check_in_date)).toEqual(['2026-07-14']);
    expect(listQueuedCheckIns(OTHER_OWNER).map((e) => e.check_in_date)).toEqual(['2026-07-15']);
    expect(getQueuedCheckIn(OWNER, '2026-07-15')).toBeNull();

    // Writes are too: removing a day for one owner leaves the other's intact,
    // even for the same calendar date.
    enqueueCheckIn(OTHER_OWNER, JUL_14, FIXED_NOW);
    removeQueuedCheckIn(OWNER, '2026-07-14');
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
    expect(listQueuedCheckIns(OTHER_OWNER)).toHaveLength(2);
  });

  it('purgeQueuedCheckInsForOtherOwners keeps only the active account’s entries', () => {
    enqueueCheckIn(OWNER, JUL_14, FIXED_NOW);
    enqueueCheckIn(OTHER_OWNER, JUL_15, FIXED_NOW);
    purgeQueuedCheckInsForOtherOwners(OWNER);
    expect(listQueuedCheckIns(OWNER)).toHaveLength(1);
    expect(listQueuedCheckIns(OTHER_OWNER)).toEqual([]);
  });

  it('purgeQueuedCheckInsForOtherOwners empties storage when the active account has nothing queued', () => {
    enqueueCheckIn(OTHER_OWNER, JUL_15, FIXED_NOW);
    purgeQueuedCheckInsForOtherOwners(OWNER);
    expect(localStorage.getItem(OFFLINE_CHECKIN_QUEUE_KEY)).toBeNull();
  });

  it('purgeExpiredQueuedCheckIns drops entries past the 14-day TTL (and unparsable queued_at), all owners', () => {
    // 13 days old — still fresh; 15 days old — clinically stale, dropped.
    enqueueCheckIn(OWNER, JUL_14, () => new Date('2026-07-02T18:30:00Z'));
    enqueueCheckIn(OWNER, JUL_15, () => new Date('2026-06-30T18:30:00Z'));
    enqueueCheckIn(OTHER_OWNER, JUL_15, () => new Date('2026-06-01T00:00:00Z'));
    // An unparsable queued_at could never expire — it is dropped too.
    localStorage.setItem(
      OFFLINE_CHECKIN_QUEUE_KEY,
      JSON.stringify({
        [OWNER]: [
          ...listQueuedCheckIns(OWNER),
          { ...JUL_15, check_in_date: '2026-07-13', queued_at: 'not-a-timestamp' },
        ],
        [OTHER_OWNER]: listQueuedCheckIns(OTHER_OWNER),
      }),
    );

    purgeExpiredQueuedCheckIns(FIXED_NOW);

    expect(listQueuedCheckIns(OWNER)).toEqual([
      { ...JUL_14, queued_at: '2026-07-02T18:30:00.000Z' },
    ]);
    expect(listQueuedCheckIns(OTHER_OWNER)).toEqual([]);
  });

  it('reads the pre-user-binding ARRAY format as empty — unattributable entries are dropped, not guessed', () => {
    localStorage.setItem(
      OFFLINE_CHECKIN_QUEUE_KEY,
      JSON.stringify([{ ...JUL_14, queued_at: '2026-07-14T10:00:00Z' }]),
    );
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
    // The first write replaces the legacy payload entirely.
    enqueueCheckIn(OWNER, JUL_15, FIXED_NOW);
    expect(listQueuedCheckIns(OWNER)).toHaveLength(1);
  });

  it('reads corrupt JSON, non-object payloads, and malformed entries as an empty/filtered queue', () => {
    localStorage.setItem(OFFLINE_CHECKIN_QUEUE_KEY, '{not json');
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
    localStorage.setItem(OFFLINE_CHECKIN_QUEUE_KEY, JSON.stringify('nope'));
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
    localStorage.setItem(OFFLINE_CHECKIN_QUEUE_KEY, JSON.stringify(null));
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
    // Out-of-range answers, wrong date shape, missing fields, and a non-array
    // owner bucket are all filtered.
    localStorage.setItem(
      OFFLINE_CHECKIN_QUEUE_KEY,
      JSON.stringify({
        [OWNER]: [
          { ...JUL_14, queued_at: '2026-07-14T10:00:00Z' },
          { ...JUL_15, walking: 9, queued_at: 'x' },
          { ...JUL_15, check_in_date: 'July 15', queued_at: 'x' },
          { walking: 1 },
          null,
        ],
        [OTHER_OWNER]: { nope: true },
      }),
    );
    expect(listQueuedCheckIns(OWNER)).toEqual([{ ...JUL_14, queued_at: '2026-07-14T10:00:00Z' }]);
    expect(listQueuedCheckIns(OTHER_OWNER)).toEqual([]);
  });

  it('returns null (never throws) when storage writes fail', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });
    expect(enqueueCheckIn(OWNER, JUL_15, FIXED_NOW)).toBeNull();
    setItem.mockRestore();
  });

  it('survives storage read/remove failures without throwing', () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage unavailable');
    });
    const removeItem = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('storage unavailable');
    });
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
    expect(() => {
      clearQueuedCheckIns();
    }).not.toThrow();
    expect(() => {
      purgeExpiredQueuedCheckIns(FIXED_NOW);
    }).not.toThrow();
    getItem.mockRestore();
    removeItem.mockRestore();
  });

  it('is cleared for ALL owners by tokenStore.clearSession (the shared real-session-end path)', () => {
    enqueueCheckIn(OWNER, JUL_15, FIXED_NOW);
    enqueueCheckIn(OTHER_OWNER, JUL_14, FIXED_NOW);
    clearSession();
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
    expect(listQueuedCheckIns(OTHER_OWNER)).toEqual([]);
  });

  it('is cleared by the account-deletion flow (DeleteAccountCard → logout → clearSession)', async () => {
    enqueueCheckIn(OWNER, JUL_15, FIXED_NOW);
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
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });
});
