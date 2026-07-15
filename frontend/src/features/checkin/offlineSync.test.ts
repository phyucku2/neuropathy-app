import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse, delay } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AdlCheckInIn } from '../../api/types';
import { postAdlCheckIn } from '../../api/endpoints';
import { ME } from '../../test/fixtures';
import { renderApp, signIn } from '../../test/renderApp';
import { server } from '../../test/server';
import { enqueueCheckIn, listQueuedCheckIns, removeQueuedCheckIn } from './offlineQueue';
import { consumeDroppedNotices, flushQueuedCheckIns, subscribeFlushOutcomes } from './offlineSync';

const FIXED_NOW = () => new Date('2026-07-15T18:30:00Z');

/** The signed-in account (msw /auth/me returns ME) — the queue's owner. */
const OWNER = ME.user_id;
const OTHER_OWNER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

function seed(check_in_date: string, walking = 1, stairs = 2, balance_confidence = 3) {
  return enqueueCheckIn(OWNER, { walking, stairs, balance_confidence, check_in_date }, FIXED_NOW);
}

/** Capture every POST /adl body the mock backend receives; 200 by default. */
function captureAdlPosts(): AdlCheckInIn[] {
  const bodies: AdlCheckInIn[] = [];
  server.use(
    http.post('/adl', async ({ request }) => {
      const body = (await request.json()) as AdlCheckInIn;
      bodies.push(body);
      return HttpResponse.json({
        check_in_date: body.check_in_date,
        daily_score: body.walking + body.stairs + body.balance_confidence,
        superseded: false,
      });
    }),
  );
  return bodies;
}

beforeEach(() => {
  localStorage.clear();
  consumeDroppedNotices(); // drain module-level notice state between tests
});

describe('flushQueuedCheckIns', () => {
  it('posts queued entries oldest day first, each with ITS OWN stored check_in_date, and empties the queue', async () => {
    signIn();
    const bodies = captureAdlPosts();
    seed('2026-07-15', 4, 4, 4);
    seed('2026-07-13');
    seed('2026-07-14');

    const outcome = await flushQueuedCheckIns(OWNER);

    // Honest dates: the backend accepts client check_in_date (ADR-0030), so
    // entries are never re-dated to "today".
    expect(bodies.map((b) => b.check_in_date)).toEqual(['2026-07-13', '2026-07-14', '2026-07-15']);
    expect(bodies[2]).toEqual({
      walking: 4,
      stairs: 4,
      balance_confidence: 4,
      check_in_date: '2026-07-15',
    });
    expect(outcome.synced.map((s) => s.entry.check_in_date)).toEqual([
      '2026-07-13',
      '2026-07-14',
      '2026-07-15',
    ]);
    expect(outcome.synced[0]?.result.daily_score).toBe(6);
    expect(outcome.dropped).toEqual([]);
    expect(outcome.remaining).toBe(0);
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it('flushes ONLY the given owner’s entries — another account’s queue is never posted', async () => {
    signIn();
    const bodies = captureAdlPosts();
    enqueueCheckIn(
      OTHER_OWNER,
      { walking: 0, stairs: 0, balance_confidence: 0, check_in_date: '2026-07-14' },
      FIXED_NOW,
    );
    seed('2026-07-15');

    const outcome = await flushQueuedCheckIns(OWNER);

    expect(bodies.map((b) => b.check_in_date)).toEqual(['2026-07-15']);
    expect(outcome.remaining).toBe(0);
    // The foreign entries are untouched (purging them is the login flow's job).
    expect(listQueuedCheckIns(OTHER_OWNER)).toHaveLength(1);
  });

  it('never double-posts an entry: concurrent triggers share the in-flight pass plus ONE fresh rerun', async () => {
    signIn();
    const posted: string[] = [];
    server.use(
      http.post('/adl', async ({ request }) => {
        const body = (await request.json()) as AdlCheckInIn;
        posted.push(body.check_in_date ?? '');
        await delay(30);
        return HttpResponse.json({
          check_in_date: body.check_in_date,
          daily_score: 6,
          superseded: false,
        });
      }),
    );
    seed('2026-07-15');

    const [first, second, third] = await Promise.all([
      flushQueuedCheckIns(OWNER),
      flushQueuedCheckIns(OWNER),
      flushQueuedCheckIns(OWNER),
    ]);

    // The entry was posted exactly once: the first pass sent it; the shared
    // rerun (which the two mid-flight triggers received) found an empty queue.
    expect(posted).toEqual(['2026-07-15']);
    expect(first.synced).toHaveLength(1);
    expect(second).toBe(third); // mid-flight callers share ONE rerun pass
    expect(second.synced).toEqual([]);
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it('a mid-flight trigger gets a FRESH pass, so a day the stale snapshot missed still syncs', async () => {
    signIn();
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const posted: string[] = [];
    server.use(
      http.post('/adl', async ({ request }) => {
        const body = (await request.json()) as AdlCheckInIn;
        posted.push(body.check_in_date ?? '');
        if (body.check_in_date === '2026-07-14') {
          await gate; // hold the first pass mid-flight
        }
        return HttpResponse.json({
          check_in_date: body.check_in_date,
          daily_score: 6,
          superseded: false,
        });
      }),
    );
    seed('2026-07-14');

    const firstPass = flushQueuedCheckIns(OWNER);
    await waitFor(() => {
      expect(posted).toEqual(['2026-07-14']);
    });
    // While the pass is in flight, an OLDER day is captured (not in the pass's
    // snapshot) and a new trigger fires — it must not be silently absorbed.
    seed('2026-07-13');
    const rerun = flushQueuedCheckIns(OWNER);
    release();

    const [firstOutcome, rerunOutcome] = await Promise.all([firstPass, rerun]);
    expect(firstOutcome.synced.map((s) => s.entry.check_in_date)).toEqual(['2026-07-14']);
    expect(rerunOutcome.synced.map((s) => s.entry.check_in_date)).toEqual(['2026-07-13']);
    expect(posted).toEqual(['2026-07-14', '2026-07-13']);
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it('skips an entry a fresh submission recalled mid-pass — the stale answers never supersede the fresh ones', async () => {
    signIn();
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const posted: AdlCheckInIn[] = [];
    server.use(
      http.post('/adl', async ({ request }) => {
        const body = (await request.json()) as AdlCheckInIn;
        posted.push(body);
        if (body.check_in_date === '2026-07-13') {
          await gate; // hold the pass on the OLDER day
        }
        return HttpResponse.json({
          check_in_date: body.check_in_date,
          daily_score: 6,
          superseded: false,
        });
      }),
    );
    // The queue holds an older day AND today (captured offline earlier, stale answers).
    seed('2026-07-13');
    seed('2026-07-15', 1, 1, 1);

    const pass = flushQueuedCheckIns(OWNER);
    await waitFor(() => {
      expect(posted.map((b) => b.check_in_date)).toEqual(['2026-07-13']);
    });

    // The exact interleaving under test: while the pass is held on 07-13, the
    // user submits FRESH answers for today online (CheckInPage's submit path:
    // POST succeeds, then the queued same-day entry is recalled, then a flush
    // is triggered — which queues a fresh rerun pass).
    await postAdlCheckIn({
      walking: 4,
      stairs: 4,
      balance_confidence: 4,
      check_in_date: '2026-07-15',
    });
    removeQueuedCheckIn(OWNER, '2026-07-15');
    const rerun = flushQueuedCheckIns(OWNER);
    release();
    await Promise.all([pass, rerun]);

    // Exactly ONE post for today, and it is the FRESH one — the stale queued
    // entry was skipped by the pre-POST re-read (and the rerun found nothing).
    const todays = posted.filter((b) => b.check_in_date === '2026-07-15');
    expect(todays).toEqual([
      { walking: 4, stairs: 4, balance_confidence: 4, check_in_date: '2026-07-15' },
    ]);
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it('drops a 409-refused entry with its verbatim detail (surfaced once), and still syncs the rest', async () => {
    signIn();
    const refused = 'This check-in is turned off right now.';
    server.use(
      http.post('/adl', async ({ request }) => {
        const body = (await request.json()) as AdlCheckInIn;
        if (body.check_in_date === '2026-07-13') {
          return HttpResponse.json({ detail: refused }, { status: 409 });
        }
        return HttpResponse.json({
          check_in_date: body.check_in_date,
          daily_score: 6,
          superseded: false,
        });
      }),
    );
    seed('2026-07-13');
    seed('2026-07-14');

    const outcome = await flushQueuedCheckIns(OWNER);

    expect(outcome.dropped).toHaveLength(1);
    expect(outcome.dropped[0]?.entry.check_in_date).toBe('2026-07-13');
    expect(outcome.dropped[0]?.detail).toBe(refused);
    expect(outcome.synced.map((s) => s.entry.check_in_date)).toEqual(['2026-07-14']);
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
    // Consumed exactly once.
    expect(consumeDroppedNotices().map((d) => d.detail)).toEqual([refused]);
    expect(consumeDroppedNotices()).toEqual([]);
  });

  it('drops a 422-refused entry the same way', async () => {
    signIn();
    server.use(
      http.post('/adl', () =>
        HttpResponse.json({ detail: 'check_in_date cannot be in the future' }, { status: 422 }),
      ),
    );
    seed('2026-07-15');
    const outcome = await flushQueuedCheckIns(OWNER);
    expect(outcome.dropped[0]?.detail).toBe('check_in_date cannot be in the future');
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it('stops on a network failure, leaving the remaining entries queued and emitting nothing', async () => {
    signIn();
    server.use(http.post('/adl', () => HttpResponse.error()));
    const outcomes: unknown[] = [];
    const unsubscribe = subscribeFlushOutcomes((o) => outcomes.push(o));
    seed('2026-07-14');
    seed('2026-07-15');

    const outcome = await flushQueuedCheckIns(OWNER);

    expect(outcome).toEqual({ synced: [], dropped: [], remaining: 2 });
    expect(listQueuedCheckIns(OWNER)).toHaveLength(2);
    expect(outcomes).toEqual([]); // nothing happened — no listener noise
    unsubscribe();
  });

  it('stops when auth is expired mid-flush (401 even after refresh), leaving the entry queued', async () => {
    signIn();
    // /adl 401s on every attempt; the refresh itself succeeds, so the session is
    // NOT cleared — the entry must stay queued for a later signed-in flush.
    server.use(http.post('/adl', () => HttpResponse.json({ detail: 'Nope' }, { status: 401 })));
    seed('2026-07-15');

    const outcome = await flushQueuedCheckIns(OWNER);

    expect(outcome).toEqual({ synced: [], dropped: [], remaining: 1 });
    expect(listQueuedCheckIns(OWNER)).toHaveLength(1);
  });

  it('does nothing (and posts nothing) when the queue is empty', async () => {
    signIn();
    const bodies = captureAdlPosts();
    const outcome = await flushQueuedCheckIns(OWNER);
    expect(outcome).toEqual({ synced: [], dropped: [], remaining: 0 });
    expect(bodies).toEqual([]);
  });
});

describe('OfflineCheckInSync triggers', () => {
  it('flushes on app boot once the session is authenticated', async () => {
    const bodies = captureAdlPosts();
    seed('2026-07-14');
    renderApp('/');
    await screen.findByRole('link', { name: /Sources/ }); // authenticated shell is up
    await waitFor(() => {
      expect(bodies.map((b) => b.check_in_date)).toEqual(['2026-07-14']);
    });
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it("flushes again on a window 'online' event", async () => {
    const bodies = captureAdlPosts();
    renderApp('/');
    await screen.findByRole('link', { name: /Sources/ }); // listener registered
    seed('2026-07-15');
    window.dispatchEvent(new Event('online'));
    await waitFor(() => {
      expect(bodies.map((b) => b.check_in_date)).toEqual(['2026-07-15']);
    });
  });

  it('never posts while anonymous (no authenticated session, no flush)', async () => {
    const bodies = captureAdlPosts();
    const dispatch = vi.spyOn(window, 'addEventListener');
    seed('2026-07-14');
    renderApp('/login', { authenticated: false });
    await screen.findByLabelText('Email');
    window.dispatchEvent(new Event('online'));
    // Give any wrongly-registered flush a tick to fire.
    await new Promise((resolve) => setTimeout(resolve, 25));
    expect(bodies).toEqual([]);
    expect(listQueuedCheckIns(OWNER)).toHaveLength(1);
    expect(dispatch.mock.calls.filter(([type]) => type === 'online')).toEqual([]);
    dispatch.mockRestore();
  });
});
