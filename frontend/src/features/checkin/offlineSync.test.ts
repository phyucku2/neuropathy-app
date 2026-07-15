import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse, delay } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AdlCheckInIn } from '../../api/types';
import { renderApp, signIn } from '../../test/renderApp';
import { server } from '../../test/server';
import { enqueueCheckIn, listQueuedCheckIns } from './offlineQueue';
import { consumeDroppedNotices, flushQueuedCheckIns, subscribeFlushOutcomes } from './offlineSync';

const FIXED_NOW = () => new Date('2026-07-15T18:30:00Z');

function seed(check_in_date: string, walking = 1, stairs = 2, balance_confidence = 3) {
  return enqueueCheckIn({ walking, stairs, balance_confidence, check_in_date }, FIXED_NOW);
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

    const outcome = await flushQueuedCheckIns();

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
    expect(listQueuedCheckIns()).toEqual([]);
  });

  it('is single-flight: concurrent triggers share one pass (the online event can fire repeatedly)', async () => {
    signIn();
    let posts = 0;
    server.use(
      http.post('/adl', async () => {
        posts += 1;
        await delay(30);
        return HttpResponse.json({
          check_in_date: '2026-07-15',
          daily_score: 6,
          superseded: false,
        });
      }),
    );
    seed('2026-07-15');

    const [first, second, third] = await Promise.all([
      flushQueuedCheckIns(),
      flushQueuedCheckIns(),
      flushQueuedCheckIns(),
    ]);

    expect(posts).toBe(1);
    expect(second).toBe(first);
    expect(third).toBe(first);
    // A LATER trigger (after the pass finished) starts a fresh pass.
    seed('2026-07-15');
    await flushQueuedCheckIns();
    expect(posts).toBe(2);
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

    const outcome = await flushQueuedCheckIns();

    expect(outcome.dropped).toHaveLength(1);
    expect(outcome.dropped[0]?.entry.check_in_date).toBe('2026-07-13');
    expect(outcome.dropped[0]?.detail).toBe(refused);
    expect(outcome.synced.map((s) => s.entry.check_in_date)).toEqual(['2026-07-14']);
    expect(listQueuedCheckIns()).toEqual([]);
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
    const outcome = await flushQueuedCheckIns();
    expect(outcome.dropped[0]?.detail).toBe('check_in_date cannot be in the future');
    expect(listQueuedCheckIns()).toEqual([]);
  });

  it('stops on a network failure, leaving the remaining entries queued and emitting nothing', async () => {
    signIn();
    server.use(http.post('/adl', () => HttpResponse.error()));
    const outcomes: unknown[] = [];
    const unsubscribe = subscribeFlushOutcomes((o) => outcomes.push(o));
    seed('2026-07-14');
    seed('2026-07-15');

    const outcome = await flushQueuedCheckIns();

    expect(outcome).toEqual({ synced: [], dropped: [], remaining: 2 });
    expect(listQueuedCheckIns()).toHaveLength(2);
    expect(outcomes).toEqual([]); // nothing happened — no listener noise
    unsubscribe();
  });

  it('stops when auth is expired mid-flush (401 even after refresh), leaving the entry queued', async () => {
    signIn();
    // /adl 401s on every attempt; the refresh itself succeeds, so the session is
    // NOT cleared — the entry must stay queued for a later signed-in flush.
    server.use(http.post('/adl', () => HttpResponse.json({ detail: 'Nope' }, { status: 401 })));
    seed('2026-07-15');

    const outcome = await flushQueuedCheckIns();

    expect(outcome).toEqual({ synced: [], dropped: [], remaining: 1 });
    expect(listQueuedCheckIns()).toHaveLength(1);
  });

  it('does nothing (and posts nothing) when the queue is empty', async () => {
    signIn();
    const bodies = captureAdlPosts();
    const outcome = await flushQueuedCheckIns();
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
    expect(listQueuedCheckIns()).toEqual([]);
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
    expect(listQueuedCheckIns()).toHaveLength(1);
    expect(dispatch.mock.calls.filter(([type]) => type === 'online')).toEqual([]);
    dispatch.mockRestore();
  });
});
