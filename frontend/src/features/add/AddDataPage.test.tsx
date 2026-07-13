import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

const PDF_FILE = new File(['%PDF-1.7 synthetic'], 'balance-report.pdf', {
  type: 'application/pdf',
});

async function pickFile(user: ReturnType<typeof userEvent.setup>) {
  const input = await screen.findByLabelText(/Report PDF/);
  await user.upload(input, PDF_FILE);
}

describe('AddDataPage — BioMech upload', () => {
  it('keeps Upload disabled until a file is chosen', async () => {
    const user = userEvent.setup();
    renderApp('/add');
    const button = await screen.findByRole('button', { name: 'Upload report' });
    expect(button).toBeDisabled();
    await pickFile(user);
    expect(button).toBeEnabled();
  });

  it('uploads the PDF as multipart field "file" and shows the outcome', async () => {
    let fieldName: string | null = null;
    let fileName: string | null = null;
    server.use(
      http.post('/biomech/reports', async ({ request }) => {
        const form = await request.formData();
        const entry = form.get('file');
        fieldName = entry === null ? null : 'file';
        // instanceof is realm-sensitive under jsdom/undici — duck-type the File.
        fileName =
          entry !== null && typeof entry === 'object' && 'name' in entry ? entry.name : null;
        return HttpResponse.json({
          report_kind: 'balance',
          assessment_at: '2026-07-02T10:00:00Z',
          imported: 3,
          skipped: 1,
          warnings: [],
        });
      }),
    );
    const user = userEvent.setup();
    renderApp('/add');
    await pickFile(user);
    await user.click(screen.getByRole('button', { name: 'Upload report' }));
    const status = await screen.findByText(/3 of 4 values imported from your balance report/);
    expect(status).toHaveTextContent('assessed Jul 2, 2026');
    expect(status).toHaveTextContent('1 already on file — nothing was duplicated');
    expect(fieldName).toBe('file');
    expect(fileName).toBe('balance-report.pdf');
  });

  it('renders parser warnings as plain text, never as markup', async () => {
    const htmlishWarning = 'Sway area: value <b>weird</b> is not a plain number (skipped).';
    server.use(
      http.post('/biomech/reports', () =>
        HttpResponse.json({
          report_kind: 'balance',
          assessment_at: null,
          imported: 2,
          skipped: 0,
          warnings: [htmlishWarning, 'Cadence: appears more than once; kept the first value.'],
        }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/add');
    await pickFile(user);
    await user.click(screen.getByRole('button', { name: 'Upload report' }));
    expect(await screen.findByText('We skipped a few things')).toBeInTheDocument();
    const items = screen.getAllByRole('listitem');
    // The literal "<b>" must appear as text — no element is created from it.
    expect(items.map((item) => item.textContent)).toContain(htmlishWarning);
    expect(items.some((item) => item.querySelector('b') !== null)).toBe(false);
  });

  it('explains a 409 (feature turned off) with a pointer to Sources', async () => {
    server.use(
      http.post('/biomech/reports', () =>
        HttpResponse.json({ detail: 'BioMech report upload is turned off' }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/add');
    await pickFile(user);
    await user.click(screen.getByRole('button', { name: 'Upload report' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('BioMech report upload is turned off');
    expect(alert).toHaveTextContent('back on in Sources');
  });

  it('surfaces a 422 parse rejection verbatim', async () => {
    server.use(
      http.post('/biomech/reports', () =>
        HttpResponse.json({ detail: 'Not a readable PDF' }, { status: 422 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/add');
    await pickFile(user);
    await user.click(screen.getByRole('button', { name: 'Upload report' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Not a readable PDF');
  });
});

describe('AddDataPage — EMR connect stub', () => {
  it('presents the provider-portal stub and the connections list', async () => {
    renderApp('/add');
    expect(await screen.findByText('Connect your records')).toBeInTheDocument();
    expect(screen.getByText(/connect via your provider portal/)).toBeInTheDocument();
    expect(screen.getByText('Coming soon')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Advanced Health & Wellness')).toBeInTheDocument();
    });
    expect(screen.getByText('Regional Medical Center')).toBeInTheDocument();
  });

  it('shows an empty state when there are no connections', async () => {
    server.use(http.get('/connections', () => HttpResponse.json([])));
    renderApp('/add');
    expect(await screen.findByText(/No clinic connections yet/)).toBeInTheDocument();
  });
});
