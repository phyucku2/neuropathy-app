import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import type {
  CapabilityStateOut,
  ClinicianCapabilitySetIn,
  ObservationItem,
} from '../../api/types';
import { CLINIC_CAPABILITIES, PANEL_PATIENT_ID } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { actAsClinician, server } from '../../test/server';
import { minRenewalDate } from './CapabilityOrders';
import { NON_DIAGNOSTIC_TEXT } from './NonDiagnosticNote';
// #28 — deterministic lazy route under test: this side-effect import warms vitest's module
// registry for the SAME module App.tsx lazy-imports, so React.lazy resolves from cache in a
// microtask instead of paying a first-use transform/load inside a findBy* window. The page
// itself is still rendered through the real lazy route below.
import './PatientDetailPage';

const DETAIL_PATH = `/clinic/patients/${PANEL_PATIENT_ID}`;

/**
 * #28 — the flaky 404 assertion, hardened. The wait spans a multi-hop async chain (session
 * restore → lazy chunk → the tab fetch's 404 → re-render), and findBy*'s 1s default ceiling
 * was occasionally outrun under CI load (~1/334). findBy POLLS — it resolves the moment the
 * heading renders — so a generous ceiling adds zero time to a passing run and is purely the
 * failure bound. No sleeps.
 */
function findNotFoundHeading() {
  return screen.findByRole('heading', { name: 'Patient not found' }, { timeout: 10_000 });
}

async function openTab(name: string) {
  const user = userEvent.setup();
  renderApp(DETAIL_PATH);
  await screen.findByRole('heading', { name: 'Pat Example' });
  await user.click(screen.getByRole('button', { name }));
  return user;
}

/** A limit/offset-honoring observations handler over a full newest-first list. */
function pagedClinicObservations(all: ObservationItem[], total = all.length) {
  return http.get('/clinic/patients/:patientId/observations', ({ request }) => {
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get('limit') ?? '50');
    const offset = Number(url.searchParams.get('offset') ?? '0');
    return HttpResponse.json({
      items: all.slice(offset, offset + limit),
      total,
      limit,
      offset,
    });
  });
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

    // The deterministic Neuropathy Status Index is ALWAYS shown here — the SAME card
    // the patient sees, never the AI narrator (ADR-0012).
    const hero = await screen.findByRole('region', { name: /30 day score for Pat Example/ });
    expect(hero).toHaveClass('traj', 'improving');
    expect(screen.getByText('74')).toBeInTheDocument();
    expect(screen.getByText('improving')).toBeInTheDocument();
    expect(screen.getByText('+7 pts')).toBeInTheDocument();
    expect(screen.getByText('Confidence: High')).toBeInTheDocument();

    // Non-diagnostic posture (product requirement from the mockup).
    expect(screen.getByText(NON_DIAGNOSTIC_TEXT)).toBeInTheDocument();

    // Signals and gaps reuse the shared trajectory components.
    expect(screen.getByText('Balance score')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'declining' })).toHaveTextContent('↓');
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
    expect(await findNotFoundHeading()).toBeInTheDocument();
  });
});

describe('PatientDetailPage — visit summary tab', () => {
  it('renders the SAME deterministic Visit-Ready Summary the patient prints', async () => {
    actAsClinician();
    await openTab('Summary');
    // The shared status hero, named for the patient, plus the co-located disclaimer.
    expect(
      await screen.findByRole('region', { name: /60 days summary for Pat Example/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent(/not a diagnosis/);
    // Sourced sections + the print/export affordance.
    expect(screen.getByRole('heading', { name: 'What changed' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Print or export' })).toBeEnabled();
    // Deterministic only — the change-pointed (D2-gated) prompts are absent by default.
    expect(screen.queryByText(/ask the patient about it/)).not.toBeInTheDocument();
  });

  it('changes the window and refetches', async () => {
    actAsClinician();
    const user = await openTab('Summary');
    await screen.findByRole('region', { name: /60 days summary for Pat Example/ });
    await user.click(screen.getByRole('button', { name: '1 year' }));
    expect(
      await screen.findByRole('region', { name: /1 year summary for Pat Example/ }),
    ).toBeInTheDocument();
  });

  it('collapses the whole view to the neutral not-found screen on a 404', async () => {
    actAsClinician();
    server.use(
      http.get('/clinic/patients/:patientId/visit-summary', () =>
        HttpResponse.json({ detail: 'Patient not found' }, { status: 404 }),
      ),
    );
    await openTab('Summary');
    expect(await findNotFoundHeading()).toBeInTheDocument();
    // No PHI header left above a not-found body.
    expect(screen.queryByText('Pat Example')).not.toBeInTheDocument();
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

    // Walking asymmetry: 7.6 → 6.1 (LOWER is better) — a falling line judged better.
    const asymmetryRow = screen.getByRole('row', { name: /Walking asymmetry/ });
    expect(asymmetryRow).toHaveTextContent('↓ 1.5');
    expect(asymmetryRow).toHaveTextContent('better');

    // A single lab reading is never judged. Named by the backend's display —
    // the same name the Observations tab shows, never the raw code.
    const labRow = screen.getByRole('row', { name: /Hemoglobin A1c/ });
    expect(labRow).toHaveTextContent('Lab');
    expect(labRow).toHaveTextContent('single reading');
    expect(labRow).toHaveTextContent('not judged');

    // The word "stable" is a clinical claim this table must never fabricate.
    expect(screen.queryByText(/stable/i)).not.toBeInTheDocument();

    // The disclaimer sits under the table too.
    expect(screen.getByText(NON_DIAGNOSTIC_TEXT)).toBeInTheDocument();
  });

  it('pages through every observation so an old lab keeps its delta and display name', async () => {
    actAsClinician();
    const hemoglobin = (value: number, effectiveAt: string): ObservationItem => ({
      code: '718-7', // NOT in the UI registry — the backend display must name it.
      display: 'Hemoglobin',
      value,
      value_text: null,
      unit: 'g/dL',
      effective_at: effectiveAt,
      source: 'lab',
      status: 'final',
    });
    // Newest-first: the latest hemoglobin sits on page 1, the older one on page 2.
    const all = [
      hemoglobin(14.1, '2026-07-01T10:00:00Z'),
      ...syntheticObservations(120),
      hemoglobin(13.2, '2026-01-05T10:00:00Z'),
      ...syntheticObservations(29),
    ];
    server.use(pagedClinicObservations(all));
    await openTab('Trend table');
    const row = await screen.findByRole('row', { name: /Hemoglobin/ });
    // The page-2 reading gives it a real delta — never a fake 'single reading'.
    expect(row).toHaveTextContent('↑ 0.9');
    expect(row).not.toHaveTextContent('single reading');
    expect(row).not.toHaveTextContent('718-7');
    // Everything was fetched (151 of 151): no truncation notice.
    expect(screen.queryByText(/Based on the most recent/)).not.toBeInTheDocument();
  });

  it('stops at the 1,000-row safety cap and says so explicitly', async () => {
    actAsClinician();
    server.use(pagedClinicObservations(syntheticObservations(1050)));
    await openTab('Trend table');
    expect(
      await screen.findByText('Based on the most recent 1,000 of 1,050 records.'),
    ).toBeInTheDocument();
  });

  it('says "unit changed" instead of a delta when the latest two readings differ in unit', async () => {
    actAsClinician();
    server.use(
      pagedClinicObservations([
        {
          code: '4548-4',
          display: 'Hemoglobin A1c',
          value: 53,
          value_text: null,
          unit: 'mmol/mol',
          effective_at: '2026-07-01T10:00:00Z',
          source: 'lab',
          status: 'final',
        },
        {
          code: '4548-4',
          display: 'Hemoglobin A1c',
          value: 7.2,
          value_text: null,
          unit: '%',
          effective_at: '2026-06-01T10:00:00Z',
          source: 'lab',
          status: 'final',
        },
      ]),
    );
    await openTab('Trend table');
    const row = await screen.findByRole('row', { name: /Hemoglobin A1c/ });
    // 53 mmol/mol minus 7.2 % is not a change: no number, no verdict.
    expect(row).toHaveTextContent('unit changed');
    expect(row).toHaveTextContent('not judged');
    expect(row).not.toHaveTextContent('45.8');
    expect(row).not.toHaveTextContent('better');
    expect(row).not.toHaveTextContent('worse');
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
    expect(await findNotFoundHeading()).toBeInTheDocument();
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
    expect(await screen.findByText('Showing 1–10 of 10')).toBeInTheDocument();
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
    expect(await findNotFoundHeading()).toBeInTheDocument();
  });
});

/** A lapsed order: the backend serves it inactive with a past expires_at. */
const EXPIRED_ORDER: CapabilityStateOut = {
  key: 'ingest_biomech',
  name: 'BioMech report upload',
  active: false,
  managed_by: 'clinic',
  expires_at: '2026-06-01T23:59:59Z',
  enforced: true,
};

describe('PatientDetailPage — features tab (capability orders)', () => {
  it('renders toggles with expiry and read-only rows for unwired capabilities', async () => {
    // Every shipped key is enforced as of ADR-0020, so the read-only path now only
    // covers a FUTURE un-wired key — modeled here with a synthetic one.
    server.use(
      http.get('/clinic/patients/:patientId/capabilities', () =>
        HttpResponse.json({
          capabilities: [
            ...CLINIC_CAPABILITIES,
            {
              key: 'future_feature',
              name: 'Future feature',
              active: true,
              managed_by: 'clinic',
              expires_at: null,
              enforced: false,
            },
          ],
        }),
      ),
    );
    actAsClinician();
    await openTab('Features');
    const biomech = await screen.findByRole('switch', { name: 'BioMech report upload' });
    expect(biomech).toBeChecked();
    expect(screen.getByText('renews Aug 6, 2026')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Daily function check-in' })).not.toBeChecked();
    // A now-wired key is an interactive switch...
    expect(screen.getByRole('switch', { name: 'AI trajectory summary' })).toBeInTheDocument();
    // ...while the unenforced future key is read-only, no switch offered.
    expect(screen.queryByRole('switch', { name: 'Future feature' })).not.toBeInTheDocument();
    expect(screen.getByText('Not wired yet')).toBeInTheDocument();
    expect(screen.getByText('Changes are logged and shown to the patient.')).toBeInTheDocument();
  });

  it('renders a patient-held consent key read-only — no switch, no renewal input (ADR-0020 §3(b))', async () => {
    // share_with_clinic is enforced but managed_by='patient': the clinician can
    // never set it (backend 409, PatientHeldCapabilityError). The console must
    // show its status read-only, NOT a switch + renewal that would 409 on save.
    actAsClinician();
    await openTab('Features');
    // A clinic-managed enforced key still gets the full interactive affordance.
    expect(
      await screen.findByRole('switch', { name: 'BioMech report upload' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Renewal date for BioMech report upload')).toBeInTheDocument();
    // The patient-held key shows its status but offers NO switch and NO renewal.
    expect(screen.getByText('Share data with my clinic')).toBeInTheDocument();
    expect(screen.getByText('Controlled by the patient — read-only here.')).toBeInTheDocument();
    expect(
      screen.queryByRole('switch', { name: 'Share data with my clinic' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('checkbox', { name: 'Share data with my clinic' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText('Renewal date for Share data with my clinic'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Set renewal for Share data with my clinic' }),
    ).not.toBeInTheDocument();
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

  it('labels a lapsed order "expired", never "renews"', async () => {
    actAsClinician();
    const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    server.use(
      http.get('/clinic/patients/:patientId/capabilities', () =>
        HttpResponse.json({ capabilities: [{ ...EXPIRED_ORDER, expires_at: yesterday }] }),
      ),
    );
    await openTab('Features');
    expect(await screen.findByText(/^expired /)).toBeInTheDocument();
    expect(screen.queryByText(/renews/)).not.toBeInTheDocument();
  });

  it('renews an expired order as an explicit enable-with-expiry (ADR-0013)', async () => {
    actAsClinician();
    const expired: CapabilityStateOut = {
      ...EXPIRED_ORDER,
      expires_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    };
    const putBodies: ClinicianCapabilitySetIn[] = [];
    server.use(
      http.get('/clinic/patients/:patientId/capabilities', () =>
        HttpResponse.json({ capabilities: [expired] }),
      ),
      http.put('/clinic/patients/:patientId/capabilities/:key', async ({ request }) => {
        const body = (await request.json()) as ClinicianCapabilitySetIn;
        putBodies.push(body);
        // The backend's ADR-0013 rule: expiry pairs only with active=true.
        if (!body.active && body.expires_at != null) {
          return HttpResponse.json({ detail: 'expiry only with enable' }, { status: 422 });
        }
        return HttpResponse.json({
          ...expired,
          active: body.active,
          expires_at: body.expires_at ?? null,
        });
      }),
    );
    const user = await openTab('Features');
    await screen.findByText(/^expired /);
    fireEvent.change(screen.getByLabelText('Renewal date for BioMech report upload'), {
      target: { value: '2026-09-01' },
    });
    await user.click(screen.getByRole('button', { name: 'Set renewal for BioMech report upload' }));
    expect(await screen.findByText('renews Sep 1, 2026')).toBeInTheDocument();
    // The stale row said active=false; the renewal still sends active=true.
    expect(putBodies).toEqual([{ active: true, expires_at: '2026-09-01T23:59:59Z' }]);
    expect(screen.getByRole('switch', { name: 'BioMech report upload' })).toBeChecked();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('refetches the capability list right before submitting a renewal', async () => {
    actAsClinician();
    const events: string[] = [];
    let externallyEnabled = false;
    server.use(
      http.get('/clinic/patients/:patientId/capabilities', () => {
        events.push('GET');
        const capabilities = CLINIC_CAPABILITIES.map((row) =>
          row.key === 'ingest_adl' ? { ...row, active: externallyEnabled } : row,
        );
        return HttpResponse.json({ capabilities });
      }),
      http.put('/clinic/patients/:patientId/capabilities/:key', async ({ request, params }) => {
        events.push('PUT');
        const body = (await request.json()) as ClinicianCapabilitySetIn;
        const existing = CLINIC_CAPABILITIES.find(
          (row) => row.key === params['key'],
        ) as CapabilityStateOut;
        return HttpResponse.json({
          ...existing,
          active: body.active,
          expires_at: body.expires_at ?? null,
        });
      }),
    );
    const user = await openTab('Features');
    await screen.findByRole('switch', { name: 'Lab result upload' });
    // Another clinician enables the check-in while this page sits open.
    externallyEnabled = true;
    fireEvent.change(screen.getByLabelText('Renewal date for Lab result upload'), {
      target: { value: '2026-09-01' },
    });
    await user.click(screen.getByRole('button', { name: 'Set renewal for Lab result upload' }));
    expect(await screen.findByText('renews Sep 1, 2026')).toBeInTheDocument();
    // The fresh GET fired BEFORE the PUT — never acting on a stale snapshot —
    // and the refetch re-rendered the external change.
    expect(events).toEqual(['GET', 'GET', 'PUT']);
    expect(screen.getByRole('switch', { name: 'Daily function check-in' })).toBeChecked();
  });

  it('floors the renewal date input at tomorrow (local) so past dates are unpickable', async () => {
    actAsClinician();
    await openTab('Features');
    const input = await screen.findByLabelText('Renewal date for Lab result upload');
    expect(input).toHaveAttribute('min', minRenewalDate());
    // The floor itself is strictly in the future.
    expect(new Date(minRenewalDate()).getTime()).toBeGreaterThan(Date.now());
  });

  it('surfaces a backend 422 on a refused renewal verbatim', async () => {
    actAsClinician();
    server.use(
      http.put('/clinic/patients/:patientId/capabilities/:key', () =>
        HttpResponse.json(
          {
            detail: [
              {
                type: 'value_error',
                loc: ['body'],
                msg: 'Value error, expires_at only applies when active=true; omit it when disabling',
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );
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
    expect(await findNotFoundHeading()).toBeInTheDocument();
  });
});

describe('PatientDetailPage — mid-session consent revocation', () => {
  it('collapses the WHOLE detail view when a tab fetch 404s after the initial load', async () => {
    actAsClinician();
    const user = userEvent.setup();
    renderApp(DETAIL_PATH);
    await screen.findByRole('heading', { name: 'Pat Example' });
    // Consent is revoked while the page is open: the next tab fetch 404s.
    server.use(
      http.get('/clinic/patients/:patientId/observations', () =>
        HttpResponse.json({ detail: 'Patient not found' }, { status: 404 }),
      ),
    );
    await user.click(screen.getByRole('button', { name: 'Trend table' }));
    expect(await findNotFoundHeading()).toBeInTheDocument();
    // No post-revocation PHI: name, consent date, and tab chips are ALL gone.
    expect(screen.queryByText('Pat Example')).not.toBeInTheDocument();
    expect(screen.queryByText(/Consented/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Observations' })).not.toBeInTheDocument();
  });
});

describe('PatientDetailPage — existence privacy', () => {
  it('renders a neutral not-found screen for an id outside the panel', async () => {
    actAsClinician();
    renderApp('/clinic/patients/00000000-0000-4000-8000-000000000000');
    expect(await findNotFoundHeading()).toBeInTheDocument();
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
