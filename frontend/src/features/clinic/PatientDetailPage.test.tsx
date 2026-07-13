import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import type { ObservationItem } from '../../api/types';
import { PANEL_PATIENT_ID } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { actAsClinician, server } from '../../test/server';
import { NON_DIAGNOSTIC_TEXT } from './NonDiagnosticNote';

const DETAIL_PATH = `/clinic/patients/${PANEL_PATIENT_ID}`;

async function openTab(name: string) {
  const user = userEvent.setup();
  renderApp(DETAIL_PATH);
  await screen.findByRole('heading', { name: 'Pat Example' });
  await user.click(screen.getByRole('button', { name }));
  return user;
}

describe('PatientDetailPage — trajectory tab', () => {
  it('shows the deterministic hero, signals, gaps, and the non-diagnostic disclaimer', async () => {
    actAsClinician();
    renderApp(DETAIL_PATH);
    expect(await screen.findByRole('heading', { name: 'Pat Example' })).toBeInTheDocument();
    expect(screen.getByText('Consented Jun 1, 2026')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '← Back to panel' })).toHaveAttribute(
      'href',
      '/clinic',
    );

    // The deterministic summary is ALWAYS shown (never the AI narrator, ADR-0012).
    const hero = await screen.findByRole('region', { name: '30-day trend for Pat Example' });
    expect(hero).toHaveClass('traj', 'improving');
    expect(screen.getByText('Improving')).toBeInTheDocument();
    expect(screen.getByText(/Balance and daily function are up/)).toBeInTheDocument();
    expect(screen.queryByText(/AI-written summary/)).not.toBeInTheDocument();

    // Non-diagnostic posture (product requirement from the mockup).
    expect(screen.getByText(NON_DIAGNOSTIC_TEXT)).toBeInTheDocument();

    // Signals and gaps reuse the shared trajectory components.
    expect(screen.getByText('Balance score')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'improving' })).toHaveTextContent('↑');
    expect(screen.getByText('No lab results in the last 90 days')).toBeInTheDocument();
  });

  it('renders the neutral not-found screen when the trajectory read is 404', async () => {
    actAsClinician();
    server.use(
      http.get('/clinic/patients/:patientId/trajectory', () =>
        HttpResponse.json({ detail: 'Patient not found' }, { status: 404 }),
      ),
    );
    renderApp(DETAIL_PATH);
    expect(await screen.findByRole('heading', { name: 'Patient not found' })).toBeInTheDocument();
  });
});

describe('PatientDetailPage — cross-source trend table', () => {
  it('shows one judged row per metric and never says "stable"', async () => {
    actAsClinician();
    await openTab('Trend table');
    expect(await screen.findByRole('heading', { name: 'What the data shows' })).toBeInTheDocument();

    // Balance score: 57 → 64 → 65 (higher is better) — judged better.
    const balanceRow = screen.getByRole('row', { name: /Balance score/ });
    expect(balanceRow).toHaveTextContent('BioMech');
    expect(balanceRow).toHaveTextContent('65 score · Jul 2, 2026');
    expect(balanceRow).toHaveTextContent('↑ 1');
    expect(balanceRow).toHaveTextContent('better');

    // Sway velocity: 12.9 → 11.4 (LOWER is better) — a falling line judged better.
    const swayRow = screen.getByRole('row', { name: /Sway velocity/ });
    expect(swayRow).toHaveTextContent('↓ 1.5');
    expect(swayRow).toHaveTextContent('better');

    // A single lab reading is never judged.
    const labRow = screen.getByRole('row', { name: /Long-term blood sugar/ });
    expect(labRow).toHaveTextContent('Lab');
    expect(labRow).toHaveTextContent('single reading');
    expect(labRow).toHaveTextContent('not judged');

    // The word "stable" is a clinical claim this table must never fabricate.
    expect(screen.queryByText(/stable/i)).not.toBeInTheDocument();

    // The disclaimer sits under the table too.
    expect(screen.getByText(NON_DIAGNOSTIC_TEXT)).toBeInTheDocument();
  });

  it('shows an empty state when there are no numeric readings', async () => {
    actAsClinician();
    server.use(
      http.get('/clinic/patients/:patientId/observations', () =>
        HttpResponse.json({ items: [], total: 0, limit: 100, offset: 0 }),
      ),
    );
    await openTab('Trend table');
    expect(await screen.findByText(/No numeric readings/)).toBeInTheDocument();
  });

  it('renders the neutral not-found screen on a 404', async () => {
    actAsClinician();
    server.use(
      http.get('/clinic/patients/:patientId/observations', () =>
        HttpResponse.json({ detail: 'Patient not found' }, { status: 404 }),
      ),
    );
    await openTab('Trend table');
    expect(await screen.findByRole('heading', { name: 'Patient not found' })).toBeInTheDocument();
  });
});

function syntheticObservations(count: number): ObservationItem[] {
  return Array.from({ length: count }, (_, index) => ({
    code: 'adl_daily_score',
    display: 'Daily function score',
    value: 10 + index,
    value_text: null,
    unit: '{score}',
    effective_at: `2026-06-${String((index % 28) + 1).padStart(2, '0')}T10:00:00Z`,
    source: 'adl',
    status: 'final',
  }));
}

describe('PatientDetailPage — observations tab', () => {
  it('lists the page of raw records with values, sources, and dates', async () => {
    actAsClinician();
    await openTab('Observations');
    expect(await screen.findByText('Showing 1–6 of 6')).toBeInTheDocument();
    const labRow = screen.getByRole('row', { name: /Hemoglobin A1c/ });
    expect(labRow).toHaveTextContent('7.2 %');
    expect(labRow).toHaveTextContent('Lab');
    expect(labRow).toHaveTextContent('Jun 20, 2026');
    expect(labRow).toHaveTextContent('final');
    // A single page: both pager buttons disabled.
    expect(screen.getByRole('button', { name: 'Newer' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Older' })).toBeDisabled();
  });

  it('pages forward and back with limit/offset', async () => {
    actAsClinician();
    const all = syntheticObservations(25);
    server.use(
      http.get('/clinic/patients/:patientId/observations', ({ request }) => {
        const url = new URL(request.url);
        const limit = Number(url.searchParams.get('limit') ?? '50');
        const offset = Number(url.searchParams.get('offset') ?? '0');
        return HttpResponse.json({
          items: all.slice(offset, offset + limit),
          total: all.length,
          limit,
          offset,
        });
      }),
    );
    const user = await openTab('Observations');
    expect(await screen.findByText('Showing 1–20 of 25')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Newer' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Older' }));
    expect(await screen.findByText('Showing 21–25 of 25')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Older' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Newer' }));
    expect(await screen.findByText('Showing 1–20 of 25')).toBeInTheDocument();
  });

  it('shows an empty state for a patient with no observations', async () => {
    actAsClinician();
    server.use(
      http.get('/clinic/patients/:patientId/observations', () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    );
    await openTab('Observations');
    expect(await screen.findByText('No observations recorded yet.')).toBeInTheDocument();
  });

  it('renders the neutral not-found screen on a 404', async () => {
    actAsClinician();
    server.use(
      http.get('/clinic/patients/:patientId/observations', () =>
        HttpResponse.json({ detail: 'Patient not found' }, { status: 404 }),
      ),
    );
    await openTab('Observations');
    expect(await screen.findByRole('heading', { name: 'Patient not found' })).toBeInTheDocument();
  });
});

describe('PatientDetailPage — features tab (capability orders)', () => {
  it('renders toggles with expiry and read-only rows for unwired capabilities', async () => {
    actAsClinician();
    await openTab('Features');
    const biomech = await screen.findByRole('switch', { name: 'BioMech report upload' });
    expect(biomech).toBeChecked();
    expect(screen.getByText('renews Aug 6, 2026')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Daily function check-in' })).not.toBeChecked();
    // enforced=false: read-only, no switch offered.
    expect(screen.queryByRole('switch', { name: 'AI trajectory summary' })).not.toBeInTheDocument();
    expect(screen.getByText('Not wired yet')).toBeInTheDocument();
    expect(screen.getByText('Changes are logged and shown to the patient.')).toBeInTheDocument();
  });

  it('turns a capability on through the server-confirmed state', async () => {
    actAsClinician();
    const user = await openTab('Features');
    const adl = await screen.findByRole('switch', { name: 'Daily function check-in' });
    await user.click(adl);
    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Daily function check-in' })).toBeChecked();
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('sets an order-style renewal date on an active capability', async () => {
    actAsClinician();
    const user = await openTab('Features');
    await screen.findByRole('switch', { name: 'Lab result upload' });
    fireEvent.change(screen.getByLabelText('Renewal date for Lab result upload'), {
      target: { value: '2026-09-01' },
    });
    await user.click(screen.getByRole('button', { name: 'Set renewal for Lab result upload' }));
    expect(await screen.findByText('renews Sep 1, 2026')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('surfaces the backend 422 verbatim when renewing an inactive capability', async () => {
    actAsClinician();
    const user = await openTab('Features');
    await screen.findByRole('switch', { name: 'Daily function check-in' });
    fireEvent.change(screen.getByLabelText('Renewal date for Daily function check-in'), {
      target: { value: '2026-09-01' },
    });
    await user.click(
      screen.getByRole('button', { name: 'Set renewal for Daily function check-in' }),
    );
    // The backend's own wording, not a rewrite (ADR-0013 expiry-only-with-enable).
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'expires_at only applies when active=true; omit it when disabling',
    );
    // The row keeps its server state.
    expect(screen.getByRole('switch', { name: 'Daily function check-in' })).not.toBeChecked();
  });

  it('shows the error state when the capabilities read fails', async () => {
    actAsClinician();
    server.use(
      http.get('/clinic/patients/:patientId/capabilities', () =>
        HttpResponse.json({ detail: 'Capabilities unavailable' }, { status: 503 }),
      ),
    );
    await openTab('Features');
    expect(await screen.findByRole('alert')).toHaveTextContent('Capabilities unavailable');
  });

  it('renders the neutral not-found screen on a 404', async () => {
    actAsClinician();
    server.use(
      http.get('/clinic/patients/:patientId/capabilities', () =>
        HttpResponse.json({ detail: 'Patient not found' }, { status: 404 }),
      ),
    );
    await openTab('Features');
    expect(await screen.findByRole('heading', { name: 'Patient not found' })).toBeInTheDocument();
  });
});

describe('PatientDetailPage — existence privacy', () => {
  it('renders a neutral not-found screen for an id outside the panel', async () => {
    actAsClinician();
    renderApp('/clinic/patients/00000000-0000-4000-8000-000000000000');
    expect(await screen.findByRole('heading', { name: 'Patient not found' })).toBeInTheDocument();
    expect(screen.getByText('There is no patient record at this address.')).toBeInTheDocument();
    // Mirrors the backend's 404-over-403 posture: NEVER an access explanation.
    expect(screen.queryByText(/access/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/permission/i)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to your panel' })).toHaveAttribute(
      'href',
      '/clinic',
    );
  });
});
