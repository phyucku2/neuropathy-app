/**
 * The patient Visit-Ready Summary handout (ADR-0045), rendered through the whole App so the test
 * also proves the React.lazy route chunk resolves under Suspense and the Sources card links here.
 * Covers: the default render, the window picker refetch (lead-section flip), the print seam, the
 * honest empty state, the error state, and reachability from Sources.
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { VISIT_SUMMARY_INSUFFICIENT, visitSummaryForWindow } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

// The platform seam (ADR-0024), mocked as a local module (the seam lesson from
// ReminderCard.test): web by default; individual tests flip it to native.
vi.mock('../../auth/platform', () => ({
  isNativePlatform: vi.fn(() => false),
  getPlatform: vi.fn(() => 'web'),
}));

import { isNativePlatform } from '../../auth/platform';

const nativeMock = vi.mocked(isNativePlatform);

beforeEach(() => {
  nativeMock.mockReset().mockReturnValue(false);
});

describe('HandoutPage', () => {
  it('renders the summary with the status hero, sourced sections, and the disclaimer', async () => {
    renderApp('/handout');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Visit summary' }),
    ).toBeInTheDocument();

    // The status hero (default 60-day window) + the co-located non-diagnostic note.
    expect(await screen.findByRole('region', { name: /Your 60 days summary/ })).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent(/not a diagnosis/);

    // Sourced sections render.
    expect(screen.getByRole('heading', { name: 'What changed' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Symptoms' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /nerve pain over this window/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Questions to ask' })).toBeInTheDocument();

    // The print affordance.
    expect(screen.getByRole('button', { name: 'Print or save as PDF' })).toBeEnabled();
  });

  it('changes the window and refetches, flipping the lead section', async () => {
    const user = userEvent.setup();
    renderApp('/handout');
    await screen.findByRole('region', { name: /Your 60 days summary/ });

    // Short window leads with the diff.
    let whatChanged = screen.getByRole('heading', { name: 'What changed' });
    let symptoms = screen.getByRole('heading', { name: 'Symptoms' });
    expect(
      whatChanged.compareDocumentPosition(symptoms) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '1 year' }));

    // The refetch re-renders the long window: the hero label updates and the trend now leads.
    expect(await screen.findByRole('region', { name: /Your 1 year summary/ })).toBeInTheDocument();
    whatChanged = screen.getByRole('heading', { name: 'What changed' });
    symptoms = screen.getByRole('heading', { name: 'Symptoms' });
    expect(
      symptoms.compareDocumentPosition(whatChanged) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('hides the stale summary and disables print while a new window is loading (never a relabel)', async () => {
    // Delay only the 1-year response so the in-flight state is observable.
    server.use(
      http.get('/me/visit-summary', async ({ request }) => {
        const windowDays = Number(new URL(request.url).searchParams.get('window') ?? '60');
        if (windowDays === 365) {
          await delay(200);
        }
        return HttpResponse.json(visitSummaryForWindow(windowDays));
      }),
    );
    const user = userEvent.setup();
    renderApp('/handout');
    await screen.findByRole('region', { name: /Your 60 days summary/ });

    await user.click(screen.getByRole('button', { name: '1 year' }));

    // In flight: the old 60-day payload must NOT render under the new "1 year" label — it is
    // hidden entirely — and the mislabel-able sheet is unprintable.
    expect(screen.queryByRole('region', { name: /summary/ })).not.toBeInTheDocument();
    expect(screen.getByText('Preparing your summary…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Print or save as PDF' })).toBeDisabled();

    // The new window arrives and renders under its own label; print re-enables.
    expect(await screen.findByRole('region', { name: /Your 1 year summary/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Print or save as PDF' })).toBeEnabled();
  });

  it('keeps a stale summary under its OWN window label when the refetch fails', async () => {
    server.use(
      http.get('/me/visit-summary', ({ request }) => {
        const windowDays = Number(new URL(request.url).searchParams.get('window') ?? '60');
        if (windowDays === 365) {
          return HttpResponse.json({ detail: 'Summary unavailable' }, { status: 503 });
        }
        return HttpResponse.json(visitSummaryForWindow(windowDays));
      }),
    );
    const user = userEvent.setup();
    renderApp('/handout');
    await screen.findByRole('region', { name: /Your 60 days summary/ });

    await user.click(screen.getByRole('button', { name: '1 year' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Summary unavailable');

    // The still-rendered data is labelled from its own payload (60 days) — never the picker's
    // failed "1 year" — so anything printed can never contradict its label.
    expect(screen.getByRole('region', { name: /Your 60 days summary/ })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /Your 1 year summary/ })).not.toBeInTheDocument();
  });

  it('replaces the dead print button with an honest hint on the native shell', async () => {
    // window.print() is a silent no-op inside the Capacitor webview (printHandout.ts) — the
    // button must not render at all; an honest pointer to the browser shows instead.
    nativeMock.mockReturnValue(true);
    renderApp('/handout');
    await screen.findByRole('region', { name: /Your 60 days summary/ });
    expect(screen.queryByRole('button', { name: 'Print or save as PDF' })).not.toBeInTheDocument();
    expect(screen.getByText(/open this page in your phone’s web browser/)).toBeInTheDocument();
  });

  it('prints through the injected window.print (jsdom has none)', async () => {
    const user = userEvent.setup();
    const print = vi.fn();
    window.print = print as unknown as typeof window.print;
    renderApp('/handout');
    await screen.findByRole('region', { name: /Your 60 days summary/ });
    await user.click(screen.getByRole('button', { name: 'Print or save as PDF' }));
    expect(print).toHaveBeenCalledTimes(1);
  });

  it('shows the honest empty state when there is no composite yet', async () => {
    server.use(http.get('/me/visit-summary', () => HttpResponse.json(VISIT_SUMMARY_INSUFFICIENT)));
    renderApp('/handout');
    expect(await screen.findByText('Not enough data yet')).toBeInTheDocument();
    // No fabricated trend.
    expect(screen.queryByRole('heading', { name: 'Symptoms' })).not.toBeInTheDocument();
  });

  it('shows the error state when the summary read fails', async () => {
    server.use(
      http.get('/me/visit-summary', () =>
        HttpResponse.json({ detail: 'Summary unavailable' }, { status: 503 }),
      ),
    );
    renderApp('/handout');
    expect(await screen.findByRole('alert')).toHaveTextContent('Summary unavailable');
  });

  it('is reachable from the "Open visit summary" card on Sources', async () => {
    const user = userEvent.setup();
    renderApp('/settings');
    const card = (await screen.findByText('Summary for your appointment')).closest('.card');
    expect(card).not.toBeNull();
    await user.click(within(card as HTMLElement).getByRole('link', { name: 'Open visit summary' }));
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: 'Visit summary' })).toBeInTheDocument();
    });
  });
});
