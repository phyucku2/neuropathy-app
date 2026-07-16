import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/renderApp';
import { actAsClinician, server } from '../../test/server';
import { INVITE_SENT_MESSAGE } from './PanelPage';

describe('role-aware routing', () => {
  it('routes a clinician from the patient home to the clinician panel', async () => {
    actAsClinician();
    renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Your panel' })).toBeInTheDocument();
    // Clinician shell: marked top bar with the signed-in name, no patient tab bar.
    expect(screen.getByText('◍ Neuropathy · Clinician')).toBeInTheDocument();
    expect(screen.getByText('Dr. Rivera')).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument();
  });

  it('routes a clinician away from every patient route', async () => {
    actAsClinician();
    renderApp('/trends');
    expect(await screen.findByRole('heading', { name: 'Your panel' })).toBeInTheDocument();
  });

  it('routes a patient away from the clinician area', async () => {
    renderApp('/clinic');
    // The default /auth/me is the patient account: back to the patient home.
    expect(await screen.findByText('30 Day Score')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Your panel' })).not.toBeInTheDocument();
  });

  it('sends anonymous visitors of the clinician area to sign-in', async () => {
    renderApp('/clinic', { authenticated: false });
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  });
});

describe('PanelPage', () => {
  it('lists consented patients with name, consent date, and connection chip', async () => {
    actAsClinician();
    renderApp('/clinic');
    expect(await screen.findByText('Pat Example')).toBeInTheDocument();
    expect(screen.getByText('Jordan Marsh')).toBeInTheDocument();
    expect(screen.getByText('Consented Jun 1, 2026')).toBeInTheDocument();
    expect(screen.getByText('Consented May 20, 2026')).toBeInTheDocument();
    expect(screen.getAllByText('Connected')).toHaveLength(2);
    // Each row links to the patient detail screen.
    expect(screen.getByRole('link', { name: /Pat Example/ })).toHaveAttribute(
      'href',
      '/clinic/patients/22222222-2222-4222-8222-222222222222',
    );
  });

  it('shows the empty state when no patient has consented yet', async () => {
    actAsClinician();
    server.use(http.get('/clinic/patients', () => HttpResponse.json({ patients: [] })));
    renderApp('/clinic');
    expect(await screen.findByText('No consented patients yet.')).toBeInTheDocument();
    expect(screen.getByText(/Invite a patient below/)).toBeInTheDocument();
  });

  it('shows the error state when the panel read fails', async () => {
    actAsClinician();
    server.use(
      http.get('/clinic/patients', () =>
        HttpResponse.json({ detail: 'Panel unavailable' }, { status: 503 }),
      ),
    );
    renderApp('/clinic');
    expect(await screen.findByRole('alert')).toHaveTextContent('Panel unavailable');
  });

  it('shows the SAME invitation message whether or not the email matches', async () => {
    actAsClinician();
    const user = userEvent.setup();
    renderApp('/clinic');
    const email = await screen.findByLabelText('Patient email');
    const send = screen.getByRole('button', { name: 'Send invitation' });

    // An email that matches a real patient account…
    await user.type(email, 'pat.example@example.com');
    await user.click(send);
    const first = await screen.findByRole('status');
    expect(first).toHaveTextContent(INVITE_SENT_MESSAGE);

    // …and one that matches nothing: byte-identical UI outcome (non-enumeration).
    await user.type(email, 'nobody.here@example.com');
    await user.click(send);
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(INVITE_SENT_MESSAGE);
    });
    // The screen never claims to know whether the email matched.
    expect(screen.queryByText(/no such patient/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
  });

  it('surfaces an invitation transport failure', async () => {
    actAsClinician();
    server.use(
      http.post('/clinic/invitations', () =>
        HttpResponse.json({ detail: 'Too many invitations' }, { status: 429 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/clinic');
    await user.type(await screen.findByLabelText('Patient email'), 'pat.example@example.com');
    await user.click(screen.getByRole('button', { name: 'Send invitation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many invitations');
  });
});
