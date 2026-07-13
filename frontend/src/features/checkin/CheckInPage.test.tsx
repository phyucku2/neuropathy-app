import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import type { AdlCheckInIn } from '../../api/types';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';
import { localCheckInDate } from './CheckInPage';

async function answerAll(user: ReturnType<typeof userEvent.setup>) {
  const groups = await screen.findAllByRole('radiogroup');
  expect(groups).toHaveLength(3);
  await user.click(screen.getAllByRole('radio', { name: '3' })[0] as HTMLElement);
  await user.click(screen.getAllByRole('radio', { name: '2' })[1] as HTMLElement);
  await user.click(screen.getByRole('radio', { name: '4 — Very confident' }));
}

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

  it('shows a friendly message on other failures', async () => {
    server.use(http.post('/adl', () => new HttpResponse(null, { status: 500 })));
    const user = userEvent.setup();
    renderApp('/check-in');
    await answerAll(user);
    await user.click(screen.getByRole('button', { name: 'Save my check-in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong');
  });
});
