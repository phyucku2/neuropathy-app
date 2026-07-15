/**
 * "Health record connections" (ADR-0028): provider picker + connect start. The
 * authorize-URL opener is mocked at its seam (native/externalBrowser) — the REAL
 * navigation is proven in the browser E2E (e2e/patient/emr-connect.spec.ts).
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { openAuthorizeUrl } = vi.hoisted(() => ({ openAuthorizeUrl: vi.fn() }));
vi.mock('../../native/externalBrowser', () => ({
  openAuthorizeUrl: (url: string) => openAuthorizeUrl(url) as Promise<void>,
}));

import { EMR_CONNECT_START, CAPABILITIES } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';
import { EMR_PENDING_CONNECT_KEY, loadPendingConnect } from '../emr/pendingConnect';

describe('SettingsPage — health record connections (EMR connect)', () => {
  beforeEach(() => {
    openAuthorizeUrl.mockReset().mockResolvedValue(undefined);
  });

  it('renders the provider picker near the clinic connections, with search', async () => {
    const user = userEvent.setup();
    renderApp('/settings');
    expect(
      await screen.findByRole('heading', { name: 'Health record connections' }),
    ).toBeInTheDocument();
    // Both registry fixtures render; Epic (public sandbox) gets a Connect button…
    expect(
      await screen.findByRole('button', { name: 'Connect Epic (MyChart)' }),
    ).toBeInTheDocument();
    // …while a provider with no public endpoint yet is honest instead of failable.
    expect(screen.getAllByText('MEDITECH').length).toBeGreaterThan(0); // name + vendor line
    expect(screen.getByText('Not available yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Connect MEDITECH' })).not.toBeInTheDocument();

    // The search is SERVER-side (GET /emr/providers?q=…, the real endpoint's match).
    await user.type(screen.getByLabelText('Search for your provider'), 'mychart');
    await waitFor(() => {
      expect(screen.queryAllByText('MEDITECH')).toHaveLength(0);
    });
    expect(screen.getByRole('button', { name: 'Connect Epic (MyChart)' })).toBeInTheDocument();

    await user.clear(screen.getByLabelText('Search for your provider'));
    await user.type(screen.getByLabelText('Search for your provider'), 'zzz-no-match');
    expect(await screen.findByText('No providers match your search.')).toBeInTheDocument();
  });

  it('connect: persists the pending state, then opens the authorize URL via the seam', async () => {
    const user = userEvent.setup();
    renderApp('/settings');
    await user.click(await screen.findByRole('button', { name: 'Connect Epic (MyChart)' }));

    await waitFor(() => {
      expect(openAuthorizeUrl).toHaveBeenCalledWith(EMR_CONNECT_START.authorize_url);
    });
    // The pending handshake was persisted BEFORE leaving the page — the callback
    // relay validates the EMR's echoed state against exactly this value.
    expect(loadPendingConnect()).toEqual({
      state: EMR_CONNECT_START.state,
      connectionId: EMR_CONNECT_START.connection_id,
      providerName: 'Epic (MyChart)',
    });
  });

  it('surfaces a connect failure detail verbatim (e.g. the emr_connect-off 409) and persists nothing', async () => {
    server.use(
      http.post('/emr/connect', () =>
        HttpResponse.json({ detail: 'This feature is turned off' }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/settings');
    await user.click(await screen.findByRole('button', { name: 'Connect Epic (MyChart)' }));

    expect(await screen.findByText('This feature is turned off')).toBeInTheDocument();
    expect(openAuthorizeUrl).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(EMR_PENDING_CONNECT_KEY)).toBeNull();
  });

  it('renders the toggled-off hint instead of the picker when emr_connect is off (UI hint; the server still enforces)', async () => {
    server.use(
      http.get('/capabilities', () =>
        HttpResponse.json({
          capabilities: CAPABILITIES.map((row) =>
            row.key === 'emr_connect' ? { ...row, active: false } : row,
          ),
        }),
      ),
    );
    renderApp('/settings');
    expect(
      await screen.findByText(
        'Medical record connection is turned off in your sources above, so new health record connections can’t be started.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Search for your provider')).not.toBeInTheDocument();
  });
});
