import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { CAPABILITIES } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

describe('SettingsPage — capability toggles', () => {
  it('renders every capability as a toggle row with its server state', async () => {
    renderApp('/settings');
    const biomech = await screen.findByRole('switch', { name: 'BioMech report upload' });
    expect(biomech).toBeChecked();
    expect(screen.getByRole('switch', { name: 'Daily function check-in' })).not.toBeChecked();
    expect(screen.getByText('Off · hidden and paused in your trend')).toBeInTheDocument();
  });

  it('renders enforced=false rows read-only in the coming-soon style', async () => {
    renderApp('/settings');
    await screen.findByRole('switch', { name: 'BioMech report upload' });
    // The unenforced capability gets a pill instead of a switch.
    expect(
      screen.queryByRole('switch', { name: 'Medical record connection' }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText('Coming soon').length).toBeGreaterThanOrEqual(1);
  });

  it('toggles optimistically and keeps the server-confirmed state', async () => {
    const user = userEvent.setup();
    renderApp('/settings');
    const adl = await screen.findByRole('switch', { name: 'Daily function check-in' });
    await user.click(adl);
    // Optimistic flip is immediate; the msw handler then confirms active=true.
    expect(adl).toBeChecked();
    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Daily function check-in' })).toBeChecked();
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('rolls back on 409 and surfaces the clinically-managed message verbatim', async () => {
    const detail = 'This setting is managed by your clinic while your connection is active.';
    server.use(
      http.put('/capabilities/:key', () => HttpResponse.json({ detail }, { status: 409 })),
    );
    const user = userEvent.setup();
    renderApp('/settings');
    const biomech = await screen.findByRole('switch', { name: 'BioMech report upload' });
    expect(biomech).toBeChecked();
    await user.click(biomech);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(detail); // verbatim
    // Rolled back to the server's last-known state.
    expect(screen.getByRole('switch', { name: 'BioMech report upload' })).toBeChecked();
  });

  it('labels clinician-managed rows, including a clinician-set expiry', async () => {
    server.use(
      http.get('/capabilities', () =>
        HttpResponse.json({
          capabilities: [
            { ...CAPABILITIES[0], managed_by: 'clinic' },
            { ...CAPABILITIES[1], expires_at: '2026-09-01T00:00:00Z' },
            { ...CAPABILITIES[2], managed_by: 'clinic', expires_at: '2026-09-01T00:00:00Z' },
          ],
        }),
      ),
    );
    renderApp('/settings');
    expect(await screen.findByText('Managed by your clinic')).toBeInTheDocument();
    expect(screen.getByText('Until Sep 1, 2026')).toBeInTheDocument();
    // Expiry only exists when a clinician set it, so it must render alongside
    // the managed-by label instead of being swallowed by it.
    expect(screen.getByText('Managed by your clinic · until Sep 1, 2026')).toBeInTheDocument();
  });

  it('shows the error state when the capabilities read fails', async () => {
    server.use(
      http.get('/capabilities', () =>
        HttpResponse.json({ detail: 'Capabilities unavailable' }, { status: 503 }),
      ),
    );
    renderApp('/settings');
    expect(await screen.findByRole('alert')).toHaveTextContent('Capabilities unavailable');
  });
});

describe('SettingsPage — clinic connections', () => {
  it('lists connections with consent state and approves a pending one', async () => {
    const { CONNECTION_ACTIVE, CONNECTION_PENDING } = await import('../../test/fixtures');
    let consented = false;
    server.use(
      http.get('/connections', () =>
        HttpResponse.json(
          consented
            ? [{ ...CONNECTION_PENDING, status: 'active' }, CONNECTION_ACTIVE]
            : [CONNECTION_PENDING, CONNECTION_ACTIVE],
        ),
      ),
      http.post('/connections/:id/consent', () => {
        consented = true;
        return HttpResponse.json({ ...CONNECTION_PENDING, status: 'active' });
      }),
    );
    const user = userEvent.setup();
    renderApp('/settings');
    expect(await screen.findByText('Advanced Health & Wellness')).toBeInTheDocument();
    expect(screen.getByText('Awaiting your approval')).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Approve connection' }));
    // After consent the list reloads; the pending row is now active.
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Approve connection' })).not.toBeInTheDocument();
    });
    expect(screen.getAllByText('Connected')).toHaveLength(2);
  });

  it('revokes an active connection only after the confirm tap', async () => {
    let deleted = false;
    server.use(
      http.delete('/connections/:id', () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderApp('/settings');
    await screen.findByText('Regional Medical Center');
    const row = screen.getByText('Regional Medical Center').closest('div');
    expect(row).not.toBeNull();
    const disconnect = screen.getByRole('button', { name: 'Disconnect' });
    await user.click(disconnect);
    expect(deleted).toBe(false);
    expect(screen.getByRole('button', { name: 'Tap again to confirm' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Tap again to confirm' }));
    await waitFor(() => {
      expect(deleted).toBe(true);
    });
  });

  it('shows the self-managing note when no connections exist', async () => {
    server.use(http.get('/connections', () => HttpResponse.json([])));
    renderApp('/settings');
    expect(await screen.findByText(/You're self-managing/)).toBeInTheDocument();
  });

  it('surfaces a consent failure', async () => {
    server.use(
      http.post('/connections/:id/consent', () =>
        HttpResponse.json({ detail: 'Connection not found' }, { status: 404 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/settings');
    await screen.findByText('Advanced Health & Wellness');
    await user.click(screen.getByRole('button', { name: 'Approve connection' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Connection not found');
  });
});

describe('navigation', () => {
  it('moves between tabs from the tab bar', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await screen.findByText('Improving');
    await user.click(screen.getByRole('link', { name: /Trends/ }));
    expect(await screen.findByRole('heading', { name: 'Trends' })).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: /Sources/ }));
    expect(await screen.findByRole('heading', { name: 'Your data sources' })).toBeInTheDocument();
  });

  it('uses `within` scoping to keep this suite honest about a single tab bar', async () => {
    renderApp('/');
    await screen.findByText('Improving');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).getAllByRole('link')).toHaveLength(4);
  });
});
