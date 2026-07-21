/**
 * Caregiver Alerts feed (ADR-0047 B1): the list of non-urgent updates, one-tap
 * acknowledge (idempotent), the co-located non-diagnostic / 911 note, the persistent
 * shell banner, the all-caught-up empty state, and the rollback on an ack failure.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { CAREGIVER_ALERTS_EMPTY } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { actAsCaregiver, server } from '../../test/server';

const BANNER_TEXT = /If something's wrong right now, call 911/;

describe('caregiver alerts feed', () => {
  it('lists updates with the co-located non-diagnostic / 911 note and the shell banner', async () => {
    actAsCaregiver();
    renderApp('/caregiver/alerts');

    // The NEW (unacknowledged) alert renders its template title + body.
    expect(await screen.findByText('A check-in was missed')).toBeInTheDocument();
    expect(screen.getByText(/It's been a little while since the last daily check-in/)).toBeInTheDocument();
    // The already-acknowledged alert shows the "Seen" state and offers no button.
    expect(screen.getByText('A shift in the wellness trend')).toBeInTheDocument();
    expect(screen.getByText('Seen')).toBeInTheDocument();

    // Exactly one un-acked row → exactly one "Got it".
    expect(screen.getAllByRole('button', { name: 'Got it' })).toHaveLength(1);
    expect(screen.getByText('New')).toBeInTheDocument();

    // The non-urgent framing is co-located beside the list (role="note"), on top of the
    // shell's persistent 911 banner — both carry the 911 wording.
    expect(screen.getByText(/not a diagnosis, and not live monitoring/)).toBeInTheDocument();
    expect(screen.getAllByText(BANNER_TEXT).length).toBeGreaterThanOrEqual(2);
  });

  it('acknowledges an alert in one tap (it flips to Seen, the button disappears)', async () => {
    actAsCaregiver();
    const user = userEvent.setup();
    renderApp('/caregiver/alerts');

    await user.click(await screen.findByRole('button', { name: 'Got it' }));

    // Optimistic: the row is now Seen and its button is gone (idempotent 204 server-side).
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Got it' })).not.toBeInTheDocument();
    });
    // Both rows are now "Seen"; there is no remaining "New".
    expect(screen.queryByText('New')).not.toBeInTheDocument();
  });

  it('shows the all-caught-up empty state when there are no updates', async () => {
    actAsCaregiver();
    server.use(http.get('/caregiver/alerts', () => HttpResponse.json(CAREGIVER_ALERTS_EMPTY)));
    renderApp('/caregiver/alerts');

    expect(
      await screen.findByRole('heading', { name: 'No updates right now' }),
    ).toBeInTheDocument();
    // The framing rides even the empty surface.
    expect(screen.getAllByText(BANNER_TEXT).length).toBeGreaterThanOrEqual(2);
  });

  it('rolls back and surfaces the message when acknowledging fails (404-over-403)', async () => {
    actAsCaregiver();
    server.use(
      http.post('/caregiver/alerts/:alertId/ack', () =>
        HttpResponse.json({ detail: 'Alert not found' }, { status: 404 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/caregiver/alerts');

    await user.click(await screen.findByRole('button', { name: 'Got it' }));

    // The row did NOT flip: the button is still there and the failure is surfaced.
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Got it' })).toBeEnabled();
    expect(screen.getByText('New')).toBeInTheDocument();
  });
});
