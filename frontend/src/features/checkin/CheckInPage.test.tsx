import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import type { AdlCheckInIn } from '../../api/types';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

async function answerAll(user: ReturnType<typeof userEvent.setup>) {
  const groups = await screen.findAllByRole('radiogroup');
  expect(groups).toHaveLength(3);
  await user.click(screen.getAllByRole('radio', { name: '3' })[0] as HTMLElement);
  await user.click(screen.getAllByRole('radio', { name: '2' })[1] as HTMLElement);
  await user.click(screen.getAllByRole('radio', { name: '4' })[2] as HTMLElement);
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

  it('posts the answers and shows the daily score', async () => {
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
    expect(received).toEqual({ walking: 3, stairs: 2, balance_confidence: 4 });
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
