import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';
import type { AdlCheckInIn, CapabilityStateOut } from '../../api/types';
import { CAPABILITIES, ME } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';
import { localCheckInDate } from './CheckInPage';
import { enqueueCheckIn, listQueuedCheckIns } from './offlineQueue';
import { consumeDroppedNotices } from './offlineSync';

/** The signed-in account (msw /auth/me returns ME) — the queue's owner. */
const OWNER = ME.user_id;

/** Capabilities with the opt-in symptom capture (ADR-0034) turned ON. */
function withSymptomsOn(): CapabilityStateOut[] {
  return CAPABILITIES.map((c) => (c.key === 'ingest_symptoms' ? { ...c, active: true } : c));
}

async function answerAll(user: ReturnType<typeof userEvent.setup>) {
  const groups = await screen.findAllByRole('radiogroup');
  expect(groups).toHaveLength(3);
  await user.click(screen.getAllByRole('radio', { name: '3' })[0] as HTMLElement);
  await user.click(screen.getAllByRole('radio', { name: '2' })[1] as HTMLElement);
  await user.click(screen.getByRole('radio', { name: '4 — Very confident' }));
}

beforeEach(() => {
  localStorage.clear();
  consumeDroppedNotices();
});

describe('CheckInPage', () => {
  it('keeps Save disabled until all three questions are answered', async () => {
    const user = userEvent.setup();
    renderApp('/check-in');
    const save = await screen.findByRole('button', { name: 'Save my check-in' });
    expect(save).toBeDisabled();
    await user.click(screen.getAllByRole('radio', { name: '3' })[0] as HTMLElement);
    expect(save).toBeDisabled();
    await answerAll(user);
    expect(save).toBeEnabled();
  });

  it('posts the answers with the browser-local calendar day and shows the daily score', async () => {
    let received: AdlCheckInIn | null = null;
    server.use(
      http.post('/adl', async ({ request }) => {
        received = (await request.json()) as AdlCheckInIn;
        return HttpResponse.json({
          check_in_date: '2026-07-13',
          daily_score: 9,
          superseded: false,
        });
      }),
    );
    const user = userEvent.setup();
    renderApp('/check-in');
    await answerAll(user);
    await user.click(screen.getByRole('button', { name: 'Save my check-in' }));
    expect(await screen.findByText('Check-in saved')).toBeInTheDocument();
    expect(screen.getByText('9 of 12')).toBeInTheDocument();
    expect(screen.queryByText(/This replaces the check-in/)).not.toBeInTheDocument();
    // check_in_date is the browser-LOCAL day (built from local date parts, not
    // UTC), so an evening check-in west of UTC stays on today's calendar day.
    const now = new Date();
    const localDay = `${String(now.getFullYear())}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    expect(received).toEqual({
      walking: 3,
      stairs: 2,
      balance_confidence: 4,
      check_in_date: localDay,
    });
  });

  it('localCheckInDate uses local date parts, never the UTC day', () => {
    // 23:30 on Jul 13 in a UTC-7 zone is 06:30 Jul 14 UTC; the local day must win.
    const lateEvening = new Date(2026, 6, 13, 23, 30, 0);
    expect(localCheckInDate(lateEvening)).toBe('2026-07-13');
    expect(localCheckInDate(new Date(2026, 0, 5))).toBe('2026-01-05');
  });

  it('exposes the scale anchors to assistive tech via accessible names', async () => {
    renderApp('/check-in');
    await screen.findAllByRole('radiogroup');
    // Endpoint options carry the anchor meaning in their accessible name
    // (walking and stairs share the same Very hard/Easy anchors).
    expect(screen.getAllByRole('radio', { name: '0 — Very hard' })).toHaveLength(2);
    expect(screen.getAllByRole('radio', { name: '4 — Easy' })).toHaveLength(2);
    expect(screen.getByRole('radio', { name: '0 — Not confident' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '4 — Very confident' })).toBeInTheDocument();
    // The visible anchor row is no longer hidden from AT.
    expect(screen.getByText('0 · Not confident')).toBeVisible();
    expect(screen.getByText('0 · Not confident')).not.toHaveAttribute('aria-hidden');
  });

  it('moves and selects with arrow keys, with a roving tabindex', async () => {
    const user = userEvent.setup();
    renderApp('/check-in');
    const groups = await screen.findAllByRole('radiogroup');
    const walking = within(groups[0] as HTMLElement);
    const first = walking.getByRole('radio', { name: '0 — Very hard' });

    // Before any selection, only the first option is in the tab order.
    expect(first).toHaveAttribute('tabindex', '0');
    expect(walking.getByRole('radio', { name: '2' })).toHaveAttribute('tabindex', '-1');

    first.focus();
    await user.keyboard('{ArrowRight}');
    expect(walking.getByRole('radio', { name: '1' })).toBeChecked();
    expect(walking.getByRole('radio', { name: '1' })).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(walking.getByRole('radio', { name: '2' })).toBeChecked();
    await user.keyboard('{ArrowLeft}');
    await user.keyboard('{ArrowUp}');
    expect(first).toBeChecked();
    // Wrap-around: ArrowLeft from 0 lands on 4.
    await user.keyboard('{ArrowLeft}');
    expect(walking.getByRole('radio', { name: '4 — Easy' })).toBeChecked();
    expect(walking.getByRole('radio', { name: '4 — Easy' })).toHaveFocus();

    // Roving tabindex follows the selection; other keys leave it untouched.
    expect(walking.getByRole('radio', { name: '4 — Easy' })).toHaveAttribute('tabindex', '0');
    expect(first).toHaveAttribute('tabindex', '-1');
    await user.keyboard('a');
    expect(walking.getByRole('radio', { name: '4 — Easy' })).toBeChecked();
  });

  it('shows the superseded notice when the day is re-submitted', async () => {
    server.use(
      http.post('/adl', () =>
        HttpResponse.json({ check_in_date: '2026-07-13', daily_score: 9, superseded: true }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/check-in');
    await answerAll(user);
    await user.click(screen.getByRole('button', { name: 'Save my check-in' }));
    expect(
      await screen.findByText(/This replaces the check-in you already did today/),
    ).toBeInTheDocument();
  });

  it("handles the 409 'feature turned off' refusal with a link to Sources", async () => {
    server.use(
      http.post('/adl', () =>
        HttpResponse.json({ detail: 'Daily function check-in is turned off' }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/check-in');
    await answerAll(user);
    await user.click(screen.getByRole('button', { name: 'Save my check-in' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Daily function check-in is turned off');
    expect(screen.getByRole('link', { name: /turn it back on in Sources/ })).toBeInTheDocument();
  });

  it('shows a friendly message on other API failures — a 500 is NEVER queued offline', async () => {
    server.use(http.post('/adl', () => new HttpResponse(null, { status: 500 })));
    const user = userEvent.setup();
    renderApp('/check-in');
    await answerAll(user);
    await user.click(screen.getByRole('button', { name: 'Save my check-in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong');
    // The network-vs-API split (ADR-0030): an API error means the server SAW the
    // request — queueing it would risk a duplicate; only network failures queue.
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it('queues the check-in on a NETWORK failure and shows the saved-on-device status', async () => {
    server.use(http.post('/adl', () => HttpResponse.error()));
    const user = userEvent.setup();
    renderApp('/check-in');
    await answerAll(user);
    await user.click(screen.getByRole('button', { name: 'Save my check-in' }));

    expect(
      await screen.findByRole('heading', { name: 'Check-in saved on this device' }),
    ).toBeInTheDocument();
    // role=status (polite live region), not an alert — this is a success variant.
    expect(screen.getByRole('status')).toHaveTextContent(
      "Saved on this device — will send automatically when you're back online.",
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(listQueuedCheckIns(OWNER)).toEqual([
      {
        walking: 3,
        stairs: 2,
        balance_confidence: 4,
        check_in_date: localCheckInDate(),
        queued_at: expect.any(String) as string,
      },
    ]);
  });

  it('flips the offline-saved state to the real saved view when connectivity returns', async () => {
    let offline = true;
    server.use(
      http.post('/adl', async ({ request }) => {
        if (offline) {
          return HttpResponse.error();
        }
        const body = (await request.json()) as AdlCheckInIn;
        return HttpResponse.json({
          check_in_date: body.check_in_date,
          daily_score: body.walking + body.stairs + body.balance_confidence,
          superseded: false,
        });
      }),
    );
    const user = userEvent.setup();
    renderApp('/check-in');
    await answerAll(user);
    await user.click(screen.getByRole('button', { name: 'Save my check-in' }));
    await screen.findByRole('heading', { name: 'Check-in saved on this device' });

    // Connectivity returns: the 'online' event triggers the flush, and the page
    // reflects the server's REAL response for the queued entry.
    offline = false;
    window.dispatchEvent(new Event('online'));

    expect(await screen.findByRole('heading', { name: 'Check-in saved' })).toBeInTheDocument();
    expect(screen.getByText('9 of 12')).toBeInTheDocument();
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it('shows a queued same-day entry on load and lets a new submission replace it', async () => {
    let offline = true;
    server.use(
      http.post('/adl', async ({ request }) => {
        if (offline) {
          return HttpResponse.error();
        }
        const body = (await request.json()) as AdlCheckInIn;
        return HttpResponse.json({
          check_in_date: body.check_in_date,
          daily_score: body.walking + body.stairs + body.balance_confidence,
          superseded: true,
        });
      }),
    );
    enqueueCheckIn(OWNER, {
      walking: 1,
      stairs: 2,
      balance_confidence: 0,
      check_in_date: localCheckInDate(),
    });
    const user = userEvent.setup();
    renderApp('/check-in');

    // The pending entry is visible, with its values, in a polite live region.
    const notice = await screen.findByText(/A check-in from today is saved on this device/);
    expect(notice).toHaveTextContent(
      'A check-in from today is saved on this device, waiting to send: walking 1, stairs 2, balance 0. Submitting again replaces it.',
    );
    expect(notice).toHaveAttribute('role', 'status');

    // A new submission (now online) REPLACES the queued one — one check-in per
    // day, newest wins (ADR-0006 mirrored on-device).
    offline = false;
    await answerAll(user);
    await user.click(screen.getByRole('button', { name: 'Save my check-in' }));
    expect(await screen.findByRole('heading', { name: 'Check-in saved' })).toBeInTheDocument();
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it('flushes OLDER queued days after a successful new submission', async () => {
    const bodies: AdlCheckInIn[] = [];
    server.use(
      http.post('/adl', async ({ request }) => {
        const body = (await request.json()) as AdlCheckInIn;
        bodies.push(body);
        return HttpResponse.json({
          check_in_date: body.check_in_date,
          daily_score: 6,
          superseded: false,
        });
      }),
    );
    enqueueCheckIn(OWNER, {
      walking: 2,
      stairs: 2,
      balance_confidence: 2,
      check_in_date: '2020-01-01',
    });
    const user = userEvent.setup();
    renderApp('/check-in');
    // The boot flush may already have sent the old entry; a successful submit
    // must trigger a flush too, so drain and re-seed AFTER load to isolate the
    // post-submit trigger.
    await screen.findAllByRole('radiogroup');
    bodies.length = 0;
    enqueueCheckIn(OWNER, {
      walking: 2,
      stairs: 2,
      balance_confidence: 2,
      check_in_date: '2020-01-01',
    });

    await answerAll(user);
    await user.click(screen.getByRole('button', { name: 'Save my check-in' }));
    await screen.findByRole('heading', { name: 'Check-in saved' });
    await waitFor(() => {
      expect(bodies.map((b) => b.check_in_date)).toEqual([localCheckInDate(), '2020-01-01']);
    });
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it('surfaces a one-time notice when a background flush drops a refused entry', async () => {
    server.use(
      http.post('/adl', () =>
        HttpResponse.json({ detail: 'This check-in is turned off right now.' }, { status: 409 }),
      ),
    );
    enqueueCheckIn(OWNER, {
      walking: 1,
      stairs: 1,
      balance_confidence: 1,
      check_in_date: '2026-07-14',
    });
    renderApp('/check-in');

    // The boot flush (OfflineCheckInSync) hits the 409 → the entry is dropped and
    // the refusal surfaces ONCE, with the entry's day.
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      "An offline check-in from Jul 14 couldn't be sent: This check-in is turned off right now.",
    );
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
    expect(consumeDroppedNotices()).toEqual([]);
  });

  it('leaves the saved-on-device state when the flush DROPS this page’s own entry (the refusal becomes primary)', async () => {
    let offline = true;
    server.use(
      http.post('/adl', () => {
        if (offline) {
          return HttpResponse.error();
        }
        return HttpResponse.json(
          { detail: 'This check-in is turned off right now.' },
          { status: 409 },
        );
      }),
    );
    const user = userEvent.setup();
    renderApp('/check-in');
    await answerAll(user);
    await user.click(screen.getByRole('button', { name: 'Save my check-in' }));
    await screen.findByRole('heading', { name: 'Check-in saved on this device' });

    // Connectivity returns, but the server REFUSES the queued entry (409): the
    // "will send automatically" promise no longer holds, so the success state
    // must not persist — the refusal notice is now the primary message.
    offline = false;
    window.dispatchEvent(new Event('online'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      /An offline check-in from .+ couldn't be sent: This check-in is turned off right now\./,
    );
    expect(
      screen.queryByRole('heading', { name: 'Check-in saved on this device' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/will send automatically/)).not.toBeInTheDocument();
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it('dedupes identical consecutive sync notices (and keys them stably)', async () => {
    const refused = 'This check-in is turned off right now.';
    server.use(http.post('/adl', () => HttpResponse.json({ detail: refused }, { status: 409 })));
    enqueueCheckIn(OWNER, {
      walking: 1,
      stairs: 1,
      balance_confidence: 1,
      check_in_date: '2026-07-14',
    });
    renderApp('/check-in');
    await screen.findByRole('alert');

    // The same day is captured offline again and refused again — the resulting
    // notice text is IDENTICAL to the one already shown, so it collapses into
    // one instead of stacking duplicates.
    enqueueCheckIn(OWNER, {
      walking: 2,
      stairs: 2,
      balance_confidence: 2,
      check_in_date: '2026-07-14',
    });
    window.dispatchEvent(new Event('online'));
    await waitFor(() => {
      expect(listQueuedCheckIns(OWNER)).toEqual([]);
    });

    const alerts = screen.getAllByRole('alert');
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent(
      `An offline check-in from Jul 14 couldn't be sent: ${refused}`,
    );
  });

  it('never shows or flushes ANOTHER account’s queued entries (shared-browser scenario)', async () => {
    // Patient A captured a check-in offline on this browser, then A's tab closed
    // without a logout — the entry is still on disk when patient B signs in.
    const FOREIGN_OWNER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
    enqueueCheckIn(FOREIGN_OWNER, {
      walking: 1,
      stairs: 2,
      balance_confidence: 3,
      check_in_date: localCheckInDate(),
    });
    const bodies: AdlCheckInIn[] = [];
    server.use(
      http.post('/adl', async ({ request }) => {
        const body = (await request.json()) as AdlCheckInIn;
        bodies.push(body);
        return HttpResponse.json({
          check_in_date: body.check_in_date,
          daily_score: 6,
          superseded: false,
        });
      }),
    );

    // B (the ME account) boots the app on the check-in page.
    renderApp('/check-in');
    await screen.findAllByRole('radiogroup');

    // B sees NO queued-today notice for A's entry...
    expect(screen.queryByText(/saved on this device, waiting to send/)).not.toBeInTheDocument();
    // ...the boot flush posts NOTHING of A's into B's record...
    await new Promise((resolve) => setTimeout(resolve, 25));
    expect(bodies).toEqual([]);
    // ...and confirming B's profile purged A's foreign entries entirely.
    await waitFor(() => {
      expect(listQueuedCheckIns(FOREIGN_OWNER)).toEqual([]);
    });
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  it('keeps the same account’s queue across a sign-out-free reload (same-user round trip)', async () => {
    // The ME account queued an OLD day earlier; the same account reopening the
    // app must still see + flush it (per-user binding never drops OWN entries).
    const bodies: AdlCheckInIn[] = [];
    server.use(
      http.post('/adl', async ({ request }) => {
        const body = (await request.json()) as AdlCheckInIn;
        bodies.push(body);
        return HttpResponse.json({
          check_in_date: body.check_in_date,
          daily_score: 6,
          superseded: false,
        });
      }),
    );
    enqueueCheckIn(OWNER, {
      walking: 1,
      stairs: 2,
      balance_confidence: 3,
      check_in_date: '2026-07-01',
    });
    renderApp('/check-in');
    await screen.findAllByRole('radiogroup');
    await waitFor(() => {
      expect(bodies.map((b) => b.check_in_date)).toEqual(['2026-07-01']);
    });
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });

  // ---- symptom capture toggle (ADR-0034 Phase 1) ----

  it('hides the pain and numbness questions when symptom capture is off (default)', async () => {
    renderApp('/check-in');
    // The default capabilities fixture has ingest_symptoms off — only the three
    // function questions render, exactly as before symptom capture existed.
    const groups = await screen.findAllByRole('radiogroup');
    expect(groups).toHaveLength(3);
    expect(screen.queryByText('Symptoms today')).not.toBeInTheDocument();
    expect(screen.queryByRole('radiogroup', { name: /worst pain/i })).not.toBeInTheDocument();
  });

  it('shows pain + numbness when the toggle is on and includes them in the POST', async () => {
    let received: AdlCheckInIn | null = null;
    server.use(
      http.get('/capabilities', () => HttpResponse.json({ capabilities: withSymptomsOn() })),
      http.post('/adl', async ({ request }) => {
        received = (await request.json()) as AdlCheckInIn;
        return HttpResponse.json({
          check_in_date: '2026-07-13',
          daily_score: 9,
          superseded: false,
        });
      }),
    );
    const user = userEvent.setup();
    renderApp('/check-in');
    // Five questions now: three function + two symptom (0-10).
    await waitFor(() => {
      expect(screen.getAllByRole('radiogroup')).toHaveLength(5);
    });
    const groups = screen.getAllByRole('radiogroup');
    const save = screen.getByRole('button', { name: 'Save my check-in' });

    // Function answers alone are NOT enough while symptom capture is on.
    await user.click(within(groups[0] as HTMLElement).getByRole('radio', { name: '3' }));
    await user.click(within(groups[1] as HTMLElement).getByRole('radio', { name: '2' }));
    await user.click(
      within(groups[2] as HTMLElement).getByRole('radio', { name: '4 — Very confident' }),
    );
    expect(save).toBeDisabled();

    // The symptom scales anchor 0 = none, 10 = worst (higher = worse).
    const pain = within(
      screen.getByRole('radiogroup', { name: 'What was your worst pain today?' }),
    );
    expect(pain.getByRole('radio', { name: '0 — No pain' })).toBeInTheDocument();
    expect(pain.getByRole('radio', { name: '10 — Worst imaginable' })).toBeInTheDocument();
    await user.click(pain.getByRole('radio', { name: '7' }));
    const numbness = within(
      screen.getByRole('radiogroup', { name: 'How strong was any numbness or tingling today?' }),
    );
    await user.click(numbness.getByRole('radio', { name: '3' }));
    expect(save).toBeEnabled();

    await user.click(save);
    expect(await screen.findByText('Check-in saved')).toBeInTheDocument();
    const now = new Date();
    const localDay = `${String(now.getFullYear())}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    expect(received).toEqual({
      walking: 3,
      stairs: 2,
      balance_confidence: 4,
      check_in_date: localDay,
      pain: 7,
      numbness: 3,
    });
  });

  it('queues the symptom answers offline and flushes them when back online', async () => {
    let offline = true;
    const bodies: AdlCheckInIn[] = [];
    server.use(
      http.get('/capabilities', () => HttpResponse.json({ capabilities: withSymptomsOn() })),
      http.post('/adl', async ({ request }) => {
        const body = (await request.json()) as AdlCheckInIn;
        if (offline) {
          return HttpResponse.error();
        }
        bodies.push(body);
        return HttpResponse.json({
          check_in_date: body.check_in_date,
          daily_score: 9,
          superseded: false,
        });
      }),
    );
    const user = userEvent.setup();
    renderApp('/check-in');
    await waitFor(() => {
      expect(screen.getAllByRole('radiogroup')).toHaveLength(5);
    });
    const groups = screen.getAllByRole('radiogroup');
    await user.click(within(groups[0] as HTMLElement).getByRole('radio', { name: '3' }));
    await user.click(within(groups[1] as HTMLElement).getByRole('radio', { name: '2' }));
    await user.click(
      within(groups[2] as HTMLElement).getByRole('radio', { name: '4 — Very confident' }),
    );
    await user.click(within(groups[3] as HTMLElement).getByRole('radio', { name: '7' }));
    await user.click(within(groups[4] as HTMLElement).getByRole('radio', { name: '3' }));
    await user.click(screen.getByRole('button', { name: 'Save my check-in' }));

    await screen.findByRole('heading', { name: 'Check-in saved on this device' });
    // The queued entry carries the symptom answers (ADR-0034), not just the function ones.
    expect(listQueuedCheckIns(OWNER)).toEqual([
      {
        walking: 3,
        stairs: 2,
        balance_confidence: 4,
        pain: 7,
        numbness: 3,
        check_in_date: localCheckInDate(),
        queued_at: expect.any(String) as string,
      },
    ]);

    // Connectivity returns: the flush sends pain + numbness through to the server.
    offline = false;
    window.dispatchEvent(new Event('online'));
    await screen.findByRole('heading', { name: 'Check-in saved' });
    await waitFor(() => {
      expect(bodies).toHaveLength(1);
    });
    expect(bodies[0]).toMatchObject({ pain: 7, numbness: 3 });
    expect(listQueuedCheckIns(OWNER)).toEqual([]);
  });
});
