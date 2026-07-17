/**
 * Your Records (read-only, display-only). Rendered through the whole App so the test
 * also proves the React.lazy route chunk resolves under Suspense in jsdom and that the
 * Sources card links here. Exercises the three states (connected + records, connected
 * but empty, not connected), the read-only/non-judged rendering of EMR rows, the
 * "coming soon" placeholders, and the disclaimer.
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { CAPABILITIES, OBSERVATIONS } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

/** Capabilities with the medical-record connection toggle OFF (the not-connected state). */
const CAPABILITIES_EMR_OFF = CAPABILITIES.map((row) =>
  row.key === 'emr_connect' ? { ...row, active: false } : row,
);

describe('RecordsPage', () => {
  it('shows EMR records read-only with provenance, plus placeholders and the disclaimer', async () => {
    renderApp('/records');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Your records' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/A read-only copy of the records retrieved/)).toBeInTheDocument();

    // The two EMR-sourced fixture rows render with value+unit and a date.
    const glucose = screen.getByText('Glucose').closest('.record');
    expect(glucose).not.toBeNull();
    expect(glucose as HTMLElement).toHaveTextContent('101 mg/dL');
    expect(glucose as HTMLElement).toHaveTextContent('Jun 15, 2026');
    expect(screen.getByText('Vitamin B12').closest('.record')).toHaveTextContent('420 pg/mL');

    // Provenance line — one per EMR row, never judged.
    expect(screen.getAllByText('from your health record')).toHaveLength(2);

    // Read-only, display-only: NO interpretation / judged direction / diagnosis.
    expect(screen.queryByText(/is better for this measure/)).not.toBeInTheDocument();
    expect(screen.queryByText(/· better/)).not.toBeInTheDocument();
    expect(screen.queryByText(/· worse/)).not.toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Pick a measure' })).not.toBeInTheDocument();

    // Non-EMR sources (BioMech, check-ins) are NOT shown here — that's Trends.
    expect(screen.queryByText('Balance score')).not.toBeInTheDocument();

    // "Coming soon" placeholders for the classes we don't pull yet.
    for (const title of ['Conditions', 'Medications', 'Allergies']) {
      expect(screen.getByRole('heading', { level: 2, name: title })).toBeInTheDocument();
    }
    expect(screen.getAllByText('Coming soon')).toHaveLength(3);
    expect(
      screen.getAllByText(/We'll show these here once we can read them from your record\./),
    ).toHaveLength(3);

    // The read-only, non-diagnostic disclaimer.
    expect(
      screen.getByText(/This is a read-only copy of your health record, not medical advice/),
    ).toBeInTheDocument();
  });

  it('shows the "nothing pulled yet" empty state when connected but no EMR records', async () => {
    // Connection on (default caps), but /observations has only non-EMR sources.
    server.use(
      http.get('/observations', () =>
        HttpResponse.json({
          items: OBSERVATIONS.filter((item) => item.source !== 'emr'),
          total: OBSERVATIONS.length,
          limit: 100,
          offset: 0,
        }),
      ),
    );
    renderApp('/records');

    expect(await screen.findByText('No results pulled from your record yet.')).toBeInTheDocument();
    // Placeholders still render; still no EMR rows.
    expect(screen.getByRole('heading', { level: 2, name: 'Medications' })).toBeInTheDocument();
    expect(screen.queryByText('from your health record')).not.toBeInTheDocument();
  });

  it('shows the gentle connect prompt pointing to Sources when not connected', async () => {
    server.use(
      http.get('/capabilities', () => HttpResponse.json({ capabilities: CAPABILITIES_EMR_OFF })),
    );
    renderApp('/records');

    expect(await screen.findByText('No health record connected yet.')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'Go to Sources' });
    expect(link).toHaveAttribute('href', '/settings');
    // Even with no connection, we're honest about what's coming.
    expect(screen.getByRole('heading', { level: 2, name: 'Allergies' })).toBeInTheDocument();
  });

  it('shows the error state when the records read fails', async () => {
    server.use(
      http.get('/observations', () =>
        HttpResponse.json({ detail: 'Storage unavailable' }, { status: 503 }),
      ),
    );
    renderApp('/records');
    expect(await screen.findByRole('alert')).toHaveTextContent('Storage unavailable');
  });

  it('is reachable from the "View your records" card on Sources', async () => {
    const user = userEvent.setup();
    renderApp('/settings');

    const card = (await screen.findByText('Your health record')).closest('.card');
    expect(card).not.toBeNull();
    await user.click(within(card as HTMLElement).getByRole('link', { name: 'View your records' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Your records' }),
    ).toBeInTheDocument();
  });
});
