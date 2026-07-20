/**
 * The patient Visit-Ready Summary handout (ADR-0045), rendered through the whole App so the test
 * also proves the React.lazy route chunk resolves under Suspense and the Sources card links here.
 * Covers: the default render, the window picker refetch (lead-section flip), the print seam, the
 * honest empty state, the error state, and reachability from Sources.
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { VISIT_SUMMARY_INSUFFICIENT } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

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
