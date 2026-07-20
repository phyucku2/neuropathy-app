/**
 * /emr/callback relay (ADR-0028): state validation against the persisted pending
 * handshake, the bearer-authenticated backend relay, verbatim API errors, and the
 * pull / two-tap-disconnect actions on the activated connection.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { EMR_AUTH_CODE, EMR_STATE, EMR_CONNECT_START } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';
import { EMR_PENDING_CONNECT_KEY, loadPendingConnect, savePendingConnect } from './pendingConnect';

function seedPending(state = EMR_STATE): void {
  savePendingConnect({
    state,
    connectionId: EMR_CONNECT_START.connection_id,
    providerName: 'Epic (MyChart)',
  });
}

const callbackPath = `/emr/callback?code=${EMR_AUTH_CODE}&state=${EMR_STATE}`;

describe('EmrCallbackPage — the SMART redirect relay', () => {
  it('relays a matching code+state to the backend and shows the activated connection', async () => {
    seedPending();
    renderApp(callbackPath);
    expect(await screen.findByText('Epic (MyChart)')).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pull labs now' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to Sources' })).toBeInTheDocument();
    // The one-shot handshake state is consumed — a stale copy must not linger.
    expect(sessionStorage.getItem(EMR_PENDING_CONNECT_KEY)).toBeNull();
  });

  it('pulls labs on demand and reports the imported count', async () => {
    const user = userEvent.setup();
    seedPending();
    renderApp(callbackPath);
    await user.click(await screen.findByRole('button', { name: 'Pull labs now' }));
    expect(
      await screen.findByText('Imported 2 of 2 lab results into your record.'),
    ).toBeInTheDocument();
  });

  it('pulls clinician notes on demand and reports the imported count (metadata only)', async () => {
    const user = userEvent.setup();
    seedPending();
    renderApp(callbackPath);
    await user.click(await screen.findByRole('button', { name: 'Pull clinician notes' }));
    // COUNTS ONLY (ADR-0045 P2 #27): the success copy names how many notes were added and
    // points at the medical record to read each — it NEVER surfaces any note body.
    expect(
      await screen.findByText(
        'Added 1 clinician note to your visit summary — open each in your medical record to read it.',
      ),
    ).toBeInTheDocument();
  });

  it('surfaces the notes-pull 409 verbatim when the feature is off (never a note body)', async () => {
    server.use(
      http.post('/emr/connections/:id/pull-notes', () =>
        HttpResponse.json({ detail: 'Importing clinician notes is turned off' }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    seedPending();
    renderApp(callbackPath);
    await user.click(await screen.findByRole('button', { name: 'Pull clinician notes' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Importing clinician notes is turned off');
  });

  it('disconnects with a two-tap confirm and shows the revoked state', async () => {
    const user = userEvent.setup();
    seedPending();
    renderApp(callbackPath);
    const disconnect = await screen.findByRole('button', { name: 'Disconnect' });
    await user.click(disconnect);
    // First tap arms; nothing is revoked yet.
    expect(screen.getByRole('button', { name: 'Tap again to confirm' })).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Tap again to confirm' }));
    expect(await screen.findByText('Disconnected')).toBeInTheDocument();
    // A revoked connection offers no further actions.
    expect(screen.queryByRole('button', { name: 'Pull labs now' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Disconnect' })).not.toBeInTheDocument();
  });

  it('refuses a state that does not match the pending handshake WITHOUT calling the backend', async () => {
    let relayed = false;
    server.use(
      http.get('/emr/callback', () => {
        relayed = true;
        return HttpResponse.json({ detail: 'must not be called' }, { status: 500 });
      }),
    );
    seedPending('a-different-state');
    renderApp(callbackPath);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'This sign-in response doesn’t match a connection this app started, so it was not accepted.',
    );
    expect(screen.getByText(/Go back to Sources/)).toBeInTheDocument();
    expect(relayed).toBe(false);
    // The pending handshake is NOT cleared — it may still legitimately complete.
    expect(sessionStorage.getItem(EMR_PENDING_CONNECT_KEY)).not.toBeNull();
  });

  it('explains a callback with no code/state and points back to Sources', async () => {
    renderApp('/emr/callback');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Your provider did not send back an authorization code.');
    expect(screen.getByText(/Go back to Sources/)).toBeInTheDocument();
  });

  it('surfaces the backend detail verbatim when the relay fails (single-use state 404)', async () => {
    // A replayed/expired state: pending matches, but the backend refuses (the msw
    // handler answers the real 404 for a code that is not the expected one).
    seedPending();
    renderApp(`/emr/callback?code=wrong-code&state=${EMR_STATE}`);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Unknown, expired, or already-used state');
    expect(screen.getByText(/Go back to Sources/)).toBeInTheDocument();
    // One-shot: the consumed pending state is cleared; retry starts from Sources.
    expect(sessionStorage.getItem(EMR_PENDING_CONNECT_KEY)).toBeNull();
  });
});

describe('pendingConnect store — corrupt entries are "no pending handshake"', () => {
  it('returns null for absent, malformed, and wrong-shaped entries', () => {
    expect(loadPendingConnect()).toBeNull();
    sessionStorage.setItem(EMR_PENDING_CONNECT_KEY, 'not-json{');
    expect(loadPendingConnect()).toBeNull();
    sessionStorage.setItem(EMR_PENDING_CONNECT_KEY, JSON.stringify({ state: 42 }));
    expect(loadPendingConnect()).toBeNull();
  });
});
